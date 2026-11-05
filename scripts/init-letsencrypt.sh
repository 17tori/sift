#!/usr/bin/env bash
# Issues the first Let's Encrypt certificate via the webroot that nginx already serves on :80,
# then reloads nginx into HTTPS mode. Renewals are automatic (certbot service + nginx 6h reload).
#   ./scripts/init-letsencrypt.sh            # production certificate
#   STAGING=1 ./scripts/init-letsencrypt.sh  # test against LE staging (no rate limits)
set -euo pipefail
cd "$(dirname "$0")/.."
getkv() { grep -E "^$1=" .env | head -1 | cut -d= -f2-; }

DOMAIN="$(getkv DOMAIN)"
EMAIL="$(getkv LETSENCRYPT_EMAIL)"
[[ -n "$DOMAIN" && "$DOMAIN" != "sift.example.com" ]] || { echo "DOMAIN is not set in .env" >&2; exit 1; }

docker compose up -d nginx
echo "Checking http://${DOMAIN}/healthz is reachable from the internet..."
if ! curl -fsS --max-time 10 "http://${DOMAIN}/healthz" >/dev/null; then
  echo "http://${DOMAIN}/healthz is not reachable. Point the DNS A-record at this server and open port 80." >&2
  exit 1
fi

email_args=(--register-unsafely-without-email)
[[ -n "$EMAIL" && "$EMAIL" != "admin@example.com" ]] && email_args=(--email "$EMAIL")

staging=()
[[ "${STAGING:-0}" == "1" ]] && staging=(--staging)

docker compose run --rm --entrypoint certbot certbot certonly \
  --webroot -w /var/www/certbot \
  -d "$DOMAIN" \
  "${email_args[@]}" --agree-tos --no-eff-email --non-interactive --keep-until-expiring \
  "${staging[@]}"

# nginx picks the HTTPS template at start when the certificate exists
docker compose restart nginx
sleep 3
curl -fsS --max-time 10 "https://${DOMAIN}/healthz" && echo && echo "HTTPS is live for ${DOMAIN}"
