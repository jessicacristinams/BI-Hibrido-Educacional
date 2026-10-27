# BI Híbrido Educacional — Sigadash.v2

Um Modelo de Business Intelligence Híbrido Educacional para Tomada de Decisão no Ensino Superior.

Dashboard em React + TypeScript (Vite + Recharts) sobre o histórico acadêmico da
Escola Politécnica. Os dados dos alunos **ficam só no servidor**: a API (FastAPI)
filtra e agrega cada recorte e o navegador recebe apenas os números de cada painel.

```
dados/df_tabela_final.csv ─► backend/scripts/build_database.py ─► backend/data/sigadash.db
 (fora do Git; sem ele,         (mineração em python/)                 (SQLite)
  dados fictícios)
                                                                          │
navegador ◄── GET /api/painel/alunos?curso=…&periodos=…  ◄── FastAPI ─────┘
          ◄── GET /api/painel/disciplinas?…                (filtra e agrega no servidor)
```

### Arquitetura (LGPD e escalabilidade)

- os dados dos alunos ficam só no servidor: o CSV fica em `dados/`, fora da pasta
  pública e fora do Git;
- a API devolve só contagens, taxas, médias e rankings do recorte pedido, nunca
  o código de um aluno (há teste automatizado para isso);
- há uma opção, desligada por padrão, para ocultar números de grupos pequenos (veja **Dados e LGPD**);
- o chat também não devolve o código do aluno nem aceita `SELECT *`;
- cada mudança de filtro é um `GET` pequeno, e o volume de dados no servidor pode
  crescer sem pesar no navegador. O Painel de Disciplinas usa uma tabela
  pré-agregada (curso × disciplina × período) e as respostas ficam em cache.

## Como rodar

O dashboard depende do backend. São dois terminais:

```bash
# uma vez
pip install -r backend/requirements.txt
npm install
python backend/scripts/build_database.py      # dados/df_tabela_final.csv (ou dados fictícios) -> backend/data/sigadash.db
cp backend/.env.example backend/.env          # configurar o LLM do chat (OpenAI ou Ollama)

# terminal 1 — API (http://localhost:8000, documentação em /docs)
cd backend && uvicorn app.main:app --reload

# terminal 2 — dashboard (http://localhost:5173)
npm run dev
```

Quem clona o repositório não tem o CSV real (ele não é versionado): o
`build_database.py` gera então uma base de **alunos fictícios** e o dashboard mostra o
selo "Dados sintéticos (demonstração)". Com autorização, coloque o arquivo real em
`dados/df_tabela_final.csv` e rode o script de novo (veja [`dados/README.md`](dados/README.md)).

O Vite encaminha `/api` para a porta 8000. Rode o `build_database.py` de novo sempre
que o CSV mudar (ou `npm run banco`). Detalhes da API em [`backend/README.md`](backend/README.md).

Para **publicar num servidor** (Docker, senha de acesso, compressão e limite de
perguntas ao chat, com OpenAI ou Ollama), veja [`deploy/README.md`](deploy/README.md):

```bash
cp .env.example .env     # senha e modelo
docker compose up -d --build
```

## Painel de Alunos

Filtros: **Polo**, **Período Letivo** (seleção múltipla), **Curso** e **Indicador** (seleção múltipla).

- **Período Letivo (multi-seleção)** — com nenhum período marcado ("Todos os
  Períodos"), cada aluno aparece com a *situação mais recente do seu histórico
  completo*. Com períodos marcados, vale a situação do período **mais recente
  dentre os marcados** (ex.: Aluno X em {2022.1, 2022.2} → ATIVO; em
  {2022.1, 2022.2, 2023.1} → RETIDO).
- **Indicador (multi-seleção)** (Alunos Ativos · Evasão · Retenção · Formados) —
  com nenhum marcado, valem os quatro ("Todos os Indicadores"). Com indicadores
  marcados, aparecem só os pares de KPIs (total + taxa) dessas categorias; a
  série histórica mostra só as linhas delas; os gráficos de evasão aparecem
  quando Evasão está marcada e o de formação quando Formados está marcado. As
  taxas continuam calculadas sobre o total de alunos do recorte.
- Evasão/formação por semestre cursado rolam na horizontal (há semestres até ~27).

## Painel de Disciplinas

Filtros: **Polo**, **Curso**, **Período Letivo** (seleção múltipla) e **Disciplina** 
(seleção múltipla com busca; a lista acompanha o curso escolhido). Nenhuma
disciplina marcada = Todas as Disciplinas; com várias marcadas, KPIs, rankings,
série histórica e tabela consideram só esse conjunto.

Os quatro filtros de cada painel ficam na mesma linha em telas largas e quebram
em 2 ou 1 por linha em telas estreitas. O chat do Assistente IA abre sobreposto
ao dashboard, sem redimensionar o conteúdo. Ele envia a pergunta ao backend, que
gera um SQL, consulta o banco e devolve a resposta em texto, com um gráfico
quando ajuda (escolhido pelo modelo e validado pelo backend), uma prévia da
tabela e o SQL usado.

Rankings (Top 10), em grade fixa de 2 linhas × 3 colunas:

| Mais Aprovados | Mais Reprovados | Melhor Média |
|---|---|---|
| Menos Faltas | Mais Faltas | Pior Média |

Médias de nota e de faltas consideram apenas matrículas com o valor registrado.
Taxas de aprovação/reprovação = aprovados (ou reprovados) ÷ (aprovados + reprovados).

## Dados e LGPD

**Origem.** O sistema foi desenvolvido sobre uma amostra de registros acadêmicos reais da
Escola Politécnica, cedida com autorização da instituição. Cada estudante aparece só por um
`codigo_estudante`, número aleatório sem tabela de correspondência no projeto. Como os
registros (curso, períodos, notas, situação) ainda descrevem pessoas reais, eles são tratados
como **dados pessoais pseudonimizados** (LGPD, art. 13 §4º), e não como dados anonimizados.

**O que o projeto faz para protegê-los:**

| Medida | Onde |
|---|---|
| Os registros ficam só no servidor. O navegador recebe apenas números agregados do recorte pedido. | `backend/app/api/painel.py` |
| Nenhuma resposta da API dos painéis traz o código do aluno. Há teste automatizado para isso. | `backend/tests/test_painel_api.py` |
| O acesso ao dashboard e ao chat exige usuário e senha (só pessoas autorizadas). Por isso, os painéis mostram os **valores reais**, inclusive de grupos pequenos, e batem com as respostas do chat. | `deploy/` |
| **Supressão de grupos pequenos (opcional, desligada por padrão):** com `SUPRESSAO_K` = *k* > 1 (ex.: 5), nenhum número é exibido nos painéis para um grupo com menos de *k* pessoas (recorte inteiro, períodos das séries, barras, linhas da tabela, disciplinas dos rankings). Útil para uma versão aberta ao público. | `backend/app/painel/` |
| O chat não devolve o código do aluno nem aceita `SELECT *`. | `backend/app/services/sql_guard.py` |
| O CSV real não é versionado (`dados/*.csv` no `.gitignore`) e não fica na imagem Docker final. | `.gitignore`, `backend/Dockerfile` |
| Quem clona o repositório roda o sistema com **dados fictícios** gerados por script. | `backend/scripts/gerar_dados_sinteticos.py` |

**Limites conhecidos:**

- Com os valores reais (padrão), um grupo muito pequeno (ex.: 1 aluno numa disciplina e período)
  mostra a nota desse aluno a quem tem acesso. Por isso o sistema deve ficar restrito a pessoas
  autorizadas. Se a supressão for ligada, ela vale só para os painéis: o chat continua
  respondendo com os valores reais.

## Estrutura

```
dados/                     CSV de entrada (fora do Git; veja dados/README.md)
python/                    mineração (pandas): regras de negócio
  common.py                leitura/limpeza do CSV + utilitários de período
  alunos_mining.py         categorias por aluno×período, resumo, evasão, formação
  disciplinas_mining.py    regra de aprovado/reprovado
backend/                   API FastAPI
  scripts/build_database.py  CSV -> SQLite (usa a mineração de python/)
  scripts/gerar_dados_sinteticos.py  base de alunos fictícios (demonstração e testes)
  app/painel/              filtros e agregações dos painéis
  app/api/painel.py        GET /api/painel/...
  app/services/            Assistente IA (pergunta -> SQL -> resposta)
src/types/painel.ts        tipos das respostas da API
src/services/painelApi.ts  cliente dos painéis
src/services/chatApi.ts    cliente do Assistente IA
src/App.tsx                interface
```

Detalhes das regras: veja `CLASSIFICACAO.md`.
