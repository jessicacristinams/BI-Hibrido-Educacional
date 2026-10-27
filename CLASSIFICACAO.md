**A classificação é feita uma vez, na mineração (Python); os recortes, na API.**
`backend/scripts/build_database.py` roda a mineração de `python/` e grava no SQLite:

- `alunos_periodo` — uma linha por (aluno, período) com a categoria **já classificada**.
  A API nunca reclassifica: filtra pelos períodos marcados e, por aluno, pega a linha
  do período mais recente dentre os selecionados.
- `alunos` — uma linha por aluno com a situação do último período em que ele tem
  registro no CSV inteiro, mais evasão e formação.
- `matriculas` — cada matrícula com aprovado/reprovado resolvidos, média e faltas;
  `painel_disciplinas` agrega isso por curso × disciplina × período.

O navegador só recebe o resultado agregado de cada recorte (`GET /api/painel/...`).

## Definição de "Todos os Períodos"

> **"Todos os Períodos" = situação mais recente disponível do aluno, considerando
> todo o histórico dele** — não é a soma dos períodos.

Com o filtro de período vazio, os KPIs de alunos usam `alunos.situacao_atual`
diretamente. Com períodos marcados, usam a categoria do período mais recente
dentre os marcados (via `alunos_periodo`).

## Regras de negócio (Python)

**Categoria por (aluno, período)** — prioridade `FORMADO > EVADIDO > RETIDO > ATIVO`
sobre as situações `DS_TP_SIT_ACAD` observadas no período:

| Categoria de base | Valores de `DS_TP_SIT_ACAD` |
|---|---|
| FORMADO | FORMADO |
| EVADIDO | EXCLUÍDO, DESVINCULADO, DESLIGAMENTO, TRANSFERENCIA EXTERNA, TRANSFERENCIA INTERNA |
| ATIVO | MATRICULADO, MATRICULA VINCULO, TRANCAMENTO, INTERCAMBIO, REINTEGRAÇÃO, MOBILIDADE ESTUDANTIL, INTEGRALIZADO (e qualquer valor novo, com aviso no log) |

Requerimento :
  pandas>=2.0
  
As listas ficam em constantes no topo de `alunos_mining.py`.

**Semestre cursado** = `2×(ano_período − ano_admissão) + (sem_período − sem_admissão) + 1`.

**Regra dos 13 semestres** — período ATIVO com semestre **bruto** maior que 13
(`LIMITE_SEMESTRES`) vira RETIDO.

**Piso de exibição** — semestre exibido nunca é menor que 1. A regra dos 13 usa o valor bruto.

**Evasão** — primeiro período EVADIDO do aluno: período, semestre e tipo bruto
de saída (texto original do CSV). O gráfico "Evasão pelo Tipo de Saída" conta
esses eventos cujo período está no conjunto selecionado (ou todos, se vazio);
o número exibido pelo `HBarLabel` é exatamente o `valor` devolvido pela API.

**Formação** — período/semestre do último período ATIVO (ou RETIDO) antes do
primeiro FORMADO; se não houver nenhum antes, usa o próprio período do FORMADO.

**Disciplinas** — `APROVADO` e `DISPENSADO` contam como aprovado; `REPROVADO` como
reprovado; as demais situações (CANCELADO, RENOVAÇÃO DE ESTÁGIO, vazio) contam só
como matrícula. Linhas sem disciplina (registros apenas de situação acadêmica)
ficam fora da tabela `matriculas`.

## Frontend

- `MultiSelectDropdown` substitui o dropdown de período nos dois painéis
  (estado `string[]`; vazio = Todos os Períodos).
- **Indicador** no painel de alunos: multiseleção (`indicadoresSelecionados: Categoria[]`;
  vazio = todos). KPIs e gráficos só das categorias marcadas.
- **Disciplina** no painel de disciplinas: multiseleção com busca
  (`disciplinasSelecionadas: string[]`; vazio = todas). A API filtra pelas
  disciplinas marcadas, como faz com os períodos.
- Chat do Assistente IA em `position: fixed` (sobreposto, sem reflow do dashboard).
- Rankings de disciplinas em grade fixa 2×3; `RankingCard` recebe os 10 itens
  prontos da API (sem "Ver todos", sem numeração à esquerda).
- `SemestrePorPeriodoChart`: histograma por semestre com rolagem horizontal.
- `HBarLabel` é passado na prop `label` do `<Bar>` (forma que o Recharts usa
  para desenhar rótulos por barra).
