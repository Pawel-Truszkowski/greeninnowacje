#!/usr/bin/env bash
# Deploy to the demo VPS: copy the code, rebuild, restart.
#
# Usage:  SSH_HOST=root@srvXX.mikr.us SSH_PORT=10XXX ./deploy/deploy.sh
#
# The server keeps its own .env (never copied from here — it holds different secrets)
# and its own database volume, so a deployment never touches the data.
set -euo pipefail

SSH_HOST="${SSH_HOST:?ustaw SSH_HOST, np. root@srv99.mikr.us}"
SSH_PORT="${SSH_PORT:-22}"
REMOTE_DIR="${REMOTE_DIR:-/root/projects/greeninnowacje}"
COMPOSE="docker compose -f docker-compose.prod.yml"

echo "==> wysyłam kod na ${SSH_HOST}:${REMOTE_DIR}"
rsync -az --delete \
  -e "ssh -p ${SSH_PORT}" \
  --exclude '.git/' \
  --exclude '.venv/' \
  --exclude '.env' \
  --exclude 'staticfiles/' \
  --exclude '__pycache__/' \
  --exclude '.pytest_cache/' \
  --exclude '.ruff_cache/' \
  --exclude 'poc/' \
  --exclude 'spec/' \
  ./ "${SSH_HOST}:${REMOTE_DIR}/"

echo "==> buduję i restartuję"
ssh -p "${SSH_PORT}" "${SSH_HOST}" "cd ${REMOTE_DIR} && ${COMPOSE} build && ${COMPOSE} up -d && docker image prune -f"

echo "==> stan usług"
ssh -p "${SSH_PORT}" "${SSH_HOST}" "cd ${REMOTE_DIR} && ${COMPOSE} ps"

echo "==> gotowe. Logi:  ssh -p ${SSH_PORT} ${SSH_HOST} 'cd ${REMOTE_DIR} && ${COMPOSE} logs -f app'"
