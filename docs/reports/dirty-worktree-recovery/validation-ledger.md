---
title: "Dirty Worktree Recovery Validation Ledger"
date: "2026-07-01"
scope: "DanteDash and Knowledge Hub"
---

# Dirty Worktree Recovery Validation Ledger

## DanteDash Candidate

Branch: `codex/kh-native-chroma-sunset-recovery`.

Included scope:

- KH-native KB runtime and strict no-Chroma mode.
- Chat provider runtime decoupled from Chroma-backed `KnowledgeBase`.
- Knowledge Hub package search, image-query, stats, preview, and item lookup client paths.
- Cutover/parity scoring and import retry hardening.
- Read-only smoke expectations for KH-native runtime.
- Recovery manifest, classification, and plan artifacts.

Explicitly excluded:

- Electron and sidebar UI polish.
- Graph Focus UI and graph gateway work.
- Knowledge Hub cockpit frontend.
- LightRAG ingest/eval reports.
- Prompt/voice/model prompt work.
- Snapshot/deep-memory files.
- Local env backups.

Validation:

| Check | Result |
|---|---:|
| `git diff --cached --check` | pass |
| `uv run --project backend pytest backend/tests/test_kb_gateway.py backend/tests/test_knowledge_hub_client.py backend/tests/test_kh_import_missing.py backend/tests/test_kb_cutover_score.py backend/tests/test_runtime_shell_env.py backend/tests/test_library_get_item.py backend/tests/test_preview_routes.py` | 73 passed |
| `scripts/smoke-dante-dashboard.sh` with a temporary ignored `.env` symlink for the clean worktree | pass |

Live smoke evidence:

- `/api/stats`: total `8099`, image `2231`, text `4187`, video `1681`.
- `/api/kb/status`: mode `knowledge_hub`, `strict_no_chroma=true`, Chroma fallback `false`, image-query search `knowledge_hub`, visual text rescue `disabled`.
- `/api/search/image`: returned 5 KH-native results; first result `dante_visual_img_0d25ee0747336d6011c0e137427b6aca`.
- Decoupage package count: `2093`; sample decoupage item resolved from Knowledge Hub.
- Frontend reached at the configured local Vite URL.
- Chat workspace smoke created a project/thread through the backend route.

Residual risk:

- The clean worktree smoke used the running local backend rather than starting an isolated backend from the clean checkout because provider `.env` is intentionally ignored and protected.
- Some backend files are large because the KH-native package layer is substantial. Focused tests and live smoke cover the intended runtime path.

## Knowledge Hub Candidate

Branch: `codex/kh-dantedash-image-query`.

Included scope:

- Dantedash package image-query endpoint and package search surface.
- Dantedash package search constrained to `kb_slugs=["dantedash"]`.
- Read paths do not create or ensure visual vector collections.
- API tests for text/image scoping and read-only collection behavior.

Explicitly excluded:

- Dirty main graph-native work.
- External research work.
- Runtime profile/local model changes from the dirty main worktree.
- Backup files, browser artifacts, and generated reports.

Validation:

| Check | Result |
|---|---:|
| `git diff --check` | pass |
| `uv run pytest tests/test_api_v1.py tests/test_visual_memory.py` | 18 passed |

Residual risk:

- This candidate builds on an existing clean branch that already contained broader dantedash package image-query work. The recovery patch adds scoped read behavior, local-only guards for package reads, foreign-manifest preservation, and focused tests.
- The original dirty Knowledge Hub main worktree remains mixed and must not be committed directly.

## Deferred Dirty Tracks

Deferred tracks remain in their original dirty worktrees:

- DanteDash UI/desktop polish.
- DanteDash Graph Focus and graph gateway.
- Knowledge Hub cockpit.
- LightRAG ingest/eval/report artifacts.
- Prompt/voice/model prompt work.
- Snapshots and deep memories.
- Env/runtime/browser backups and local artifacts.

No destructive cleanup was performed.
