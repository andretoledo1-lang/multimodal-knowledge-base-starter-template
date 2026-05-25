"""GET /api/items, DELETE /api/items/{file_id}, GET /api/stats."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException

from ..deps import get_kb
from ..kb import KnowledgeBase
from ..schemas import (
    DeleteResponse,
    ItemDTO,
    ItemsResponse,
    StatsResponse,
    preview_url_for,
)

router = APIRouter(tags=["library"])
logger = logging.getLogger("kb.library")


@router.get("/items", response_model=ItemsResponse)
def list_items(kb: KnowledgeBase = Depends(get_kb)) -> ItemsResponse:
    raw = kb.list_items()
    items = []
    for r in raw:
        items.append(
            ItemDTO(
                file_id=r["file_id"],
                original_name=r["original_name"],
                modality=r.get("modality", "unknown"),
                upload_time=r.get("upload_time", ""),
                node_ids=r.get("node_ids", []),
                preview_url=preview_url_for(
                    {"id": r["file_id"], "modality": r.get("modality")}
                ),
            )
        )
    items.sort(key=lambda x: x.upload_time, reverse=True)
    return ItemsResponse(items=items)


@router.delete("/items/{file_id}", response_model=DeleteResponse)
def delete_item(file_id: str, kb: KnowledgeBase = Depends(get_kb)) -> DeleteResponse:
    n = kb.delete_by_file_id(file_id)
    if n == 0:
        raise HTTPException(status_code=404, detail=f"No item with file_id={file_id}")
    logger.info("Deleted %d vectors for file_id=%s", n, file_id)
    return DeleteResponse(deleted=n)


@router.get("/stats", response_model=StatsResponse)
def stats(kb: KnowledgeBase = Depends(get_kb)) -> StatsResponse:
    return StatsResponse(total=kb.count(), by_modality=kb.count_by_modality())
