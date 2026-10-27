"""Endpoints dos painéis do dashboard: o navegador só recebe o recorte já filtrado e agregado."""

from __future__ import annotations

import sqlite3
from typing import Annotated, Callable, TypeVar

from fastapi import APIRouter, HTTPException, Query

from app.api.deps import SettingsDep
from app.core.errors import DatabaseUnavailableError
from app.painel.alunos import filtros_alunos, painel_alunos
from app.painel.comum import origem_dados
from app.painel.disciplinas import disciplinas_do_curso, filtros_disciplinas, painel_disciplinas
from app.schemas.painel import Categoria, FiltrosResponse, PainelAlunos, PainelDisciplinas

router = APIRouter(prefix="/api/painel", tags=["painéis"])

MAX_ITENS_FILTRO = 600  # limite de valores por filtro de múltipla escolha
T = TypeVar("T")

Curso = Annotated[str | None, Query(max_length=200, description="Vazio = todos os cursos")]
Periodos = Annotated[list[str], Query(description="Repita o parâmetro: ?periodos=2023.1&periodos=2023.2. Vazio = todos")]


def _limitar(nome: str, valores: list[str]) -> list[str]:
    if len(valores) > MAX_ITENS_FILTRO:
        raise HTTPException(status_code=422, detail=f"Filtro '{nome}' aceita no máximo {MAX_ITENS_FILTRO} valores.")
    return valores


def _consultar(fn: Callable[[], T]) -> T:
    try:
        return fn()
    except sqlite3.OperationalError as exc:
        if "no such table" in str(exc):
            raise DatabaseUnavailableError(
                "Banco de dados desatualizado. Gere-o de novo com: python backend/scripts/build_database.py"
            ) from exc
        raise


@router.get("/filtros", response_model=FiltrosResponse)
def filtros(settings: SettingsDep) -> dict:
    """Opções dos filtros (cursos e períodos) e totais exibidos no cabeçalho."""
    db = settings.database_path

    def _f() -> dict:
        a, d = filtros_alunos(db), filtros_disciplinas(db)
        return {
            "alunos": {"cursos": a["cursos"], "periodos": a["periodos"]},
            "disciplinas": {"cursos": d["cursos"], "periodos": d["periodos"]},
            "totais": {"alunos": a["total_alunos"], "matriculas": d["total_matriculas"]},
            "origemDados": origem_dados(db),
            "limiteSupressao": settings.supressao_k,
        }

    return _consultar(_f)


@router.get("/alunos", response_model=PainelAlunos)
def alunos(
    settings: SettingsDep,
    curso: Curso = None,
    periodos: Periodos = [],  # noqa: B006 — padrão imutável na prática (FastAPI cria uma lista nova)
    indicadores: Annotated[list[Categoria], Query(description="Vazio = todos os indicadores")] = [],  # noqa: B006
) -> dict:
    """KPIs, série histórica e gráficos de evasão/formação do Painel de Alunos para o recorte pedido."""
    _limitar("periodos", periodos)
    return _consultar(
        lambda: painel_alunos(settings.database_path, curso or None, periodos, list(indicadores), settings.supressao_k)
    )


@router.get("/disciplinas", response_model=PainelDisciplinas)
def disciplinas(
    settings: SettingsDep,
    curso: Curso = None,
    periodos: Periodos = [],  # noqa: B006
    disciplinas: Annotated[list[str], Query(description="Vazio = todas as disciplinas")] = [],  # noqa: B006
) -> dict:
    """KPIs, rankings, série histórica e tabela do Painel de Disciplinas para o recorte pedido."""
    _limitar("periodos", periodos)
    _limitar("disciplinas", disciplinas)
    return _consultar(
        lambda: painel_disciplinas(settings.database_path, curso or None, periodos, disciplinas, settings.supressao_k)
    )


@router.get("/disciplinas/opcoes", response_model=list[str])
def opcoes_disciplinas(settings: SettingsDep, curso: Curso = None) -> list[str]:
    """Disciplinas oferecidas no curso (opções do filtro Disciplina)."""
    return _consultar(lambda: disciplinas_do_curso(settings.database_path, curso or None))
