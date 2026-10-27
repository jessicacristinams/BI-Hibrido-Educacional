import pytest

from app.core.errors import UnsafeSQLError
from app.db.catalog import TABELAS_PERMITIDAS
from app.services.sql_guard import validate_select


@pytest.mark.parametrize(
    "sql, esperado",
    [
        ("SELECT COUNT(*) FROM alunos", "SELECT COUNT(*) FROM alunos"),
        ("```sql\nSELECT curso FROM alunos;\n```", "SELECT curso FROM alunos"),
        ("WITH t AS (SELECT curso FROM alunos) SELECT curso FROM t", None),
        ("SELECT curso FROM alunos UNION SELECT curso FROM matriculas", None),
        ("SELECT a.curso FROM alunos a JOIN matriculas m ON m.codigo_estudante = a.codigo_estudante", None),
    ],
)
def test_aceita_consultas_de_leitura(sql, esperado):
    assert validate_select(sql, TABELAS_PERMITIDAS) == (esperado or sql)


@pytest.mark.parametrize(
    "sql",
    [
        "",
        "DROP TABLE alunos",
        "DELETE FROM alunos",
        "UPDATE alunos SET curso = 'x'",
        "INSERT INTO alunos SELECT * FROM alunos",
        "SELECT 1; DELETE FROM alunos",
        "PRAGMA table_info(alunos)",
        "ATTACH DATABASE 'x.db' AS x",
        "SELECT * FROM sqlite_master",
        "SELECT * FROM main.alunos",
        "SELECT * FROM json_each('[1]')",
        "WITH t AS (DELETE FROM alunos RETURNING *) SELECT * FROM t",
        "SELEC curso FROM",
    ],
)
def test_bloqueia_consultas_inseguras_ou_invalidas(sql):
    with pytest.raises(UnsafeSQLError):
        validate_select(sql, TABELAS_PERMITIDAS)


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT codigo_estudante FROM alunos",
        "SELECT codigo_estudante AS id, curso FROM alunos",
        "SELECT * FROM alunos",
        "SELECT a.* FROM alunos a",
        "SELECT MAX(codigo_estudante) FROM alunos",
        "SELECT GROUP_CONCAT(codigo_estudante) FROM matriculas",
        "SELECT curso FROM alunos UNION SELECT codigo_estudante FROM alunos",
    ],
)
def test_lgpd_bloqueia_identificador_do_aluno_na_resposta(sql):
    with pytest.raises(UnsafeSQLError, match="LGPD"):
        validate_select(sql, TABELAS_PERMITIDAS)


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT COUNT(DISTINCT codigo_estudante) AS alunos FROM matriculas",
        "SELECT COUNT(*) FROM (SELECT codigo_estudante FROM alunos)",
        "WITH t AS (SELECT codigo_estudante, curso FROM alunos) SELECT curso, COUNT(*) FROM t GROUP BY curso",
    ],
)
def test_lgpd_permite_contar_alunos(sql):
    assert validate_select(sql, TABELAS_PERMITIDAS)
