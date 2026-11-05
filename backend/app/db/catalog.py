"""Descrição do banco enviada ao LLM.

A parte fixa (tabelas, colunas e regras de negócio) é escrita à mão, porque é
ela que ensina o modelo a responder do mesmo jeito que o dashboard. A parte
variável (cursos, períodos, situações) é lida do próprio banco, para que o
modelo use exatamente os textos gravados.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from app.db.database import connect_readonly

TABELAS_PERMITIDAS = frozenset({"alunos", "alunos_periodo", "matriculas"})

SCHEMA_DESCRICAO = """\
TABLE alunos  -- uma linha por aluno
  codigo_estudante   TEXT PRIMARY KEY
  curso              TEXT     -- nome do curso como gravado (com acentos)
  curso_busca        TEXT     -- curso em MAIÚSCULAS e SEM acentos, para filtros com LIKE
  periodo_admissao   TEXT     -- 'AAAA.S'
  ano_conclusao      INTEGER  -- ano de conclusão informado (pode ser NULL)
  periodo_atual      TEXT     -- último período em que o aluno tem registro
  semestre_atual     INTEGER  -- semestre cursado no período atual
  situacao_atual     TEXT     -- 'ATIVO' | 'EVADIDO' | 'RETIDO' | 'FORMADO' (situação mais recente)
  evadiu             INTEGER  -- 1 se o aluno teve algum período EVADIDO
  periodo_evasao     TEXT     -- primeiro período EVADIDO
  semestre_evasao    INTEGER  -- semestre cursado na evasão
  tipo_evasao        TEXT     -- tipo de saída (ex.: 'EXCLUÍDO', 'DESVINCULADO')
  formou             INTEGER  -- 1 se o aluno se formou
  periodo_formacao   TEXT     -- último período cursado ANTES da formação (usado só para "em que semestre
                              --   os alunos se formam"); NÃO é o período em que o aluno consta como FORMADO
  semestre_formacao  INTEGER  -- semestre cursado nesse período de referência

TABLE alunos_periodo  -- uma linha por (aluno, período letivo)
  codigo_estudante  TEXT  -- FK alunos.codigo_estudante
  curso             TEXT
  curso_busca       TEXT
  periodo_letivo    TEXT     -- 'AAAA.S'
  semestre          INTEGER  -- semestre cursado naquele período
  categoria         TEXT     -- 'ATIVO' | 'EVADIDO' | 'RETIDO' | 'FORMADO' naquele período

TABLE matriculas  -- uma linha por matrícula de um aluno em uma disciplina
  id                   INTEGER PRIMARY KEY
  codigo_estudante     TEXT  -- FK alunos.codigo_estudante
  curso                TEXT
  curso_busca          TEXT
  disciplina           TEXT  -- nome da disciplina como gravado (com acentos)
  disciplina_busca     TEXT  -- disciplina em MAIÚSCULAS e SEM acentos, para filtros com LIKE
  periodo_letivo       TEXT  -- 'AAAA.S'
  situacao_disciplina  TEXT  -- situação original no histórico (pode ser NULL)
  aprovado             INTEGER  -- 1 se APROVADO ou DISPENSADO
  reprovado            INTEGER  -- 1 se REPROVADO
  media_final          REAL     -- nota final de 0 a 10 (pode ser NULL)
  total_faltas         REAL     -- total de faltas (pode ser NULL)
  semestre             INTEGER  -- semestre do curso que o aluno cursava ao fazer a disciplina (1 = 1º semestre)
"""

REGRAS_NEGOCIO = """\
- Todos os dados são da Escola Politécnica (único polo).
- Períodos letivos têm o formato 'AAAA.S' (ex.: '2023.1'); a comparação de texto respeita a ordem cronológica.
- Situação do aluno: FORMADO > EVADIDO > RETIDO > ATIVO. RETIDO = aluno ativo que já passou do 13º semestre.
- "Taxa", "proporção", "percentual", "índice" e "porcentagem" significam a mesma coisa (em %).

Cursos:
- Filtre curso com igualdade e o nome EXATO da lista em <valores> (ex.: curso = 'ENGENHARIA COMPUTACÃO').
- Sinônimos: "Computação"/"Engenharia da Computação" = 'ENGENHARIA COMPUTACÃO'; "Elétrica"/"Engenharia
  Elétrica" = 'ENGENHARIA ELETROTÉCNICA'; "Mecânica" = só 'ENGENHARIA MECÂNICA' (a 'ENGENHARIA MECÂNICA
  INDUSTRIAL' só entra se o usuário disser "Industrial"); "Telecom" = 'ENGENHARIA TELECOMUNICAÇÕES';
  "Automação"/"Controle e Automação" = 'ENGENHARIA CONTROLE E AUTOMAÇÃO'.

Situação dos alunos (igual aos cards do dashboard):
- SEM período informado (histórico todo, "hoje", "por curso"): use alunos.situacao_atual. Ex.: taxa de evasão
  de um grupo = SUM(situacao_atual = 'EVADIDO') ÷ COUNT(*) do grupo; o mesmo para RETIDO, FORMADO e ATIVO.
- Não use alunos.evadiu nem alunos.formou para taxas nem para totais: evadiu = 1 inclui alunos que evadiram e
  depois voltaram (reintegração) e alguns até se formaram.
- Nunca calcule taxas em alunos_periodo sem filtrar UM periodo_letivo ou agrupar por periodo_letivo: cada
  aluno aparece em vários períodos. Comparar cursos sem período = tabela alunos com situacao_atual.
- COM período informado: use alunos_periodo, que tem uma linha por aluno em cada período. Taxa de evasão
  (ou retenção, atividade, formação) EM UM PERÍODO = SUM(categoria = 'EVADIDO') ÷ COUNT(*) naquele periodo_letivo.
- Intervalo de períodos ("de 2018.1 a 2024.2", "por período"): uma linha por periodo_letivo (GROUP BY
  periodo_letivo), com BETWEEN no intervalo pedido.
- Numa taxa, o denominador é sempre o grupo inteiro: nunca filtre (WHERE) pela mesma condição do
  numerador, senão a taxa dá 100%. Conte o numerador com SUM(condição).
- Séries históricas e evolução por período (ativos, evadidos, retidos, formados/concluintes), iguais ao
  gráfico "Séries Históricas": conte alunos_periodo por categoria em cada periodo_letivo com
  SUM(categoria = 'FORMADO') etc. Formados por ano = o mesmo, agrupado por SUBSTR(periodo_letivo, 1, 4).
- Tendência ("aumentou?", "diminuiu?", "antes e depois de 2020"): compare a MÉDIA por período (e a taxa), não o
  total, porque as fases têm quantidades diferentes de períodos. Use CASE WHEN periodo_letivo < 'AAAA.1'.
- Eventos de evasão (quando e como o aluno saiu): alunos.semestre_evasao ("em que semestre evadem",
  "evadiram nos N primeiros semestres" = semestre_evasao <= N) e alunos.tipo_evasao ("tipo de saída",
  "forma de saída"), sempre com evadiu = 1. "Em quantos semestres se formam" / "tempo médio até a
  formatura" = AVG(alunos.semestre_formacao) com formou = 1 (não subtraia outras colunas).
- Ingressantes por período = alunos agrupados por periodo_admissao.

Disciplinas:
- Taxa de aprovação = SUM(aprovado) ÷ (SUM(aprovado) + SUM(reprovado)) — o denominador NÃO é COUNT(*), que
  inclui cancelamentos e outras situações; taxa de reprovação =
  SUM(reprovado) ÷ (SUM(aprovado) + SUM(reprovado)). Em rankings de TAXA, exija HAVING avaliados >= 30.
- Rankings de média de nota ou de faltas (iguais aos do dashboard): sem mínimo de alunos, só com
  HAVING COUNT(media_final) > 0 (ou COUNT(total_faltas) > 0).
- Disciplina específica: filtre com igualdade no nome completo (disciplina_busca = 'FISICA 1'). Com LIKE '%...%'
  entram disciplinas parecidas (ex.: 'TOPICOS ESPECIAIS DE FISICA 1'). "Cálculo 1" =
  'CALCULO DIFERENCIAL E INTEGRAL 1'; "Cálculo 2" = 'CALCULO DIFERENCIAL E INTEGRAL 2'.
- "Primeiro ano", "primeiros semestres", "início do curso" = matriculas.semestre <= 2 ("primeiro período" ou
  "primeiro semestre" = semestre = 1). É o semestre do curso, NÃO um período letivo como 2023.1.
- Médias de nota e de faltas consideram só valores não nulos (AVG já ignora NULL).

Conversa:
- Só reaproveite filtros (curso, período) de perguntas anteriores quando a pergunta atual for um
  acompanhamento ("e em 2023.2?", "e para Civil?", "mostre só os três primeiros"). Nesse caso, repita a
  consulta anterior mudando apenas o que foi pedido. Uma pergunta nova não herda filtros.
"""


@lru_cache(maxsize=4)
def _valores_do_banco(path: Path, mtime: float) -> str:  # mtime invalida o cache quando o banco é regerado
    con = connect_readonly(path)
    try:
        cursos = [r[0] for r in con.execute("SELECT DISTINCT curso FROM alunos ORDER BY curso")]
        (p_min, p_max) = con.execute(
            "SELECT MIN(periodo_letivo), MAX(periodo_letivo) FROM alunos_periodo"
        ).fetchone()
        situacoes = [
            r[0]
            for r in con.execute(
                "SELECT DISTINCT situacao_disciplina FROM matriculas"
                " WHERE situacao_disciplina IS NOT NULL ORDER BY 1"
            )
        ]
        tipos_evasao = [
            r[0]
            for r in con.execute(
                "SELECT DISTINCT tipo_evasao FROM alunos WHERE tipo_evasao IS NOT NULL ORDER BY 1"
            )
        ]
    finally:
        con.close()

    return (
        f"- Cursos (alunos.curso): {', '.join(repr(c) for c in cursos)}\n"
        f"- Períodos disponíveis: de '{p_min}' a '{p_max}'\n"
        f"- Valores de matriculas.situacao_disciplina: {', '.join(repr(s) for s in situacoes)}\n"
        f"- Valores de alunos.tipo_evasao: {', '.join(repr(t) for t in tipos_evasao)}\n"
    )


def descricao_banco(path: Path) -> str:
    valores = _valores_do_banco(path, path.stat().st_mtime) if path.exists() else ""
    return (
        f"<schema>\n{SCHEMA_DESCRICAO}</schema>\n\n"
        f"<regras>\n{REGRAS_NEGOCIO}</regras>\n\n"
        f"<valores>\n{valores}</valores>"
    )
