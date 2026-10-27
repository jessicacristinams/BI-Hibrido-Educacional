"""API dos painéis: o navegador recebe só o recorte agregado, calculado no servidor."""

import sqlite3

import pandas as pd
import pytest

from app.core.config import Settings
from tests.conftest import FakeLLM


@pytest.fixture
def client(make_client):
    return make_client(FakeLLM([]))


@pytest.fixture
def db(db_path):
    con = sqlite3.connect(db_path)
    yield con
    con.close()


def test_filtros_e_totais(client, db):
    body = client.get("/api/painel/filtros").json()
    assert body["totais"]["alunos"] == db.execute("SELECT COUNT(*) FROM alunos").fetchone()[0]
    assert body["totais"]["matriculas"] == db.execute("SELECT COUNT(*) FROM matriculas").fetchone()[0]
    assert body["alunos"]["periodos"] == sorted(body["alunos"]["periodos"])
    assert body["alunos"]["cursos"] and body["disciplinas"]["cursos"]


def test_alunos_sem_filtro_usa_situacao_atual(client, db):
    body = client.get("/api/painel/alunos").json()
    esperado = dict(db.execute("SELECT situacao_atual, COUNT(*) FROM alunos GROUP BY 1").fetchall())
    assert {k["categoria"]: k["total"] for k in body["kpis"]} == {c: esperado.get(c, 0) for c in ["ATIVO", "EVADIDO", "RETIDO", "FORMADO"]}
    assert body["totalAlunos"] == sum(esperado.values())
    assert sum(k["taxa"] for k in body["kpis"]) == pytest.approx(100)


def test_alunos_com_periodos_usa_o_periodo_mais_recente_do_recorte(client, db_path):
    ap = pd.read_sql("SELECT codigo_estudante, periodo_letivo, categoria FROM alunos_periodo", sqlite3.connect(db_path))
    periodos = sorted(ap["periodo_letivo"].unique())[:3]
    recorte = ap[ap["periodo_letivo"].isin(periodos)].sort_values("periodo_letivo")
    esperado = recorte.groupby("codigo_estudante")["categoria"].last().value_counts().to_dict()

    body = client.get("/api/painel/alunos", params={"periodos": periodos}).json()
    assert {k["categoria"]: k["total"] for k in body["kpis"] if k["total"]} == esperado
    assert [p["periodo"] for p in body["serieHistorica"]] == periodos


def test_indicadores_filtram_as_categorias_mas_a_taxa_e_sobre_o_total(client):
    todos = client.get("/api/painel/alunos").json()
    so_evasao = client.get("/api/painel/alunos", params={"indicadores": ["EVADIDO"]}).json()
    assert so_evasao["categoriasVisiveis"] == ["EVADIDO"]
    assert [k["categoria"] for k in so_evasao["kpis"]] == ["EVADIDO"]
    assert so_evasao["kpis"][0] == next(k for k in todos["kpis"] if k["categoria"] == "EVADIDO")
    assert so_evasao["formacaoPorSemestre"] == []


def test_periodo_desconhecido_e_ignorado(client):
    assert client.get("/api/painel/alunos", params={"periodos": ["1900.1"]}).json() == client.get("/api/painel/alunos").json()


def test_disciplinas_agregado_bate_com_as_matriculas(client, db):
    body = client.get("/api/painel/disciplinas").json()
    total, aprov, reprov = db.execute("SELECT COUNT(*), SUM(aprovado), SUM(reprovado) FROM matriculas").fetchone()
    assert body["kpis"]["totalMatriculas"] == total == sum(t["matriculas"] for t in body["tabela"])
    assert body["kpis"]["totalAprovados"] == aprov
    assert body["kpis"]["totalReprovados"] == reprov
    # médias da tabela pré-agregada = médias calculadas direto das matrículas
    medias = {
        (c, d): (m, f)
        for c, d, m, f in db.execute(
            "SELECT curso, disciplina, AVG(media_final), AVG(total_faltas) FROM matriculas GROUP BY 1, 2"
        )
    }
    for linha in body["tabela"]:
        m, f = medias[(linha["curso"], linha["disciplina"])]
        assert linha["mediaFinal"] == pytest.approx(m) if m is not None else linha["mediaFinal"] is None
        assert linha["mediaFaltas"] == pytest.approx(f) if f is not None else linha["mediaFaltas"] is None
    for nome in ("rankingMaisAprovados", "rankingPiorMedia", "rankingMaisFaltas"):
        assert 0 < len(body[nome]) <= 10


def test_disciplinas_filtradas_por_curso_periodo_e_disciplina(client, db):
    curso, periodo, disciplina = db.execute(
        "SELECT curso, periodo_letivo, disciplina FROM matriculas GROUP BY 1, 2, 3 ORDER BY COUNT(*) DESC LIMIT 1"
    ).fetchone()
    body = client.get(
        "/api/painel/disciplinas", params={"curso": curso, "periodos": [periodo], "disciplinas": [disciplina]}
    ).json()
    (n,) = db.execute(
        "SELECT COUNT(*) FROM matriculas WHERE curso = ? AND periodo_letivo = ? AND disciplina = ?",
        (curso, periodo, disciplina),
    ).fetchone()
    assert body["kpis"]["totalMatriculas"] == n
    assert [(t["curso"], t["disciplina"]) for t in body["tabela"]] == [(curso, disciplina)]
    assert body["serieHistorica"] == [{"periodo": periodo, "aprovados": body["kpis"]["totalAprovados"], "reprovados": body["kpis"]["totalReprovados"]}]


@pytest.mark.parametrize("params", [{"curso": "CURSO QUE NAO EXISTE"}, {"disciplinas": ["DISCIPLINA QUE NAO EXISTE"]}])
def test_recorte_inexistente_devolve_zeros(client, params):
    body = client.get("/api/painel/disciplinas", params=params).json()
    assert body["kpis"]["totalMatriculas"] == 0 and body["tabela"] == [] and body["rankingMaisAprovados"] == []


def test_opcoes_de_disciplina_por_curso(client, db):
    curso = db.execute("SELECT curso FROM matriculas LIMIT 1").fetchone()[0]
    esperado = [r[0] for r in db.execute("SELECT DISTINCT disciplina FROM matriculas WHERE curso = ? ORDER BY 1", (curso,))]
    assert client.get("/api/painel/disciplinas/opcoes", params={"curso": curso}).json() == esperado


def test_respostas_nao_trazem_identificadores_de_alunos(client, db):
    codigos = [r[0] for r in db.execute("SELECT codigo_estudante FROM alunos LIMIT 50")]
    for url in ("/api/painel/filtros", "/api/painel/alunos", "/api/painel/disciplinas", "/api/painel/disciplinas/opcoes"):
        texto = client.get(url).text
        assert "codigo_estudante" not in texto
        assert not any(f'"{c}"' in texto for c in codigos)


def test_validacao_dos_parametros(client):
    assert client.get("/api/painel/alunos", params={"indicadores": ["XPTO"]}).status_code == 422
    assert client.get("/api/painel/disciplinas", params={"disciplinas": [f"D{i}" for i in range(601)]}).status_code == 422


def test_banco_desatualizado_sem_tabela_do_painel(make_client, db_path, tmp_path):
    antigo = tmp_path / "antigo.db"
    origem = sqlite3.connect(db_path)
    destino = sqlite3.connect(antigo)
    origem.backup(destino)
    destino.execute("DROP TABLE painel_disciplinas")
    destino.commit()
    origem.close()
    destino.close()
    client = make_client(FakeLLM([]), Settings(_env_file=None, openai_api_key="x", database_path=antigo))
    r = client.get("/api/painel/disciplinas")
    assert r.status_code == 503 and "build_database" in r.json()["detail"]


# ── LGPD: supressão de grupos pequenos ────────────────────────────────────────


@pytest.fixture
def client_k(make_client, db_path):
    def _make(k: int):
        return make_client(FakeLLM([]), Settings(_env_file=None, openai_api_key="x", database_path=db_path, supressao_k=k))

    return _make


def test_supressao_vem_desligada_por_padrao():
    assert Settings(_env_file=None, openai_api_key="x").supressao_k == 1


def test_filtros_informam_origem_e_limite(client_k):
    body = client_k(5).get("/api/painel/filtros").json()
    assert body["origemDados"] == "sintetico" and body["limiteSupressao"] == 5


def test_recorte_pequeno_nao_mostra_nenhum_numero(client_k, db):
    (total,) = db.execute("SELECT COUNT(*) FROM alunos").fetchone()
    client = client_k(total + 1)  # recorte inteiro abaixo do limite

    alunos = client.get("/api/painel/alunos").json()
    assert alunos["suprimido"] and alunos["totalAlunos"] is None
    assert all(k["total"] is None and k["taxa"] is None for k in alunos["kpis"])
    assert alunos["evasaoPorSemestre"] == alunos["formacaoPorSemestre"] == alunos["evasaoPorTipoSaida"] == []
    assert all(p[c] is None for p in alunos["serieHistorica"] for c in ("ativos", "evadidos", "retidos", "formados"))

    (matriculas,) = db.execute("SELECT COUNT(*) FROM matriculas").fetchone()
    disc = client_k(matriculas + 1).get("/api/painel/disciplinas").json()
    assert disc["suprimido"] and all(v is None for v in disc["kpis"].values())
    assert all(disc[r] == [] for r in disc if r.startswith("ranking"))
    assert all(t["suprimido"] and t["matriculas"] is None and t["mediaFinal"] is None for t in disc["tabela"])


def test_com_k_5_nenhum_grupo_de_1_a_4_aparece(client_k, db):
    k = 5
    alunos = client_k(k).get("/api/painel/alunos").json()
    assert not alunos["suprimido"]
    for p in alunos["serieHistorica"]:
        valores = [p[c] for c in ("ativos", "evadidos", "retidos", "formados")]
        assert all(v is None for v in valores) or sum(valores) >= k
    for barra in alunos["evasaoPorSemestre"] + alunos["formacaoPorSemestre"] + alunos["evasaoPorTipoSaida"]:
        assert barra["valor"] is None or barra["valor"] == 0 or barra["valor"] >= k

    body = client_k(k).get("/api/painel/disciplinas").json()
    tabela = {(t["curso"], t["disciplina"]): t for t in body["tabela"]}
    reais = {
        (c, d): (n, nm, nf)
        for c, d, n, nm, nf in db.execute(
            "SELECT curso, disciplina, COUNT(*), COUNT(media_final), COUNT(total_faltas) FROM matriculas GROUP BY 1, 2"
        )
    }
    assert any(n < k for n, _, _ in reais.values())  # a base de teste tem grupos pequenos
    for chave, (n, nm, nf) in reais.items():
        linha = tabela[chave]
        assert linha["suprimido"] == (n < k)
        if n < k:
            assert all(linha[c] is None for c in ("matriculas", "aprovados", "reprovados", "taxaAprovacao"))
        else:
            assert linha["matriculas"] == n
            assert (linha["mediaFinal"] is None) == (nm < k) or nm == 0
            assert (linha["mediaFaltas"] is None) == (nf < k) or nf == 0

    por_disc = dict(db.execute("SELECT disciplina, COUNT(*) FROM matriculas GROUP BY 1").fetchall())
    for item in body["rankingMaisAprovados"] + body["rankingMaisReprovados"]:
        assert por_disc[item["disciplina"]] >= k

    # disciplina com poucas matrículas num período: a série esconde o ponto
    curso, periodo, disciplina, n = db.execute(
        "SELECT curso, periodo_letivo, disciplina, COUNT(*) FROM matriculas GROUP BY 1, 2, 3"
        " HAVING COUNT(*) BETWEEN 1 AND 4 LIMIT 1"
    ).fetchone()
    pequeno = client_k(k).get(
        "/api/painel/disciplinas", params={"curso": curso, "periodos": [periodo], "disciplinas": [disciplina]}
    ).json()
    assert pequeno["suprimido"] and pequeno["serieHistorica"] == [{"periodo": periodo, "aprovados": None, "reprovados": None}]
    assert str(n) not in {str(v) for v in pequeno["kpis"].values()}


def test_k_1_desliga_a_supressao(client_k):
    for url in ("/api/painel/alunos", "/api/painel/disciplinas"):
        body = client_k(1).get(url).json()
        assert not body["suprimido"] and body["limiteSupressao"] == 1
    tabela = client_k(1).get("/api/painel/disciplinas").json()["tabela"]
    assert not any(t["suprimido"] for t in tabela)


# ── Base de demonstração (dados fictícios) ───────────────────────────────────


def test_build_sem_csv_real_usa_dados_sinteticos(tmp_path, monkeypatch):
    from tests.conftest import load_script

    mod = load_script("build_database")
    monkeypatch.setattr(mod, "DEFAULT_CSV", tmp_path / "nao_existe.csv")
    monkeypatch.setattr(mod, "DEFAULT_SINTETICO", tmp_path / "sintetico.csv")
    out = tmp_path / "demo.db"
    monkeypatch.setattr("sys.argv", ["build_database.py", "--out", str(out)])
    assert mod.main() == 0
    assert (tmp_path / "sintetico.csv").exists()
    con = sqlite3.connect(out)
    assert dict(con.execute("SELECT chave, valor FROM metadados").fetchall())["origem_dados"] == "sintetico"
    assert con.execute("SELECT COUNT(*) FROM alunos").fetchone()[0] == 2000
    con.close()
