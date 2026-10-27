# Frontend publicado: build do Vite servido pelo nginx, que também faz o proxy de /api para o backend,
# pede usuário/senha (HTTP Basic) e limita as perguntas ao chat. Build a partir da raiz do projeto.

FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY index.html vite.config.ts tsconfig.json tsconfig.app.json tsconfig.node.json ./
COPY src/ src/
COPY public/ public/
RUN npm run build

FROM nginx:1.27-alpine
COPY deploy/nginx/default.conf.template /etc/nginx/templates/default.conf.template
COPY --chmod=755 deploy/nginx/40-senha.sh /docker-entrypoint.d/40-senha.sh
COPY --from=build /app/dist /usr/share/nginx/html
