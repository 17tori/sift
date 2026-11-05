#!/bin/sh
# Renews Let's Encrypt certificates twice a day (no-op until a cert is due).
# nginx re-reads certificates every 6 hours on its own (see infrastructure/nginx/entrypoint.sh).
trap exit TERM
while :; do
  certbot renew --webroot -w /var/www/certbot --quiet
  sleep 12h &
  wait $!
done
