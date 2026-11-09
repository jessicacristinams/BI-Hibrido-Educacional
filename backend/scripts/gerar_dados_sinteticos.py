"""
gerar_dados_sinteticos.py — CSV de alunos FICTÍCIOS no formato de df_tabela_final.csv.

Os dados reais não ficam no repositório (LGPD). Para quem clona o projeto (banca,
desenvolvimento, testes) conseguir rodar o sistema, este script gera uma base inventada:
códigos, trajetórias, notas e faltas são sorteados; nada vem dos registros reais. Os nomes
de cursos e disciplinas são só rótulos de currículo, não dados pessoais.

Também gera uma PREVISÃO FICTÍCIA do próximo semestre no formato do resumo do notebook de
previsão (resumo_projetado_todos_os_cursos.csv). Não há modelo aqui: as quantidades partem dos
alunos fictícios em 2024.2 e são repartidas com proporções sorteadas, só para a demonstração.

Uso (a partir da raiz do projeto):
    python backend/scripts/gerar_dados_sinteticos.py
    python backend/scripts/gerar_dados_sinteticos.py --alunos 3000 --semente 7 --out dados/df_tabela_sintetica.csv
"""

from __future__ import annotations

import argparse
import csv
import random
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = ROOT / "dados" / "df_tabela_sintetica.csv"
DEFAULT_PREVISAO_OUT = ROOT / "dados" / "previsao" / "resumo_projetado_sintetico.csv"

COLUNAS = [
    "codigo_estudante", "NM_PROGR_FORM", "PERIODO_ADMIS", "NU_ANO_CONC", "DS_TP_SIT_ACAD",
    "NM_COMPNT_CURR", "DS_SIT_HIST", "CD_PERD_LETV", "NU_MEDIA_FIM", "NU_TOT_FALTAS",
]

# curso -> peso no sorteio
CURSOS = {
    "ENGENHARIA CIVIL": 20, "ENGENHARIA COMPUTACÃO": 12, "ENGENHARIA ELETROTÉCNICA": 12,
    "ENGENHARIA CONTROLE E AUTOMAÇÃO": 9, "ENGENHARIA MECÂNICA": 9, "ENGENHARIA ELETRÔNICA": 7,
    "ENGENHARIA TELECOMUNICAÇÕES": 7, "ENGENHARIA MECÂNICA INDUSTRIAL": 6, "ENGENHARIA MECATRÔNICA": 3,
    "FISICA DE MATERIAIS": 3,
}

BASICAS = [
    "CÁLCULO DIFERENCIAL E INTEGRAL 1", "GEOMETRIA ANALITICA", "INTRODUÇÃO À PROGRAMAÇÃO",
    "QUÍMICA GERAL", "PORTUGUÊS INSTRUMENTAL", "SOCIOLOGIA E MEIO AMBIENTE",
    "CÁLCULO DIFERENCIAL E INTEGRAL 2", "FÍSICA 1", "ÁLGEBRA LINEAR", "DESENHO TÉCNICO",
    "CÁLCULO DIFERENCIAL E INTEGRAL 3", "FÍSICA 2", "PROBABILIDADE E ESTATÍSTICA", "CÁLCULO NUMERICO",
    "MECÂNICA GERAL", "METODOLOGIA CIENTÍFICA",
]

ESPECIFICAS = {
    "ENGENHARIA CIVIL": ["TOPOGRAFIA", "RESISTÊNCIA DOS MATERIAIS 1", "MECÂNICA DOS SOLOS 1", "HIDRÁULICA",
                         "ESTRUTURAS DE CONCRETO 1", "ADMINISTRACAO DE OBRAS", "ESTRADAS", "SANEAMENTO"],
    "ENGENHARIA COMPUTACÃO": ["ESTRUTURAS DE DADOS", "SISTEMAS DIGITAIS", "BANCO DE DADOS", "REDES DE COMPUTADORES",
                              "SISTEMAS OPERACIONAIS", "ENGENHARIA DE SOFTWARE", "COMPILADORES", "TEORIA DA COMPUTAÇÃO"],
    "ENGENHARIA ELETROTÉCNICA": ["CIRCUITOS ELÉTRICOS 1", "CIRCUITOS ELÉTRICOS 2", "MÁQUINAS ELÉTRICAS",
                                 "ANALISE DE SISTEMA DE POTENCIA 1", "INSTALAÇÕES ELÉTRICAS", "ELETROMAGNETISMO",
                                 "PROTEÇÃO DE SISTEMAS", "ACIONAMENTO DE MAQUINAS ELÉTRICAS"],
    "ENGENHARIA CONTROLE E AUTOMAÇÃO": ["SINAIS E SISTEMAS", "CONTROLE 1", "CONTROLE 2", "AUTOMAÇÃO INDUSTRIAL",
                                        "MODELAGEM E ANALISE DE SISTEMAS", "INSTRUMENTAÇÃO", "ROBÓTICA", "CLP"],
    "ENGENHARIA MECÂNICA": ["TERMODINÂMICA", "MECÂNICA DOS FLUIDOS", "ELEMENTOS DE MÁQUINAS", "PROCESSOS DE FABRICAÇÃO",
                            "TRANSFERÊNCIA DE CALOR", "DESENHO TÉCNICO MECÂNICO 2", "VIBRAÇÕES", "MATERIAIS DE CONSTRUÇÃO MECÂNICA"],
    "ENGENHARIA ELETRÔNICA": ["ELETRÔNICA ANALÓGICA", "ELETRÔNICA DIGITAL", "MICROPROCESSADORES", "SINAIS E SISTEMAS",
                              "ELETRÔNICA DE POTÊNCIA", "CIRCUITOS ELÉTRICOS 1", "PROJETO DE CIRCUITOS", "SISTEMAS EMBARCADOS"],
    "ENGENHARIA TELECOMUNICAÇÕES": ["PRINCÍPIOS DE COMUNICAÇÃO", "ANTENAS", "COMUNICAÇÕES DIGITAIS", "PROPAGAÇÃO",
                                    "REDES DE COMPUTADORES", "MICRO-ONDAS", "TELEFONIA", "PROCESSAMENTO DE SINAIS"],
    "ENGENHARIA MECÂNICA INDUSTRIAL": ["TERMODINÂMICA", "PROCESSOS DE FABRICAÇÃO", "GESTÃO DA PRODUÇÃO", "ERGONOMIA",
                                       "MANUTENÇÃO INDUSTRIAL", "ADMINISTRACAO INDUSTRIAL", "METROLOGIA", "SOLDAGEM"],
    "ENGENHARIA MECATRÔNICA": ["SISTEMAS DIGITAIS", "CONTROLE 1", "ROBÓTICA", "ELEMENTOS DE MÁQUINAS",
                               "MICROPROCESSADORES", "ACIONAMENTOS", "SENSORES", "PROJETO MECATRÔNICO"],
    "FISICA DE MATERIAIS": ["CIÊNCIAS DOS MATERIAIS", "FÍSICA DO ESTADO SÓLIDO", "MECÂNICA QUÂNTICA", "CRISTALOGRAFIA",
                            "CARACTERIZAÇÃO DE MATERIAIS", "COMPUTAÇÃO QUÂNTICA", "POLÍMEROS", "CERÂMICAS"],
}

TIPOS_EVASAO = [("EXCLUÍDO", 45), ("DESVINCULADO", 33), ("DESLIGAMENTO", 20), ("TRANSFERENCIA EXTERNA", 2),
                ("TRANSFERENCIA INTERNA", 1)]


def _periodos() -> list[str]:
    out = []
    for ano in range(2010, 2026):
        for sem in (1, 2):
            out.append(f"{ano}.{sem}")
            if (ano, sem) == (2020, 2):
                out.append("2020.3")  # período especial, como na base real
    return out


def _peso(rng: random.Random, opcoes: list[tuple[str, int]]) -> str:
    return rng.choices([o for o, _ in opcoes], weights=[p for _, p in opcoes])[0]


def gerar(n_alunos: int = 2000, semente: int = 42) -> list[list[str]]:
    rng = random.Random(semente)
    periodos = _periodos()
    regulares = [p for p in periodos if not p.endswith(".3")]
    codigos = rng.sample(range(100000, 999999), n_alunos)
    cursos = list(CURSOS)
    linhas: list[list[str]] = []

    for codigo in codigos:
        curso = rng.choices(cursos, weights=list(CURSOS.values()))[0]
        admissao = rng.choice(regulares[:-1])
        nivel = rng.gauss(6.5, 1.2)  # "habilidade" média do aluno
        destino = rng.choices(["formado", "evadido", "ativo"], weights=[30, 40, 30])[0]
        fim_semestre = {"formado": rng.randint(10, 15), "evadido": rng.randint(1, 9), "ativo": 99}[destino]
        disciplinas = BASICAS + ESPECIFICAS[curso]
        ano_conclusao = ""

        semestre = 0
        for periodo in periodos[periodos.index(admissao):]:
            especial = periodo.endswith(".3")
            if especial and rng.random() > 0.3:
                continue
            if not especial:
                semestre += 1

            def linha(situacao: str, disc: str = "", hist: str = "", media: str = "", faltas: str = "") -> None:
                linhas.append([str(codigo), curso, admissao, ano_conclusao, situacao, disc, hist, periodo, media, faltas])

            if destino == "evadido" and semestre == fim_semestre:
                linha(_peso(rng, TIPOS_EVASAO))
                break
            if destino == "formado" and semestre == fim_semestre:
                ano_conclusao = f"{int(periodo[:4])}.0"
                linha("FORMADO")
                break
            if not especial and rng.random() < 0.03:
                linha("TRANCAMENTO")
                continue

            situacao = _peso(rng, [("MATRICULADO", 96), ("MATRICULA VINCULO", 2), ("INTERCAMBIO", 1), ("REINTEGRAÇÃO", 1)])
            inicio = min(len(disciplinas) - 5, (semestre - 1) * 3)
            ofertadas = disciplinas[max(0, inicio - 2): inicio + 8]
            for disc in rng.sample(ofertadas, rng.randint(1, 2) if especial else min(len(ofertadas), rng.randint(3, 6))):
                sorteio = rng.random()
                if sorteio < 0.03:
                    linha(situacao, disc, "DISPENSADO")
                elif sorteio < 0.04:
                    linha(situacao, disc, "CANCELADO")
                elif sorteio < 0.05 and semestre > 8:
                    linha(situacao, disc, "RENOVAÇÃO DE ESTÁGIO")
                elif sorteio < 0.06:
                    linha(situacao, disc, "REPROVADO", "", f"{rng.randint(16, 40)}.0")  # reprovado por falta, sem nota
                else:
                    nota = min(10.0, max(0.0, rng.gauss(nivel, 2.0)))
                    hist = "APROVADO" if nota >= 5 else "REPROVADO"
                    linha(situacao, disc, hist, f"{round(nota, 2)}", f"{float(min(30, int(rng.expovariate(1 / 3))))}")
    return linhas


# Previsão fictícia: mesmo período-base e período-alvo do notebook de previsão.
PREVISAO_BASE, PREVISAO_ALVO = "2024.2", "2025.1"
PERIODOS_INGRESSO = {"2023.1", "2023.2", "2024.1", "2024.2"}  # média de ingressantes, como no notebook
COLUNAS_PREVISAO = ["NM_PROGR_FORM", "periodo_base", "periodo_alvo", "situacao", "quantidade_projetada", "proporcao_projetada"]
SITUACOES_TERMINAIS = {"FORMADO"} | {t for t, _ in TIPOS_EVASAO}


def gerar_previsao(linhas: list[list[str]], semente: int = 42) -> list[list]:
    """Resumo projetado fictício por curso, a partir das linhas geradas por gerar()."""
    rng = random.Random(semente)
    na_base: dict[str, set[str]] = defaultdict(set)
    admissao: dict[str, tuple[str, str]] = {}
    for codigo, curso, periodo_admis, _, situacao, _, _, periodo, _, _ in linhas:
        admissao[codigo] = (curso, periodo_admis)
        if periodo == PREVISAO_BASE and situacao not in SITUACOES_TERMINAIS:
            na_base[curso].add(codigo)
    ingressos = Counter(curso for curso, adm in admissao.values() if adm in PERIODOS_INGRESSO)

    saida: list[list] = []
    for curso in CURSOS:
        n, ingresso = len(na_base[curso]), ingressos[curso] / len(PERIODOS_INGRESSO)
        if n == 0 and ingresso == 0:
            continue
        pesos = {
            "ALUNOS ATIVOS": rng.uniform(0.62, 0.78),
            "ALUNOS RETIDOS": rng.uniform(0.12, 0.25),
            "EVASÃO": rng.uniform(0.05, 0.10),
            "CONCLUSÃO": rng.uniform(0.01, 0.04),
        }
        soma = sum(pesos.values())
        qtd = {s: round(n * p / soma) for s, p in pesos.items()}
        qtd["ALUNOS ATIVOS"] += round(ingresso)
        total = sum(qtd.values())
        for situacao, q in sorted(qtd.items(), key=lambda sq: -sq[1]):
            saida.append([curso, PREVISAO_BASE, PREVISAO_ALVO, situacao, q, round(q / total, 4) if total else 0.0])
    return saida


def ler_linhas(csv_path: Path) -> list[list[str]]:
    with csv_path.open(encoding="utf-8-sig", newline="") as f:
        leitor = csv.reader(f, delimiter=";")
        next(leitor)
        return list(leitor)


def escrever_previsao(linhas: list[list[str]], out: Path, semente: int = 42) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(COLUNAS_PREVISAO)
        w.writerows(gerar_previsao(linhas, semente))
    print(f"• Previsão fictícia em {out}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Gera um CSV de alunos fictícios no formato de df_tabela_final.csv")
    ap.add_argument("--alunos", type=int, default=2000)
    ap.add_argument("--semente", type=int, default=42)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--previsao-out", type=Path, default=DEFAULT_PREVISAO_OUT)
    args = ap.parse_args()

    linhas = gerar(args.alunos, args.semente)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(COLUNAS)
        w.writerows(linhas)
    print(f"• {len(linhas):,} linhas de {args.alunos:,} alunos fictícios em {args.out}")
    escrever_previsao(linhas, args.previsao_out, args.semente)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
