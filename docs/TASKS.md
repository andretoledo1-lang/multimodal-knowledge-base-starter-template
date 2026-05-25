# Multimodal Knowledge Base v2 — Implementation Tasks

> **Audience:** Coding agents implementing this project end-to-end.
> **Tone:** Imperative. When you see "do X", do X. When you see a constraint, do not violate it.
> **Source-of-truth status:** This document is canonical. If something here conflicts with another file, fix the other file.

---

## 1. Overview

Port the existing Streamlit demo at `/Users/tw/dev/multimodal_kb_demo` into a polished single-page React app on top of FastAPI, preserving the demo's already-solid embedding/retrieval/RAG core.

### Architecture

```
React + Vite + TS + shadcn/ui + TanStack Query   (dev :5173)
            │
            ▼  HTTP + SSE  (Vite proxy /api → :8000 in dev,
            │              same-origin StaticFiles in prod)
FastAPI  (:8000)
            │
            ▼
kb.py / rag.py  (clean separation, COPIED VERBATIM from demo)
            │
            ▼
ChromaDB (persistent)  +  Gemini Embedding 2  +  Gemini 2.5 Flash (vision)
```

### Key features

- **Ingest** — multipart upload of any modality (image / PDF / video / text) → embeddings stored in Chroma.
- **Search** — text query AND image query, cross-modal because all modalities share one embedding space.
- **Chat** — streaming RAG over the KB. SSE tokens, then a final `event: sources` payload with previews.
- **Library** — view + delete with optimistic updates, modality badges, loading skeletons, empty states.
- **Stats** — `/api/stats` returns per-modality counts.
- **Single-port prod** — `vite build` outputs to `backend/static/`, FastAPI mounts it. One Docker image.

### Why Gemini Embedding 2 matters

Natively multimodal. One vector space for text / image / PDF / video / audio. Searching with text directly hits the best image or PDF page — no glue code. PDFs >6 pages are split into 6-page chunks (page range stored in metadata). Videos ≤120s are embedded directly; longer videos are frame-sampled at intervals with timestamps in metadata.

### Why SSE (not WebSockets)

Native in the browser, perfect with FastAPI's `StreamingResponse`. Token-by-token streaming with a clean event protocol. Simpler than WebSockets and matches the use case exactly (server-push only).

---

## 2. Tech stack

### Backend

| Package                             | Version  | Purpose                               |
| ----------------------------------- | -------- | ------------------------------------- |
| python                              | 3.12     | Runtime                               |
| fastapi                             | >=0.115  | HTTP framework                        |
| uvicorn[standard]                   | >=0.30   | ASGI server                           |
| python-multipart                    | >=0.0.9  | Multipart file uploads                |
| python-dotenv                       | >=1.0.0  | `.env` loading                        |
| google-genai                        | >=1.0.0  | Gemini Embedding 2 + Gemini 2.5 Flash |
| chromadb                            | >=0.5.20 | Vector store (PersistentClient)       |
| llama-index-core                    | >=0.12.0 | Text chunking + ingestion pipeline    |
| llama-index-embeddings-google-genai | >=0.2.0  | LlamaIndex ↔ Gemini bridge           |
| llama-index-vector-stores-chroma    | >=0.4.0  | LlamaIndex ↔ Chroma bridge           |
| pypdf                               | >=5.0.0  | PDF splitting                         |
| pymupdf                             | >=1.24.0 | PDF page rendering (`fitz`)           |
| Pillow                              | >=10.0.0 | Image manipulation                    |
| opencv-python-headless              | >=4.9.0  | Video frame extraction                |
| numpy                               | >=1.26.0 | L2 normalisation                      |

### Frontend

| Package                                        | Version | Purpose                                  |
| ---------------------------------------------- | ------- | ---------------------------------------- |
| node                                           | 20      | Build runtime                            |
| react / react-dom                              | ^18.3   | UI                                       |
| typescript                                     | ^5.6    | Types                                    |
| vite                                           | ^5.4    | Dev server + bundler                     |
| @vitejs/plugin-react                           | ^4.3    | Vite React integration                   |
| tailwindcss / postcss / autoprefixer           | ^3.4    | Styling                                  |
| tailwindcss-animate                            | ^1.0    | Animation utilities                      |
| @tanstack/react-query                          | ^5      | Data fetching + caching                  |
| @tanstack/react-query-devtools                 | ^5      | Devtools                                 |
| lucide-react                                   | ^0.460  | Icons                                    |
| clsx, tailwind-merge, class-variance-authority | latest  | shadcn primitive deps                    |
| sonner                                         | ^1.7    | Toasts                                   |
| react-dropzone                                 | ^14     | Drag-drop uploads                        |
| shadcn/ui                                      | latest  | Component primitives (generated locally) |

### shadcn components to install

```
button card dialog input textarea tabs badge skeleton scroll-area
separator tooltip sonner progress alert label slider checkbox
```

---

## 3. Repo layout

```
multimodal_kb_v2/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py            # FastAPI app, lifespan, static mount, middleware
│   │   ├── deps.py            # Settings + KB singleton
│   │   ├── schemas.py         # Pydantic v2 request/response models
│   │   ├── kb.py              # COPIED VERBATIM from demo — DO NOT EDIT
│   │   ├── rag.py             # COPIED VERBATIM from demo — DO NOT EDIT
│   │   ├── sample_data.py     # COPIED VERBATIM from demo — DO NOT EDIT
│   │   └── routes/
│   │       ├── __init__.py
│   │       ├── ingest.py      # POST /api/ingest, /api/seed, /api/clear
│   │       ├── search.py      # POST /api/search, /api/search/image
│   │       ├── chat.py        # POST /api/chat (SSE StreamingResponse)
│   │       ├── library.py     # GET /api/items, DELETE /api/items/{id}, GET /api/stats
│   │       └── preview.py     # GET /api/preview/{id} + pdf-page + video-frame
│   ├── static/                # Vite build output (created on prod build)
│   ├── chroma_db/             # Vector store (gitignored)
│   ├── uploads/               # Original files (gitignored)
│   ├── pyproject.toml
│   ├── uv.lock
│   ├── .env.example
│   └── .python-version
├── frontend/
│   ├── src/
│   │   ├── main.tsx
│   │   ├── App.tsx
│   │   ├── index.css
│   │   ├── lib/
│   │   │   ├── api.ts
│   │   │   ├── queryClient.ts
│   │   │   ├── utils.ts
│   │   │   └── sse.ts          # SSE frame parser for fetch+ReadableStream
│   │   ├── hooks/              # useStats, useItems, useSearch, useImageSearch,
│   │   │                       # useIngest, useDeleteItem, useSeed, useClear, useChat
│   │   └── components/
│   │       ├── ui/             # shadcn primitives
│   │       └── ...
│   ├── index.html
│   ├── package.json
│   ├── tsconfig.json
│   ├── tailwind.config.ts
│   ├── postcss.config.js
│   ├── vite.config.ts
│   └── components.json
├── docs/
│   └── TASKS.md                # this file
├── Dockerfile
├── .dockerignore
├── .gitignore
└── README.md
```

---

## 4. Environment variables

| Name             | Required | Default         | Purpose                                                                                                      |
| ---------------- | -------- | --------------- | ------------------------------------------------------------------------------------------------------------ |
| `GEMINI_API_KEY` | yes      | —               | Auth for google-genai (embedding + chat).                                                                    |
| `KB_PERSIST_DIR` | no       | `./chroma_db`   | Chroma persistent storage path.                                                                              |
| `KB_UPLOAD_DIR`  | no       | `./uploads`     | Original files storage path.                                                                                 |
| `KB_COLLECTION`  | no       | `multimodal_kb` | Chroma collection name.                                                                                      |
| `CORS_ORIGINS`   | no       | (empty)         | Comma-separated origins. Unused in same-origin prod; needed only if frontend served from a different domain. |
| `LOG_LEVEL`      | no       | `INFO`          | Python logging level.                                                                                        |

`.env.example` must be checked in. Real `.env` is gitignored.

---

## 5. Backend reference

### 5.1 Hard rules

- **`kb.py`, `rag.py`, `sample_data.py` are copied verbatim** from `/Users/tw/dev/multimodal_kb_demo/`. Do not modify them. If a route needs new behavior, build it in the route layer, not by editing kb/rag.
- All file uploads are written to a `tempfile.NamedTemporaryFile(suffix=...)` before `kb.ingest_path(...)` is called. `kb.ingest_path` itself copies the file into `uploads/` under a UUID-suffixed name; do not duplicate that work.
- The KB is a **process-wide singleton** (cached via `functools.lru_cache` in `deps.py`). One instance per worker.
- Route layer never imports `streamlit`. Ever.

### 5.2 Public KB / RAG surface (do not modify)

```python
# kb.py
class KnowledgeBase:
    def __init__(self, *, api_key: str, collection_name: str = "multimodal_kb",
                 persist_dir: str | Path = "chroma_db",
                 upload_dir: str | Path = "uploads",
                 embed_model: str = "gemini-embedding-2-preview",
                 embed_dim: int = 768) -> None: ...

    def ingest_path(self, path: str | Path, *, original_name: str | None = None,
                    tags: list[str] | None = None,
                    on_progress: ProgressCallback = _noop,
                    video_frame_interval_s: int = 5) -> list[str]: ...

    def search_text(self, query: str, *, top_k: int = 5,
                    modality_filter: list[str] | None = None,
                    on_progress: ProgressCallback = _noop) -> list[SearchResult]: ...

    def search_image(self, image_path: str | Path, *, top_k: int = 5,
                     modality_filter: list[str] | None = None,
                     on_progress: ProgressCallback = _noop) -> list[SearchResult]: ...

    def count(self) -> int: ...
    def count_by_modality(self) -> dict[str, int]: ...
    def list_items(self, limit: int = 200) -> list[dict[str, Any]]: ...
    def delete_by_file_id(self, file_id: str) -> int: ...
    def clear(self) -> None: ...

@dataclass
class SearchResult:
    node_id: str
    score: float
    modality: str            # "image" | "pdf" | "video" | "text"
    metadata: dict[str, Any]
    snippet: str = ""

    @property
    def file_path(self) -> Path | None: ...
    @property
    def display_name(self) -> str: ...

def render_pdf_page(pdf_path: Path, page_index_0based: int = 0,
                    zoom: float = 1.5) -> PIL.Image.Image: ...
def load_video_frame_at(path: Path, timestamp_s: float) -> PIL.Image.Image | None: ...
```

```python
# rag.py
DEFAULT_VISION_MODEL = "gemini-2.5-flash"

@dataclass
class GroundedAnswer:
    answer: str
    sources: list[SearchResult]
    visual_attachments: int

def answer_with_vision(kb: KnowledgeBase, question: str, *,
                       top_k: int = 5,
                       modality_filter: list[str] | None = None,
                       model: str = DEFAULT_VISION_MODEL,
                       max_images: int = 6,
                       on_progress=None) -> Iterator[str | GroundedAnswer]:
    """Generator. Yields str chunks (tokens) then a final GroundedAnswer."""
```

### 5.3 Metadata schema (per modality)

All vectors carry:

```python
{
  "id":           "<uuid hex>",           # the file_id (groups vectors from same source)
  "original_name": "filename.ext",
  "file_path":    "/abs/path/to/uploads/<uuid>.<ext>",
  "upload_time":  "ISO 8601",
  "file_size":    <int bytes>,
  "tags":         "comma,separated",
  "modality":     "image" | "pdf" | "video" | "text",
}
```

Modality-specific additions:

- **image** — none.
- **pdf** — `page_start` (1-based, inclusive), `page_end` (inclusive), `total_pages`.
- **video** — `duration_seconds`. Whole-video embeddings carry `frame_index: -1`. Frame-sampled embeddings carry `frame_index: 1..N` and `timestamp_seconds: float`.
- **text** — LlamaIndex chunk metadata (chunk_id, etc.) merged in.

### 5.4 API table

| Method | Path                                             | Body                                                      | Response                                |
| ------ | ------------------------------------------------ | --------------------------------------------------------- | --------------------------------------- |
| POST   | `/api/ingest`                                    | multipart: `files[]`, `tags?`, `video_frame_interval_s?`  | `IngestResponse`                        |
| POST   | `/api/search`                                    | JSON: `{query, top_k?, modality_filter?}`                 | `SearchResponse`                        |
| POST   | `/api/search/image`                              | multipart: `file`, `top_k?`, `modality_filter?`           | `SearchResponse`                        |
| POST   | `/api/chat`                                      | JSON: `{question, top_k?, modality_filter?, max_images?}` | `text/event-stream`                     |
| GET    | `/api/items`                                     | —                                                         | `{items: ItemDTO[]}`                    |
| DELETE | `/api/items/{file_id}`                           | —                                                         | `{deleted: int}`                        |
| GET    | `/api/stats`                                     | —                                                         | `{total: int, by_modality: {[m]: int}}` |
| POST   | `/api/seed`                                      | —                                                         | `IngestResponse`                        |
| POST   | `/api/clear`                                     | —                                                         | `{cleared: true}`                       |
| GET    | `/api/preview/{file_id}`                         | —                                                         | image bytes (original image)            |
| GET    | `/api/preview/{file_id}/pdf-page/{page_1based}`  | —                                                         | `image/jpeg` (rendered page)            |
| GET    | `/api/preview/{file_id}/video-frame?t=<seconds>` | —                                                         | `image/jpeg` (sampled frame)            |

### 5.5 Pydantic schemas (Pydantic v2)

```python
# app/schemas.py

class SearchResultDTO(BaseModel):
    node_id: str
    score: float                 # 0..1
    modality: str                # image | pdf | video | text
    display_name: str
    file_id: str                 # metadata["id"]
    metadata: dict[str, Any]     # full pass-through (sanitised: drop file_path)
    snippet: str = ""
    preview_url: str | None      # built server-side

class SearchResponse(BaseModel):
    results: list[SearchResultDTO]

class SearchRequest(BaseModel):
    query: str
    top_k: int = 5
    modality_filter: list[str] | None = None

class ChatRequest(BaseModel):
    question: str
    top_k: int = 5
    modality_filter: list[str] | None = None
    max_images: int = 6

class IngestItemDTO(BaseModel):
    file_id: str
    original_name: str
    modality: str
    node_ids: list[str]
    total_pages: int | None = None
    duration_seconds: float | None = None
    preview_url: str | None = None

class IngestResponse(BaseModel):
    items: list[IngestItemDTO]
    total: int

class ItemDTO(BaseModel):
    file_id: str
    original_name: str
    modality: str
    upload_time: str
    node_ids: list[str]
    preview_url: str | None

class StatsResponse(BaseModel):
    total: int
    by_modality: dict[str, int]
```

### 5.6 SSE event protocol (`POST /api/chat`)

Response headers:

```
Content-Type: text/event-stream
Cache-Control: no-cache
X-Accel-Buffering: no
```

Body — three event kinds:

1. **Tokens** (default `message` event):

   ```
   data: "Hello"

   data: " world"

   ```

   Each `data:` line is JSON-encoded (so newlines/quotes in tokens never break the protocol).

2. **Sources** (named event), emitted once when generation finishes:

   ```
   event: sources
   data: {"sources":[{"node_id":"...","display_name":"...","modality":"pdf","score":0.87,"preview_url":"/api/preview/abc/pdf-page/4","metadata":{...}}],"visual_attachments":4}

   ```

3. **Done** (named event), emitted last:

   ```
   event: done
   data: {}

   ```

The route iterates `answer_with_vision(...)`. Each `str` becomes a token event. The terminal `GroundedAnswer` becomes a `sources` event followed by `done`.

### 5.7 `preview_url` builder

```python
def preview_url_for(meta: dict) -> str | None:
    file_id = meta.get("id")
    if not file_id:
        return None
    m = meta.get("modality")
    if m == "image":
        return f"/api/preview/{file_id}"
    if m == "pdf":
        page = meta.get("page_start", 1)
        return f"/api/preview/{file_id}/pdf-page/{page}"
    if m == "video":
        t = meta.get("timestamp_seconds")
        if t is None:
            t = 0.0  # whole-video embedding: pick frame at t=0
        return f"/api/preview/{file_id}/video-frame?t={t}"
    return None  # text → no preview
```

### 5.8 Logging

```python
# main.py
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)

@app.middleware("http")
async def access_log(request, call_next):
    t0 = time.perf_counter()
    response = await call_next(request)
    dt_ms = (time.perf_counter() - t0) * 1000
    logger.info("%s %s → %d (%.1fms)",
                request.method, request.url.path,
                response.status_code, dt_ms)
    return response
```

Routes that do real work (ingest, chat) should emit one `INFO` line each summarising the operation (file count, model, top_k, sources_returned, etc.).

### 5.9 Static mount (prod)

```python
# After all /api routers are registered:
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")
```

In dev, `static/` doesn't exist → mount is skipped → Vite proxy handles the SPA on `:5173`.

---

## 6. Frontend reference

### 6.1 TanStack Query keys

| Key                                   | Owner       | Invalidated by                |
| ------------------------------------- | ----------- | ----------------------------- |
| `['stats']`                           | `useStats`  | ingest, delete, seed, clear   |
| `['items']`                           | `useItems`  | ingest, delete, seed, clear   |
| `['search', query, topK, modalities]` | `useSearch` | (never — pure query function) |

Image-search uses `useMutation`, never cached.

### 6.2 Optimistic delete pattern

```ts
useMutation({
  mutationFn: (file_id) => api.deleteItem(file_id),
  onMutate: async (file_id) => {
    await qc.cancelQueries({ queryKey: ["items"] });
    const prev = qc.getQueryData<Items>(["items"]);
    qc.setQueryData<Items>(["items"], (old) => ({
      ...old!,
      items: old!.items.filter((i) => i.file_id !== file_id),
    }));
    return { prev };
  },
  onError: (_e, _id, ctx) => ctx?.prev && qc.setQueryData(["items"], ctx.prev),
  onSettled: () => {
    qc.invalidateQueries({ queryKey: ["items"] });
    qc.invalidateQueries({ queryKey: ["stats"] });
  },
});
```

### 6.3 SSE on POST — why we don't use EventSource

`EventSource` is **GET-only**. We send a JSON body, so we use `fetch('/api/chat', { method: 'POST', body: ... })` and read `response.body` as a `ReadableStream`. We hand-parse SSE frames in `lib/sse.ts` (~30 lines):

```ts
// Yields { event: 'message' | 'sources' | 'done', data: string }
export async function* parseSSE(stream: ReadableStream<Uint8Array>) {
  const reader = stream.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    let idx;
    while ((idx = buf.indexOf("\n\n")) !== -1) {
      const frame = buf.slice(0, idx);
      buf = buf.slice(idx + 2);
      let event = "message";
      const dataLines: string[] = [];
      for (const line of frame.split("\n")) {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        else if (line.startsWith("data:"))
          dataLines.push(line.slice(5).trimStart());
      }
      yield { event, data: dataLines.join("\n") };
    }
  }
}
```

### 6.4 `useChat` shape

```ts
type ChatMessage =
  | { role: "user"; content: string }
  | {
      role: "assistant";
      content: string;
      sources?: SearchResultDTO[];
      streaming?: boolean;
    };

const { messages, partial, isStreaming, send, reset } = useChat();
```

`send(question)` appends a user message + an empty assistant message marked `streaming: true`. Tokens append to `partial`. On `sources` event, attaches them to the in-flight assistant message. On `done`, flushes `partial` into the assistant message and clears `streaming`.

### 6.5 Modality colors / icons (centralized)

```ts
// lib/utils.ts
export const MODALITY = {
  image: {
    color:
      "bg-violet-500/15 text-violet-700 dark:text-violet-300 border-violet-500/30",
    icon: ImageIcon,
    label: "Image",
  },
  pdf: {
    color: "bg-rose-500/15 text-rose-700 dark:text-rose-300 border-rose-500/30",
    icon: FileText,
    label: "PDF",
  },
  video: {
    color: "bg-sky-500/15 text-sky-700 dark:text-sky-300 border-sky-500/30",
    icon: Video,
    label: "Video",
  },
  text: {
    color:
      "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300 border-emerald-500/30",
    icon: FileType,
    label: "Text",
  },
} as const;
```

### 6.6 Loading states — skeletons, not spinners

- Library grid → 6 `LibraryCardSkeleton`s.
- Search results → 4 `ResultCardSkeleton`s.
- Stats card → 4 short `Skeleton` lines.
- Chat: while streaming, a `…` pulsing dot in the assistant bubble.

### 6.7 Empty states

- **Sidebar / Library, 0 items** — "Your knowledge base is empty." + "Upload your first files" CTA + "Load demo data" link.
- **Search with no query** — "Search across everything you've uploaded — text, images, PDFs, videos."
- **Search with results 0** — "No matches. Try a different query or different modality filters."
- **Chat fresh** — "Ask anything about your knowledge base. The assistant will cite its sources."

### 6.8 Vite proxy + build target

```ts
// vite.config.ts
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": { target: "http://localhost:8000", changeOrigin: true },
    },
  },
  build: {
    outDir: "../backend/static",
    emptyOutDir: true,
  },
  resolve: {
    alias: { "@": path.resolve(__dirname, "./src") },
  },
});
```

---

## 7. Implementation phases & acceptance criteria

### Phase 0 — TASKS.md _(this file)_

**Done when:** this file exists at `docs/TASKS.md` and contains an unambiguous spec for everything below.

### Phase 1 — Backend skeleton

- `cd backend && uv init --python 3.12`
- Vet Python deps via the `package-vetting` skill, then `uv add` them (single batch; see §8).
- Copy three files verbatim from `/Users/tw/dev/multimodal_kb_demo/`: `kb.py`, `rag.py`, `sample_data.py` → `backend/app/`.
- Implement `app/deps.py` (settings + KB singleton).
- Implement `app/main.py` (FastAPI + lifespan + middleware + router registration + static mount).

**Done when:** `uv run uvicorn app.main:app --reload --port 8000` boots and `GET /api/stats` returns `{total: 0, by_modality: {}}`.

### Phase 2 — Backend routes

- All routes as per the API table.
- `app/schemas.py` with the Pydantic models above.
- SSE chat per §5.6.
- Preview routes per §5.7.

**Done when:** every endpoint in the API table responds correctly to a `curl` smoke test. `POST /api/seed` populates the KB. `POST /api/chat` streams tokens then a sources event then a done event.

### Phase 3 — Frontend scaffold

- `cd frontend && npm create vite@latest . -- --template react-ts` (interactive prompts skipped; the dir already exists, so use `--force` or scaffold to a temp dir and move).
- Vet npm deps, then install in one batch (see §8).
- `npx tailwindcss init -p`; configure content paths and theme.
- `npx shadcn@latest init` (configure tsconfig paths, components dir = `src/components/ui`).
- `npx shadcn@latest add button card dialog input textarea tabs badge skeleton scroll-area separator tooltip sonner progress alert label slider checkbox`.
- `vite.config.ts` per §6.8.
- `main.tsx` wires `<QueryClientProvider>` + `<Toaster richColors closeButton />`.

**Done when:** `npm run dev` opens `:5173` showing an empty styled shell, and `npm run build` outputs to `../backend/static/` without errors.

### Phase 4 — Frontend hooks & API layer

- `lib/api.ts` — typed wrappers per the API table, throwing `ApiError(status, detail)` on non-2xx.
- `lib/sse.ts` — SSE parser per §6.3.
- Hooks per §6.1 / §6.2 / §6.4.

**Done when:** the React DevTools show queries firing, cache populating, and an optimistic delete works.

### Phase 5 — Frontend components

- All components in the layout (see Repo layout). Per-modality color and icon via `MODALITY`. Sonner toasts for mutation outcomes. Skeletons everywhere instead of spinners.
- Chat: streaming tokens render character-by-character; sources card shows after `event: sources` with thumbnail previews; clicking a source opens a `Dialog` with the full preview + metadata.

**Done when:** all manual checks in §9 pass.

### Phase 6 — Integration & polish

- App shell: sidebar (320px fixed-left) + main pane with `Tabs` (Search / Chat / Library).
- Error boundary at root with sonner toast on render error.
- Keyboard: `cmd/ctrl+k` focuses the search input on the Search tab; `enter` in the Chat composer sends, `shift+enter` newlines.
- Dark mode toggle in sidebar footer (shadcn theme).

**Done when:** keyboard shortcuts work, dark mode toggles correctly, render errors don't blank the screen.

### Phase 7 — Dockerization & docs

- `Dockerfile` — multi-stage:
  1. `node:20-slim` — `WORKDIR /app/frontend`, copy `frontend/`, `npm ci && npm run build`. Vite writes to `/app/backend/static/`.
  2. `python:3.12-slim` — install `uv` (`pip install --no-cache-dir uv`), `WORKDIR /app/backend`, copy `backend/`, `COPY --from=0 /app/backend/static ./static`, `uv sync --frozen --no-dev`, expose `8000`, `CMD ["uv","run","uvicorn","app.main:app","--host","0.0.0.0","--port","8000"]`.
- `.dockerignore`: `node_modules`, `dist`, `**/__pycache__`, `chroma_db`, `uploads`, `.env`, `.git`, `.venv`.
- `README.md`: quickstart (dev + prod), env-var reference, troubleshooting.

**Done when:** `docker build -t kb . && docker run -e GEMINI_API_KEY=$GEMINI_API_KEY -p 8000:8000 -v $(pwd)/data:/app/backend/data kb` serves the full app on `:8000`.

---

## 8. Package-vetting protocol

Before any `uv add` or `npm install`, invoke the `package-vetting` skill with the full list:

**Python (single batch):**

```
fastapi uvicorn[standard] python-multipart python-dotenv google-genai
chromadb llama-index-core llama-index-embeddings-google-genai
llama-index-vector-stores-chroma pypdf pymupdf Pillow
opencv-python-headless numpy
```

Dev-only:

```
pytest httpx ruff
```

**Node (single batch):**

Runtime:

```
@tanstack/react-query @tanstack/react-query-devtools lucide-react sonner
react-dropzone clsx tailwind-merge class-variance-authority
tailwindcss-animate
```

Dev:

```
tailwindcss postcss autoprefixer @types/node
```

shadcn primitives are added via `npx shadcn@latest add` (not direct npm installs).

If the vetter flags anything, replace it or ask the user before proceeding. Document the vetted, pinned commands inline in this section as they are confirmed.

---

## 9. Verification

### Manual smoke (run after each phase)

1. `cd backend && uv run uvicorn app.main:app --reload --port 8000` boots cleanly.
2. `cd frontend && npm run dev` opens `:5173` with the styled shell.
3. Click **Load demo data** in the sidebar — ~5 items appear; stats updates without a refresh.
4. Search "engineering retrospective" — the markdown source is in the top result.
5. Search by image using `samples/q3_revenue_chart.png` — chart-adjacent items rank highly.
6. Chat: "What was Acme's Q3 revenue?" — tokens stream, sources show after, clicking a source opens its preview dialog.
7. Library tab — delete an item — vanishes immediately; sidebar count decrements.
8. Reload — KB state persists.
9. `cd frontend && npm run build && cd ../backend && uv run uvicorn app.main:app --port 8000` — `http://localhost:8000` serves the full SPA same-origin; all routes still work.
10. `docker build -t kb . && docker run -e GEMINI_API_KEY=$GEMINI_API_KEY -p 8000:8000 kb` — single container hosts everything.

### Automated (light)

- `backend/tests/test_routes.py` — pytest + httpx + a tmp `KB_PERSIST_DIR`. Smokes ingest → items → stats → delete. Skip chat (uses a live LLM).
- Frontend CI: `npx tsc --noEmit` and `npm run build` must succeed.

---

## 10. Non-goals (out of scope)

- Auth / multi-tenant.
- Real-time collab.
- Audio modality (Gemini Embedding 2 supports it, but the demo doesn't surface it).
- Hybrid (BM25 + vector) search.
- LangGraph-style agents on top of RAG.

Implement these only if the user explicitly asks.
