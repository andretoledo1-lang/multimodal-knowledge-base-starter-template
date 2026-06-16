"""GET /api/items, DELETE /api/items/{file_id}, GET /api/stats."""
from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from ..deps import get_kb
from ..kb import KnowledgeBase
from ..schemas import (
    DeleteResponse,
    ItemDTO,
    ItemDetailResponse,
    ItemsResponse,
    StatsResponse,
    item_detail_to_dto,
    preview_url_for,
)

router = APIRouter(tags=["library"])
logger = logging.getLogger("kb.library")


@router.get("/items", response_model=ItemsResponse)
def list_items(
    limit: Annotated[int | None, Query(ge=1)] = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    kb: KnowledgeBase = Depends(get_kb),
) -> ItemsResponse:
    raw, total = kb.list_items(limit=limit, offset=offset)
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
                    {
                        "id": r["file_id"],
                        "modality": r.get("modality"),
                        "preview_image_file_id": r.get("preview_image_file_id"),
                    }
                ),
            )
        )
    items.sort(key=lambda x: x.upload_time, reverse=True)
    return ItemsResponse(items=items, total=total, returned=len(items), limit=limit, offset=offset)


@router.get("/items/lookup", response_model=ItemDetailResponse)
def get_item(
    file_id: Annotated[str | None, Query()] = None,
    node_id: Annotated[str | None, Query()] = None,
    kb: KnowledgeBase = Depends(get_kb),
) -> ItemDetailResponse:
    if bool(file_id) == bool(node_id):
        raise HTTPException(status_code=400, detail="Pass exactly one of file_id or node_id")
    try:
        item = kb.get_item(file_id=file_id, node_id=node_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if item is None:
        target = f"file_id={file_id}" if file_id else f"node_id={node_id}"
        raise HTTPException(status_code=404, detail=f"No item with {target}")
    return item_detail_to_dto(item)


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
