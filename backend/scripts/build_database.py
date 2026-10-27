"""
build_database.py — gera o banco SQLite de onde a API tira os dados dos painéis e do Assistente IA.

Uso (a partir da raiz do projeto):
    python backend/scripts/build_database.py            # dados/df_tabela_final.csv ou, se ausente, dados sintéticos
    python backend/scripts/build_database.py --sintetico
    python backend/scripts/build_database.py --csv dados/df_tabela_final.csv --out backend/data/sigadash.db

Reaproveita a mineração de `python/` para que o chat e o dashboard sigam as
mesmas regras de negócio (categorias de aluno, regra dos 13 semestres,
aprovado/reprovado por disciplina). Rodar sempre que o CSV mudar.

Tabelas geradas:
  alunos          uma linha por aluno (situação atual, evasão, formação)
  alunos_periodo  uma linha por (aluno, período) com a categoria classificada
  matriculas      uma linha por matrícula em disciplina (nota, faltas, aprovado/reprovado)
  painel_disciplinas  agregado por curso × disciplina × período (Painel de Disciplinas)
  metadados       origem dos dados (real ou sintético) e data de geração
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from alunos_mining import mine_alunos  # noqa: E402
from common import (  # noqa: E402
    COL_ANO_CONC,
    COL_CURSO,
    COL_DISCIPLINA,
    COL_ESTUDANTE,
    COL_FALTAS,
    COL_MEDIA,
    COL_PERIODO,
    COL_SIT_HIST,
    load_csv,
    normalize_text,
    parse_period,
)
from disciplinas_mining import SITUACOES_APROVADO, SITUACOES_REPROVADO  # noqa: E402

DEFAULT_CSV = ROOT / "dados" / "df_tabela_final.csv"
DEFAULT_SINTETICO = ROOT / "dados" / "df_tabela_sintetica.csv"
DEFAULT_OUT = ROOT / "backend" / "data" / "sigadash.db"

DDL = """
CREATE TABLE alunos (
    codigo_estudante   TEXT PRIMARY KEY,
    curso              TEXT NOT NULL,
    curso_busca        TEXT NOT NULL,
    periodo_admissao   TEXT,
    ano_conclusao      INTEGER,
    periodo_atual      TEXT NOT NULL,
    semestre_atual     INTEGER NOT NULL,
    situacao_atual     TEXT NOT NULL,
    evadiu             INTEGER NOT NULL,
    periodo_evasao     TEXT,
    semestre_evasao    INTEGER,
    tipo_evasao        TEXT,
    formou             INTEGER NOT NULL,
    periodo_formacao   TEXT,
    semestre_formacao  INTEGER
);

CREATE TABLE alunos_periodo (
    codigo_estudante  TEXT NOT NULL REFERENCES alunos(codigo_estudante),
    curso             TEXT NOT NULL,
    curso_busca       TEXT NOT NULL,
    periodo_letivo    TEXT NOT NULL,
    semestre          INTEGER NOT NULL,
    categoria         TEXT NOT NULL,
    PRIMARY KEY (codigo_estudante, periodo_letivo)
);

CREATE TABLE matriculas (
    id                   INTEGER PRIMARY KEY,
    codigo_estudante     TEXT NOT NULL REFERENCES alunos(codigo_estudante),
    curso                TEXT NOT NULL,
    curso_busca          TEXT NOT NULL,
    disciplina           TEXT NOT NULL,
    disciplina_busca     TEXT NOT NULL,
    periodo_letivo       TEXT NOT NULL,
    situacao_disciplina  TEXT,
    aprovado             INTEGER NOT NULL,
    reprovado            INTEGER NOT NULL,
    media_final          REAL,
    total_faltas         REAL
);

CREATE INDEX ix_alunos_curso ON alunos(curso);
CREATE INDEX ix_alunos_periodo_periodo ON alunos_periodo(periodo_letivo);
CREATE INDEX ix_alunos_periodo_curso ON alunos_periodo(curso);
CREATE INDEX ix_matriculas_disciplina ON matriculas(disciplina);
CREATE INDEX ix_matriculas_disciplina_busca ON matriculas(disciplina_busca);
CREATE INDEX ix_matriculas_periodo ON matriculas(periodo_letivo);
CREATE INDEX ix_matriculas_curso ON matriculas(curso);
CREATE INDEX ix_matriculas_estudante ON matriculas(codigo_estudante);
"""


DDL_PAINEL = """
CREATE TABLE painel_disciplinas AS
SELECT curso, disciplina, periodo_letivo,
       COUNT(*)            AS matriculas,
       SUM(aprovado)       AS aprovados,
       SUM(reprovado)      AS reprovados,
       SUM(media_final)    AS soma_media,
       COUNT(media_final)  AS n_media,
       SUM(total_faltas)   AS soma_faltas,
       COUNT(total_faltas) AS n_faltas
FROM matriculas
GROUP BY curso, disciplina, periodo_letivo;

CREATE INDEX ix_painel_disciplinas_curso ON painel_disciplinas(curso);
CREATE INDEX ix_painel_disciplinas_periodo ON painel_disciplinas(periodo_letivo);
"""


def _ano_conclusao(df: pd.DataFrame) -> dict[str, int]:
    anos = pd.to_numeric(df[COL_ANO_CONC], errors="coerce")
    por_aluno = anos.groupby(df[COL_ESTUDANTE]).max().dropna()
    return {str(k): int(v) for k, v in por_aluno.items()}


def _rows_alunos(resumo: list[dict], ano_conc: dict[str, int]) -> list[tuple]:
    rows = []
    for a in resumo:
        ev = a["evasao"] or {}
        fo = a["formacao"] or {}
        rows.append((
            a["codigo_estudante"],
            a["curso"],
            normalize_text(a["curso"]),
            a["admissao"],
            ano_conc.get(a["codigo_estudante"]),
            a["periodo_atual"],
            a["semestre_atual"],
            a["situacao_atual"],
            int(bool(a["evasao"])),
            ev.get("periodo"),
            ev.get("semestre"),
            ev.get("tipo"),
            int(bool(a["formacao"])),
            fo.get("periodo"),
            fo.get("semestre"),
        ))
    return rows


def _rows_alunos_periodo(periodo: list[dict]) -> list[tuple]:
    busca: dict[str, str] = {}
    rows = []
    for p in periodo:
        curso = p["curso"]
        if curso not in busca:
            busca[curso] = normalize_text(curso)
        rows.append((p["codigo_estudante"], curso, busca[curso], p["periodo"], p["semestre"], p["categoria"]))
    return rows


def _rows_matriculas(df: pd.DataFrame) -> list[tuple]:
    """Mesmo recorte e mesma regra de aprovado/reprovado de disciplinas_mining."""
    ok = (
        df[COL_CURSO].notna()
        & df[COL_DISCIPLINA].notna()
        & df[COL_PERIODO].map(lambda p: parse_period(p) is not None)
    )
    base = df[ok]
    sit = base[COL_SIT_HIST].map(normalize_text)
    aprov = sit.isin(SITUACOES_APROVADO).astype(int)
    reprov = sit.isin(SITUACOES_REPROVADO).astype(int)

    busca: dict[str, str] = {}

    def _busca(v: str) -> str:
        if v not in busca:
            busca[v] = normalize_text(v)
        return busca[v]

    def _num(v: float) -> float | None:
        return None if pd.isna(v) else round(float(v), 2)

    def _txt(v: object) -> str | None:
        return None if pd.isna(v) else str(v)

    return [
        (str(e), c, _busca(c), d, _busca(d), p, _txt(s), int(a), int(r), _num(m), _num(f))
        for e, c, d, p, s, a, r, m, f in zip(
            base[COL_ESTUDANTE],
            base[COL_CURSO],
            base[COL_DISCIPLINA],
            base[COL_PERIODO],
            base[COL_SIT_HIST],
            aprov,
            reprov,
            base[COL_MEDIA],
            base[COL_FALTAS],
        )
    ]


def build(csv_path: Path, out_path: Path, origem: str = "real") -> None:
    t0 = time.perf_counter()
    df = load_csv(csv_path)
    print(f"• CSV lido: {len(df):,} linhas")

    alunos = mine_alunos(df)
    print("• Mineração de alunos concluída")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = out_path.with_suffix(".tmp")
    tmp_path.unlink(missing_ok=True)

    # Grava num arquivo temporário e troca no final: a API nunca enxerga um banco pela metade.
    con = sqlite3.connect(tmp_path)
    try:
        con.executescript(DDL)
        con.executemany(
            "INSERT INTO alunos VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            _rows_alunos(alunos["alunos_resumo"], _ano_conclusao(df)),
        )
        con.executemany(
            "INSERT INTO alunos_periodo VALUES (?,?,?,?,?,?)",
            _rows_alunos_periodo(alunos["alunos_periodo"]),
        )
        con.executemany(
            "INSERT INTO matriculas (codigo_estudante, curso, curso_busca, disciplina, disciplina_busca,"
            " periodo_letivo, situacao_disciplina, aprovado, reprovado, media_final, total_faltas)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            _rows_matriculas(df),
        )
        # Agregado do Painel de Disciplinas: só contagens e somas por curso × disciplina × período,
        # sem linhas por aluno. Médias = soma ÷ quantidade de valores registrados.
        con.executescript(DDL_PAINEL)
        # Origem dos dados ("real" ou "sintetico"): o dashboard avisa quando são fictícios.
        con.execute("CREATE TABLE metadados (chave TEXT PRIMARY KEY, valor TEXT NOT NULL)")
        con.executemany(
            "INSERT INTO metadados VALUES (?, ?)",
            [("origem_dados", origem), ("gerado_em", time.strftime("%Y-%m-%dT%H:%M:%S"))],
        )
        con.commit()
        con.execute("ANALYZE")
        for tabela in ("alunos", "alunos_periodo", "matriculas", "painel_disciplinas"):
            (n,) = con.execute(f"SELECT COUNT(*) FROM {tabela}").fetchone()
            print(f"  ✔ {tabela}: {n:,} linhas")
    finally:
        con.close()

    tmp_path.replace(out_path)
    print(f"• Banco gravado em {out_path} ({time.perf_counter() - t0:.1f}s)")


def _rel(path: Path) -> Path:
    return path.relative_to(ROOT) if path.is_relative_to(ROOT) else path


def main() -> int:
    ap = argparse.ArgumentParser(description="Gera o banco SQLite da API do Sigadash.v2")
    ap.add_argument("--csv", type=Path, default=None, help=f"padrão: {_rel(DEFAULT_CSV)}")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--origem", choices=["real", "sintetico"], default="real", help="origem do --csv informado")
    ap.add_argument("--sintetico", action="store_true", help="usa dados fictícios mesmo se houver CSV real")
    args = ap.parse_args()

    csv_path, origem = args.csv, args.origem
    if csv_path is None:
        if DEFAULT_CSV.exists() and not args.sintetico:
            csv_path, origem = DEFAULT_CSV, "real"
        else:
            # Os dados reais não vão para o repositório (LGPD); sem eles, o sistema roda com dados fictícios.
            if not args.sintetico:
                print(f"⚠ {_rel(DEFAULT_CSV)} não encontrado: usando DADOS SINTÉTICOS (alunos fictícios).")
            if not DEFAULT_SINTETICO.exists():
                sys.path.insert(0, str(Path(__file__).resolve().parent))
                from gerar_dados_sinteticos import main as gerar_sinteticos

                sys.argv = [sys.argv[0], "--out", str(DEFAULT_SINTETICO)]
                gerar_sinteticos()
            csv_path, origem = DEFAULT_SINTETICO, "sintetico"

    if not csv_path.exists():
        print(f"CSV não encontrado: {csv_path}", file=sys.stderr)
        return 1
    build(csv_path, args.out, origem)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
