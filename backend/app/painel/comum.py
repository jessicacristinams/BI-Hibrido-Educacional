"""Utilidades compartilhadas pelos painéis do dashboard (consultas agregadas no SQLite)."""

from __future__ import annotations

import sqlite3
import unicodedata
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path
from typing import Iterator, Sequence

from app.db.database import connect_readonly

CATEGORIAS = ("ATIVO", "EVADIDO", "RETIDO", "FORMADO")


@contextmanager
def conexao(path: Path) -> Iterator[sqlite3.Connection]:
    con = connect_readonly(path)
    try:
        yield con
    finally:
        con.close()


def chave_pt(texto: str) -> tuple[str, str]:
    """Ordem alfabética como o localeCompare("pt-BR") do navegador: ignora acentos e caixa, desempata pelo original."""
    sem_acento = "".join(c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c))
    return (sem_acento.casefold(), texto)


def marcadores(valores: Sequence[object]) -> str:
    return ",".join("?" * len(valores))


def histograma_semestres(contagem: dict[int, int]) -> list[dict]:
    """Histograma denso de 1..max (semestres sem valor aparecem com 0)."""
    if not contagem:
        return []
    return [{"semestre": s, "valor": contagem.get(s, 0)} for s in range(1, max(contagem) + 1)]


def pct(num: float, den: float) -> float:
    return num / den * 100 if den > 0 else 0.0


def grupo_pequeno(n: int | None, k: int) -> bool:
    """LGPD: um grupo com 1..k-1 pessoas tem os números ocultados (0 não identifica ninguém)."""
    return n is not None and 0 < n < k


@lru_cache(maxsize=4)
def _origem(path: Path, mtime: float) -> str:
    with conexao(path) as con:
        try:
            row = con.execute("SELECT valor FROM metadados WHERE chave = 'origem_dados'").fetchone()
        except sqlite3.OperationalError:  # banco gerado antes da tabela metadados
            return "real"
    return row[0] if row else "real"


def origem_dados(path: Path) -> str:
    """"real" ou "sintetico" (base de demonstração gerada sem os dados dos alunos)."""
    return _origem(path, path.stat().st_mtime)
