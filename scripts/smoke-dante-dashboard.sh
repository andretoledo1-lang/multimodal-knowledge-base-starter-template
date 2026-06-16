#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_URL="${DANTE_MULTIMODAL_API_BASE_URL:-http://127.0.0.1:8035}"
FRONTEND_URL="${DANTE_MULTIMODAL_DASHBOARD_URL:-http://127.0.0.1:5173}"
EXPECTED_TOTAL="${DANTE_MULTIMODAL_EXPECTED_TOTAL:-4188}"
ENV_FILE="${ROOT_DIR}/backend/.env"

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

note() {
  echo "OK: $*"
}

[[ -f "${ENV_FILE}" ]] || fail "backend/.env is missing"
[[ -d "${ROOT_DIR}/backend" ]] || fail "backend directory is missing"
[[ -d "${ROOT_DIR}/frontend" ]] || fail "frontend directory is missing"
[[ -f "${ROOT_DIR}/backend/app/mcp_server.py" ]] || fail "MCP server module is missing"
[[ -f "${ROOT_DIR}/electron/main.cjs" ]] || fail "Electron wrapper is missing"
[[ -d "${ROOT_DIR}/chroma_db" ]] || fail "runtime chroma_db directory is missing"

grep -q "^KB_COLLECTION=dante_multimodal_kb" "${ENV_FILE}" || fail "KB_COLLECTION is not dante_multimodal_kb"
grep -q "^KB_PERSIST_DIR=${ROOT_DIR}/chroma_db" "${ENV_FILE}" || fail "KB_PERSIST_DIR does not point at this workspace"
grep -q "^KB_UPLOAD_DIR=${ROOT_DIR}/uploads" "${ENV_FILE}" || fail "KB_UPLOAD_DIR does not point at this workspace"

stats_json="$(curl -fsS --max-time 5 "${BACKEND_URL}/api/stats")" || fail "backend stats endpoint is unavailable"
total="$(python3 -c 'import json,sys; print(json.load(sys.stdin).get("total", ""))' <<<"${stats_json}")"
images="$(python3 -c 'import json,sys; print(json.load(sys.stdin).get("by_modality", {}).get("image", ""))' <<<"${stats_json}")"
texts="$(python3 -c 'import json,sys; print(json.load(sys.stdin).get("by_modality", {}).get("text", ""))' <<<"${stats_json}")"

[[ "${total}" == "${EXPECTED_TOTAL}" ]] || fail "unexpected KB total ${total}, expected ${EXPECTED_TOTAL}"
[[ -n "${images}" && -n "${texts}" ]] || fail "stats response is missing image/text modality counts"

curl -fsSI --max-time 5 "${FRONTEND_URL}/" >/dev/null || fail "frontend is unavailable"

workspace_json="$(
  curl -fsS --max-time 5 -X POST "${BACKEND_URL}/api/workspace/bootstrap"
)" || fail "workspace bootstrap endpoint is unavailable"
project_id="$(
  python3 -c 'import json,sys; print(json.load(sys.stdin).get("project", {}).get("id", ""))' \
    <<<"${workspace_json}"
)"
[[ -n "${project_id}" ]] || fail "workspace bootstrap response is missing project id"

smoke_title="Smoke $(date -u +%Y%m%dT%H%M%SZ)"
thread_json="$(
  curl -fsS --max-time 5 \
    -H "Content-Type: application/json" \
    -d "{\"project_id\":\"${project_id}\",\"title\":\"${smoke_title}\",\"top_k\":5}" \
    "${BACKEND_URL}/api/threads"
)" || fail "thread creation endpoint is unavailable"
thread_id="$(
  python3 -c 'import json,sys; print(json.load(sys.stdin).get("id", ""))' \
    <<<"${thread_json}"
)"
[[ -n "${thread_id}" ]] || fail "thread creation response is missing thread id"

detail_id="$(
  curl -fsS --max-time 5 "${BACKEND_URL}/api/threads/${thread_id}" \
    | python3 -c 'import json,sys; print(json.load(sys.stdin).get("id", ""))'
)" || fail "thread detail endpoint is unavailable"
[[ "${detail_id}" == "${thread_id}" ]] || fail "thread detail response returned unexpected id"

archived="$(
  curl -fsS --max-time 5 \
    -X PATCH \
    -H "Content-Type: application/json" \
    -d '{"archived":true}' \
    "${BACKEND_URL}/api/threads/${thread_id}" \
    | python3 -c 'import json,sys; print(str(json.load(sys.stdin).get("archived", False)).lower())'
)" || fail "thread archive endpoint is unavailable"
[[ "${archived}" == "true" ]] || fail "thread archive response did not mark the thread archived"

(cd "${ROOT_DIR}/backend" && python3 -m py_compile app/mcp_server.py) || fail "MCP server module does not compile with system python"

note "workspace=${ROOT_DIR}"
note "backend=${BACKEND_URL} total=${total} image=${images} text=${texts}"
note "frontend=${FRONTEND_URL}"
note "chat_workspace_project=${project_id} smoke_thread=${thread_id}"
note "KB read-only smoke complete"
