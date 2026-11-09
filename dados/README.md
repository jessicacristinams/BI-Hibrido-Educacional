# dados/

Pasta dos dados de entrada do banco. **Nenhum CSV desta pasta vai para o Git**
(`.gitignore`: `dados/*.csv`), porque são registros de estudantes reais (LGPD).

| Arquivo | O que é | Quem usa |
|---|---|---|
| `df_tabela_final.csv` | amostra real, pseudonimizada, autorizada pela instituição. **Não está no repositório.** Quem tem autorização recebe o arquivo por fora e o coloca aqui. | `build_database.py` (padrão) |
| `df_tabela_sintetica.csv` | alunos **fictícios** no mesmo formato, gerados por `backend/scripts/gerar_dados_sinteticos.py`. Também não é versionado: é recriado quando falta. | `build_database.py` quando não há o CSV real, ou com `--sintetico` |

```bash
# a partir da raiz do projeto
python backend/scripts/build_database.py              # usa o CSV real se existir; senão, dados fictícios
python backend/scripts/build_database.py --sintetico  # força os dados fictícios
```

## Previsão do próximo semestre (`dados/previsao/`, também fora do Git)

| Arquivo | O que é | Quando é usado |
|---|---|---|
| `previsao/resumo_projetado_todos_os_cursos.csv` | resultado do notebook de previsão (Random Forest de transição, rodado fora do sistema) sobre os dados reais. **Não está no repositório.** | junto com o CSV real |
| `previsao/resumo_projetado_sintetico.csv` | previsão **fictícia** no mesmo formato, criada por `gerar_dados_sinteticos.py` a partir dos alunos fictícios (sem modelo: proporções sorteadas) | junto com os dados fictícios; recriada quando falta |

O `build_database.py` só carrega o arquivo na tabela `previsao`; o algoritmo não roda no sistema.
O dashboard mostra a linha do curso escolhido ou, com "Todos os cursos", a soma dos cursos (com as
porcentagens recalculadas sobre o total). Para atualizar a previsão real, substitua o arquivo (mesmas
colunas) e gere o banco de novo. Sem ele, a seção de previsão fica vazia.

## Períodos carregados

O banco vai até **2024.2**: os registros de 2025.1 e 2025.2 estão incompletos no CSV e são descartados
pelo `build_database.py` antes da classificação dos alunos (a "situação atual" de cada aluno é a de
2024.2). Painéis e chat usam o mesmo recorte. Para carregar tudo, use `--todos-os-periodos`; para outro
limite, `--ate AAAA.S`. A previsão aparece como o semestre seguinte ao período-base (2025.1).

Com os dados fictícios, o dashboard mostra o selo **"Dados sintéticos (demonstração)"**.
Os números não representam a instituição: servem para rodar e avaliar o sistema.

Formato (separador `;`, UTF-8): `codigo_estudante;NM_PROGR_FORM;PERIODO_ADMIS;NU_ANO_CONC;DS_TP_SIT_ACAD;NM_COMPNT_CURR;DS_SIT_HIST;CD_PERD_LETV;NU_MEDIA_FIM;NU_TOT_FALTAS`.
