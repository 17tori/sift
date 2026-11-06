#!/usr/bin/env bash
# Zero-config update on the server: pull, rebuild, migrate, restart changed services.
#   ./scripts/deploy.sh            # deploy current branch HEAD from origin
#   REF=v1.2.0 ./scripts/deploy.sh # deploy a tag / commit
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ -d .git ]]; then
  git fetch --tags origin
  if [[ -n "${REF:-}" ]]; then git checkout --quiet "$REF"; else git pull --ff-only; fi
  echo "Deploying $(git rev-parse --short HEAD)"
fi

docker compose build
docker compose run --rm migrate
docker compose up -d --remove-orphans
# nginx resolves api/bot addresses once at start: after they are recreated it must restart too,
# otherwise it keeps proxying to the old containers' IPs and the Mini App hangs on the splash.
docker compose up -d --force-recreate --no-deps nginx
docker image prune -f >/dev/null

for _ in $(seq 1 40); do
  [[ "$(docker inspect -f '{{.State.Health.Status}}' "$(docker compose ps -q api)")" == "healthy" ]] && { docker compose ps; echo "Deploy OK"; exit 0; }
  sleep 3
done
echo "API did not become healthy, recent logs:" >&2
docker compose logs --tail 80 api >&2
exit 1
