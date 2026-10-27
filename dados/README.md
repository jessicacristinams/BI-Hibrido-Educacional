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

Com os dados fictícios, o dashboard mostra o selo **"Dados sintéticos (demonstração)"**.
Os números não representam a instituição: servem para rodar e avaliar o sistema.

Formato (separador `;`, UTF-8): `codigo_estudante;NM_PROGR_FORM;PERIODO_ADMIS;NU_ANO_CONC;DS_TP_SIT_ACAD;NM_COMPNT_CURR;DS_SIT_HIST;CD_PERD_LETV;NU_MEDIA_FIM;NU_TOT_FALTAS`.
