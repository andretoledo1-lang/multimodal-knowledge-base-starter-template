---
title: "fix: Dirty worktree commit recovery"
type: "brainstorm"
date: "2026-07-01"
topic: "dirty worktree commit recovery"
---

# fix: Dirty worktree commit recovery

## Summary

Recover the DanteDash and Knowledge Hub worktrees into reviewable commits without losing existing work or mixing unrelated tracks. The winning strategy is not a bulk commit and not a reset. It is a manifest-first recovery that classifies every changed file, extracts scope-specific patches into clean worktrees, validates each track, and only then commits and pushes.

---

## Problem Frame

The KH-native Chroma sunset work is functioning, but the active worktree contains many unrelated changes from UI polish, Graph, LightRAG, Knowledge Hub, reports, snapshots, and prior generated artifacts. A blind `git add .` would ship unrelated or unreviewed code. A destructive cleanup would risk losing other agents' work. The recovery workflow must therefore preserve the current dirty state while producing clean, auditable changesets.

The current inventory shows a broad dirty surface in DanteDash, including backend runtime files, frontend UI files, Electron shell files, docs, snapshots, and many untracked reports. The Knowledge Hub repo is also dirty, with modified runtime modules and untracked backups/reports. This is a coordination problem first and a git problem second.

---

## Multi-Agent Brainstorm

| Lens | Position | Score impact |
|---|---|---|
| Release Manager | Do not commit from the dirty working copy. Build clean review branches from patch bundles and keep the dirty worktree as evidence until every track is accounted for. | High |
| Git Hygiene Specialist | Use path classification plus patch extraction. Avoid stash as the primary mechanism because it hides mixed hunks and becomes opaque across two repos. | High |
| DanteDash Feature Owner | The KH-native sunset is the only urgent ship candidate. UI polish, Graph focus, LightRAG enrichment, reports, and snapshots should not ride in that PR unless proven required. | High |
| Knowledge Hub Integrator | KH changes must be separated into a KH PR, because DanteDash and KH have different repos, branches, tests, and review surfaces. | High |
| QA Lead | Every commit group needs its own focused verification record. Global smoke can supplement but cannot prove that a selected patch bundle is clean. | Medium |
| Scope Adversary | Mixed files are the failure mode: `kb_backends.py`, `knowledge_hub_client.py`, and route files may contain multiple tracks in one file. The recovery must inspect hunks, not only paths. | High |
| Data-Loss Adversary | Backups, generated reports, and snapshots may be valuable evidence even if they should not be committed. The plan must archive or explicitly classify them before cleanup. | High |
| Judge | Approves the manifest-first patch extraction approach at 0.94 confidence, above the requested 0.93 gate, because it minimizes loss risk and review contamination while preserving a path to commit/push. | Pass |

---

## Requirements

**Safety and evidence**

- R1. The recovery must start with a complete manifest of modified, untracked, ignored-relevant, and cross-repo changes before any commit, cleanup, or branch rewrite.
- R2. No user or other-agent change may be reverted, deleted, stashed away as the only copy, or overwritten without an explicit classification and rollback path.
- R3. Protected files such as env backups, provider configuration, runtime logs, and generated reports must be classified as commit, archive, ignore, or defer before cleanup.

**Commit separation**

- R4. DanteDash and Knowledge Hub changes must ship as separate review branches or PRs.
- R5. Within DanteDash, KH-native Chroma sunset changes must be separated from UI polish, Graph, LightRAG ingest, prompt/voice, generated reports, and snapshot changes.
- R6. Files with mixed hunks must be split by hunk intent rather than committed by path alone.

**Validation**

- R7. Each proposed commit group must carry a verification note naming the tests, smoke checks, or read-only evidence that justify the group.
- R8. The KH-native Chroma sunset group must prove that DanteDash reads from Knowledge Hub/Qdrant without Chroma fallback and without `pirata-kb` contamination in generic chat/search.
- R9. The final handoff must state what was committed, what was deferred, and what remains dirty by design.

---

## Key Decisions

- **Manifest-first over direct staging:** The worktree is too mixed for safe direct staging. A manifest gives reviewers and future agents a stable map before any patch extraction.
- **Clean worktrees over primary dirty worktree commits:** A clean target branch reduces the chance that unrelated files enter a commit by accident.
- **Patch extraction over stash-first recovery:** Stash is useful as a backup, but not as the primary workflow because it collapses unrelated changes into a hidden bundle.
- **Separate repos, separate PRs:** DanteDash and Knowledge Hub should not be treated as one atomic commit because they have separate ownership and validation gates.
- **Hunk-level review for mixed files:** Large backend files are likely to contain changes from multiple tracks. Path-level grouping is insufficient.

---

## Candidate Approaches Considered

| Approach | Strength | Weakness | Decision |
|---|---|---|---|
| Bulk commit current worktree | Fastest possible path to a branch | High risk of unrelated UI, Graph, LightRAG, and generated artifacts entering one PR | Rejected |
| Stash everything, reapply selectively | Preserves a snapshot and can help recovery | Opaque, fragile across two repos, poor for hunk-level intent | Rejected as primary |
| Manifest-first patch extraction | Auditable, preserves work, supports clean PRs | Requires more review effort up front | Selected |
| New clean clone and cherry-pick by path | Very clean final branch | Can lose mixed hunk intent unless paired with manifest and patch review | Accepted as implementation tactic |

---

## Scope Boundaries

In scope:

- Classify current DanteDash and Knowledge Hub dirty worktrees.
- Create a commit recovery manifest and grouping rubric.
- Define safe extraction of KH-native Chroma sunset patches into clean branches.
- Define validation gates for each proposed commit group.

Out of scope:

- Deleting old reports, snapshots, backups, or runtime artifacts during planning.
- Rewriting the KH-native feature itself.
- Solving unrelated UI, Graph, LightRAG, or prompt-pack quality issues.
- Pushing or opening PRs before the selected patches are validated in clean worktrees.

---

## Success Criteria

- The KH-native Chroma sunset work can be committed without unrelated UI, Graph, LightRAG, report, or snapshot changes.
- The Knowledge Hub scope fix can be committed in its own repo without unrelated KH runtime work.
- Any remaining dirty files are classified and intentionally deferred.
- A reviewer can understand why each file is included in a commit group.
- Judge confidence stays at or above 0.93 after adversarial review.

---

## Sources / Research

- `git status --short` shows a broad dirty DanteDash worktree with backend, frontend, docs, scripts, snapshots, and untracked generated artifacts.
- `git diff --numstat` shows high-risk large diffs in `backend/app/kb_backends.py`, `backend/app/lightrag_cinema_craft_ingest.py`, `backend/tests/test_kb_gateway.py`, and `backend/app/kb_gateway.py`.
- The Knowledge Hub repo also has modified runtime files and untracked backup/report artifacts, so it needs a separate recovery track.
- Workspace instructions in `AGENTS.md` require preserving user changes, avoiding destructive commands, and verifying live health before claiming completion.

---

## Judge Review

The judge scores the selected approach at 0.94 / 1.00.

| Axis | Score | Rationale |
|---|---:|---|
| Safety | 0.97 | Avoids destructive cleanup and preserves all current work. |
| Reviewability | 0.95 | Produces small, scoped branches instead of one mixed branch. |
| Execution clarity | 0.92 | Requires careful hunk splitting but gives a concrete workflow. |
| Time efficiency | 0.89 | Slower than bulk commit, but avoids costly PR rework. |
| Fit to current evidence | 0.96 | Directly addresses the observed dirty worktree shape. |
