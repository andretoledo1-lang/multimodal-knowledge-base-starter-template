"""GET previews for ingested files (image / pdf-page / video-frame)."""
from __future__ import annotations

import io
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, Response

from ..deps import get_kb
from ..kb import KnowledgeBase, load_video_frame_at, render_pdf_page

router = APIRouter(tags=["preview"])
logger = logging.getLogger("kb.preview")


def _lookup_file(kb: KnowledgeBase, file_id: str) -> tuple[Path, dict]:
    """Locate the on-disk path and any metadata for a given file_id.

    Defensive check: the resolved path must live inside `kb.upload_dir` so a
    corrupted/forged metadata row cannot trick us into serving arbitrary files.
    """
    data = kb.collection.get(where={"id": file_id}, include=["metadatas"])
    metas = data.get("metadatas") or []
    if not metas:
        raise HTTPException(status_code=404, detail=f"No item with file_id={file_id}")
    meta = metas[0] or {}
    fp = meta.get("file_path")
    if not fp:
        raise HTTPException(status_code=404, detail="Item has no file path")
    path = Path(fp).resolve()
    upload_root = kb.upload_dir.resolve()
    if not path.is_relative_to(upload_root):
        logger.warning("Refusing to serve %s — outside upload_dir %s", path, upload_root)
        raise HTTPException(status_code=404, detail="File not available")
    if not path.exists():
        raise HTTPException(status_code=410, detail="File no longer on disk")
    return path, meta


def _jpeg_response(img) -> Response:
    buf = io.BytesIO()
    if img.mode != "RGB":
        img = img.convert("RGB")
    img.save(buf, format="JPEG", quality=85)
    return Response(content=buf.getvalue(), media_type="image/jpeg")


@router.get("/preview/{file_id}")
def preview_image(file_id: str, kb: KnowledgeBase = Depends(get_kb)):
    path, meta = _lookup_file(kb, file_id)
    if meta.get("modality") != "image":
        raise HTTPException(status_code=400, detail="This file is not an image")
    return FileResponse(str(path))


@router.get("/preview/{file_id}/pdf-page/{page_1based}")
def preview_pdf_page(file_id: str, page_1based: int, kb: KnowledgeBase = Depends(get_kb)):
    path, meta = _lookup_file(kb, file_id)
    if meta.get("modality") != "pdf":
        raise HTTPException(status_code=400, detail="This file is not a PDF")
    img = render_pdf_page(path, page_index_0based=max(0, page_1based - 1), zoom=1.5)
    return _jpeg_response(img)


@router.get("/preview/{file_id}/video-frame")
def preview_video_frame(
    file_id: str,
    t: float = Query(default=0.0, ge=0.0),
    kb: KnowledgeBase = Depends(get_kb),
):
    path, meta = _lookup_file(kb, file_id)
    if meta.get("modality") != "video":
        raise HTTPException(status_code=400, detail="This file is not a video")
    img = load_video_frame_at(path, t)
    if img is None:
        raise HTTPException(status_code=404, detail=f"No frame available at t={t}")
    return _jpeg_response(img)
