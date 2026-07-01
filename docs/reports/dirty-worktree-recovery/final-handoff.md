---
title: "Dirty Worktree Recovery Final Handoff"
date: "2026-07-01"
scope: "DanteDash and Knowledge Hub"
---

# Dirty Worktree Recovery Final Handoff

## Result

Two reviewable commit candidates are ready:

1. DanteDash: `codex/kh-native-chroma-sunset-recovery`.
2. Knowledge Hub: `codex/kh-dantedash-image-query`.

The original dirty worktrees were preserved. No reset, checkout cleanup, backup deletion, ingest, reindex, or runtime database mutation was performed.

## DanteDash PR Boundary

Commit candidate:

- KH-native runtime is the operational path.
- Chroma fallback and Chroma visual rescue are disabled by default in strict Knowledge Hub mode.
- Chat provider clients live in `ChatRuntime`, so KH-native mode does not need to construct the Chroma-backed `KnowledgeBase` for chat.
- Knowledge Hub package search, preview, library, stats, and image-query reads are wired through the backend gateway.
- Cutover score, parity, import retry, and smoke scripts document the no-Chroma posture.

Do not include:

- Electron chrome/sidebar UI changes.
- Chat visual layout changes.
- Graph Focus changes.
- Knowledge Hub cockpit frontend.
- LightRAG ingest and eval artifacts.
- Prompt/voice/model prompt changes.
- Snapshots.
- Local `.env` backups.

Rollback:

- Chroma remains a cold rollback/export surface during the observation window.
- The runtime path can be toggled by environment flags only if an operator explicitly leaves strict KH-native mode.

## Knowledge Hub PR Boundary

Commit candidate:

- Dantedash package search and image-query are scoped to `kb_slugs=["dantedash"]`.
- Dantedash read paths do not create visual vector collections.
- API tests prove dantedash package search does not fall back into another corpus such as `pirata-kb`.

Do not include:

- Dirty main graph-native work.
- External research.
- Local/cloud model cleanup.
- Runtime profile work.
- Generated reports and browser artifacts.

Rollback:

- Reverting the Knowledge Hub branch restores the previous dantedash package search behavior.
- DanteDash should keep strict no-Chroma enabled only when KH package search/image-query remains healthy.

## Remaining Dirty Work

Remaining dirty work is not lost. It is intentionally deferred in the original worktrees and classified in `classification.md`.

Next safe follow-up after both PRs are merged:

1. Observe KH-native DanteDash for two weeks.
2. Decide whether to remove Chroma from the operational runtime entirely.
3. Handle UI, graph, cockpit, and LightRAG tracks as separate PRs.
