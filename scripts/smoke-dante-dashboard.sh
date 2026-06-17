#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_URL="${DANTE_MULTIMODAL_API_BASE_URL:-http://127.0.0.1:8035}"
FRONTEND_URL="${DANTE_MULTIMODAL_DASHBOARD_URL:-http://127.0.0.1:5173}"
EXPECTED_TOTAL="${DANTE_MULTIMODAL_EXPECTED_TOTAL:-6281}"
EXPECTED_IMAGES="${DANTE_MULTIMODAL_EXPECTED_IMAGES:-2094}"
EXPECTED_TEXTS="${DANTE_MULTIMODAL_EXPECTED_TEXTS:-4187}"
EXPECTED_DECOUPAGE="${DANTE_MULTIMODAL_EXPECTED_DECOUPAGE:-2093}"
DANTE_GRAPH_STRICT_SMOKE="${DANTE_GRAPH_STRICT_SMOKE:-0}"
ENV_FILE="${ROOT_DIR}/backend/.env"
UV_BIN="${UV_BIN:-uv}"

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

note() {
  echo "OK: $*"
}

warn() {
  echo "WARN: $*" >&2
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
[[ "${images}" == "${EXPECTED_IMAGES}" ]] || fail "unexpected image count ${images}, expected ${EXPECTED_IMAGES}"
[[ "${texts}" == "${EXPECTED_TEXTS}" ]] || fail "unexpected text count ${texts}, expected ${EXPECTED_TEXTS}"

graph_health_json="$(curl -fsS --max-time 5 "${BACKEND_URL}/api/graph/health")" || fail "graph health endpoint is unavailable"
graph_exists="$(
  python3 -c 'import json,sys; print(str(json.load(sys.stdin).get("source", {}).get("exists", False)).lower())' \
    <<<"${graph_health_json}"
)"
graph_source="$(
  python3 -c 'import json,sys; print(json.load(sys.stdin).get("source", {}).get("source_name", ""))' \
    <<<"${graph_health_json}"
)"
if [[ "${graph_exists}" == "true" ]]; then
  if [[ "${DANTE_GRAPH_STRICT_SMOKE}" == "1" ]]; then
    graph_search_json="$(curl -fsS --max-time 30 "${BACKEND_URL}/api/graph/search?q=treatment&limit=3")" \
      || fail "strict graph search failed"
    graph_result_count="$(
      python3 -c 'import json,sys; print(len(json.load(sys.stdin).get("results", [])))' \
        <<<"${graph_search_json}"
    )"
    [[ "${graph_result_count}" -gt 0 ]] || fail "strict graph search returned no results"
  fi
else
  if [[ "${DANTE_GRAPH_STRICT_SMOKE}" == "1" ]]; then
    fail "strict graph smoke expected a readable GraphML source"
  fi
  warn "graph source is unavailable; default smoke keeps graph optional"
fi

decoupage_check="$(
  cd "${ROOT_DIR}/backend" && EXPECTED_DECOUPAGE="${EXPECTED_DECOUPAGE}" "${UV_BIN}" run python - <<'PY'
import os
from app.deps import get_kb

expected = int(os.environ["EXPECTED_DECOUPAGE"])
kb = get_kb()
data = kb.collection.get(where={"artifact_type": "visual_decoupage_bundle"}, include=["metadatas"])
ids = data.get("ids") or []
metas = data.get("metadatas") or []
if len(ids) != expected:
    raise SystemExit(f"unexpected decoupage count {len(ids)}, expected {expected}")

sample_id = "dante_visual_decoupage_0d25ee0747336d6011c0e137427b6aca"
sample = kb.collection.get(ids=[sample_id], include=["metadatas"])
if not sample.get("ids"):
    raise SystemExit(f"missing sample decoupage node {sample_id}")
meta = (sample.get("metadatas") or [{}])[0] or {}
linked = "dante_visual_img_0d25ee0747336d6011c0e137427b6aca"
expected_meta = {
    "dataset_id": "dante-visual-reference-assets",
    "artifact_type": "visual_decoupage_bundle",
    "schema": "decoupage_sidecar",
    "dante_image_id": "aftersun-2022-001",
    "linked_image_file_id": linked,
    "preview_image_file_id": linked,
}
for key, expected_value in expected_meta.items():
    if meta.get(key) != expected_value:
        raise SystemExit(f"sample decoupage metadata mismatch {key}: {meta.get(key)!r}")
print(f"decoupage={len(ids)} sample={sample_id}")
PY
)" || fail "decoupage Chroma package check failed"

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
note "graph=${graph_source:-unavailable} source_exists=${graph_exists} strict=${DANTE_GRAPH_STRICT_SMOKE}"
note "${decoupage_check}"
note "frontend=${FRONTEND_URL}"
note "chat_workspace_project=${project_id} smoke_thread=${thread_id}"
note "KB read-only smoke complete"
