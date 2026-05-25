"""
Multimodal Knowledge Base core.

Stack:
    Gemini Embedding 2 (gemini-embedding-2-preview)  - one model for text/image/PDF/video
    LlamaIndex VectorStoreIndex                      - ingestion pipeline + query engine
    ChromaDB (PersistentClient + ChromaVectorStore)  - local vector store

Design:
    - Text is chunked and embedded through LlamaIndex's IngestionPipeline
      (so users can extend with LlamaParse, semantic splitting, etc.).
    - Images / PDFs / video frames are embedded directly via google-genai
      (LlamaIndex's text-only embed interface can't accept raw bytes), then
      inserted as TextNodes with a pre-computed `embedding` field. The vectors
      live in the same Chroma collection - same dimensionality, same model -
      so cross-modal retrieval just works.
    - All embeddings are 768-dim (Matryoshka truncation - quality/cost balance).
"""
from __future__ import annotations

import io
import os
import shutil
import tempfile
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterator

import chromadb
import cv2
import fitz  # PyMuPDF
import numpy as np
from google import genai
from google.genai import types
from llama_index.core import Settings, StorageContext, VectorStoreIndex
from llama_index.core.ingestion import IngestionPipeline
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.schema import TextNode
from llama_index.core.vector_stores import (
    MetadataFilter,
    MetadataFilters,
    VectorStoreQuery,
)
from llama_index.embeddings.google_genai import GoogleGenAIEmbedding
from llama_index.vector_stores.chroma import ChromaVectorStore
from PIL import Image
from pypdf import PdfReader, PdfWriter

# ---------- Configuration ----------

EMBED_MODEL = "gemini-embedding-2-preview"
EMBED_DIM = 768
MAX_PDF_PAGES_PER_EMBED = 6      # Gemini Embedding 2 PDF limit
MAX_VIDEO_SECONDS_DIRECT = 120   # Above this, sample frames instead
DEFAULT_VIDEO_FRAME_INTERVAL_S = 5

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}
VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
TEXT_EXTS = {".txt", ".md", ".csv", ".log"}
PDF_EXTS = {".pdf"}

# MIME type lookup
MIME_BY_EXT = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
    ".pdf": "application/pdf",
    ".mp4": "video/mp4",
    ".mov": "video/quicktime",
    ".avi": "video/x-msvideo",
    ".mkv": "video/x-matroska",
    ".webm": "video/webm",
}


# ---------- Pipeline event protocol ----------

@dataclass
class PipelineEvent:
    """Emitted during ingestion or search so the UI can show a live trace."""
    stage: str
    detail: str
    progress: float | None = None  # 0..1


ProgressCallback = Callable[[PipelineEvent], None]


def _noop(_event: PipelineEvent) -> None:
    pass


# ---------- Result type ----------

@dataclass
class SearchResult:
    node_id: str
    score: float        # cosine similarity (1 - distance), 0..1
    modality: str
    metadata: dict[str, Any]
    snippet: str = ""

    @property
    def file_path(self) -> Path | None:
        p = self.metadata.get("file_path")
        return Path(p) if p else None

    @property
    def display_name(self) -> str:
        return self.metadata.get("original_name", self.node_id)


# ---------- Knowledge Base ----------

class KnowledgeBase:
    """
    Multimodal KB on top of LlamaIndex + Chroma + Gemini Embedding 2.

    Single instance per process. Cache it with @st.cache_resource in Streamlit.
    """

    def __init__(
        self,
        *,
        api_key: str,
        collection_name: str = "multimodal_kb",
        persist_dir: str | Path = "chroma_db",
        upload_dir: str | Path = "uploads",
        embed_model: str = EMBED_MODEL,
        embed_dim: int = EMBED_DIM,
    ):
        self.api_key = api_key
        self.collection_name = collection_name
        self.persist_dir = Path(persist_dir)
        self.upload_dir = Path(upload_dir)
        self.embed_model_name = embed_model
        self.embed_dim = embed_dim

        self.persist_dir.mkdir(exist_ok=True, parents=True)
        self.upload_dir.mkdir(exist_ok=True, parents=True)

        # 1. Direct google-genai client - used for media bytes embedding & vision RAG
        self.genai_client = genai.Client(api_key=api_key)

        # 2. LlamaIndex embedding wrapper - used for text chunking pipeline
        self.embed_model = GoogleGenAIEmbedding(
            model_name=embed_model,
            api_key=api_key,
            embedding_config=types.EmbedContentConfig(
                output_dimensionality=embed_dim
            ),
        )
        Settings.embed_model = self.embed_model

        # 3. Chroma persistent client + collection (cosine = best for unit-norm vectors)
        self.chroma_client = chromadb.PersistentClient(path=str(self.persist_dir))
        self.collection = self.chroma_client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )

        # 4. LlamaIndex vector store + index - this is the public RAG interface
        self.vector_store = ChromaVectorStore(chroma_collection=self.collection)
        self.storage_context = StorageContext.from_defaults(vector_store=self.vector_store)
        self.index = VectorStoreIndex.from_vector_store(
            self.vector_store,
            embed_model=self.embed_model,
        )

        # 5. Text ingestion pipeline (chunking + embedding + insert)
        self.text_pipeline = IngestionPipeline(
            transformations=[
                SentenceSplitter(chunk_size=500, chunk_overlap=50),
                self.embed_model,
            ],
            vector_store=self.vector_store,
        )

    # ===== Embedding primitives =====

    def _embed_bytes(self, data: bytes, mime_type: str) -> list[float]:
        """Embed a single image/PDF/video blob via Gemini Embedding 2."""
        result = self.genai_client.models.embed_content(
            model=self.embed_model_name,
            contents=[types.Part.from_bytes(data=data, mime_type=mime_type)],
            config=types.EmbedContentConfig(output_dimensionality=self.embed_dim),
        )
        vec = result.embeddings[0].values
        return _l2_normalize(vec)

    def _embed_query_text(self, text: str) -> list[float]:
        """Embed a search query (we re-use embed_model so it goes through LlamaIndex)."""
        vec = self.embed_model.get_query_embedding(text)
        return _l2_normalize(vec)

    # ===== Ingestion: dispatcher =====

    def ingest_path(
        self,
        path: str | Path,
        *,
        original_name: str | None = None,
        tags: list[str] | None = None,
        on_progress: ProgressCallback = _noop,
        video_frame_interval_s: int = DEFAULT_VIDEO_FRAME_INTERVAL_S,
    ) -> list[str]:
        """Persist a file under uploads/ and dispatch to the right ingester."""
        src = Path(path)
        ext = src.suffix.lower()
        if not src.exists():
            raise FileNotFoundError(src)

        # Copy original into managed uploads dir (so it survives temp cleanup)
        file_id = uuid.uuid4().hex
        dest = self.upload_dir / f"{file_id}{ext}"
        if src.resolve() != dest.resolve():
            shutil.copy2(src, dest)

        base_meta = {
            "id": file_id,
            "original_name": original_name or src.name,
            "file_path": str(dest),
            "upload_time": datetime.now().isoformat(timespec="seconds"),
            "file_size": dest.stat().st_size,
            "tags": ",".join(tags) if tags else "",
        }

        on_progress(PipelineEvent("read", f"Loaded {base_meta['original_name']} ({_human_size(base_meta['file_size'])})"))

        if ext in IMAGE_EXTS:
            return [self._ingest_image(dest, base_meta, on_progress)]
        if ext in PDF_EXTS:
            return self._ingest_pdf(dest, base_meta, on_progress)
        if ext in VIDEO_EXTS:
            return self._ingest_video(dest, base_meta, on_progress, video_frame_interval_s)
        if ext in TEXT_EXTS:
            return self._ingest_text_file(dest, base_meta, on_progress)
        raise ValueError(f"Unsupported file type: {ext}")

    # ===== Ingestion: per-modality =====

    def _ingest_image(
        self,
        path: Path,
        base_meta: dict[str, Any],
        on_progress: ProgressCallback,
    ) -> str:
        on_progress(PipelineEvent("embed", "Embedding image with Gemini Embedding 2…"))
        data = path.read_bytes()
        mime = MIME_BY_EXT.get(path.suffix.lower(), "image/jpeg")
        vec = self._embed_bytes(data, mime)

        node_id = f"img_{base_meta['id']}"
        node = TextNode(
            id_=node_id,
            text=f"[Image] {base_meta['original_name']}",
            metadata={**base_meta, "modality": "image"},
            embedding=vec,
        )
        on_progress(PipelineEvent("store", "Writing vector to ChromaDB…"))
        self.vector_store.add([node])
        on_progress(PipelineEvent("done", f"Indexed image: {base_meta['original_name']}", 1.0))
        return node_id

    def _ingest_pdf(
        self,
        path: Path,
        base_meta: dict[str, Any],
        on_progress: ProgressCallback,
    ) -> list[str]:
        reader = PdfReader(str(path))
        total_pages = len(reader.pages)
        base_meta["total_pages"] = total_pages
        on_progress(PipelineEvent("inspect", f"PDF has {total_pages} page(s)"))

        # Short PDF: embed the whole file in one call (preserves text+visual layout)
        if total_pages <= MAX_PDF_PAGES_PER_EMBED:
            on_progress(PipelineEvent("embed", "Embedding full PDF…"))
            data = path.read_bytes()
            vec = self._embed_bytes(data, "application/pdf")
            node_id = f"pdf_{base_meta['id']}"
            node = TextNode(
                id_=node_id,
                text=f"[PDF] {base_meta['original_name']} ({total_pages} pages)",
                metadata={
                    **base_meta,
                    "modality": "pdf",
                    "page_start": 1,
                    "page_end": total_pages,
                },
                embedding=vec,
            )
            self.vector_store.add([node])
            on_progress(PipelineEvent("done", f"Indexed PDF: {base_meta['original_name']}", 1.0))
            return [node_id]

        # Long PDF: split into ≤6-page chunks
        on_progress(PipelineEvent("split", f"Splitting into {(total_pages + MAX_PDF_PAGES_PER_EMBED - 1) // MAX_PDF_PAGES_PER_EMBED} chunk(s)…"))
        chunk_paths = _split_pdf(path, MAX_PDF_PAGES_PER_EMBED)
        ids: list[str] = []
        try:
            for i, (chunk_path, start_p, end_p) in enumerate(chunk_paths, 1):
                on_progress(PipelineEvent(
                    "embed",
                    f"Embedding pages {start_p}-{end_p}…",
                    progress=i / len(chunk_paths),
                ))
                data = chunk_path.read_bytes()
                vec = self._embed_bytes(data, "application/pdf")
                node_id = f"pdf_{base_meta['id']}_p{start_p}-{end_p}"
                node = TextNode(
                    id_=node_id,
                    text=f"[PDF] {base_meta['original_name']} pages {start_p}-{end_p}",
                    metadata={
                        **base_meta,
                        "modality": "pdf",
                        "page_start": start_p,
                        "page_end": end_p,
                    },
                    embedding=vec,
                )
                self.vector_store.add([node])
                ids.append(node_id)
        finally:
            for p, _, _ in chunk_paths:
                p.unlink(missing_ok=True)

        on_progress(PipelineEvent("done", f"Indexed PDF: {base_meta['original_name']} ({len(ids)} chunks)", 1.0))
        return ids

    def _ingest_video(
        self,
        path: Path,
        base_meta: dict[str, Any],
        on_progress: ProgressCallback,
        frame_interval_s: int,
    ) -> list[str]:
        duration_s = _video_duration_seconds(path)
        base_meta["duration_seconds"] = round(duration_s, 1)
        on_progress(PipelineEvent("inspect", f"Video duration: {duration_s:.1f}s"))

        # Short video: embed the whole MP4 directly (Gemini Embedding 2 supports up to ~120s)
        if duration_s <= MAX_VIDEO_SECONDS_DIRECT:
            on_progress(PipelineEvent("embed", "Embedding full video…"))
            data = path.read_bytes()
            mime = MIME_BY_EXT.get(path.suffix.lower(), "video/mp4")
            vec = self._embed_bytes(data, mime)
            node_id = f"vid_{base_meta['id']}"
            node = TextNode(
                id_=node_id,
                text=f"[Video] {base_meta['original_name']} ({duration_s:.1f}s)",
                metadata={**base_meta, "modality": "video", "frame_index": -1},
                embedding=vec,
            )
            self.vector_store.add([node])
            on_progress(PipelineEvent("done", f"Indexed video: {base_meta['original_name']}", 1.0))
            return [node_id]

        # Long video: sample frames every N seconds, embed each as image
        on_progress(PipelineEvent(
            "split",
            f"Sampling frames every {frame_interval_s}s (~{int(duration_s // frame_interval_s)} frames)…",
        ))
        frames = _sample_video_frames(path, frame_interval_s)
        ids: list[str] = []
        for i, (timestamp_s, frame_bytes) in enumerate(frames, 1):
            on_progress(PipelineEvent(
                "embed",
                f"Frame {i}/{len(frames)} @ {timestamp_s:.1f}s",
                progress=i / max(len(frames), 1),
            ))
            vec = self._embed_bytes(frame_bytes, "image/jpeg")
            node_id = f"vid_{base_meta['id']}_f{i:03d}"
            node = TextNode(
                id_=node_id,
                text=f"[Video frame] {base_meta['original_name']} @ {timestamp_s:.1f}s",
                metadata={
                    **base_meta,
                    "modality": "video",
                    "timestamp_seconds": round(timestamp_s, 2),
                    "frame_index": i,
                },
                embedding=vec,
            )
            self.vector_store.add([node])
            ids.append(node_id)

        on_progress(PipelineEvent("done", f"Indexed video: {base_meta['original_name']} ({len(ids)} frames)", 1.0))
        return ids

    def _ingest_text_file(
        self,
        path: Path,
        base_meta: dict[str, Any],
        on_progress: ProgressCallback,
    ) -> list[str]:
        text = path.read_text(encoding="utf-8", errors="ignore")
        on_progress(PipelineEvent("split", "Chunking text via LlamaIndex SentenceSplitter…"))
        return self.ingest_text(
            text,
            base_meta=base_meta,
            on_progress=on_progress,
        )

    def ingest_text(
        self,
        text: str,
        *,
        base_meta: dict[str, Any] | None = None,
        on_progress: ProgressCallback = _noop,
    ) -> list[str]:
        """Chunk + embed + insert raw text. Uses LlamaIndex IngestionPipeline."""
        from llama_index.core import Document  # local import keeps top-of-file clean

        meta = dict(base_meta or {})
        meta.setdefault("id", uuid.uuid4().hex)
        meta.setdefault("original_name", meta.get("original_name", "text_snippet"))
        meta.setdefault("upload_time", datetime.now().isoformat(timespec="seconds"))
        meta["modality"] = "text"

        doc = Document(text=text, metadata=meta)
        on_progress(PipelineEvent("embed", "Running LlamaIndex IngestionPipeline (split → embed → store)…"))
        nodes = self.text_pipeline.run(documents=[doc], show_progress=False)
        on_progress(PipelineEvent(
            "done",
            f"Indexed text: {meta.get('original_name')} ({len(nodes)} chunks)",
            1.0,
        ))
        return [n.node_id for n in nodes]

    # ===== Retrieval =====

    def search_text(
        self,
        query: str,
        *,
        top_k: int = 5,
        modality_filter: list[str] | None = None,
        on_progress: ProgressCallback = _noop,
    ) -> list[SearchResult]:
        on_progress(PipelineEvent("embed", "Embedding query with Gemini Embedding 2…"))
        qvec = self._embed_query_text(query)
        return self._query_by_embedding(qvec, top_k=top_k, modality_filter=modality_filter, on_progress=on_progress)

    def search_image(
        self,
        image_path: str | Path,
        *,
        top_k: int = 5,
        modality_filter: list[str] | None = None,
        on_progress: ProgressCallback = _noop,
    ) -> list[SearchResult]:
        path = Path(image_path)
        on_progress(PipelineEvent("embed", "Embedding query image (cross-modal)…"))
        data = path.read_bytes()
        mime = MIME_BY_EXT.get(path.suffix.lower(), "image/jpeg")
        qvec = self._embed_bytes(data, mime)
        return self._query_by_embedding(qvec, top_k=top_k, modality_filter=modality_filter, on_progress=on_progress)

    def _query_by_embedding(
        self,
        qvec: list[float],
        *,
        top_k: int,
        modality_filter: list[str] | None,
        on_progress: ProgressCallback,
    ) -> list[SearchResult]:
        on_progress(PipelineEvent("search", f"Searching {self.count()} vectors…"))

        filters = None
        if modality_filter:
            filters = MetadataFilters(
                filters=[MetadataFilter(key="modality", value=m) for m in modality_filter],
                condition="or",
            )

        q = VectorStoreQuery(
            query_embedding=qvec,
            similarity_top_k=top_k,
            filters=filters,
        )
        result = self.vector_store.query(q)
        out: list[SearchResult] = []
        nodes = result.nodes or []
        sims = result.similarities or [None] * len(nodes)
        for node, sim in zip(nodes, sims):
            score = float(sim) if sim is not None else 0.0
            # Chroma returns cosine distance; LlamaIndex normalizes to similarity for some versions.
            # If we somehow got a distance instead, convert.
            if score < 0:
                score = 1.0 + score
            score = max(0.0, min(1.0, score))
            out.append(SearchResult(
                node_id=node.node_id,
                score=score,
                modality=node.metadata.get("modality", "unknown"),
                metadata=dict(node.metadata),
                snippet=node.get_content() if hasattr(node, "get_content") else "",
            ))

        on_progress(PipelineEvent("done", f"Returned {len(out)} result(s)", 1.0))
        return out

    # ===== Bookkeeping =====

    def count(self) -> int:
        return self.collection.count()

    def count_by_modality(self) -> dict[str, int]:
        """Approximate per-modality count via metadata scan."""
        try:
            data = self.collection.get(include=["metadatas"])
        except Exception:
            return {}
        counts: dict[str, int] = {}
        for meta in data.get("metadatas") or []:
            modality = (meta or {}).get("modality", "unknown")
            counts[modality] = counts.get(modality, 0) + 1
        return counts

    def list_items(self, limit: int = 200) -> list[dict[str, Any]]:
        """List stored items grouped by source file (for the manage view)."""
        data = self.collection.get(include=["metadatas"])
        ids = data.get("ids") or []
        metas = data.get("metadatas") or []
        grouped: dict[str, dict[str, Any]] = {}
        for nid, meta in zip(ids, metas):
            meta = meta or {}
            file_id = meta.get("id", nid)
            entry = grouped.setdefault(file_id, {
                "file_id": file_id,
                "original_name": meta.get("original_name", file_id),
                "file_path": meta.get("file_path"),
                "modality": meta.get("modality", "unknown"),
                "upload_time": meta.get("upload_time", ""),
                "node_ids": [],
            })
            entry["node_ids"].append(nid)
        return list(grouped.values())[:limit]

    def delete_by_file_id(self, file_id: str) -> int:
        """Delete all chunks/frames for a single source file. Returns count deleted."""
        data = self.collection.get(where={"id": file_id}, include=["metadatas"])
        ids = data.get("ids") or []
        if not ids:
            return 0
        # Best-effort: also remove the original file from disk
        metas = data.get("metadatas") or []
        for meta in metas:
            fp = (meta or {}).get("file_path")
            if fp and Path(fp).exists():
                Path(fp).unlink(missing_ok=True)
        self.collection.delete(ids=ids)
        return len(ids)

    def clear(self) -> None:
        """Reset the entire KB. Safe; collection is recreated."""
        try:
            self.chroma_client.delete_collection(self.collection_name)
        except Exception:
            pass
        shutil.rmtree(self.upload_dir, ignore_errors=True)
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        # Reinitialize
        self.collection = self.chroma_client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        self.vector_store = ChromaVectorStore(chroma_collection=self.collection)
        self.storage_context = StorageContext.from_defaults(vector_store=self.vector_store)
        self.index = VectorStoreIndex.from_vector_store(
            self.vector_store, embed_model=self.embed_model
        )
        self.text_pipeline = IngestionPipeline(
            transformations=[
                SentenceSplitter(chunk_size=500, chunk_overlap=50),
                self.embed_model,
            ],
            vector_store=self.vector_store,
        )


# ---------- Helpers ----------

def _l2_normalize(vec: list[float] | np.ndarray) -> list[float]:
    arr = np.asarray(vec, dtype=np.float32)
    norm = float(np.linalg.norm(arr))
    if norm > 0:
        arr = arr / norm
    return arr.tolist()


def _human_size(n: int) -> str:
    units = ["B", "KB", "MB", "GB"]
    f = float(n)
    for u in units:
        if f < 1024 or u == units[-1]:
            return f"{f:.1f} {u}"
        f /= 1024
    return f"{n} B"


def _split_pdf(pdf_path: Path, max_pages: int) -> list[tuple[Path, int, int]]:
    """Split a PDF into temp files of <=max_pages each. Returns (path, start_1based, end_1based)."""
    reader = PdfReader(str(pdf_path))
    total = len(reader.pages)
    chunks: list[tuple[Path, int, int]] = []
    for start in range(0, total, max_pages):
        end = min(start + max_pages, total)
        writer = PdfWriter()
        for i in range(start, end):
            writer.add_page(reader.pages[i])
        tmp = Path(tempfile.NamedTemporaryFile(suffix=".pdf", delete=False).name)
        with open(tmp, "wb") as f:
            writer.write(f)
        chunks.append((tmp, start + 1, end))
    return chunks


def render_pdf_page(pdf_path: Path, page_index_0based: int = 0, zoom: float = 1.5) -> Image.Image:
    """Render a PDF page to a PIL.Image. Used for previews and vision-RAG context."""
    doc = fitz.open(str(pdf_path))
    try:
        idx = max(0, min(page_index_0based, len(doc) - 1))
        page = doc[idx]
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
        return Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    finally:
        doc.close()


def _video_duration_seconds(path: Path) -> float:
    cap = cv2.VideoCapture(str(path))
    try:
        fps = cap.get(cv2.CAP_PROP_FPS) or 0
        frames = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
        if fps <= 0:
            return 0.0
        return float(frames) / float(fps)
    finally:
        cap.release()


def _sample_video_frames(path: Path, interval_s: float) -> list[tuple[float, bytes]]:
    """Return [(timestamp_seconds, jpeg_bytes), ...] sampled every interval_s."""
    cap = cv2.VideoCapture(str(path))
    samples: list[tuple[float, bytes]] = []
    try:
        fps = cap.get(cv2.CAP_PROP_FPS) or 0
        total = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
        if fps <= 0 or total <= 0:
            return samples
        step_frames = max(int(round(fps * interval_s)), 1)
        idx = 0
        while idx < total:
            cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ok, frame = cap.read()
            if not ok:
                break
            ok2, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
            if ok2:
                samples.append((idx / fps, buf.tobytes()))
            idx += step_frames
    finally:
        cap.release()
    return samples


def load_video_frame_at(path: Path, timestamp_s: float) -> Image.Image | None:
    """Load a single frame for preview. Returns PIL.Image or None."""
    cap = cv2.VideoCapture(str(path))
    try:
        fps = cap.get(cv2.CAP_PROP_FPS) or 0
        if fps <= 0:
            return None
        frame_idx = int(round(timestamp_s * fps))
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ok, frame = cap.read()
        if not ok:
            return None
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        return Image.fromarray(rgb)
    finally:
        cap.release()
