# syntax=docker/dockerfile:1.7
# Stage 1: build the Telegram Mini App
FROM node:22-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# Stage 2: nginx serving the static build + reverse proxy to the API / bot
FROM nginx:1.27-alpine
RUN rm -f /etc/nginx/conf.d/default.conf && mkdir -p /etc/nginx/templates-src /var/www/certbot
COPY infrastructure/nginx/nginx.conf /etc/nginx/nginx.conf
COPY infrastructure/nginx/proxy_params.inc /etc/nginx/proxy_params.inc
COPY infrastructure/nginx/templates/ /etc/nginx/templates-src/
COPY infrastructure/nginx/entrypoint.sh /entrypoint.sh
COPY --from=web /web/dist /usr/share/nginx/html
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
