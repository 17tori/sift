#!/usr/bin/env bash
# One-time bootstrap of a fresh Ubuntu 24.04 VPS for SIFT.
#   sudo DOMAIN=sift.example.com LETSENCRYPT_EMAIL=you@example.com BOT_TOKEN=123:abc ./scripts/install.sh
# Idempotent: safe to re-run. Installs Docker (official repo), firewall, swap, unattended upgrades,
# generates .env with random secrets (if missing), builds and starts the stack.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
log() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
die() { printf '\033[1;31mERROR:\033[0m %s\n' "$*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || die "run as root (sudo)"
. /etc/os-release
[[ "${ID}" == "ubuntu" ]] || die "Ubuntu required (found ${ID})"
[[ "${VERSION_ID}" == "24.04" ]] || log "warning: tested on Ubuntu 24.04, found ${VERSION_ID}"

# --- base packages -----------------------------------------------------------
log "Installing base packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq ca-certificates curl gnupg ufw unattended-upgrades openssl git >/dev/null

# --- Docker Engine + Compose plugin from the official repository --------------
if ! command -v docker >/dev/null || ! docker compose version >/dev/null 2>&1; then
  log "Installing Docker Engine"
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update -qq
  apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin >/dev/null
  systemctl enable --now docker
fi
docker compose version

# --- swap: 2 GB absorbs image builds and peak spikes ---------------------------
if ! swapon --show | grep -q '/swapfile'; then
  log "Creating 2G swap"
  fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile >/dev/null && swapon /swapfile
  grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi
cat > /etc/sysctl.d/99-sift.conf <<'SYSCTL'
vm.swappiness=10
vm.overcommit_memory=1
net.core.somaxconn=1024
SYSCTL
sysctl --system >/dev/null

# --- firewall: SSH + HTTP(S) only. Postgres/Redis are never published. --------
log "Configuring ufw"
ufw allow OpenSSH >/dev/null
ufw allow 80/tcp >/dev/null
ufw allow 443/tcp >/dev/null
ufw --force enable >/dev/null

# --- automatic security updates -------------------------------------------------
dpkg-reconfigure -f noninteractive unattended-upgrades >/dev/null 2>&1 || true

# --- .env -----------------------------------------------------------------------
setkv() {  # setkv KEY VALUE  -> replace KEY=... line in .env
  local k="$1" v="$2"
  v="${v//\\/\\\\}"; v="${v//&/\\&}"; v="${v//|/\\|}"
  if grep -q "^${k}=" .env; then sed -i "s|^${k}=.*|${k}=${v}|" .env; else echo "${k}=${v}" >> .env; fi
}
getkv() { grep -E "^$1=" .env | head -1 | cut -d= -f2-; }

if [[ ! -f .env ]]; then
  log "Generating .env from .env.example"
  cp .env.example .env
  chmod 600 .env
  setkv SECRET_KEY "$(openssl rand -hex 32)"
  pg_pw="$(openssl rand -hex 24)"
  setkv POSTGRES_PASSWORD "$pg_pw"
  setkv DATABASE_URL "postgresql+asyncpg://$(getkv POSTGRES_USER):${pg_pw}@postgres:5432/$(getkv POSTGRES_DB)"
  setkv BOT_WEBHOOK_SECRET "$(openssl rand -hex 24)"
fi
if [[ -n "${DOMAIN:-}" ]]; then
  setkv DOMAIN "$DOMAIN"
  setkv PUBLIC_BASE_URL "https://${DOMAIN}"
  setkv WEBAPP_URL "https://${DOMAIN}/"
fi
[[ -n "${LETSENCRYPT_EMAIL:-}" ]] && setkv LETSENCRYPT_EMAIL "$LETSENCRYPT_EMAIL"
[[ -n "${BOT_TOKEN:-}" ]] && setkv BOT_TOKEN "$BOT_TOKEN"
[[ -n "${BOT_USERNAME:-}" ]] && setkv BOT_USERNAME "$BOT_USERNAME"
[[ -n "${ADMIN_TELEGRAM_IDS:-}" ]] && setkv ADMIN_TELEGRAM_IDS "$ADMIN_TELEGRAM_IDS"
# Any provider key passed in the environment goes straight into .env
for k in GEMINI_API_KEY GEMINI_MODEL SERPER_API_KEY GOOGLE_VISION_API_KEY ANTHROPIC_API_KEY JINA_API_KEY \
         EBAY_CLIENT_ID EBAY_CLIENT_SECRET ALIEXPRESS_APP_KEY ALIEXPRESS_APP_SECRET ALIEXPRESS_TRACKING_ID \
         TAOBAO_APP_KEY TAOBAO_APP_SECRET TAOBAO_ADZONE_ID; do
  [[ -n "${!k:-}" ]] && setkv "$k" "${!k}"
done

missing=()
for k in DOMAIN BOT_TOKEN BOT_USERNAME SECRET_KEY POSTGRES_PASSWORD; do
  v="$(getkv "$k")"
  [[ -z "$v" || "$v" == "sift.example.com" ]] && missing+=("$k")
done
if (( ${#missing[@]} )); then
  log "Fill in .env before starting: ${missing[*]}"
  log "Then re-run: sudo ./scripts/install.sh"
  exit 0
fi

mkdir -p backups && chmod 700 backups

# --- start ------------------------------------------------------------------------
log "Building and starting the stack (first build takes a few minutes)"
docker compose up -d --build
log "Waiting for the API to become healthy"
for _ in $(seq 1 60); do
  [[ "$(docker inspect -f '{{.State.Health.Status}}' "$(docker compose ps -q api)" 2>/dev/null)" == "healthy" ]] && break
  sleep 3
done
docker compose ps

log "Requesting the TLS certificate"
"$ROOT/scripts/init-letsencrypt.sh" || log "certificate step failed: check DNS A-record for $(getkv DOMAIN) and re-run scripts/init-letsencrypt.sh"

log "Done. Open https://$(getkv DOMAIN)/healthz and send /start to @$(getkv BOT_USERNAME)"
