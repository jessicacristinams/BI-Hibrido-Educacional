"""Painel de Alunos: filtros e contagens feitos no servidor.

Situação "no recorte":
- sem período selecionado ("Todos os Períodos"): situação mais recente do histórico completo
  (alunos.situacao_atual);
- com períodos: para cada aluno, a categoria do período MAIS RECENTE dentre os selecionados.

Os indicadores (filtro Indicador) só escolhem quais categorias aparecem; as taxas são sempre
sobre o total de alunos do recorte. Nenhuma linha identifica alunos: só contagens.

LGPD (k = supressao_k): se o recorte tem de 1 a k-1 alunos, nenhum número dele é exibido; na
série histórica, o mesmo vale para cada período com de 1 a k-1 alunos; nos gráficos de evasão e
formação, barras com 1 a k-1 alunos ficam ocultas.
"""

from __future__ import annotations

from collections import Counter
from functools import lru_cache
from pathlib import Path

from app.painel.comum import CATEGORIAS, chave_pt, conexao, grupo_pequeno, histograma_semestres, marcadores, pct

SERIE_KEY = {"ATIVO": "ativos", "EVADIDO": "evadidos", "RETIDO": "retidos", "FORMADO": "formados"}


@lru_cache(maxsize=4)
def _filtros(path: Path, mtime: float) -> dict:  # mtime invalida o cache quando o banco é regerado
    with conexao(path) as con:
        cursos = [r[0] for r in con.execute("SELECT DISTINCT curso FROM alunos_periodo ORDER BY curso")]
        periodos = [r[0] for r in con.execute("SELECT DISTINCT periodo_letivo FROM alunos_periodo ORDER BY periodo_letivo")]
        (total_alunos,) = con.execute("SELECT COUNT(*) FROM alunos").fetchone()
    return {"cursos": cursos, "periodos": periodos, "total_alunos": total_alunos}


def filtros_alunos(path: Path) -> dict:
    return _filtros(path, path.stat().st_mtime)


def _onde(curso: str | None, periodos: list[str], col_periodo: str) -> tuple[str, list]:
    condicoes, params = [], []
    if curso is not None:
        condicoes.append("curso = ?")
        params.append(curso)
    if periodos:
        condicoes.append(f"{col_periodo} IN ({marcadores(periodos)})")
        params.extend(periodos)
    return (" WHERE " + " AND ".join(condicoes)) if condicoes else "", params


@lru_cache(maxsize=256)
def _painel(
    path: Path, mtime: float, curso: str | None, periodos: tuple[str, ...], indicadores: tuple[str, ...], k: int
) -> dict:
    todos_periodos = _filtros(path, mtime)["periodos"]
    conhecidos = set(todos_periodos)
    selecionados = sorted(p for p in set(periodos) if p in conhecidos)

    marcados = set(indicadores)
    visiveis = [c for c in CATEGORIAS if c in marcados] if marcados else list(CATEGORIAS)
    mostra_evasao = "EVADIDO" in visiveis
    mostra_formacao = "FORMADO" in visiveis

    with conexao(path) as con:
        # ── KPIs: situação de cada aluno no recorte ──────────────────────────
        if not selecionados:
            onde, params = _onde(curso, [], "")
            sql = f"SELECT situacao_atual, COUNT(*) FROM alunos{onde} GROUP BY situacao_atual"
        else:
            onde, params = _onde(curso, selecionados, "periodo_letivo")
            sql = (
                "SELECT categoria, COUNT(*) FROM ("
                "  SELECT categoria, ROW_NUMBER() OVER (PARTITION BY codigo_estudante ORDER BY periodo_letivo DESC) AS rn"
                f"  FROM alunos_periodo{onde}"
                ") WHERE rn = 1 GROUP BY categoria"
            )
        por_categoria = dict(con.execute(sql, params).fetchall())
        total_alunos = sum(por_categoria.values())

        # ── Série histórica: contagem por período e categoria ───────────────
        onde, params = _onde(curso, selecionados, "periodo_letivo")
        serie_bruta = con.execute(
            f"SELECT periodo_letivo, categoria, COUNT(*) FROM alunos_periodo{onde} GROUP BY periodo_letivo, categoria",
            params,
        ).fetchall()

        # ── Evasão e formação (eventos filtrados pelo período em que ocorreram) ─
        ev_semestre: Counter = Counter()
        ev_tipo: Counter = Counter()
        if mostra_evasao:
            onde, params = _onde(curso, selecionados, "periodo_evasao")
            onde = (onde + " AND" if onde else " WHERE") + " evadiu = 1"
            for semestre, tipo, n in con.execute(
                f"SELECT semestre_evasao, tipo_evasao, COUNT(*) FROM alunos{onde} GROUP BY semestre_evasao, tipo_evasao",
                params,
            ):
                ev_semestre[semestre] += n
                ev_tipo[tipo] += n

        form_semestre: Counter = Counter()
        if mostra_formacao:
            onde, params = _onde(curso, selecionados, "periodo_formacao")
            onde = (onde + " AND" if onde else " WHERE") + " formou = 1"
            for semestre, n in con.execute(
                f"SELECT semestre_formacao, COUNT(*) FROM alunos{onde} GROUP BY semestre_formacao", params
            ):
                form_semestre[semestre] += n

    periodos_serie = selecionados if selecionados else todos_periodos
    serie = {p: {"periodo": p, "ativos": 0, "evadidos": 0, "retidos": 0, "formados": 0} for p in periodos_serie}
    for periodo, categoria, n in serie_bruta:
        if periodo in serie:
            serie[periodo][SERIE_KEY[categoria]] += n
    for ponto in serie.values():
        if grupo_pequeno(sum(ponto[c] for c in SERIE_KEY.values()), k):
            ponto.update({c: None for c in SERIE_KEY.values()})

    suprimido = grupo_pequeno(total_alunos, k)
    return {
        "totalAlunos": None if suprimido else total_alunos,
        "suprimido": suprimido,
        "limiteSupressao": k,
        "kpis": [
            {"categoria": c, "total": None, "taxa": None}
            if suprimido
            else {"categoria": c, "total": por_categoria.get(c, 0), "taxa": pct(por_categoria.get(c, 0), total_alunos)}
            for c in visiveis
        ],
        "categoriasVisiveis": visiveis,
        "serieHistorica": [serie[p] for p in periodos_serie],
        "evasaoPorSemestre": [] if suprimido else _ocultar_barras(histograma_semestres(dict(ev_semestre)), k),
        "formacaoPorSemestre": [] if suprimido else _ocultar_barras(histograma_semestres(dict(form_semestre)), k),
        "evasaoPorTipoSaida": [] if suprimido else _ocultar_barras([
            {"tipo": t, "valor": v} for t, v in sorted(ev_tipo.items(), key=lambda tv: (-tv[1], chave_pt(tv[0])))
        ], k),
    }


def _ocultar_barras(barras: list[dict], k: int) -> list[dict]:
    return [{**b, "valor": None} if grupo_pequeno(b["valor"], k) else b for b in barras]


def painel_alunos(path: Path, curso: str | None, periodos: list[str], indicadores: list[str], k: int = 1) -> dict:
    return _painel(path, path.stat().st_mtime, curso, tuple(sorted(set(periodos))), tuple(sorted(set(indicadores))), k)
