"""
Multimodal vision RAG.

After retrieving the top-k items from the KB, we attach the actual visual
content (image bytes, rendered PDF page, sampled video frame) to the prompt
so Gemini 2.5 Flash literally *sees* what was retrieved.

This is what makes "the chart on page 4 of the PDF answers my text question"
actually work.
"""
from __future__ import annotations

import io
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

from google import genai
from google.genai import types
from PIL import Image

from .kb import (
    KnowledgeBase,
    PipelineEvent,
    SearchResult,
    load_video_frame_at,
    render_pdf_page,
)

DEFAULT_VISION_MODEL = "gemini-2.5-flash"


@dataclass
class GroundedAnswer:
    answer: str
    sources: list[SearchResult]
    visual_attachments: int  # how many image-bearing parts we sent to the LLM


def _pdf_page_for_result(r: SearchResult) -> int:
    """Return 0-based page index to render for a PDF result."""
    page = r.metadata.get("page") or r.metadata.get("page_start")
    return max(0, int(page) - 1) if page else 0


def _image_to_bytes(img: Image.Image, fmt: str = "JPEG", quality: int = 85) -> bytes:
    buf = io.BytesIO()
    if img.mode != "RGB":
        img = img.convert("RGB")
    img.save(buf, format=fmt, quality=quality)
    return buf.getvalue()


def build_multimodal_context(
    results: list[SearchResult],
    *,
    max_images: int = 6,
) -> tuple[list, list[str]]:
    """
    Turn search results into a multimodal `contents` list for Gemini.

    Returns (contents_parts, source_descriptions). The caller should prepend
    the user's question.
    """
    parts: list = []
    descriptions: list[str] = []
    image_count = 0

    for i, r in enumerate(results, 1):
        meta = r.metadata
        name = r.display_name
        modality = r.modality
        loc = ""
        if modality == "pdf" and meta.get("page_start"):
            start = int(meta["page_start"])
            end = int(meta.get("page_end") or start)
            total = meta.get("total_pages")
            label = f"page {start}" if start == end else f"pages {start}-{end}"
            loc = f" ({label} of {total})" if total else f" ({label})"
        elif modality == "video" and meta.get("timestamp_seconds") is not None:
            loc = f" (@ {meta['timestamp_seconds']}s)"

        descriptions.append(f"[{i}] {name}{loc} — {modality}, similarity {r.score:.0%}")

        if image_count >= max_images:
            continue

        path = r.file_path
        if not path or not path.exists():
            # Pure-text result (or media file lost): include the snippet as text
            if r.snippet:
                parts.append(f"Source [{i}] {name}: {r.snippet[:1500]}")
            continue

        try:
            if modality == "image":
                parts.append(types.Part.from_bytes(
                    data=path.read_bytes(),
                    mime_type=_guess_image_mime(path),
                ))
                parts.append(f"^ Source [{i}]: {name}")
                image_count += 1
            elif modality == "pdf":
                page_idx = _pdf_page_for_result(r)
                img = render_pdf_page(path, page_idx, zoom=2.0)
                parts.append(types.Part.from_bytes(
                    data=_image_to_bytes(img),
                    mime_type="image/jpeg",
                ))
                parts.append(f"^ Source [{i}]: {name} (rendered page {page_idx + 1})")
                image_count += 1
            elif modality == "video":
                ts = float(meta.get("timestamp_seconds") or 0.0)
                img = load_video_frame_at(path, ts)
                if img is None:
                    continue
                parts.append(types.Part.from_bytes(
                    data=_image_to_bytes(img),
                    mime_type="image/jpeg",
                ))
                parts.append(f"^ Source [{i}]: {name} @ {ts:.1f}s")
                image_count += 1
            elif modality == "text":
                if r.snippet:
                    parts.append(f"Source [{i}] {name}:\n{r.snippet[:1500]}")
        except Exception as e:  # noqa: BLE001
            parts.append(f"Source [{i}] {name}: (could not load preview: {e})")

    return parts, descriptions


def _guess_image_mime(path: Path) -> str:
    return {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".gif": "image/gif",
    }.get(path.suffix.lower(), "image/jpeg")


SYSTEM_PROMPT = """You are a multimodal research assistant grounded in the user's knowledge base.
You will be shown a question and a set of retrieved sources. Some sources are images, some are rendered PDF pages, some are video frames, some are text excerpts.

Rules:
- Answer using only the retrieved sources. If the answer isn't there, say so.
- Cite sources inline as [1], [2], etc. matching the numbered list provided.
- For PDF sources, include the page number in your prose (e.g. "on page 4 [1]") so the reader can verify.
- When the answer involves something visible in an image/PDF/video, describe what you see.
- Be concise but specific. Prefer 2-5 short paragraphs over a single wall of text."""


def answer_with_vision(
    kb: KnowledgeBase,
    question: str,
    *,
    top_k: int = 5,
    modality_filter: list[str] | None = None,
    model: str = DEFAULT_VISION_MODEL,
    max_images: int = 6,
    on_progress=None,
) -> Iterator[GroundedAnswer | str]:
    """
    Streaming generator. Yields:
        - intermediate string chunks (the answer being streamed),
        - a final GroundedAnswer object once complete.

    Usage:
        for chunk in answer_with_vision(kb, "..."):
            if isinstance(chunk, str):
                placeholder.markdown(running + chunk)
                running += chunk
            else:
                final = chunk
    """
    on_progress = on_progress or (lambda _e: None)

    # 1. Retrieve
    results = kb.search_text(
        question,
        top_k=top_k,
        modality_filter=modality_filter,
        on_progress=on_progress,
    )
    if not results:
        on_progress(PipelineEvent("done", "No results - cannot ground answer."))
        yield GroundedAnswer(
            answer="I couldn't find anything relevant in your knowledge base. Try indexing more content first.",
            sources=[],
            visual_attachments=0,
        )
        return

    # 2. Build multimodal context (attach actual bytes for vision)
    on_progress(PipelineEvent("compose", f"Attaching visual context for {len(results)} source(s)…"))
    visual_parts, source_lines = build_multimodal_context(results, max_images=max_images)
    visual_count = sum(1 for p in visual_parts if not isinstance(p, str))

    # 3. Build prompt
    sources_block = "\n".join(source_lines)
    prompt = (
        f"{SYSTEM_PROMPT}\n\n"
        f"Question: {question}\n\n"
        f"Retrieved sources:\n{sources_block}\n\n"
        f"Use the attached images and text below as context. Answer now."
    )
    contents = [prompt, *visual_parts]

    # 4. Stream from Gemini 2.5 Flash
    on_progress(PipelineEvent("generate", f"Calling {model} with {visual_count} image part(s)…"))
    full = []
    stream = kb.genai_client.models.generate_content_stream(
        model=model,
        contents=contents,
    )
    for chunk in stream:
        if chunk.text:
            full.append(chunk.text)
            yield chunk.text

    on_progress(PipelineEvent("done", "Answer complete.", 1.0))
    yield GroundedAnswer(
        answer="".join(full),
        sources=results,
        visual_attachments=visual_count,
    )
