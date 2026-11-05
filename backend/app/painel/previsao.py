"""Previsão do próximo semestre letivo: resultados do notebook de previsão, por curso.

O algoritmo (Random Forest de transição) roda fora do sistema; o build_database.py só carrega
o resumo projetado (tabela previsao). "Todos os cursos" = soma das quantidades de cada curso, e
as porcentagens são recalculadas sobre o total somado (não é a média das porcentagens).
"""

from __future__ import annotations

import sqlite3
from functools import lru_cache
from pathlib import Path

from app.painel.comum import CATEGORIAS, conexao, pct


@lru_cache(maxsize=32)
def _previsao(path: Path, mtime: float, curso: str | None) -> dict | None:
    condicao, params = ("WHERE curso = ?", [curso]) if curso is not None else ("", [])
    with conexao(path) as con:
        try:
            linhas = con.execute(
                f"SELECT curso, periodo_base, periodo_alvo, categoria, quantidade FROM previsao {condicao}", params
            ).fetchall()
        except sqlite3.OperationalError:  # banco gerado antes da tabela previsao
            return None
    if not linhas:
        return None

    por_categoria = {c: 0 for c in CATEGORIAS}
    for _, _, _, categoria, quantidade in linhas:
        por_categoria[categoria] += quantidade
    total = sum(por_categoria.values())
    return {
        "periodoAlvo": max(r[2] for r in linhas),
        "periodosBase": sorted({r[1] for r in linhas}),
        "totalProjetado": total,
        "itens": [{"categoria": c, "quantidade": n, "taxa": pct(n, total)} for c, n in por_categoria.items()],
    }


def previsao(path: Path, curso: str | None) -> dict | None:
    """None quando não há previsão carregada (ou para um curso fora do resumo projetado)."""
    return _previsao(path, path.stat().st_mtime, curso)
