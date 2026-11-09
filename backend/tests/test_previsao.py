"""Previsão do próximo semestre: o sistema só exibe o resumo projetado (notebook ou fictício).

Os testes usam a previsão fictícia gerada a partir dos alunos fictícios, no mesmo formato do
resumo do notebook (o CSV real fica fora do repositório).
"""

import sqlite3

import pandas as pd
import pytest

from app.core.config import Settings
from tests.conftest import FakeLLM, load_script

CATEGORIA = {"ALUNOS ATIVOS": "ATIVO", "ALUNOS RETIDOS": "RETIDO", "EVASÃO": "EVADIDO", "CONCLUSÃO": "FORMADO"}


@pytest.fixture(scope="module")
def esperado(previsao_csv) -> pd.DataFrame:
    df = pd.read_csv(previsao_csv, encoding="utf-8-sig", dtype={"periodo_base": str, "periodo_alvo": str})
    df["categoria"] = df["situacao"].map(CATEGORIA)
    return df


@pytest.fixture
def client(make_client):
    return make_client(FakeLLM([]))


def _por_categoria(body: dict) -> dict:
    return {i["categoria"]: i["quantidade"] for i in body["itens"]}


def test_todos_os_cursos_e_a_soma_dos_cursos(client, esperado):
    body = client.get("/api/painel/previsao").json()
    soma = esperado.groupby("categoria")["quantidade_projetada"].sum().to_dict()
    assert _por_categoria(body) == {c: soma.get(c, 0) for c in ["ATIVO", "EVADIDO", "RETIDO", "FORMADO"]}
    assert body["totalProjetado"] == esperado["quantidade_projetada"].sum()
    # porcentagem recalculada sobre o total somado (não é a média das porcentagens dos cursos)
    for item in body["itens"]:
        assert item["taxa"] == pytest.approx(100 * item["quantidade"] / body["totalProjetado"])
    assert body["periodoAlvo"] == "2025.1"  # semestre seguinte ao período-base 2024.2
    assert body["periodosBase"] == ["2024.2"]


def test_curso_mostra_a_linha_do_csv(client, esperado):
    for curso, linhas in esperado.groupby("NM_PROGR_FORM"):
        body = client.get("/api/painel/previsao", params={"curso": curso}).json()
        csv = dict(zip(linhas["categoria"], linhas["quantidade_projetada"]))
        assert _por_categoria(body) == {c: csv.get(c, 0) for c in ["ATIVO", "EVADIDO", "RETIDO", "FORMADO"]}
        # as porcentagens batem com as do CSV (proporcao_projetada, arredondada a 4 casas)
        for item in body["itens"]:
            linha = linhas[linhas["categoria"] == item["categoria"]]
            if not linha.empty:
                assert item["taxa"] == pytest.approx(100 * linha["proporcao_projetada"].iloc[0], abs=0.01)


def test_curso_sem_previsao_devolve_null(client):
    assert client.get("/api/painel/previsao", params={"curso": "CURSO QUE NAO EXISTE"}).json() is None


def test_sem_arquivo_de_previsao_a_tabela_fica_vazia(amostra_csv, tmp_path, make_client):
    out = tmp_path / "sem_previsao.db"
    load_script("build_database").build(amostra_csv, out, origem="sintetico", previsao_csv=tmp_path / "nao_existe.csv")
    client = make_client(FakeLLM([]), Settings(_env_file=None, openai_api_key="x", database_path=out))
    assert client.get("/api/painel/previsao").json() is None


def test_banco_antigo_sem_tabela_previsao(db_path, tmp_path, make_client):
    antigo = tmp_path / "antigo.db"
    origem, destino = sqlite3.connect(db_path), sqlite3.connect(antigo)
    origem.backup(destino)
    destino.execute("DROP TABLE previsao")
    destino.commit()
    origem.close()
    destino.close()
    client = make_client(FakeLLM([]), Settings(_env_file=None, openai_api_key="x", database_path=antigo))
    assert client.get("/api/painel/previsao").json() is None


def test_situacao_desconhecida_no_csv_e_rejeitada(amostra_csv, tmp_path):
    ruim = tmp_path / "ruim.csv"
    ruim.write_text(
        "NM_PROGR_FORM,periodo_base,periodo_alvo,situacao,quantidade_projetada,proporcao_projetada\n"
        "ENGENHARIA CIVIL,2024.2,2026.1,TRANCADOS,3,1.0\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="situações desconhecidas"):
        load_script("build_database").build(amostra_csv, tmp_path / "x.db", previsao_csv=ruim)


def test_previsao_ficticia_tem_o_formato_do_notebook(esperado):
    assert list(esperado.columns[:6]) == [
        "NM_PROGR_FORM", "periodo_base", "periodo_alvo", "situacao", "quantidade_projetada", "proporcao_projetada"
    ]
    assert set(esperado["situacao"]) <= set(CATEGORIA)
    for _, linhas in esperado.groupby("NM_PROGR_FORM"):
        assert linhas["proporcao_projetada"].sum() == pytest.approx(1, abs=0.001)
