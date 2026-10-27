# Build a partir da raiz do projeto:
#   docker build -f backend/Dockerfile -t sigadash-backend .
#
# O banco é gerado num estágio separado, a partir de dados/df_tabela_final.csv (ou, se ele não
# existir, de dados fictícios). Só o banco agregado vai para a imagem final: o CSV não fica em
# nenhuma camada dela.
FROM python:3.12-slim AS base
WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

FROM base AS banco
COPY python/ python/
COPY dados/ dados/
COPY backend/ backend/
RUN python backend/scripts/build_database.py

FROM base
COPY backend/ backend/
COPY --from=banco /app/backend/data/sigadash.db backend/data/sigadash.db

WORKDIR /app/backend
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
