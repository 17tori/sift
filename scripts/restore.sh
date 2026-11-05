#!/usr/bin/env bash
# Restores a pg_dump custom-format backup into the running Postgres.
#   ./scripts/restore.sh backups/sift-20261104-030000.dump
# Stops every app service first, so nothing writes during the restore, then starts them again.
set -euo pipefail
cd "$(dirname "$0")/.."
src="${1:?usage: restore.sh <file.dump>}"
[[ -f "$src" ]] || { echo "no such file: $src" >&2; exit 1; }
name="$(basename "$src")"

read -r -p "This REPLACES the current database with ${name}. Type 'restore' to continue: " ok
[[ "$ok" == "restore" ]] || { echo "aborted"; exit 1; }

echo "Taking a safety backup of the current database first"
./scripts/backup.sh

[[ "$(realpath "$src")" == "$(realpath backups)/${name}" ]] || cp "$src" "backups/${name}"

docker compose stop api worker scheduler bot
docker compose exec -T backup sh -c \
  "pg_restore -h postgres -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" --clean --if-exists --no-owner --single-transaction /backups/${name}"
docker compose run --rm migrate
docker compose up -d api worker scheduler bot
echo "Restored ${name}"
