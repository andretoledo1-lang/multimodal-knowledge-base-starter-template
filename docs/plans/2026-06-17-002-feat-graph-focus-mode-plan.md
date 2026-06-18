---
title: Graph Focus Mode
type: feat
status: active
date: 2026-06-17
---

# Graph Focus Mode

## Summary

Add a first-class focus mode to DanteDash's Black Label Graph View so the operator can temporarily hide the left search/results rail and right inspector rail, giving the visual graph the maximum practical working area. The feature should preserve existing graph search/detail behavior and only change the presentation state of the Graph tab.

---

## Problem Frame

The current Graph tab is useful for node search and inspection, but the three-column layout squeezes the Sigma canvas when the operator wants to visually explore relationships. The screenshot-driven request is specifically to hide the graph search rail and the description/inspector rail on demand, not to replace LightRAG or change graph data behavior.

---

## Assumptions

*This plan was authored in LFG headless mode without synchronous user confirmation. The items below are agent inferences that should remain visible during implementation and review.*

- The requested phrase "nao lightgraph" means this is a DanteDash UI/layout feature, not a LightRAG data/runtime mutation.
- A single graph focus toggle is the safest first slice: it hides both side rails together while preserving selected node/search state in memory.
- Dedicated independent left/right rail toggles can be added later if the operator asks for more granular control.

---

## Requirements

- R1. Add an obvious Graph View control that toggles between normal three-column layout and focused graph layout.
- R2. In focus mode, hide the left search/results rail and right inspector/description rail so the center visual area expands.
- R3. Preserve existing search query, filters, selected node, visual paused/running state, and inspector data when entering/leaving focus mode.
- R4. Trigger the graph renderer to resize/refresh after the layout changes so Sigma uses the expanded canvas area.
- R5. Provide keyboard support for quick graph focus toggling without interfering with typing in inputs/selects/textareas.
- R6. Keep the existing read-only Graph View contract: no ingest, reindex, delete, vault mutation, or graph API contract change.
- R7. Maintain responsive behavior: narrow screens should remain single-column and not strand hidden controls.

---

## Scope Boundaries

- Do not change backend graph APIs, GraphML parsing, caching, or LightRAG runtime files.
- Do not add provider adapters or graph data mutation paths.
- Do not redesign the whole DanteDash shell or global sidebar.
- Do not introduce new routing/navigation infrastructure.
- Do not add independent persistent panel preferences unless implementation shows it is needed for the focus toggle to behave predictably.

---

## Context & Research

### Relevant Code and Patterns

- `frontend/src/components/GraphPanel.tsx` owns the three-column Graph tab layout, side rails, visual controls, selected-node state, and inspector rendering.
- `frontend/src/components/GraphCanvas.tsx` owns the Sigma renderer lifecycle and currently refreshes on selected-node changes, but does not observe container-size changes.
- `frontend/src/index.css` already defines the app's Slack-inspired dark working surface, panel styling, and utility-friendly component conventions.
- `frontend/package.json` exposes `typecheck` and `build`; root `package.json` forwards them through pnpm.
- `docs/runbooks/dante-dashboard-operations.md` defines Graph View as read-only and visual renderer as opt-in.

### Institutional Learnings

- `AGENTS.md` requires preserving the app's dark Slack-inspired working surface, using read-only health/smoke checks, and choosing the smallest relevant verification set before shipping.
- Existing Graph View implementation intentionally lazy-loads the visual renderer and destroys it when paused/unmounted; focus mode should not weaken that lifecycle.

### External References

- No external research is required. This is a local React/Sigma layout change using existing dependencies.

---

## Key Technical Decisions

- Implement one `graphFocus` state in `GraphPanel`: It directly matches the operator's desired "make graph big" action and keeps the first slice simple.
- Use icon-only or compact icon+text controls in the Graph visual header: The Graph tab already uses Lucide icons and dense tool controls.
- Hide rails with `display: none` rather than offscreen positioning: This keeps layout, tab order, and screen-reader exposure aligned with visible UI while preserving rail component state.
- Add a `layoutVersion`/resize signal prop to `GraphCanvas`: Sigma needs an explicit refresh or resize after the parent grid changes.
- Add a keyboard shortcut guarded against form fields: `F` can toggle focus while avoiding accidental toggles during graph search input.

---

## Open Questions

### Resolved During Planning

- Should this change add separate left/right toggles? No for the first slice. A single focus mode solves the reported pain with less UI state.
- Should focus mode mount the visual renderer automatically? No. Existing explicit opt-in visual contract remains unchanged.
- Should focus mode hide the global app sidebar? No. The request targets the Graph tab's search and description side rails.

### Deferred to Implementation

- Exact button copy and icon pairing: choose based on available Lucide icons and existing header density.
- Whether to persist focus mode across tab switches: default to local component state unless implementation evidence shows reload persistence is expected.

---

## Implementation Units

### U1. Graph Panel Focus State And Layout

**Goal:** Add the focus-mode UI state and layout behavior that hides both side rails and expands the graph visual area.

**Requirements:** R1, R2, R3, R7

**Dependencies:** None

**Files:**
- Modify: `frontend/src/components/GraphPanel.tsx`

**Approach:**
- Add `graphFocus` state to `GraphPanel`.
- Add a compact focus toggle in the visual header, near `Show visual` / `Pause visual`.
- Replace the fixed large-screen grid columns with conditional class names:
  - normal: left rail + center + inspector
  - focus: center-only at large sizes
- Hide the left and right aside panels only when focus mode is on, while preserving their React state.
- Preserve all existing query, filter, selected node, visual state, and detail-fetching state.

**Patterns to follow:**
- Existing `visualEnabled` and `visualErrorKey` state in `GraphPanel.tsx`.
- Existing `cn()` class composition.
- Existing dense Lucide button style.

**Test scenarios:**
- Happy path: clicking the focus control hides search/results and inspector rails and expands the center panel.
- Happy path: clicking again restores both rails with the previous selected node and query/filter state still present.
- Edge case: focus mode with visual paused still shows the paused visual state in the expanded center panel.
- Responsive: on narrow screens, toggling focus does not create an unusable empty layout or trap hidden controls.

**Verification:**
- TypeScript compiles.
- Browser snapshot shows the expanded graph surface and the restored normal layout.

### U2. Graph Canvas Resize Signal

**Goal:** Ensure Sigma redraws against the expanded canvas dimensions after focus mode changes.

**Requirements:** R4

**Dependencies:** U1

**Files:**
- Modify: `frontend/src/components/GraphCanvas.tsx`
- Modify: `frontend/src/components/GraphPanel.tsx`

**Approach:**
- Add a lightweight prop such as `layoutVersion` or `layoutMode`.
- In `GraphCanvas`, refresh and resize the renderer after the prop changes.
- Use `requestAnimationFrame` or a short deferred callback so the DOM grid change has landed before resize.

**Patterns to follow:**
- Existing renderer refs and selected-node refresh effect in `GraphCanvas.tsx`.

**Test scenarios:**
- Happy path: when focus toggles while visual is mounted, renderer remains active and updates to the new container dimensions.
- Edge case: toggling focus while visual is paused does not instantiate Sigma.
- Error path: if renderer is unavailable, the existing error boundary behavior remains unchanged.

**Verification:**
- No TypeScript errors.
- Browser visual inspection confirms the canvas is not blank and fills the wider area.

### U3. Keyboard Shortcut And Documentation

**Goal:** Add a quick keyboard path and document the behavior in the operations runbook.

**Requirements:** R5, R6

**Dependencies:** U1

**Files:**
- Modify: `frontend/src/components/GraphPanel.tsx`
- Modify: `docs/runbooks/dante-dashboard-operations.md`

**Approach:**
- Add a `keydown` listener scoped to the mounted Graph panel.
- Toggle focus on `F`/`f` only when the event target is not an input, textarea, select, button, or contenteditable element.
- Document focus mode in the Graph View runbook, keeping the read-only mutation boundary explicit.

**Patterns to follow:**
- Existing runbook section `Graph View`.

**Test scenarios:**
- Happy path: pressing `F` toggles focus mode while graph panel content is active.
- Edge case: pressing `F` while typing in the search input does not toggle focus.
- Integration: runbook states focus mode is visual/layout-only and does not mutate graph data.

**Verification:**
- TypeScript compiles.
- Browser snapshot or manual check verifies shortcut behavior.

---

## System-Wide Impact

- **Interaction graph:** The change affects only Graph tab UI state and `GraphCanvas` resize behavior.
- **Error propagation:** Existing Graph health/read errors and visual error boundary remain unchanged.
- **State lifecycle risks:** Hidden rails must not reset query/filter/selected-node state; renderer must not leak canvases during focus toggles.
- **API surface parity:** No backend or MCP API changes.
- **Integration coverage:** Browser validation is needed because the main risk is actual layout/canvas behavior.
- **Unchanged invariants:** Graph View remains read-only and visual renderer remains opt-in.

---

## Risks & Dependencies

| Risk | Mitigation |
|---|---|
| Sigma canvas does not resize after layout change | Add explicit resize/refresh effect tied to focus layout signal |
| Keyboard shortcut fires while typing search text | Ignore events from form controls and contenteditable targets |
| Focus mode hides the only way to exit on small screens | Keep the focus button in the center header and ensure it remains visible |
| Work mixes with unrelated dirty branch changes | Implement in clean worktree `dantedash-graph-focus` from commit `3875810` |

---

## Verification Plan

- `pnpm --filter frontend typecheck`
- `pnpm --filter frontend build`
- Browser pipeline against the Graph tab:
  - normal layout has search rail, visual area, and inspector
  - focus mode hides both rails
  - visual area remains nonblank after focus toggle
  - restoring layout brings rails back
