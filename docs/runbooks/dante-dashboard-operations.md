# Dante Multimodal Dashboard Operations

## Purpose

`/Users/vidigal/codex/dantedash` is the primary workspace for the Dante
Multimodal Dashboard. It serves a local multimodal RAG knowledge base through a
FastAPI backend, a Vite frontend, an Electron application, CLI aliases, and a
read-only MCP wrapper.

## Stable Interfaces

- Backend: `http://127.0.0.1:8035`
- Frontend: `http://127.0.0.1:5173`
- MCP server: `dante-multimodal-rag`
- LaunchAgent label: `com.vidigal.obsidian-dante-multimodal-rag`
- Electron app: `/Applications/Dante Multimodal Dashboard.app`
- Global aliases: `dantedash`, `dantedashboard`, `dantevision`,
  `dante-multi`, `dantego`, `multimodal-rag`
- Menu command: `dante menu`

The LaunchAgent label intentionally keeps the old `obsidian` name during v1 so
existing aliases and Electron health checks keep working.

## Model Contract

- Multimodal embeddings: Voyage `voyage-multimodal-3.5`, 1024 dimensions.
- Chat model: DeepSeek `deepseek-v4-pro`.
- Text reranker: Cohere `rerank-v4.0-pro`.
- Visual analysis cards: Gemini vision provider where configured.

The backend process is the only service that should read provider credentials.
MCP clients and launchers must not receive raw provider secrets.

## Start And Stop

Start through launchd:

```bash
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.vidigal.obsidian-dante-multimodal-rag.plist
launchctl kickstart -k gui/$(id -u)/com.vidigal.obsidian-dante-multimodal-rag
```

Stop through launchd:

```bash
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.vidigal.obsidian-dante-multimodal-rag.plist
```

Manual foreground start:

```bash
/Users/vidigal/codex/dantedash/scripts/start-dante-multimodal-rag.sh
```

## Health Checks

```bash
curl -fsS http://127.0.0.1:8035/api/stats
curl -fsSI http://127.0.0.1:5173/
dantedash --status
/Users/vidigal/codex/dantedash/scripts/smoke-dante-dashboard.sh
```

Expected current KB count:

```json
{"total":4188,"by_modality":{"image":2094,"text":2094}}
```

## Local App State

DanteDash keeps Knowledge Base data and chat workspace state separate:

- Chroma: `chroma_db/` stores indexed KB nodes, embeddings, and retrieval data.
- SQLite: `backend/app_state/chat.sqlite` stores projects, threads, messages,
  thread summaries, curated project memory, model/top_k choices, and persisted
  source snapshots for the chat Context panel.

Override the SQLite path with `CHAT_STATE_DB` when needed. Treat this file as
local user data: it is ignored by git and can contain chat text. To reset chat
workspaces only, stop the app and move or delete the SQLite file. Do not use KB
clear, ingest, delete, or reindex commands for a chat-state reset.

The smoke script performs one lightweight workspace write by creating and then
archiving a temporary thread under the default project. It does not ingest,
delete, clear, or reindex KB content.

## MCP Smoke

The MCP wrapper runs from:

```bash
cd /Users/vidigal/codex/dantedash/backend
uv run python -m app.mcp_server
```

Read-only tool smoke order:

1. `stats`
2. `search`
3. `get_item`
4. `preview`
5. `chat`

## Rollback

The old Obsidian sidecar remains intact at:

```text
/Users/vidigal/claude-code/Obsidian/sidecars/dante-multimodal-rag
```

Rollback for v1 is intentionally simple:

1. Restore the external runner or set `DANTE_MULTIMODAL_PROJECT_ROOT` to the old
   sidecar path.
2. Restore the LaunchAgent `WorkingDirectory` to the old sidecar path.
3. Restart the existing LaunchAgent label.

Do not delete the old sidecar until the option 3 cleanup phase is explicitly
approved.

## Secret Safety

Ignored local files include:

```text
backend/.env
chroma_db/
uploads/
logs/
backend/.venv/
node_modules/
```

Never print raw `.env` contents or API keys in logs, docs, commits, or MCP
configuration.
