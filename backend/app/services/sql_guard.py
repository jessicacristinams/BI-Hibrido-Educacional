"""Validação do SQL gerado pelo LLM antes de executá-lo.

Aceita apenas uma única consulta de leitura (SELECT, com ou sem CTE/UNION)
sobre as tabelas conhecidas. Substitui a antiga lista de palavras proibidas,
que bloqueava consultas legítimas (ex.: coluna "updated") e deixava passar
outras (ex.: PRAGMA, ATTACH).
"""

from __future__ import annotations

import re

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

from app.core.errors import UnsafeSQLError

_FENCE_RE = re.compile(r"^\s*```(?:sql)?\s*|\s*```\s*$", re.IGNORECASE)

_NOS_PROIBIDOS = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Merge,
    exp.Create,
    exp.Drop,
    exp.Alter,
    exp.Command,
    exp.Pragma,
    exp.Attach,
    exp.Detach,
    exp.Transaction,
    exp.Commit,
    exp.Rollback,
)


def strip_markdown(sql: str) -> str:
    return _FENCE_RE.sub("", sql).strip()


def validate_select(sql: str, tabelas_permitidas: frozenset[str]) -> str:
    """Devolve o SQL limpo se for seguro; senão levanta UnsafeSQLError."""
    sql = strip_markdown(sql).rstrip(";").strip()
    if not sql:
        raise UnsafeSQLError("Nenhuma consulta SQL foi gerada.")

    try:
        statements = [s for s in sqlglot.parse(sql, read="sqlite") if s is not None]
    except ParseError as exc:
        raise UnsafeSQLError(f"SQL inválido: {exc}") from exc

    if len(statements) != 1:
        raise UnsafeSQLError("Apenas uma consulta por pergunta é permitida.")

    (root,) = statements
    if not isinstance(root, exp.Query):
        raise UnsafeSQLError("Apenas consultas de leitura (SELECT) são permitidas.")

    for node in root.walk():
        if isinstance(node, _NOS_PROIBIDOS):
            raise UnsafeSQLError("A consulta contém comandos que não são de leitura.")

    ctes = {cte.alias_or_name.lower() for cte in root.find_all(exp.CTE)}
    for table in root.find_all(exp.Table):
        nome = table.name.lower()
        if not nome:  # funções de tabela, ex.: json_each(...)
            raise UnsafeSQLError("Funções de tabela não são permitidas.")
        if table.db or table.catalog:
            raise UnsafeSQLError("Apenas o banco principal pode ser consultado.")
        if nome not in ctes and nome not in tabelas_permitidas:
            raise UnsafeSQLError(f"Tabela desconhecida: {table.name}")

    _bloquear_dados_pessoais(root)
    return sql


# LGPD: a resposta do chat é exibida ao usuário, então não pode trazer identificadores de alunos.
COLUNAS_PESSOAIS = frozenset({"codigo_estudante"})
_SET_OPERATION = getattr(exp, "SetOperation", exp.Union)


def _projecoes_de_saida(consulta: exp.Expression) -> list[exp.Expression]:
    """Colunas que chegam ao usuário (SELECT externo; em UNION, de cada lado)."""
    if isinstance(consulta, _SET_OPERATION):
        return _projecoes_de_saida(consulta.left) + _projecoes_de_saida(consulta.right)
    if isinstance(consulta, exp.Subquery):
        return _projecoes_de_saida(consulta.this)
    if isinstance(consulta, exp.Select):
        return list(consulta.expressions)
    return []


def _bloquear_dados_pessoais(root: exp.Expression) -> None:
    for proj in _projecoes_de_saida(root):
        if isinstance(proj, exp.Star) or (isinstance(proj, exp.Column) and isinstance(proj.this, exp.Star)):
            raise UnsafeSQLError(
                "Por proteção de dados (LGPD), liste as colunas desejadas em vez de SELECT * e não inclua o código do aluno."
            )
        for col in proj.find_all(exp.Column):
            # Contar alunos (COUNT(DISTINCT codigo_estudante)) é permitido; devolver o código, não.
            if col.name.lower() in COLUNAS_PESSOAIS and col.find_ancestor(exp.Count) is None:
                raise UnsafeSQLError(
                    "Por proteção de dados (LGPD), a consulta não pode devolver o código do aluno; "
                    "use COUNT(DISTINCT codigo_estudante) para contar alunos."
                )
