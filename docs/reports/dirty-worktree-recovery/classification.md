---
title: "Dirty Worktree Classification Matrix"
date: "2026-07-01"
scope: "DanteDash and Knowledge Hub"
---

# Dirty Worktree Classification Matrix

Classification tracks:

- `DD-KH`: DanteDash KH-native Chroma sunset.
- `KH-SCOPE`: Knowledge Hub dantedash package scoping.
- `UI`: DanteDash desktop/sidebar/chat/UI polish.
- `GRAPH`: Graph, LightRAG graph, or graph-gateway work.
- `LIGHTRAG`: LightRAG ingest, eval, craft corpus, or reports.
- `PROMPT`: chat prompt, voice, or model prompt work.
- `COCKPIT`: Knowledge Hub cockpit UI/routes.
- `SNAPSHOT`: snapshot/deep-memory maintenance.
- `EVIDENCE`: generated reports, browser evidence, plans, brainstorms.
- `PROTECTED`: env backups, runtime backups, browser state, local secrets-adjacent files.
- `MIXED`: requires hunk-level extraction before staging.
- `DEFER`: keep dirty for later track.

## DanteDash Tracked Files

| File | Classification | Commit action |
|---|---:|---|
| `.gitignore` | DEFER | Leave out of KH-native commit unless hunk review proves needed. |
| `AGENTS.md` | DEFER | Workspace instruction change, not part of KH-native runtime. |
| `CLAUDE.md` | DEFER | Agent instruction change, not part of KH-native runtime. |
| `README.md` | MIXED | Extract only KH-native runtime documentation if needed. |
| `backend/app/chat_prompts/policies/voice.md` | PROMPT | Defer. |
| `backend/app/deps.py` | MIXED | Extract only KH-native config and strict runtime flags. |
| `backend/app/kb_backends.py` | MIXED | Extract KH-native gateway/search/preview/image-query behavior; exclude unrelated corpus or ingest work unless required by tests. |
| `backend/app/kb_cutover_score.py` | DD-KH | Candidate for full-path extraction. |
| `backend/app/kb_gateway.py` | MIXED | Extract KH-native routing, no-Chroma posture, and result normalization only. |
| `backend/app/kb_parity.py` | DD-KH | Candidate for full-path extraction if referenced by tests/scripts. |
| `backend/app/knowledge_hub_client.py` | MIXED | Extract only shared client changes needed by DD-KH if any; otherwise defer to cockpit track. |
| `backend/app/lightrag_cinema_craft_ingest.py` | LIGHTRAG | Defer. |
| `backend/app/main.py` | MIXED | Extract only route registration required by DD-KH if needed; cockpit/graph route changes defer. |
| `backend/app/routes/graph.py` | GRAPH | Defer. |
| `backend/app/routes/knowledge_hub.py` | COCKPIT | Defer unless a DD-KH status endpoint dependency is proven. |
| `backend/app/routes/library.py` | MIXED | Extract only KH-native preview/library dependency if tests require. |
| `backend/app/routes/preview.py` | MIXED | Extract only KH-native preview routing if tests require. |
| `backend/app/schemas.py` | MIXED | Extract only schemas needed by KH-native gateway/chat/search. |
| `backend/tests/test_chat_prompt_integration.py` | PROMPT | Defer. |
| `backend/tests/test_graph_explorer.py` | GRAPH | Defer. |
| `backend/tests/test_kb_cutover_score.py` | DD-KH | Candidate for full-path extraction. |
| `backend/tests/test_kb_gateway.py` | DD-KH | Candidate for full-path extraction. |
| `backend/tests/test_kh_import_missing.py` | DD-KH | Candidate for full-path extraction. |
| `backend/tests/test_knowledge_hub_client.py` | MIXED | Extract only client tests required by DD-KH if any; otherwise defer to cockpit. |
| `backend/tests/test_lightrag_cinema_craft_ingest.py` | LIGHTRAG | Defer. |
| `backend/tests/test_runtime_shell_env.py` | DD-KH | Candidate for full-path extraction. |
| `docs/reports/knowledge-hub-cutover-certification.md` | DD-KH | Candidate for full-path extraction. |
| `docs/runbooks/dante-dashboard-operations.md` | MIXED | Extract only KH-native runtime operations notes; defer UI/graph/cockpit notes. |
| `electron/main.cjs` | UI | Defer. |
| `frontend/src/App.tsx` | UI/COCKPIT | Defer. |
| `frontend/src/components/ChatPanel.tsx` | UI | Defer. |
| `frontend/src/components/GraphCanvas.tsx` | GRAPH/UI | Defer. |
| `frontend/src/components/GraphPanel.tsx` | GRAPH/UI | Defer. |
| `frontend/src/components/Sidebar.tsx` | UI | Defer. |
| `frontend/src/index.css` | UI | Defer. |
| `frontend/src/lib/api.ts` | UI/COCKPIT | Defer unless DD-KH status typing is required. |
| `frontend/src/lib/utils.ts` | UI | Defer. |
| `index.json` | DEFER | Workspace inventory, leave out unless documentation track owns it. |
| `scripts/dante_kb_runtime_env.sh` | DD-KH | Candidate for full-path extraction. |
| `scripts/dantedash_kh_import_missing.py` | DD-KH | Candidate for full-path extraction. |
| `scripts/dantedash_kh_parity_eval.py` | DD-KH | Candidate for full-path extraction. |
| `scripts/smoke-dante-dashboard.sh` | MIXED | Extract KH-native smoke expectations only. |
| `scripts/start-dante-multimodal-rag.sh` | DD-KH | Candidate for full-path extraction. |
| `snapshots/LATEST.md` | SNAPSHOT | Defer. |
| `snapshots/index.md` | SNAPSHOT | Defer. |

## DanteDash Untracked Categories

| Category | Classification | Commit action |
|---|---:|---|
| `backend/.env.bak-*` | PROTECTED | Do not commit. |
| `backend/app/chat_runtime.py` | DD-KH | Candidate for full-path extraction. |
| `backend/app/graph_gateway.py` | GRAPH | Defer. |
| `backend/tests/test_graph_gateway.py` | GRAPH | Defer. |
| `docs/brainstorms/` | EVIDENCE | Include only dirty-worktree recovery brainstorm if useful to this PR; defer others. |
| `docs/plans/2026-07-01-002-fix-dirty-worktree-commit-recovery-plan.md` | EVIDENCE | Include with recovery docs. |
| Other `docs/plans/*.md` | EVIDENCE | Defer by track. |
| `docs/reports/lightrag-*` | LIGHTRAG/EVIDENCE | Defer. |
| `docs/reports/dirty-worktree-recovery/*` | EVIDENCE | Include with recovery docs. |
| `frontend/src/components/KnowledgeHubPanel.tsx` | COCKPIT | Defer. |
| `frontend/src/hooks/useKnowledgeHub.ts` | COCKPIT | Defer. |
| `scripts/dante_local_media_ingest.py` | LIGHTRAG/EVIDENCE | Defer. |
| `scripts/dante_materialize_media_previews.py` | LIGHTRAG/EVIDENCE | Defer. |
| `scripts/lightrag_cinema_craft_inventory.py` | LIGHTRAG | Defer. |
| `scripts/lightrag_cinema_craft_prepare.py` | LIGHTRAG | Defer. |
| `snapshots/DEEP_MEMORY_DANTEDASH_005.md` through `011.md` | SNAPSHOT | Defer. |

## Knowledge Hub Tracked Files

| File | Classification | Commit action |
|---|---:|---|
| `.gitignore` | DEFER | Leave out unless hunk review proves required. |
| `config/hub_profiles.yaml` | DEFER | Profile/runtime config change, not part of dantedash package scoping. |
| `src/knowledge_hub/config.py` | DEFER | Defer unless scoped search requires a config constant. |
| `src/knowledge_hub/hub_profile.py` | DEFER | Profile work, not scoped package search. |
| `src/knowledge_hub/hub_service.py` | MIXED | Extract only dantedash package scoping behavior. |
| `src/knowledge_hub/local_models.py` | DEFER | Local/cloud model cleanup track. |
| `src/knowledge_hub/main.py` | DEFER | API/runtime work outside scoped package search. |
| `src/knowledge_hub/mcp_server.py` | DEFER | MCP surface work outside scoped package search. |
| `src/knowledge_hub/runtime.py` | DEFER | Runtime work outside scoped package search. |
| `src/knowledge_hub/visual_embeddings.py` | DEFER | Visual embedding track. |
| `tests/test_api_v1.py` | MIXED | Extract only scoped dantedash package-search tests. |
| `tests/test_config.py` | DEFER | Config track. |
| `tests/test_hub_profile.py` | DEFER | Profile track. |
| `tests/test_hub_service.py` | DEFER | Service tests outside scoped package search unless proven needed. |
| `tests/test_mcp_server.py` | DEFER | MCP track. |
| `tests/test_visual_memory.py` | DEFER | Visual memory track. |

## Knowledge Hub Untracked Categories

| Category | Classification | Commit action |
|---|---:|---|
| `.env.bak-*`, `.codex-backups/`, `*.bak-*` | PROTECTED | Do not commit. |
| `.playwright-mcp/`, `ce-browser-*` | EVIDENCE | Defer. |
| `docs/memories/`, `docs/prompts/`, `docs/reports/`, `docs/vendor/` | EVIDENCE | Defer. |
| `src/knowledge_hub/external_research.py` | DEFER | External research track. |
| `src/knowledge_hub/graph_native.py` | GRAPH | Defer. |
| `src/knowledge_hub/multimodal_packages.py` | DEFER | Multimodal package track, not scoped dantedash search unless proven required. |
| `tests/test_external_research.py` | DEFER | External research track. |
| `tests/test_graph_native.py` | GRAPH | Defer. |
| `tests/test_multimodal_packages.py` | DEFER | Multimodal package track. |

## Blocking Rule

Any item marked `MIXED` must be inspected by hunk before it enters a commit candidate. If hunk ownership is unclear, defer it rather than committing the whole file.
