#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_HOST="${DANTE_MULTIMODAL_BACKEND_HOST:-127.0.0.1}"
BACKEND_PORT="${DANTE_MULTIMODAL_BACKEND_PORT:-8035}"
FRONTEND_HOST="${DANTE_MULTIMODAL_FRONTEND_HOST:-127.0.0.1}"
FRONTEND_PORT="${DANTE_MULTIMODAL_FRONTEND_PORT:-5173}"
API_PROXY_TARGET="http://${BACKEND_HOST}:${BACKEND_PORT}"
UV_BIN="${UV_BIN:-/Users/vidigal/.local/bin/uv}"
PNPM_BIN="${PNPM_BIN:-/opt/homebrew/bin/pnpm}"

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/Users/vidigal/.local/bin:${PATH:-}"

cleanup() {
  trap - INT TERM EXIT
  jobs -p | xargs -r kill
}
trap cleanup INT TERM EXIT

echo "Dante multimodal backend:  ${API_PROXY_TARGET}"
echo "Dante multimodal frontend: http://${FRONTEND_HOST}:${FRONTEND_PORT}"

(cd "${ROOT_DIR}/backend" && "${UV_BIN}" run uvicorn app.main:app --host "${BACKEND_HOST}" --port "${BACKEND_PORT}") &
(cd "${ROOT_DIR}" && VITE_API_PROXY_TARGET="${API_PROXY_TARGET}" "${PNPM_BIN}" --filter frontend dev --host "${FRONTEND_HOST}" --port "${FRONTEND_PORT}") &

wait
