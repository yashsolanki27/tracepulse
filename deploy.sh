#!/usr/bin/env bash
# Run this ON the VM, from the repo root, after the code is synced
# (git pull or rsync) and .env is present.
set -euo pipefail
cd "$(dirname "$0")"

COMPOSE="docker compose -f docker-compose.prod.yml"

if [ ! -f .env ]; then
  echo "ERROR: .env not found in $(pwd). Copy it up: scp .env user@vm:~/tracepulse/" >&2
  exit 1
fi

echo "==> Building and starting services..."
$COMPOSE up -d --build

echo "==> Waiting for API to become healthy..."
api_ok=0
for _ in $(seq 1 30); do
  if curl -fsS http://127.0.0.1:8000/docs >/dev/null 2>&1; then api_ok=1; break; fi
  sleep 2
done
if [ "$api_ok" -ne 1 ]; then
  echo "API did not come up in time. Recent logs:" >&2
  $COMPOSE logs --tail=50 api >&2
  exit 1
fi
echo "API OK (127.0.0.1:8000/docs)"

echo "==> Checking frontend via Caddy..."
if curl -fsS http://127.0.0.1/ | grep -qi '<div id="root"'; then
  echo "Frontend OK (port 80)"
else
  echo "WARNING: frontend responded but did not look like the SPA index." >&2
fi

echo "==> Checking API through Caddy proxy..."
curl -fsS http://127.0.0.1/api/openapi.json >/dev/null && echo "Caddy -> api proxy OK"

echo "==> Status:"
$COMPOSE ps
echo "Deploy complete."
