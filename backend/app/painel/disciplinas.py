"""Painel de Disciplinas: filtros e agregações feitos no servidor.

Aprovado/reprovado já vêm resolvidos da mineração (DISPENSADO conta como aprovado; as demais
situações só contam como matrícula). Médias de nota e de faltas ignoram valores ausentes.
Rankings: Top 10, desempate pelo nome da disciplina.

LGPD (k = supressao_k): nenhum número é exibido para um grupo com 1 a k-1 matrículas — o recorte
inteiro, um período da série, uma linha da tabela ou uma disciplina dos rankings. Médias de nota e
de faltas exigem ao menos k valores registrados.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from app.painel.comum import chave_pt, conexao, grupo_pequeno, marcadores, pct

TOP_N = 10

# Média de nota e de faltas sobre os valores registrados (NULL quando não há nenhum).
_MEDIAS = (
    "SUM(soma_media) / NULLIF(SUM(n_media), 0), "
    "SUM(soma_faltas) / NULLIF(SUM(n_faltas), 0), "
    "SUM(n_media), SUM(n_faltas)"
)


@lru_cache(maxsize=4)
def _filtros(path: Path, mtime: float) -> dict:
    with conexao(path) as con:
        cursos = [r[0] for r in con.execute("SELECT DISTINCT curso FROM painel_disciplinas ORDER BY curso")]
        periodos = [r[0] for r in con.execute("SELECT DISTINCT periodo_letivo FROM painel_disciplinas ORDER BY periodo_letivo")]
        disciplinas = [r[0] for r in con.execute("SELECT DISTINCT disciplina FROM painel_disciplinas ORDER BY disciplina")]
        (total_matriculas,) = con.execute("SELECT COALESCE(SUM(matriculas), 0) FROM painel_disciplinas").fetchone()
    return {"cursos": cursos, "periodos": periodos, "disciplinas": disciplinas, "total_matriculas": total_matriculas}


def filtros_disciplinas(path: Path) -> dict:
    f = _filtros(path, path.stat().st_mtime)
    return {"cursos": f["cursos"], "periodos": f["periodos"], "total_matriculas": f["total_matriculas"]}


@lru_cache(maxsize=32)
def _disciplinas_do_curso(path: Path, mtime: float, curso: str | None) -> list[str]:
    if curso is None:
        return _filtros(path, mtime)["disciplinas"]
    with conexao(path) as con:
        return [r[0] for r in con.execute(
            "SELECT DISTINCT disciplina FROM painel_disciplinas WHERE curso = ? ORDER BY disciplina", (curso,)
        )]


def disciplinas_do_curso(path: Path, curso: str | None) -> list[str]:
    """Opções do filtro Disciplina para o curso escolhido."""
    return _disciplinas_do_curso(path, path.stat().st_mtime, curso)


def _ranking(itens: list[dict], campo: str, ordem: str, k: int) -> list[dict]:
    # base do valor: matrículas (contagens), notas registradas (média) ou faltas registradas (frequência)
    base = {"media": "n_media", "faltas": "n_faltas"}.get(campo, "matriculas")
    validos = [
        {"disciplina": i["disciplina"], "valor": i[campo]}
        for i in itens
        if i[campo] is not None and not grupo_pequeno(i[base], k)
    ]
    sinal = -1 if ordem == "desc" else 1
    validos.sort(key=lambda x: (sinal * x["valor"], chave_pt(x["disciplina"])))
    return validos[:TOP_N]


@lru_cache(maxsize=256)
def _painel(
    path: Path, mtime: float, curso: str | None, periodos: tuple[str, ...], disciplinas: tuple[str, ...], k: int
) -> dict:
    filtros = _filtros(path, mtime)
    todos_periodos = filtros["periodos"]
    selecionados = sorted(p for p in set(periodos) if p in set(todos_periodos))
    disc_validas = sorted(d for d in set(disciplinas) if d in set(filtros["disciplinas"]))

    curso_inexistente = curso is not None and curso not in filtros["cursos"]
    # havia seleção de disciplinas, mas nenhuma existe nos dados
    disc_inexistente = bool(disciplinas) and not disc_validas

    condicoes, params = [], []
    if curso is not None:
        condicoes.append("curso = ?")
        params.append(curso)
    if disc_validas:
        condicoes.append(f"disciplina IN ({marcadores(disc_validas)})")
        params.extend(disc_validas)
    if selecionados:
        condicoes.append(f"periodo_letivo IN ({marcadores(selecionados)})")
        params.extend(selecionados)
    onde = (" WHERE " + " AND ".join(condicoes)) if condicoes else ""

    kpi = (0, 0, 0)
    por_periodo: dict[str, tuple[int, int, int]] = {}
    por_disciplina: list[dict] = []
    tabela: list[dict] = []

    if not curso_inexistente and not disc_inexistente:
        with conexao(path) as con:
            kpi = con.execute(
                "SELECT COALESCE(SUM(matriculas), 0), COALESCE(SUM(aprovados), 0), COALESCE(SUM(reprovados), 0)"
                f" FROM painel_disciplinas{onde}",
                params,
            ).fetchone()
            por_periodo = {
                p: (n, a, r)
                for p, n, a, r in con.execute(
                    "SELECT periodo_letivo, SUM(matriculas), SUM(aprovados), SUM(reprovados)"
                    f" FROM painel_disciplinas{onde} GROUP BY periodo_letivo",
                    params,
                )
            }
            por_disciplina = [
                {"disciplina": d, "matriculas": n, "aprovados": a, "reprovados": r, "media": m, "faltas": f,
                 "n_media": nm, "n_faltas": nf}
                for d, n, a, r, m, f, nm, nf in con.execute(
                    f"SELECT disciplina, SUM(matriculas), SUM(aprovados), SUM(reprovados), {_MEDIAS}"
                    f" FROM painel_disciplinas{onde}"
                    " GROUP BY disciplina",
                    params,
                )
            ]
            for c, d, n, a, r, m, f, nm, nf in con.execute(
                f"SELECT curso, disciplina, SUM(matriculas), SUM(aprovados), SUM(reprovados), {_MEDIAS}"
                f" FROM painel_disciplinas{onde} GROUP BY curso, disciplina",
                params,
            ):
                if grupo_pequeno(n, k):
                    tabela.append({
                        "curso": c, "disciplina": d, "suprimido": True, "matriculas": None, "aprovados": None,
                        "reprovados": None, "taxaAprovacao": None, "mediaFinal": None, "mediaFaltas": None,
                    })
                    continue
                tabela.append({
                    "curso": c,
                    "disciplina": d,
                    "suprimido": False,
                    "matriculas": n,
                    "aprovados": a,
                    "reprovados": r,
                    "taxaAprovacao": pct(a, a + r),
                    "mediaFinal": None if grupo_pequeno(nm, k) else m,
                    "mediaFaltas": None if grupo_pequeno(nf, k) else f,
                })
    tabela.sort(key=lambda t: (chave_pt(t["curso"]), chave_pt(t["disciplina"])))

    total, aprovados, reprovados = kpi
    suprimido = grupo_pequeno(total, k)
    if suprimido:
        por_disciplina = []
    periodos_serie = selecionados if selecionados else todos_periodos

    def ponto(p: str) -> dict:
        n, a, r = por_periodo.get(p, (0, 0, 0))
        if grupo_pequeno(n, k):
            return {"periodo": p, "aprovados": None, "reprovados": None}
        return {"periodo": p, "aprovados": a, "reprovados": r}

    return {
        "suprimido": suprimido,
        "limiteSupressao": k,
        "kpis": {
            "totalMatriculas": None if suprimido else total,
            "totalAprovados": None if suprimido else aprovados,
            "totalReprovados": None if suprimido else reprovados,
            "taxaAprovacao": None if suprimido else pct(aprovados, aprovados + reprovados),
            "taxaReprovacao": None if suprimido else pct(reprovados, aprovados + reprovados),
        },
        "rankingMaisAprovados": _ranking(por_disciplina, "aprovados", "desc", k),
        "rankingMaisReprovados": _ranking(por_disciplina, "reprovados", "desc", k),
        "rankingMelhorMedia": _ranking(por_disciplina, "media", "desc", k),
        "rankingPiorMedia": _ranking(por_disciplina, "media", "asc", k),
        "rankingMelhorFrequencia": _ranking(por_disciplina, "faltas", "asc", k),
        "rankingMaisFaltas": _ranking(por_disciplina, "faltas", "desc", k),
        "serieHistorica": [ponto(p) for p in periodos_serie],
        "tabela": tabela,
    }


def painel_disciplinas(path: Path, curso: str | None, periodos: list[str], disciplinas: list[str], k: int = 1) -> dict:
    return _painel(path, path.stat().st_mtime, curso, tuple(sorted(set(periodos))), tuple(sorted(set(disciplinas))), k)
