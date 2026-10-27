from __future__ import annotations

import csv
import importlib.util
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_llm_client
from app.core.config import Settings, get_settings
from app.main import create_app

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "backend" / "scripts"
ALUNOS_FICTICIOS = 300


def load_script(nome: str):
    spec = importlib.util.spec_from_file_location(nome, SCRIPTS / f"{nome}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="session")
def amostra_csv(tmp_path_factory) -> Path:
    """CSV de alunos fictícios (os testes não dependem dos dados reais, que não ficam no repositório)."""
    gerador = load_script("gerar_dados_sinteticos")
    out = tmp_path_factory.mktemp("csv") / "amostra.csv"
    with out.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(gerador.COLUNAS)
        w.writerows(gerador.gerar(ALUNOS_FICTICIOS, semente=1))
    return out


@pytest.fixture(scope="session")
def db_path(tmp_path_factory, amostra_csv) -> Path:
    """Banco gerado pelo script real a partir do CSV fictício."""
    out = tmp_path_factory.mktemp("db") / "sigadash.db"
    load_script("build_database").build(amostra_csv, out, origem="sintetico")
    return out


@pytest.fixture
def settings(db_path) -> Settings:
    # supressao_k=1 desliga a supressão de grupos pequenos (testada à parte em test_painel_api.py)
    return Settings(_env_file=None, openai_api_key="test", database_path=db_path, supressao_k=1)


class FakeLLM:
    """Devolve respostas pré-programadas, na ordem, e registra as chamadas."""

    def __init__(self, respostas: list[str | dict]) -> None:
        self.respostas = [json.dumps(r) if isinstance(r, dict) else r for r in respostas]
        self.chamadas: list[dict] = []

    def complete(self, system, messages, json_mode=False):
        self.chamadas.append({"system": system, "messages": messages, "json_mode": json_mode})
        return self.respostas.pop(0)


@pytest.fixture
def make_client(settings):
    def _make(llm: FakeLLM | None, settings_override: Settings | None = None) -> TestClient:
        app = create_app()
        app.dependency_overrides[get_settings] = lambda: settings_override or settings
        if llm is not None:
            app.dependency_overrides[get_llm_client] = lambda: llm
        return TestClient(app)

    return _make
