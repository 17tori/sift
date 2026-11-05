#!/bin/sh
# Daily pg_dump (custom format) with retention. Runs inside the `backup` service.
set -eu
: "${BACKUP_HOUR_UTC:=3}"
: "${BACKUP_RETENTION_DAYS:=14}"
mkdir -p /backups
echo "backup: daily at ${BACKUP_HOUR_UTC}:00 UTC, keep ${BACKUP_RETENTION_DAYS} days"
while :; do
  now_h=$(date -u +%H | sed 's/^0//'); now_m=$(date -u +%M | sed 's/^0//')
  target=$(( BACKUP_HOUR_UTC * 60 )); cur=$(( ${now_h:-0} * 60 + ${now_m:-0} ))
  wait_min=$(( (target - cur + 1440) % 1440 )); [ "$wait_min" -eq 0 ] && wait_min=1440
  sleep $(( wait_min * 60 ))
  ts=$(date -u +%Y%m%d-%H%M%S)
  file="/backups/sift-${ts}.dump"
  if pg_dump -h postgres -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc -Z 6 -f "${file}.part"; then
    mv "${file}.part" "$file"
    pg_restore --list "$file" > /dev/null && echo "backup: ok $file ($(du -h "$file" | cut -f1))"
  else
    rm -f "${file}.part"; echo "backup: FAILED at $ts" >&2
  fi
  find /backups -name 'sift-*.dump' -mtime +"$BACKUP_RETENTION_DAYS" -delete
done
