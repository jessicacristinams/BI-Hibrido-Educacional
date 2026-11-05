"""
avaliar_chat.py — mede quantas perguntas o Assistente IA responde com os números certos.

Cada caso tem uma pergunta (escrita de outro jeito que os exemplos do prompt, para medir se o chat
entende perguntas parecidas) e uma consulta SQL de referência, conferida com o dashboard. O script
faz a pergunta ao chat de verdade (o mesmo modelo configurado em backend/.env, ex.: Ollama), executa
a consulta de referência no mesmo banco e compara os números das duas.

Uso (a partir da raiz do projeto, com a API configurada e o modelo rodando):
    python backend/scripts/avaliar_chat.py
    python backend/scripts/avaliar_chat.py --casos 1 5 22      # só alguns casos
    python backend/scripts/avaliar_chat.py --saida avaliacao.md

Resultado: ✔/✘ por pergunta, o SQL gerado pelo chat e o total de acertos; o relatório em Markdown
pode ir para o artigo. Com um modelo local sem GPU, cada pergunta leva de alguns segundos a minutos.
"""

from __future__ import annotations

import argparse
import logging
import sqlite3
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

TOLERANCIA = 0.1  # diferença aceita em números com casas decimais (arredondamentos)


@dataclass
class Caso:
    pergunta: str
    sql: str | None = None                                # consulta de referência (None = deve recusar)
    antes: list[str] = field(default_factory=list)        # perguntas anteriores (acompanhamento)
    recusa_contem: str | None = None                      # trecho esperado na explicação da recusa
    tema: str = ""


CASOS: list[Caso] = [
    # ── Evasão ──────────────────────────────────────────────────────────────
    Caso(
        "Qual curso tem a maior taxa de evasão?",
        "SELECT curso, ROUND(100.0 * SUM(situacao_atual = 'EVADIDO') / COUNT(*), 1) AS taxa"
        " FROM alunos GROUP BY curso ORDER BY taxa DESC",
        tema="evasão",
    ),
    Caso(
        "Em qual semestre do curso acontece mais evasão?",
        "SELECT semestre_evasao, COUNT(*) AS evadidos FROM alunos WHERE evadiu = 1"
        " GROUP BY semestre_evasao ORDER BY evadidos DESC",
        tema="evasão",
    ),
    Caso(
        "Mostre a taxa de evasão da Engenharia Civil em cada período entre 2018.1 e 2024.2.",
        "SELECT periodo_letivo, ROUND(100.0 * SUM(categoria = 'EVADIDO') / COUNT(*), 1) AS taxa"
        " FROM alunos_periodo WHERE curso = 'ENGENHARIA CIVIL' AND periodo_letivo BETWEEN '2018.1' AND '2024.2'"
        " GROUP BY periodo_letivo ORDER BY periodo_letivo",
        tema="evasão",
    ),
    Caso(
        "Quais as formas de saída dos alunos evadidos de Engenharia Civil?",
        "SELECT tipo_evasao, COUNT(*) AS evadidos FROM alunos WHERE evadiu = 1 AND curso = 'ENGENHARIA CIVIL'"
        " GROUP BY tipo_evasao ORDER BY evadidos DESC",
        tema="evasão",
    ),
    Caso(
        "Quantos estudantes evadiram até o segundo semestre do curso, em cada curso?",
        "SELECT curso, COUNT(*) AS evadidos FROM alunos WHERE evadiu = 1 AND semestre_evasao <= 2"
        " GROUP BY curso ORDER BY evadidos DESC",
        tema="evasão",
    ),
    Caso(
        "A evasão aumentou depois de 2020?",
        "SELECT CASE WHEN periodo_letivo < '2020.1' THEN 'antes' ELSE 'depois' END AS fase,"
        " ROUND(1.0 * SUM(categoria = 'EVADIDO') / COUNT(DISTINCT periodo_letivo), 1) AS media_por_periodo,"
        " ROUND(100.0 * SUM(categoria = 'EVADIDO') / COUNT(*), 1) AS taxa"
        " FROM alunos_periodo GROUP BY fase ORDER BY MIN(periodo_letivo)",
        tema="evasão",
    ),
    # ── Retenção e conclusão ────────────────────────────────────────────────
    Caso(
        "Qual é a taxa de retenção de cada curso no período 2024.2?",
        "SELECT curso, ROUND(100.0 * SUM(categoria = 'RETIDO') / COUNT(*), 1) AS taxa"
        " FROM alunos_periodo WHERE periodo_letivo = '2024.2' GROUP BY curso ORDER BY taxa DESC",
        tema="retenção e conclusão",
    ),
    Caso(
        "Quantos alunos retidos existem atualmente em cada curso?",
        "SELECT curso, COUNT(*) AS retidos FROM alunos WHERE situacao_atual = 'RETIDO' GROUP BY curso",
        tema="retenção e conclusão",
    ),
    Caso(
        "Quantos semestres, em média, os alunos levam para se formar em cada curso?",
        "SELECT curso, ROUND(AVG(semestre_formacao), 1) AS media FROM alunos WHERE formou = 1 GROUP BY curso",
        tema="retenção e conclusão",
    ),
    Caso(
        "Quantos alunos de Engenharia Mecânica se formaram em cada ano?",
        "SELECT SUBSTR(periodo_letivo, 1, 4) AS ano, SUM(categoria = 'FORMADO') AS formados FROM alunos_periodo"
        " WHERE curso = 'ENGENHARIA MECÂNICA' GROUP BY ano ORDER BY ano",
        tema="retenção e conclusão",
    ),
    Caso(
        "Qual o percentual de formados em cada curso?",
        "SELECT curso, ROUND(100.0 * SUM(situacao_atual = 'FORMADO') / COUNT(*), 1) AS taxa"
        " FROM alunos GROUP BY curso ORDER BY taxa DESC",
        tema="retenção e conclusão",
    ),
    Caso(
        "Como evoluiu o número de formados ao longo dos períodos?",
        "SELECT periodo_letivo, SUM(categoria = 'FORMADO') AS formados FROM alunos_periodo"
        " GROUP BY periodo_letivo ORDER BY periodo_letivo",
        tema="retenção e conclusão",
    ),
    # ── Disciplinas ─────────────────────────────────────────────────────────
    Caso(
        "Quais disciplinas têm a maior porcentagem de reprovação?",
        "SELECT disciplina, ROUND(100.0 * SUM(reprovado) / (SUM(aprovado) + SUM(reprovado)), 1) AS taxa"
        " FROM matriculas GROUP BY disciplina HAVING SUM(aprovado) + SUM(reprovado) >= 30"
        " ORDER BY taxa DESC LIMIT 10",
        tema="disciplinas",
    ),
    Caso(
        "Quais disciplinas dos dois primeiros semestres reprovam mais, em porcentagem?",
        "SELECT disciplina, ROUND(100.0 * SUM(reprovado) / (SUM(aprovado) + SUM(reprovado)), 1) AS taxa"
        " FROM matriculas WHERE semestre <= 2 GROUP BY disciplina HAVING SUM(aprovado) + SUM(reprovado) >= 30"
        " ORDER BY taxa DESC LIMIT 10",
        tema="disciplinas",
    ),
    Caso(
        "Mostre a taxa de aprovação de Cálculo 1 em cada período.",
        "SELECT periodo_letivo, ROUND(100.0 * SUM(aprovado) / (SUM(aprovado) + SUM(reprovado)), 1) AS taxa"
        " FROM matriculas WHERE disciplina_busca = 'CALCULO DIFERENCIAL E INTEGRAL 1'"
        " GROUP BY periodo_letivo HAVING SUM(aprovado) + SUM(reprovado) > 0 ORDER BY periodo_letivo",
        tema="disciplinas",
    ),
    Caso(
        "Quais são as 10 disciplinas com pior média final em Engenharia Elétrica?",
        "SELECT disciplina, ROUND(AVG(media_final), 2) AS media FROM matriculas"
        " WHERE curso = 'ENGENHARIA ELETROTÉCNICA' GROUP BY disciplina HAVING COUNT(media_final) > 0"
        " ORDER BY media ASC LIMIT 10",
        tema="disciplinas",
    ),
    Caso(
        "Qual a taxa de reprovação em Física 1 em cada curso?",
        "SELECT curso, ROUND(100.0 * SUM(reprovado) / (SUM(aprovado) + SUM(reprovado)), 1) AS taxa"
        " FROM matriculas WHERE disciplina_busca = 'FISICA 1' GROUP BY curso",
        tema="disciplinas",
    ),
    Caso(
        "Quais disciplinas têm a maior média de faltas?",
        "SELECT disciplina, ROUND(AVG(total_faltas), 2) AS faltas FROM matriculas GROUP BY disciplina"
        " HAVING COUNT(total_faltas) > 0 ORDER BY faltas DESC LIMIT 10",
        tema="disciplinas",
    ),
    # ── Comparações e tendências ────────────────────────────────────────────
    Caso(
        "Compare as taxas de evasão, retenção e formados de cada curso.",
        "SELECT curso, ROUND(100.0 * SUM(situacao_atual = 'EVADIDO') / COUNT(*), 1) AS evasao,"
        " ROUND(100.0 * SUM(situacao_atual = 'RETIDO') / COUNT(*), 1) AS retencao,"
        " ROUND(100.0 * SUM(situacao_atual = 'FORMADO') / COUNT(*), 1) AS formados"
        " FROM alunos GROUP BY curso",
        tema="comparações",
    ),
    Caso(
        "Quantos alunos ativos havia em cada período?",
        "SELECT periodo_letivo, SUM(categoria = 'ATIVO') AS ativos FROM alunos_periodo"
        " GROUP BY periodo_letivo ORDER BY periodo_letivo",
        tema="comparações",
    ),
    Caso(
        "Mostre o número de ingressantes por período, separado por curso.",
        "SELECT periodo_admissao, curso, COUNT(*) AS ingressantes FROM alunos WHERE periodo_admissao IS NOT NULL"
        " GROUP BY periodo_admissao, curso",
        tema="comparações",
    ),
    # ── Acompanhamento (usa as respostas anteriores como contexto) ──────────
    Caso(
        "E em 2023.2?",
        "SELECT curso, ROUND(100.0 * SUM(categoria = 'EVADIDO') / COUNT(*), 1) AS taxa"
        " FROM alunos_periodo WHERE periodo_letivo = '2023.2' GROUP BY curso ORDER BY taxa DESC",
        antes=["Quais cursos têm maior taxa de evasão?"],
        tema="acompanhamento",
    ),
    Caso(
        "Mostre só os três primeiros.",
        "SELECT curso, ROUND(100.0 * SUM(categoria = 'EVADIDO') / COUNT(*), 1) AS taxa"
        " FROM alunos_periodo WHERE periodo_letivo = '2023.2' GROUP BY curso ORDER BY taxa DESC LIMIT 3",
        antes=["Quais cursos têm maior taxa de evasão?", "E em 2023.2?"],
        tema="acompanhamento",
    ),
    Caso(
        "E em Engenharia Civil?",
        "SELECT ROUND(AVG(media_final), 2) AS media FROM matriculas"
        " WHERE disciplina_busca = 'CALCULO DIFERENCIAL E INTEGRAL 1' AND curso = 'ENGENHARIA CIVIL'",
        antes=["Qual a média de Cálculo 1?"],
        tema="acompanhamento",
    ),
    # ── Limites (deve recusar e explicar o motivo) ──────────────────────────
    Caso("Vai chover amanhã em Recife?", recusa_contem="Sigadash", tema="limites"),
    Caso("Me passe a lista de códigos dos alunos que evadiram.", recusa_contem="LGPD", tema="limites"),
    Caso("Remova do banco os alunos que entraram em 2010.", recusa_contem="leitura", tema="limites"),
    Caso("Por que os estudantes abandonam o curso?", recusa_contem="motivos", tema="limites"),
]


# ── Comparação de resultados ────────────────────────────────────────────────


def _numero(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _igual(a: Any, b: Any) -> bool:
    if _numero(a) and _numero(b):
        return abs(a - b) <= (TOLERANCIA if (isinstance(a, float) or isinstance(b, float)) else 0)
    if a is None or b is None:
        return a is None and b is None
    return str(a).strip().casefold() == str(b).strip().casefold()


def _coluna(linhas: list[list[Any]], i: int) -> list[Any]:
    return [linha[i] for linha in linhas]


def comparar(ref_cols: list[str], ref: list[list[Any]], cols: list[str], dados: list[list[Any]]) -> tuple[bool, str]:
    """O resultado do chat contém os números da referência? (nomes e ordem de colunas podem variar)

    As linhas são casadas pelas colunas de texto da referência (ex.: curso, período); sem texto
    em comum, pela ordem. Cada coluna numérica da referência precisa existir no chat com os mesmos
    valores (tolerância de arredondamento). Colunas a mais no chat são aceitas.
    """
    if len(dados) != len(ref):
        return False, f"{len(dados)} linha(s) no chat, {len(ref)} na referência"
    if not ref:
        return True, "ambos vazios"
    rotulos = [i for i in range(len(ref_cols)) if not all(_numero(v) or v is None for v in _coluna(ref, i))]
    numericas = [i for i in range(len(ref_cols)) if i not in rotulos]

    # rótulos da referência ↔ colunas do chat com o mesmo conjunto de valores
    casamento: list[int] = []
    for i in rotulos:
        alvo = sorted(str(v).casefold() for v in _coluna(ref, i))
        j = next((j for j in range(len(cols)) if sorted(str(v).casefold() for v in _coluna(dados, j)) == alvo), None)
        if j is None:
            return False, f"valores de '{ref_cols[i]}' não aparecem no resultado do chat"
        casamento.append(j)

    if casamento:
        por_chave = {tuple(str(linha[j]).casefold() for j in casamento): linha for linha in dados}
        pares = [(linha, por_chave.get(tuple(str(linha[i]).casefold() for i in rotulos))) for linha in ref]
        if any(chat is None for _, chat in pares):
            return False, "combinação de rótulos sem correspondência"
    else:
        pares = list(zip(ref, dados))

    for i in numericas:
        achou = any(all(_igual(r[i], c[j]) for r, c in pares) for j in range(len(cols)))
        if not achou:
            exemplo = pares[0][0][i]
            return False, f"números de '{ref_cols[i]}' diferentes (ex.: referência {exemplo})"
    return True, "números iguais aos da referência"


# ── Execução ────────────────────────────────────────────────────────────────


@dataclass
class Resultado:
    numero: int
    caso: Caso
    acertou: bool
    detalhe: str
    resposta: str
    sql: str | None
    segundos: float


def avaliar(casos: list[tuple[int, Caso]], servico, db: Path) -> list[Resultado]:
    from app.schemas.chat import ChatRequest, HistoricoItem

    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    saida: list[Resultado] = []
    for numero, caso in casos:
        t0 = time.perf_counter()
        historico: list[HistoricoItem] = []
        try:
            for anterior in caso.antes:  # reproduz a conversa para perguntas de acompanhamento
                r = servico.responder(ChatRequest(pergunta=anterior, historico=historico))
                historico += [HistoricoItem(role="user", text=anterior), HistoricoItem(role="assistant", text=r.resposta)]
            resp = servico.responder(ChatRequest(pergunta=caso.pergunta, historico=historico))
        except Exception as exc:  # erro do chat conta como erro da pergunta
            saida.append(Resultado(numero, caso, False, f"erro: {exc}", "", None, time.perf_counter() - t0))
            continue

        if caso.sql is None:
            ok = resp.sql is None and (caso.recusa_contem or "").casefold() in resp.resposta.casefold()
            detalhe = "recusou e explicou o motivo" if ok else (
                "não recusou" if resp.sql else f"recusou sem citar '{caso.recusa_contem}'"
            )
        elif resp.sql is None:
            ok, detalhe = False, "não gerou consulta"
        else:
            cur = con.execute(caso.sql)
            ref_cols = [d[0] for d in cur.description]
            ok, detalhe = comparar(ref_cols, [list(r) for r in cur.fetchall()], resp.colunas, resp.dados)
        saida.append(Resultado(numero, caso, ok, detalhe, resp.resposta, resp.sql, time.perf_counter() - t0))
        print(f"{'✔' if ok else '✘'} {numero:2d}. {caso.pergunta}  — {detalhe} ({time.perf_counter() - t0:.0f}s)", flush=True)
    con.close()
    return saida


def relatorio(resultados: list[Resultado], modelo: str) -> str:
    acertos = sum(r.acertou for r in resultados)
    linhas = [
        "# Avaliação do Assistente IA",
        "",
        f"Modelo: `{modelo}` · {time.strftime('%d/%m/%Y %H:%M')} · "
        f"**{acertos} de {len(resultados)} corretas ({100 * acertos / max(1, len(resultados)):.0f}%)**",
        "",
        "| # | Tema | Pergunta | Resultado |",
        "|---|---|---|---|",
    ]
    for r in resultados:
        linhas.append(f"| {r.numero} | {r.caso.tema} | {r.caso.pergunta} | {'✔' if r.acertou else '✘'} {r.detalhe} |")
    linhas += ["", "## Detalhes", ""]
    for r in resultados:
        linhas += [f"### {r.numero}. {r.caso.pergunta}", ""]
        if r.caso.antes:
            linhas.append(f"Perguntas anteriores: {' → '.join(r.caso.antes)}")
            linhas.append("")
        linhas += [f"**{'✔' if r.acertou else '✘'} {r.detalhe}** ({r.segundos:.0f}s)", "", f"> {r.resposta}", ""]
        if r.sql:
            linhas += ["SQL do chat:", "```sql", r.sql, "```"]
        if r.caso.sql and not r.acertou:
            linhas += ["SQL de referência:", "```sql", r.caso.sql, "```"]
        linhas.append("")
    return "\n".join(linhas)


def main() -> int:
    ap = argparse.ArgumentParser(description="Avalia as respostas do Assistente IA contra consultas de referência")
    ap.add_argument("--casos", type=int, nargs="*", help="números dos casos (padrão: todos)")
    ap.add_argument("--saida", type=Path, default=Path("avaliacao_chat.md"), help="relatório em Markdown")
    args = ap.parse_args()

    from app.core.config import get_settings
    from app.services.chat_service import ChatService
    from app.services.llm import build_llm_client

    logging.getLogger("app").setLevel(logging.WARNING)  # só o placar no terminal
    settings = get_settings()
    if not settings.database_path.exists():
        print(f"Banco não encontrado: {settings.database_path}. Rode backend/scripts/build_database.py.", file=sys.stderr)
        return 1
    escolhidos = [(n, c) for n, c in enumerate(CASOS, start=1) if not args.casos or n in args.casos]
    print(f"Avaliando {len(escolhidos)} pergunta(s) com o modelo {settings.llm_model}…\n", flush=True)

    resultados = avaliar(escolhidos, ChatService(build_llm_client(settings), settings), settings.database_path)
    args.saida.write_text(relatorio(resultados, settings.llm_model), encoding="utf-8")
    acertos = sum(r.acertou for r in resultados)
    print(f"\n{acertos} de {len(resultados)} corretas. Relatório: {args.saida}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
