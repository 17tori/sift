#!/bin/sh
# Picks HTTP-only or HTTPS config depending on whether the Let's Encrypt cert exists,
# then reloads every 6h so renewed certificates (and a first-issued one) are picked up.
set -eu
: "${DOMAIN:?DOMAIN is required}"
: "${BOT_WEBHOOK_PATH:=/tg/webhook}"
export DOMAIN BOT_WEBHOOK_PATH

render() {
  envsubst '${DOMAIN} ${BOT_WEBHOOK_PATH}' < /etc/nginx/templates-src/common.inc > /etc/nginx/common.conf
  if [ -f "/etc/letsencrypt/live/${DOMAIN}/fullchain.pem" ]; then
    envsubst '${DOMAIN}' < /etc/nginx/templates-src/https.conf.template > /etc/nginx/conf.d/default.conf
  else
    echo "nginx: no certificate for ${DOMAIN} yet, serving HTTP only"
    envsubst '${DOMAIN}' < /etc/nginx/templates-src/http.conf.template > /etc/nginx/conf.d/default.conf
  fi
}

render
(
  while :; do
    sleep 6h
    render
    nginx -t -q && nginx -s reload
  done
) &
exec nginx -g 'daemon off;'
