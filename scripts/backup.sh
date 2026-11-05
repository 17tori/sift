#!/usr/bin/env bash
# On-demand database backup (the `backup` service also makes one daily).
#   ./scripts/backup.sh                -> backups/sift-manual-YYYYmmdd-HHMMSS.dump
# Copy it off the server, e.g.: scp root@host:/opt/sift/backups/<file> .
set -euo pipefail
cd "$(dirname "$0")/.."
ts="$(date -u +%Y%m%d-%H%M%S)"
file="sift-manual-${ts}.dump"
docker compose exec -T backup sh -c \
  "pg_dump -h postgres -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -Fc -Z 6 -f /backups/${file}.part && mv /backups/${file}.part /backups/${file} && pg_restore --list /backups/${file} >/dev/null"
echo "OK: backups/${file} ($(du -h "backups/${file}" | cut -f1))"
