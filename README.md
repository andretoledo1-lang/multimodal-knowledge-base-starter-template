# Multimodal Knowledge Base — Starter Template

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Made By Agents](https://img.shields.io/badge/Made%20By%20Agents-madebyagents.com-000?logo=data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAyNCAyNCIgZmlsbD0id2hpdGUiPjxjaXJjbGUgY3g9IjEyIiBjeT0iMTIiIHI9IjEwIi8+PC9zdmc+)](https://www.madebyagents.com)

Open-source starter for a cross-modal RAG app: ingest **images, PDFs, videos,
and text** into one shared embedding space (Gemini Embedding 2) and search
them with a single text query, then chat with grounded, vision-aware answers
(Gemini 3.5 Flash).

Clone it, drop in a Gemini API key, and you have a working multimodal RAG
app on day one. Fork it as the foundation for a domain-specific knowledge
tool, an internal search product, or a research playground.

## Features

- **Cross-modal search** — a text query directly hits the most relevant
  image, PDF page, or video frame. No separate image index, no glue code.
- **Streaming RAG chat** — token-by-token SSE, then a sources card with
  thumbnail previews you can open full-screen.
- **Drag-and-drop ingest** — drop files anywhere in the library; modality is
  detected automatically.
- **Single port in prod** — Vite builds the SPA into FastAPI's `static/`; one
  process and one container serve API + UI.
- **Docker-ready** — multi-stage build, persistent volumes for the vector
  store and uploads.

## Stack

- **Backend:** FastAPI · ChromaDB (persistent) · `google-genai`
  (gemini-embedding-2-preview + gemini-3.5-flash) · LlamaIndex for text
  chunking · PyMuPDF / OpenCV for PDF and video preprocessing.
- **Frontend:** React 19 + Vite 8 · TypeScript · Tailwind v4 ·
  shadcn-style primitives (authored locally) · TanStack Query · Sonner ·
  react-dropzone.

---

## Quickstart — local development

You need a Gemini API key from <https://aistudio.google.com/app/apikey>.

Prereqs: [`uv`](https://docs.astral.sh/uv/) (Python), [`pnpm`](https://pnpm.io/)
(Node ≥ 22.11; `corepack enable` pins the right pnpm version), and `make`.

```bash
git clone <your-fork-url> multimodal-kb
cd multimodal-kb

cp backend/.env.example backend/.env   # paste your GEMINI_API_KEY into it

make install   # uv sync (backend) + pnpm install (frontend)
make dev       # backend :8000 + frontend :5173 in one terminal; Ctrl-C stops both
```

Open <http://localhost:5173>. Vite proxies `/api/*` to `:8000`.

Drag files into the **Library** panel (or click **Upload files**) to ingest
them, then ask questions in the **Chat** tab.

Prefer two terminals, or want to run just one side? The individual targets work:

```bash
make backend    # FastAPI only  (uv run uvicorn … --reload --port 8000)
make frontend   # Vite only     (pnpm --filter frontend dev)
```

Run `make` (or `make help`) to list every target.

## Quickstart — production build (single port)

```bash
make prod   # pnpm build → backend/static/, then uvicorn on :8000
```

Open <http://localhost:8000> — FastAPI serves both the API and the built SPA.

## Quickstart — Docker

```bash
docker build -t multimodal-kb .

docker run --rm \
  -e GEMINI_API_KEY="$GEMINI_API_KEY" \
  -p 8000:8000 \
  -v "$(pwd)/data/chroma:/app/backend/chroma_db" \
  -v "$(pwd)/data/uploads:/app/backend/uploads" \
  multimodal-kb
```

The Chroma DB and uploaded files live in those volumes, so the KB survives
container restarts.

---

## Environment variables

| Name             | Required | Default         | Purpose                                                    |
| ---------------- | -------- | --------------- | ---------------------------------------------------------- |
| `GEMINI_API_KEY` | **yes**  | —               | Auth for `google-genai` (embedding + chat).                |
| `KB_PERSIST_DIR` | no       | `./chroma_db`   | Chroma persistent storage path.                            |
| `KB_UPLOAD_DIR`  | no       | `./uploads`     | Original files storage path.                               |
| `KB_COLLECTION`  | no       | `multimodal_kb` | Chroma collection name.                                    |
| `CORS_ORIGINS`   | no       | _(empty)_       | Comma-separated origins. Same-origin prod doesn't need it. |
| `LOG_LEVEL`      | no       | `INFO`          | Python logging level.                                      |

The backend reads `backend/.env` via `python-dotenv`. Real `.env` is gitignored;
`.env.example` is checked in.

---

## How retrieval works

- All modalities share **one Gemini Embedding 2 vector space** (768-dim), so a
  text query directly retrieves the most relevant image or PDF page without any
  separate image index.
- **PDFs** are embedded **one vector per page** so retrieval pinpoints the
  exact page (no 6-page batching). Metadata carries `page`, `page_start`,
  `page_end`, and `total_pages`.
- **Videos ≤120s** are embedded as a single whole-video vector; longer videos
  are frame-sampled (default every 5s) with `timestamp_seconds` in metadata.
- **Text** files are chunked by LlamaIndex's standard text splitter.

Preview URLs are built server-side from the metadata of each result and served
by `/api/preview/*` endpoints — including on-the-fly PDF page rendering
(PyMuPDF) and video-frame extraction (OpenCV).

## Chat (SSE)

`POST /api/chat` returns `text/event-stream` with three event kinds:

```
data: "<token>"          # default 'message' event, JSON-encoded token

event: sources
data: {"sources": [...], "visual_attachments": N}

event: done
data: {}
```

The frontend uses `fetch` + `ReadableStream` (because `EventSource` is
GET-only) and a small hand-written parser in `src/lib/sse.ts`.

---

## Repo layout

```
backend/
  app/
    main.py            # FastAPI app, lifespan, static mount
    deps.py            # Settings + KB singleton (lru_cache)
    schemas.py         # Pydantic v2 DTOs
    kb.py              # KnowledgeBase: embedding, ingest, search
    rag.py             # answer_with_vision: grounded chat
    routes/{ingest,search,chat,library,preview}.py
  static/              # Vite build output (gitignored)
  chroma_db/, uploads/ # data (gitignored)
frontend/
  src/
    main.tsx, App.tsx, index.css
    lib/{api,sse,queryClient,utils}.ts
    hooks/             # useStats, useItems, useSearch, useImageSearch,
                       # useIngest, useDeleteItem, useClear, useChat
    components/        # Sidebar, SearchPanel, ChatPanel, LibraryPanel,
                       # PreviewDialog, ErrorBoundary, theme-provider, ui/*
Dockerfile
.dockerignore
```

---

## Extending this template

This is intentionally a small, readable base. A few common directions to take
it:

- **Swap the embedding provider** — `KnowledgeBase` in `backend/app/kb.py` is
  the only place that calls `google-genai` for embeddings. Replace with OpenAI,
  Cohere, Voyage, or a local model; keep the 768-dim Chroma collection or
  re-create it at the new dimension.
- **Swap the vector store** — Chroma is wrapped behind a thin interface in
  `kb.py`. pgvector, Qdrant, Weaviate, or LanceDB are drop-in replacements.
- **Swap the chat model** — `backend/app/rag.py::answer_with_vision` builds the
  multimodal prompt. Point it at another vision-capable model (GPT-4o, Claude,
  Llama 3.2 Vision) and keep the SSE contract intact.
- **Add auth + multi-tenancy** — gate `/api/*` with an auth dependency in
  `backend/app/main.py` and namespace the Chroma collection per user/org.
- **Add a different ingest pipeline** — audio transcription, web scraping,
  Notion/Drive sync. The `_ingest_one` helper in `routes/ingest.py` is the
  integration point.
- **Productionize** — add background ingest jobs, structured logging,
  rate limits, and a real object store for `uploads/`.

---

## Troubleshooting

**`GEMINI_API_KEY is not set`** — copy `backend/.env.example` to
`backend/.env` and put your key in, or pass `-e GEMINI_API_KEY=…` to
`docker run`.

**`/api` calls 404 in dev** — make sure the FastAPI process is running on
`:8000`; the Vite proxy only forwards `/api/*`.

**Chat stalls with no tokens** — verify your Gemini key has access to
`gemini-3.5-flash` and the embedding preview. Check the backend log for the
`chat q=… tokens=…` line that's emitted at end of stream.

**`opencv` errors inside Docker** — the image installs `libgl1` and
`libglib2.0-0` for `opencv-python-headless`. If you change the base image,
keep those packages.

**Library/Search shows no previews** — the relevant ingested file may have
been moved or deleted on disk; previews are served from `backend/uploads/`.

---

## Contributing

PRs and issues are welcome. For larger changes, open an issue first to discuss
the direction.

## License

[MIT](LICENSE) — do what you want, just keep the copyright notice.
