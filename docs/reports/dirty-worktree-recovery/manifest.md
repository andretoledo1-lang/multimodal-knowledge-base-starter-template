---
title: "Dirty Worktree Recovery Manifest"
date: "2026-07-01"
scope: "DanteDash and Knowledge Hub"
---

# Dirty Worktree Recovery Manifest

This manifest records the mixed dirty state before commit recovery. It is intentionally non-destructive: no reset, checkout, cleanup, deletion, ingest, reindex, or runtime mutation happened before this capture.

## Recovery Goal

Extract reviewable commit candidates from mixed worktrees without losing user or other-agent work:

- DanteDash: KH-native runtime and Chroma sunset recovery.
- Knowledge Hub: dantedash package search scoping.
- Everything else: classified, deferred, or protected until a separate track owns it.

## Evidence Files

- `docs/reports/dirty-worktree-recovery/dantedash-status.txt`
- `docs/reports/dirty-worktree-recovery/knowledge-hub-status.txt`
- `docs/reports/dirty-worktree-recovery/classification.md`

## DanteDash Snapshot

Current branch: `codex/non-anthropic-chat-eval`.

Modified tracked files were grouped into backend runtime, tests, docs, scripts, frontend/UI, Electron, snapshots, and workspace metadata. The full path inventory is in `dantedash-status.txt`.

Primary risk: the worktree combines KH-native sunset, UI polish, Graph Focus, Knowledge Hub cockpit, LightRAG ingest/eval, voice prompt, and generated snapshot/report work.

Protected items:

- `backend/.env.bak-20260630-045125-graph-kh`
- snapshot files unless explicitly selected for a snapshot maintenance commit
- generated LightRAG report directories

## Knowledge Hub Snapshot

Current branch: `main`.

Modified tracked files include runtime config/profile/model surfaces, hub service code, MCP/API surfaces, visual embedding code, and tests. The full path inventory is in `knowledge-hub-status.txt`.

Primary risk: the dantedash package-search fix is mixed with graph-native, local-model, profile, browser-smoke, and historical report work.

Protected items:

- `.env.bak-*`
- `.codex-backups/`
- browser smoke artifacts
- runtime backups

## Commit Recovery Policy

1. Build clean worktrees for candidate branches.
2. Apply only classified patches.
3. Validate inside the clean worktree.
4. Commit only after focused tests pass.
5. Leave a ledger of every included, deferred, protected, and still-dirty item.

## Initial Go/No-Go

Go for extraction only after classification has no unclassified tracked files. No-go for direct commit from either dirty source worktree.
