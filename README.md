# Multimodal Knowledge Base

A single-page React app on top of FastAPI that ingests **images, PDFs, videos,
and text** into one shared embedding space (Gemini Embedding 2) and lets you
search them cross-modally, then chat with grounded, vision-aware answers
(Gemini 2.5 Flash).

- **Cross-modal search** — a text query directly hits the most relevant image,
  PDF page, or video frame, with no glue code.
- **Streaming RAG chat** — token-by-token SSE, then a sources card with
  thumbnail previews you can open full-screen.
- **Library** — drag-and-drop ingest, modality badges, optimistic delete.
- **Single port in prod** — Vite builds the SPA into FastAPI's `static/`; one
  process and one container serve everything.

## Stack

- **Backend:** FastAPI · ChromaDB (persistent) · `google-genai`
  (gemini-embedding-2-preview + gemini-2.5-flash) · LlamaIndex for text
  chunking · PyMuPDF / OpenCV for PDF and video preprocessing.
- **Frontend:** React 19 + Vite 8 · TypeScript · Tailwind v4 ·
  shadcn-style primitives (authored locally) · TanStack Query · Sonner ·
  react-dropzone.

---

## Quickstart — local development (two processes)

You need a Gemini API key from <https://aistudio.google.com/app/apikey>.

```bash
# 1) Backend
cd backend
cp .env.example .env       # paste your GEMINI_API_KEY into .env
uv sync
uv run uvicorn app.main:app --reload --port 8000

# 2) Frontend (in a second terminal)
cd frontend
npm install
npm run dev
```

Open <http://localhost:5173>. Vite proxies `/api/*` to `:8000`.

Click **Load demo data** in the sidebar to populate the KB with a small set of
mixed-modality samples.

## Quickstart — production build (single port)

```bash
cd frontend && npm install && npm run build   # → ../backend/static/
cd ../backend && uv run uvicorn app.main:app --port 8000
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
- **PDFs >6 pages** are split into 6-page chunks; each chunk is embedded as a
  composite image. Metadata carries `page_start`, `page_end`, `total_pages`.
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
    kb.py              # KnowledgeBase (verbatim from demo)
    rag.py             # answer_with_vision (verbatim from demo)
    sample_data.py     # demo seed (verbatim from demo)
    routes/{ingest,search,chat,library,preview}.py
  static/              # Vite build output (gitignored)
  chroma_db/, uploads/ # data (gitignored)
frontend/
  src/
    main.tsx, App.tsx, index.css
    lib/{api,sse,queryClient,utils}.ts
    hooks/             # useStats, useItems, useSearch, useImageSearch,
                       # useIngest, useDeleteItem, useSeed, useClear, useChat
    components/        # Sidebar, SearchPanel, ChatPanel, LibraryPanel,
                       # PreviewDialog, ErrorBoundary, theme-provider, ui/*
Dockerfile
.dockerignore
docs/TASKS.md          # canonical implementation spec
```

---

## Troubleshooting

**`GEMINI_API_KEY is not set`** — copy `backend/.env.example` to
`backend/.env` and put your key in, or pass `-e GEMINI_API_KEY=…` to
`docker run`.

**`/api` calls 404 in dev** — make sure the FastAPI process is running on
`:8000`; the Vite proxy only forwards `/api/*`.

**Chat stalls with no tokens** — verify your Gemini key has access to
`gemini-2.5-flash` and the embedding preview. Check the backend log for the
`chat q=… tokens=…` line that's emitted at end of stream.

**`opencv` errors inside Docker** — the image installs `libgl1` and
`libglib2.0-0` for `opencv-python-headless`. If you change the base image,
keep those packages.

**Library/Search shows no previews** — the relevant ingested file may have
been moved or deleted on disk; previews are served from `backend/uploads/`.
