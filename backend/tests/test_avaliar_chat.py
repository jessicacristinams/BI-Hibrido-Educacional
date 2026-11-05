"""Script de avaliação do chat: comparador de resultados e consultas de referência."""

import json
import sqlite3

import pytest

from app.core.config import Settings
from app.services.chat_service import ChatService
from tests.conftest import load_script

av = load_script("avaliar_chat")


@pytest.mark.parametrize(
    "cols, dados, esperado",
    [
        # mesma informação, outra ordem de linhas e de colunas, nomes diferentes e coluna a mais
        (["taxa_pct", "total", "curso"], [[60.3, 156, "MECATRONICA"], [33.7, 2960, "CIVIL"]], True),
        # arredondamento diferente dentro da tolerância
        (["curso", "t"], [["CIVIL", 33.66], ["MECATRONICA", 60.31]], True),
        # número errado
        (["curso", "t"], [["CIVIL", 41.2], ["MECATRONICA", 69.9]], False),
        # faltou o primeiro curso do ranking
        (["curso", "t"], [["MECATRONICA", 60.3]], False),
        # cursos trocados
        (["curso", "t"], [["CIVIL", 60.3], ["MECATRONICA", 33.7]], False),
    ],
)
def test_comparar(cols, dados, esperado):
    ref_cols, ref = ["curso", "taxa"], [["CIVIL", 33.7], ["MECATRONICA", 60.3]]
    assert av.comparar(ref_cols, ref, cols, dados)[0] is esperado


def test_comparar_rotulos_escritos_pelo_modelo_casam_pela_ordem():
    ref_cols, ref = ["fase", "media", "taxa"], [["antes", 79.4, 4.6], ["depois", 290.1, 8.6]]
    chat = [["antes de 2020", 20, 1588, 79.4, 4.6], ["a partir de 2020", 13, 3771, 290.1, 8.6]]
    assert av.comparar(ref_cols, ref, ["fase", "periodos", "evadidos", "m", "t"], chat)[0]


def test_comparar_aceita_faltar_linha_toda_zero():
    ref_cols, ref = ["periodo", "ativos"], [["2010.1", 250], ["2025.2", 0], ["2011.1", 300]]
    assert av.comparar(ref_cols, ref, ["p", "n"], [["2010.1", 250], ["2011.1", 300]])[0]
    assert not av.comparar(ref_cols, ref, ["p", "n"], [["2010.1", 250], ["2011.1", 301]])[0]


def test_comparar_aceita_o_comeco_do_ranking():
    ref_cols, ref = ["curso", "taxa"], [["MECATRONICA", 60.3], ["CIVIL", 33.7]]
    assert av.comparar(ref_cols, ref, ["curso", "taxa"], [["MECATRONICA", 60.3]])[0]
    assert not av.comparar(ref_cols, ref, ["curso", "taxa"], [["CIVIL", 33.7]])[0]


def test_comparar_vazio_equivale_a_referencia_toda_zero():
    assert av.comparar(["ano", "formados"], [["2015", 0], ["2016", 0]], ["ano", "formados"], [])[0]
    assert not av.comparar(["ano", "formados"], [["2015", 0], ["2016", 3]], ["ano", "formados"], [])[0]


def test_comparar_sem_rotulos_usa_a_ordem():
    assert av.comparar(["a", "b"], [[1, 2.5]], ["x", "y", "z"], [["texto", 1, 2.5]])[0]
    assert not av.comparar(["a"], [[1]], ["x"], [[2]])[0]


@pytest.mark.parametrize("caso", [c for c in av.CASOS if c.sql], ids=lambda c: c.pergunta[:40])
def test_consultas_de_referencia_rodam(db_path, caso):
    con = sqlite3.connect(db_path)
    con.execute(caso.sql).fetchall()
    con.close()


class LLMDeReferencia:
    """Simula um modelo perfeito: devolve o SQL de referência de cada pergunta."""

    def __init__(self):
        self.sql = {c.pergunta: c.sql for c in av.CASOS}
        self.sql["Quais cursos têm maior taxa de evasão?"] = self.sql["Qual curso tem a maior taxa de evasão?"]
        self.sql["Qual a média de Cálculo 1?"] = (
            "SELECT ROUND(AVG(media_final), 2) AS m FROM matriculas WHERE disciplina_busca = 'CALCULO DIFERENCIAL E INTEGRAL 1'"
        )
        self.motivos = {c.pergunta: f"Recusado: {c.recusa_contem}" for c in av.CASOS if c.sql is None}

    def complete(self, system, messages, json_mode=False):
        pergunta = messages[-1]["content"]
        if "especialista em SQL" not in system:
            return json.dumps({"resposta": "ok", "grafico": None})
        if pergunta in self.motivos:
            return json.dumps({"relevante": False, "sql": None, "motivo": self.motivos[pergunta]})
        return json.dumps({"relevante": True, "sql": self.sql[pergunta]})


def test_avaliacao_completa_com_modelo_perfeito(db_path, tmp_path):
    settings = Settings(_env_file=None, openai_api_key="x", database_path=db_path)
    casos = list(enumerate(av.CASOS, start=1))
    resultados = av.avaliar(casos, ChatService(LLMDeReferencia(), settings), db_path)
    falhas = [(r.numero, r.detalhe) for r in resultados if not r.acertou]
    assert not falhas
    relatorio = av.relatorio(resultados, "modelo-de-teste")
    assert f"{len(casos)} de {len(casos)} corretas" in relatorio
