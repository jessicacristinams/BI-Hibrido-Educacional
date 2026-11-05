"""Etapa 1 do chat: pergunta em linguagem natural → SQL (SQLite)."""

from __future__ import annotations

import json
from dataclasses import dataclass

from app.core.errors import LLMProviderError
from app.services.llm import LLMClient, LLMMessage

# Pares pergunta → SQL que ensinam o modelo a usar as colunas *_busca e as
# regras de negócio. Todos são executados em tests/test_database.py.
EXEMPLOS: list[tuple[str, str]] = [
    (
        "Qual foi a média da turma em Cálculo Diferencial e Integral 1 no período 2019.2?",
        "SELECT ROUND(AVG(media_final), 2) AS media_turma FROM matriculas"
        " WHERE disciplina_busca = 'CALCULO DIFERENCIAL E INTEGRAL 1' AND periodo_letivo = '2019.2'",
    ),
    (
        "Quais cursos possuem maior taxa de evasão?",
        "SELECT curso, COUNT(*) AS total_alunos, SUM(situacao_atual = 'EVADIDO') AS evadidos,"
        " ROUND(100.0 * SUM(situacao_atual = 'EVADIDO') / COUNT(*), 1) AS taxa_evasao_pct"
        " FROM alunos GROUP BY curso ORDER BY taxa_evasao_pct DESC",
    ),
    (
        "Qual curso tem a maior proporção de formados?",
        "SELECT curso, COUNT(*) AS total_alunos, SUM(situacao_atual = 'FORMADO') AS formados,"
        " ROUND(100.0 * SUM(situacao_atual = 'FORMADO') / COUNT(*), 1) AS taxa_formados_pct"
        " FROM alunos GROUP BY curso ORDER BY taxa_formados_pct DESC",
    ),
    (
        "Compare evasão, retenção e formação entre os cursos.",
        "SELECT curso, COUNT(*) AS total_alunos,"
        " ROUND(100.0 * SUM(situacao_atual = 'EVADIDO') / COUNT(*), 1) AS taxa_evasao_pct,"
        " ROUND(100.0 * SUM(situacao_atual = 'RETIDO') / COUNT(*), 1) AS taxa_retencao_pct,"
        " ROUND(100.0 * SUM(situacao_atual = 'FORMADO') / COUNT(*), 1) AS taxa_formados_pct"
        " FROM alunos GROUP BY curso ORDER BY taxa_evasao_pct DESC",
    ),
    (
        "Qual curso teve maior taxa de evasão no período 2024.1?",
        "SELECT curso, COUNT(*) AS total_alunos, SUM(categoria = 'EVADIDO') AS evadidos,"
        " ROUND(100.0 * SUM(categoria = 'EVADIDO') / COUNT(*), 1) AS taxa_evasao_pct"
        " FROM alunos_periodo WHERE periodo_letivo = '2024.1'"
        " GROUP BY curso ORDER BY taxa_evasao_pct DESC",
    ),
    (
        "Qual a taxa de evasão de Engenharia Elétrica por período, de 2019.1 a 2023.2?",
        "SELECT periodo_letivo, COUNT(*) AS total_alunos, SUM(categoria = 'EVADIDO') AS evadidos,"
        " ROUND(100.0 * SUM(categoria = 'EVADIDO') / COUNT(*), 1) AS taxa_evasao_pct"
        " FROM alunos_periodo WHERE curso = 'ENGENHARIA ELETROTÉCNICA'"
        " AND periodo_letivo BETWEEN '2019.1' AND '2023.2' GROUP BY periodo_letivo ORDER BY periodo_letivo",
    ),
    (
        "Qual a taxa de retenção de Engenharia Civil em 2023.2?",
        "SELECT COUNT(*) AS total_alunos, SUM(categoria = 'RETIDO') AS retidos,"
        " ROUND(100.0 * SUM(categoria = 'RETIDO') / COUNT(*), 1) AS taxa_retencao_pct"
        " FROM alunos_periodo WHERE curso = 'ENGENHARIA CIVIL' AND periodo_letivo = '2023.2'",
    ),
    (
        "A evasão diminuiu depois de 2018?",
        "SELECT CASE WHEN periodo_letivo < '2018.1' THEN 'antes de 2018' ELSE 'a partir de 2018' END AS fase,"
        " COUNT(DISTINCT periodo_letivo) AS periodos, SUM(categoria = 'EVADIDO') AS evadidos,"
        " ROUND(1.0 * SUM(categoria = 'EVADIDO') / COUNT(DISTINCT periodo_letivo), 1) AS media_evadidos_por_periodo,"
        " ROUND(100.0 * SUM(categoria = 'EVADIDO') / COUNT(*), 1) AS taxa_evasao_pct"
        " FROM alunos_periodo GROUP BY fase ORDER BY MIN(periodo_letivo)",
    ),
    (
        "Quantos alunos evadiram nos três primeiros semestres, por curso?",
        "SELECT curso, COUNT(*) AS evadidos FROM alunos WHERE evadiu = 1 AND semestre_evasao <= 3"
        " GROUP BY curso ORDER BY evadidos DESC",
    ),
    (
        "Quais os tipos de saída mais comuns entre os evadidos de Engenharia da Computação?",
        "SELECT tipo_evasao, COUNT(*) AS evadidos FROM alunos"
        " WHERE evadiu = 1 AND curso = 'ENGENHARIA COMPUTACÃO'"
        " GROUP BY tipo_evasao ORDER BY evadidos DESC",
    ),
    (
        "Mostre a evolução dos concluintes.",
        "SELECT periodo_letivo, SUM(categoria = 'FORMADO') AS formados FROM alunos_periodo"
        " GROUP BY periodo_letivo ORDER BY periodo_letivo",
    ),
    (
        "Quantos alunos se formaram por ano em Engenharia Civil?",
        "SELECT SUBSTR(periodo_letivo, 1, 4) AS ano, SUM(categoria = 'FORMADO') AS formados FROM alunos_periodo"
        " WHERE curso = 'ENGENHARIA CIVIL' GROUP BY ano ORDER BY ano",
    ),
    (
        "Gráfico de evadidos de Engenharia Civil de 2020.1 a 2023.2",
        "SELECT periodo_letivo, SUM(categoria = 'EVADIDO') AS evadidos FROM alunos_periodo"
        " WHERE curso = 'ENGENHARIA CIVIL' AND periodo_letivo BETWEEN '2020.1' AND '2023.2'"
        " GROUP BY periodo_letivo ORDER BY periodo_letivo",
    ),
    (
        "Quantos alunos ativos tinha Engenharia Civil em 2022.2?",
        "SELECT COUNT(*) AS alunos_ativos FROM alunos_periodo"
        " WHERE curso = 'ENGENHARIA CIVIL' AND periodo_letivo = '2022.2' AND categoria = 'ATIVO'",
    ),
    (
        "Em média, com quantos semestres os alunos de Engenharia Civil se formam?",
        "SELECT ROUND(AVG(semestre_formacao), 1) AS media_semestres FROM alunos"
        " WHERE formou = 1 AND curso = 'ENGENHARIA CIVIL'",
    ),
    (
        "Quantos alunos estão retidos hoje em cada curso?",
        "SELECT curso, COUNT(*) AS retidos FROM alunos WHERE situacao_atual = 'RETIDO'"
        " GROUP BY curso ORDER BY retidos DESC",
    ),
    (
        "Quantos alunos ingressaram por período em cada curso?",
        "SELECT periodo_admissao, curso, COUNT(*) AS ingressantes FROM alunos"
        " WHERE periodo_admissao IS NOT NULL GROUP BY periodo_admissao, curso ORDER BY periodo_admissao, curso",
    ),
    (
        "Quais disciplinas possuem maior taxa de reprovação?",
        "SELECT disciplina, SUM(aprovado) + SUM(reprovado) AS avaliados,"
        " ROUND(100.0 * SUM(reprovado) / (SUM(aprovado) + SUM(reprovado)), 1) AS taxa_reprovacao_pct"
        " FROM matriculas GROUP BY disciplina HAVING avaliados >= 30"
        " ORDER BY taxa_reprovacao_pct DESC LIMIT 10",
    ),
    (
        "Quais disciplinas do primeiro ano têm maior taxa de reprovação?",
        "SELECT disciplina, SUM(aprovado) + SUM(reprovado) AS avaliados,"
        " ROUND(100.0 * SUM(reprovado) / (SUM(aprovado) + SUM(reprovado)), 1) AS taxa_reprovacao_pct"
        " FROM matriculas WHERE semestre <= 2 GROUP BY disciplina HAVING avaliados >= 30"
        " ORDER BY taxa_reprovacao_pct DESC LIMIT 10",
    ),
    (
        "Como evoluiu a taxa de aprovação de Geometria Analítica?",
        "SELECT periodo_letivo, SUM(aprovado) + SUM(reprovado) AS avaliados,"
        " ROUND(100.0 * SUM(aprovado) / (SUM(aprovado) + SUM(reprovado)), 1) AS taxa_aprovacao_pct"
        " FROM matriculas WHERE disciplina_busca = 'GEOMETRIA ANALITICA'"
        " GROUP BY periodo_letivo HAVING avaliados > 0 ORDER BY periodo_letivo",
    ),
    (
        "Compare a taxa de reprovação de Física 1 entre os cursos.",
        "SELECT curso, SUM(aprovado) + SUM(reprovado) AS avaliados,"
        " ROUND(100.0 * SUM(reprovado) / (SUM(aprovado) + SUM(reprovado)), 1) AS taxa_reprovacao_pct"
        " FROM matriculas WHERE disciplina_busca = 'FISICA 1' GROUP BY curso ORDER BY taxa_reprovacao_pct DESC",
    ),
    (
        "Quais disciplinas têm a menor média final em Engenharia Elétrica?",
        "SELECT disciplina, COUNT(media_final) AS notas, ROUND(AVG(media_final), 2) AS media_final"
        " FROM matriculas WHERE curso = 'ENGENHARIA ELETROTÉCNICA' GROUP BY disciplina HAVING notas > 0"
        " ORDER BY media_final ASC LIMIT 10",
    ),
]

SYSTEM_PROMPT = """\
Você é um especialista em SQL (SQLite) do Sigadash, painel acadêmico da Escola Politécnica.
Converta a pergunta do usuário em UMA consulta SQL de leitura sobre o banco abaixo.

{banco}

Regras para o SQL:
- Use somente as tabelas e colunas descritas. Apenas SELECT (CTEs são permitidas).
- Para filtrar curso ou disciplina por nome, use as colunas *_busca com LIKE e o termo em
  MAIÚSCULAS e SEM acentos (ex.: disciplina_busca LIKE '%CALCULO%'). Mostre ao usuário as colunas
  curso/disciplina originais.
- Dê nomes claros às colunas calculadas (AS media_turma, AS taxa_evasao_pct...).
- Arredonde médias e taxas com ROUND(..., 2) ou ROUND(..., 1); taxas em porcentagem.
- Para rankings ou listas longas, ordene e use LIMIT (padrão 10, a não ser que o usuário peça outro número).
- Em perguntas de "qual teve o maior/menor...", devolva o ranking ordenado (não LIMIT 1), para a resposta
  mostrar a comparação e revelar empates.
- Em taxas, traga também o numerador e o total (ex.: evadidos e total_alunos), para conferência.
- Proteção de dados (LGPD): nunca devolva codigo_estudante nem use SELECT *. Para contar alunos, use
  COUNT(DISTINCT codigo_estudante). Pedidos de dados de alunos individuais são fora do escopo.
- Em rankings de "maior/menor", traga todas as linhas ordenadas (ou LIMIT 10); só limite a N linhas
  quando o usuário pedir ("os três primeiros" = LIMIT 3).

Exemplos:
{exemplos}

Responda APENAS com um JSON no formato:
{{"relevante": true, "sql": "<consulta>"}}
Antes de recusar, confira o schema, as regras e os valores: perguntas sobre cursos, períodos,
situação dos alunos, evasão (inclusive tipo de saída e semestre), formação, ingressantes, disciplinas
(inclusive do primeiro ano), notas e faltas SÃO respondíveis. Se, mesmo assim, a pergunta não puder ser
respondida com esses dados, responda com o TIPO do motivo:
{{"relevante": false, "sql": null, "tipo": "<lgpd | alteracao | causas | fora_do_escopo>"}}
- "lgpd": pede dados de alunos individuais (códigos, nomes, lista de alunos). Ex.: "Liste os códigos dos alunos".
- "alteracao": pede para alterar, apagar ou inserir dados. Ex.: "Apague os alunos de 2010".
- "causas": pergunta o porquê/os motivos, que a base não registra. Ex.: "Por que os alunos evadem?".
- "fora_do_escopo": qualquer outro assunto (clima, notícias, conversa casual). Ex.: "Vai chover amanhã?".
"""


# Textos das recusas: o modelo só classifica o motivo (mais confiável num modelo pequeno do que
# pedir que ele escreva a explicação).
MOTIVOS_RECUSA = {
    "lgpd": "Por proteção de dados (LGPD), não mostro informações de alunos individuais; posso mostrar "
    "totais e taxas por curso, período ou disciplina.",
    "alteracao": "O assistente só consulta os dados (acesso somente leitura); não é possível alterar ou "
    "apagar registros.",
    "causas": "A base não registra os motivos da evasão (renda, perfil, razões pessoais). Posso mostrar "
    "quando os alunos saem (semestre e período) e como saem (tipo de saída).",
    "fora_do_escopo": "Só consigo responder perguntas sobre os dados acadêmicos do Sigadash "
    "(alunos, cursos, disciplinas, notas, evasão e formação).",
}


@dataclass
class GeneratedSQL:
    relevante: bool
    sql: str | None
    motivo: str | None = None


def _formatar_exemplos() -> str:
    return "\n\n".join(f"Pergunta: {p}\nSQL: {s}" for p, s in EXEMPLOS)


def build_system_prompt(descricao_banco: str) -> str:
    return SYSTEM_PROMPT.format(banco=descricao_banco, exemplos=_formatar_exemplos())


def _parse(texto: str) -> GeneratedSQL:
    try:
        data = json.loads(texto)
    except json.JSONDecodeError as exc:
        raise LLMProviderError("O modelo devolveu uma resposta em formato inesperado.") from exc
    if not isinstance(data, dict):
        raise LLMProviderError("O modelo devolveu uma resposta em formato inesperado.")
    sql = data.get("sql")
    return GeneratedSQL(
        relevante=bool(data.get("relevante")) and bool(sql),
        sql=sql if isinstance(sql, str) else None,
        motivo=MOTIVOS_RECUSA.get(str(data.get("tipo", "")).strip().lower())
        or (data.get("motivo") if isinstance(data.get("motivo"), str) else None),
    )


def generate_sql(
    llm: LLMClient,
    descricao_banco: str,
    pergunta: str,
    historico: list[LLMMessage],
    erro_anterior: tuple[str, str] | None = None,
) -> GeneratedSQL:
    """Gera o SQL. `erro_anterior` = (sql, mensagem) da tentativa que falhou, para o modelo corrigir."""
    messages: list[LLMMessage] = [*historico, {"role": "user", "content": pergunta}]
    if erro_anterior:
        sql_falho, erro = erro_anterior
        messages += [
            {"role": "assistant", "content": json.dumps({"relevante": True, "sql": sql_falho}, ensure_ascii=False)},
            {"role": "user", "content": f"Essa consulta falhou com o erro: {erro}\nCorrija e devolva o JSON."},
        ]
    return _parse(llm.complete(build_system_prompt(descricao_banco), messages, json_mode=True))
