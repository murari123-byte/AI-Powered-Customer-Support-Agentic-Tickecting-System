# Frontend image in two stages:
# 1. build: Node compiles the React app into plain static files (dist/)
# 2. serve: a small nginx image serves those files. Node isn't in the final image at all.

FROM node:20-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# The API address is baked into the JavaScript at build time (it runs in the visitor's browser).
ARG VITE_API_BASE_URL=http://localhost:8000
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
RUN npm run build

FROM nginx:1.27-alpine
# Files in templates/ get ${VARIABLES} filled in from the environment at start-up (nginx image feature).
COPY nginx.conf /etc/nginx/templates/default.conf.template
ENV API_ORIGIN=http://localhost:8000
# Only replace our own variable, not nginx's ($uri etc.).
ENV NGINX_ENVSUBST_FILTER=API_ORIGIN
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
