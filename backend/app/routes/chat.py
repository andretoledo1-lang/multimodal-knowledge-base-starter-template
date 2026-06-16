"""POST /api/chat — Server-Sent Events stream of tokens + final sources event."""
from __future__ import annotations

import json
import logging
from collections.abc import Iterator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from ..deps import get_kb
from ..kb import KnowledgeBase
from ..providers import ProviderError
from ..rag import GroundedAnswer, answer_with_vision
from ..schemas import ChatRequest, search_result_to_dto

router = APIRouter(tags=["chat"])
logger = logging.getLogger("kb.chat")


def _sse(event: str | None, data: str) -> str:
    """Format a single SSE frame. Empty event name → default 'message'."""
    prefix = f"event: {event}\n" if event else ""
    # Data must be JSON-encoded so newlines/quotes inside tokens are safe.
    return f"{prefix}data: {data}\n\n"


def _stream(kb: KnowledgeBase, req: ChatRequest) -> Iterator[str]:
    token_count = 0
    final: GroundedAnswer | None = None

    try:
        for chunk in answer_with_vision(
            kb,
            req.question,
            top_k=req.top_k,
            modality_filter=req.modality_filter,
            chat_model=req.chat_model,
            max_images=req.max_images,
        ):
            if isinstance(chunk, str):
                token_count += 1
                yield _sse(None, json.dumps(chunk))
            else:
                final = chunk
    except ProviderError:
        logger.exception("Chat provider failed")
        yield _sse(
            "error",
            json.dumps({"message": f"Selected chat mode {req.chat_model} is currently unavailable."}),
        )
        yield _sse("done", "{}")
        return
    except Exception as e:  # noqa: BLE001
        logger.exception("Chat stream failed")
        yield _sse("error", json.dumps({"message": str(e)}))
        yield _sse("done", "{}")
        return

    sources_payload: dict = {"sources": [], "visual_attachments": 0}
    if final is not None:
        sources_payload["visual_attachments"] = final.visual_attachments
        sources_payload["sources"] = [
            search_result_to_dto(r).model_dump() for r in final.sources
        ]
        if final.citation_validation is not None:
            sources_payload["citation_validation"] = final.citation_validation.to_payload()

    logger.info(
        "chat q=%r tokens=%d sources=%d visuals=%d",
        req.question, token_count,
        len(sources_payload["sources"]),
        sources_payload["visual_attachments"],
    )
    yield _sse("sources", json.dumps(sources_payload))
    yield _sse("done", "{}")


@router.post("/chat")
def chat(req: ChatRequest, kb: KnowledgeBase = Depends(get_kb)) -> StreamingResponse:
    return StreamingResponse(
        _stream(kb, req),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
