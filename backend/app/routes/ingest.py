"""POST /api/ingest, POST /api/clear."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from starlette.concurrency import run_in_threadpool

from ..deps import get_kb
from ..kb import KnowledgeBase
from ..schemas import (
    ClearResponse,
    IngestItemDTO,
    IngestResponse,
    preview_url_for,
)
from ._uploads import upload_to_tempfile

router = APIRouter(tags=["ingest"])
logger = logging.getLogger("kb.ingest")


def _ingest_one(kb: KnowledgeBase, src: Path, original_name: str,
                tags: list[str], video_frame_interval_s: int) -> IngestItemDTO:
    node_ids = kb.ingest_path(
        src,
        original_name=original_name,
        tags=tags or None,
        video_frame_interval_s=video_frame_interval_s,
    )
    # Fish metadata back out from one of the new nodes
    data = kb.collection.get(ids=[node_ids[0]], include=["metadatas"])
    meta = (data.get("metadatas") or [{}])[0] or {}
    file_id = meta.get("id", "")
    return IngestItemDTO(
        file_id=file_id,
        original_name=meta.get("original_name", original_name),
        modality=meta.get("modality", "unknown"),
        node_ids=node_ids,
        total_pages=meta.get("total_pages"),
        duration_seconds=meta.get("duration_seconds"),
        preview_url=preview_url_for(meta),
    )


@router.post("/ingest", response_model=IngestResponse)
async def ingest(
    files: Annotated[list[UploadFile], File(description="One or more files to index")],
    tags: Annotated[str, Form()] = "",
    video_frame_interval_s: Annotated[int, Form()] = 5,
    kb: KnowledgeBase = Depends(get_kb),
) -> IngestResponse:
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    items: list[IngestItemDTO] = []
    for upload in files:
        async with upload_to_tempfile(upload) as tmp_path:
            try:
                item = await run_in_threadpool(
                    _ingest_one,
                    kb, tmp_path,
                    upload.filename or tmp_path.name,
                    tag_list,
                    video_frame_interval_s,
                )
            except Exception as e:  # noqa: BLE001
                logger.exception("Ingest failed for %s", upload.filename)
                raise HTTPException(status_code=500, detail=f"Ingest failed for {upload.filename}: {e}") from e
            items.append(item)
    logger.info("Ingested %d file(s); total vectors now: %d", len(items), kb.count())
    return IngestResponse(items=items, total=len(items))


@router.post("/clear", response_model=ClearResponse)
async def clear(kb: KnowledgeBase = Depends(get_kb)) -> ClearResponse:
    await run_in_threadpool(kb.clear)
    logger.info("Cleared knowledge base")
    return ClearResponse(cleared=True)
