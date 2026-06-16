"""Grounded chat over multimodal retrieval results."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any
from typing import Iterator

from pydantic import ValidationError

from .chat_models import CHAT_MODEL_CLAUDE_OPUS, CHAT_MODEL_DEEPSEEK, ChatModelId
from .chat_profiles import get_chat_profile
from .chat_prompts import get_prompt_bundle_for_chat_model, get_role_prompt_bundle
from .chat_workers import JudgeResult, WorkerResult, validate_judge_result, validate_worker_result
from .citations import CitationValidation, validate_citations
from .kb import (
    KnowledgeBase,
    PipelineEvent,
    SearchResult,
)
from .providers import ProviderError

DEFAULT_CHAT_MODEL = CHAT_MODEL_DEEPSEEK
logger = logging.getLogger("kb.chat.orchestration")


@dataclass
class GroundedAnswer:
    answer: str
    sources: list[SearchResult]
    visual_attachments: int  # how many image-bearing parts we sent to the LLM
    citation_validation: CitationValidation | None = None


def build_grounded_context(
    results: list[SearchResult],
) -> tuple[str, list[str], int]:
    """Build a text context block from retrieved multimodal source cards."""
    context_lines: list[str] = []
    descriptions: list[str] = []
    visual_count = 0

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
        if modality in {"image", "pdf", "video"}:
            visual_count += 1
        context_lines.append(f"Source [{i}]")
        context_lines.append(f"Name: {name}{loc}")
        context_lines.append(f"Modality: {modality}")
        if meta.get("vector_score") is not None:
            context_lines.append(f"Vector score: {meta['vector_score']}")
        if meta.get("rerank_score") is not None:
            context_lines.append(f"Rerank score: {meta['rerank_score']}")
        if r.snippet:
            context_lines.append(f"Snippet: {r.snippet[:1800]}")
        elif modality in {"image", "pdf", "video"}:
            context_lines.append(
                "Visual source retrieved by multimodal embedding. No generated caption is stored yet."
            )
        context_lines.append("")

    return "\n".join(context_lines).strip(), descriptions, visual_count


def answer_with_vision(
    kb: KnowledgeBase,
    question: str,
    *,
    top_k: int = 5,
    modality_filter: list[str] | None = None,
    chat_model: ChatModelId = DEFAULT_CHAT_MODEL,
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

    # 2. Build grounded source context
    on_progress(PipelineEvent("compose", f"Composing grounded context for {len(results)} source(s)..."))
    source_context, source_lines, visual_count = build_grounded_context(results)

    if chat_model == CHAT_MODEL_CLAUDE_OPUS:
        yield from _answer_with_claude_premium(
            kb=kb,
            question=question,
            results=results,
            source_context=source_context,
            source_lines=source_lines,
            visual_count=visual_count,
            on_progress=on_progress,
        )
        return

    # 3. Build prompt
    prompt_bundle = get_prompt_bundle_for_chat_model(chat_model)
    sources_block = "\n".join(source_lines)
    user_prompt = (
        f"Question: {question}\n\n"
        f"Retrieved sources:\n{sources_block}\n\n"
        f"Source context:\n{source_context}\n\n"
        f"Answer now."
    )

    # 4. Stream from the selected chat model
    on_progress(PipelineEvent("generate", f"Calling {chat_model} with {len(results)} grounded source(s)..."))
    full = []
    for chunk in kb.chat_client_for_model(chat_model).stream_chat(
        [
            {"role": "system", "content": prompt_bundle.system_prompt},
            {"role": "user", "content": user_prompt},
        ]
    ):
        full.append(chunk)
        yield chunk

    answer = "".join(full)
    citation_validation = validate_citations(answer, source_count=len(results))
    on_progress(PipelineEvent("done", "Answer complete.", 1.0))
    yield GroundedAnswer(
        answer=answer,
        sources=results,
        visual_attachments=visual_count,
        citation_validation=citation_validation,
    )


def _answer_with_claude_premium(
    *,
    kb: KnowledgeBase,
    question: str,
    results: list[SearchResult],
    source_context: str,
    source_lines: list[str],
    visual_count: int,
    on_progress,
) -> Iterator[GroundedAnswer | str]:
    profile = get_chat_profile(CHAT_MODEL_CLAUDE_OPUS)
    premium = profile.premium
    if premium is None:
        raise ProviderError("Claude Opus Premium mode is not configured.")

    prompt_bundle = get_prompt_bundle_for_chat_model(CHAT_MODEL_CLAUDE_OPUS)
    sources_block = "\n".join(source_lines)
    repair_cap = max(1, min(getattr(kb, "claude_premium_repair_cap", premium.repair_cap), 2))

    on_progress(PipelineEvent("generate", "Preparing Premium grounded answer..."))
    dispatch = _run_opus_dispatch(
        kb=kb,
        system_prompt=prompt_bundle.system_prompt,
        question=question,
        sources_block=sources_block,
        source_context=source_context,
    )
    logger.info(
        "claude_premium dispatch decision=%s plan_items=%d",
        dispatch.get("decision"),
        len(dispatch.get("plan") if isinstance(dispatch.get("plan"), list) else []),
    )

    worker_results: list[WorkerResult] = []
    if dispatch.get("decision") == "dispatch":
        try:
            worker_results = _run_premium_helpers(
                kb=kb,
                question=question,
                sources_block=sources_block,
                source_context=source_context,
                plan=dispatch.get("plan") if isinstance(dispatch.get("plan"), list) else [],
            )
        except Exception:
            # Hidden helpers are optional. If fan-out fails, the same-provider
            # principal answers directly over the source cards.
            worker_results = []
    logger.info("claude_premium accepted_helper_results=%d", len(worker_results))

    answer = _run_opus_final_answer(
        kb=kb,
        system_prompt=prompt_bundle.system_prompt,
        question=question,
        sources_block=sources_block,
        source_context=source_context,
        worker_results=worker_results,
        revision_notes=[],
    )

    iteration = 0
    while iteration <= repair_cap:
        judge = _run_opus_judge(
            kb=kb,
            question=question,
            sources_block=sources_block,
            source_context=source_context,
            answer=answer,
            iteration=iteration,
        )
        logger.info(
            "claude_premium judge iteration=%d verdict=%s",
            iteration,
            getattr(judge, "verdict", "unavailable"),
        )
        if judge is None or judge.verdict == "pass" or iteration >= repair_cap:
            break
        iteration += 1
        logger.info("claude_premium repair iteration=%d", iteration)
        answer = _run_opus_final_answer(
            kb=kb,
            system_prompt=prompt_bundle.system_prompt,
            question=question,
            sources_block=sources_block,
            source_context=source_context,
            worker_results=worker_results,
            revision_notes=judge.revision_notes,
        )

    citation_validation = validate_citations(answer, source_count=len(results))
    on_progress(PipelineEvent("done", "Answer complete.", 1.0))
    yield answer
    yield GroundedAnswer(
        answer=answer,
        sources=results,
        visual_attachments=visual_count,
        citation_validation=citation_validation,
    )


def _run_opus_dispatch(
    *,
    kb: KnowledgeBase,
    system_prompt: str,
    question: str,
    sources_block: str,
    source_context: str,
) -> dict[str, Any]:
    prompt = (
        "Mode: dispatch_planning\n"
        "Return only a JSON object with mode, decision, reason, and plan.\n"
        "Allowed decision values: no_dispatch, dispatch.\n"
        "Allowed helper values inside plan: worker, chief.\n\n"
        f"Question: {question}\n\n"
        f"Retrieved sources:\n{sources_block}\n\n"
        f"Source context:\n{source_context}\n"
    )
    try:
        payload = _parse_json_object(
            _complete_chat(
                kb.claude_opus_chat_client,
                [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
            )
        )
    except Exception:
        return {"mode": "dispatch_planning", "decision": "no_dispatch", "reason": "dispatch unavailable", "plan": []}

    if payload.get("mode") != "dispatch_planning":
        return {"mode": "dispatch_planning", "decision": "no_dispatch", "reason": "invalid mode", "plan": []}
    if payload.get("decision") not in {"no_dispatch", "dispatch"}:
        payload["decision"] = "no_dispatch"
        payload["plan"] = []
    plan = payload.get("plan")
    if not isinstance(plan, list):
        payload["plan"] = []
    return payload


def _run_premium_helpers(
    *,
    kb: KnowledgeBase,
    question: str,
    sources_block: str,
    source_context: str,
    plan: list[object],
) -> list[WorkerResult]:
    results: list[WorkerResult] = []
    for raw_item in plan[:4]:
        if not isinstance(raw_item, dict):
            continue
        helper = raw_item.get("helper")
        if helper not in {"worker", "chief"}:
            continue
        prompt_id = "sonnet_chief" if helper == "chief" else "haiku_worker"
        visibility = "chief" if helper == "chief" else "worker"
        client = (
            kb.claude_sonnet_chief_client
            if helper == "chief"
            else kb.claude_haiku_worker_client
        )
        bundle = get_role_prompt_bundle(prompt_id, visibility=visibility)
        assigned = str(raw_item.get("extract") or raw_item.get("cluster") or question)
        prompt = (
            "Return only the internal JSON object requested by your role.\n\n"
            f"Assigned subtask: {assigned}\n\n"
            f"Question: {question}\n\n"
            f"Retrieved sources:\n{sources_block}\n\n"
            f"Source context:\n{source_context}\n"
        )
        payload = _parse_json_object(
            _complete_chat(
                client,
                [
                    {"role": "system", "content": bundle.system_prompt},
                    {"role": "user", "content": prompt},
                ],
            )
        )
        results.append(validate_worker_result(payload))
    return results


def _run_opus_final_answer(
    *,
    kb: KnowledgeBase,
    system_prompt: str,
    question: str,
    sources_block: str,
    source_context: str,
    worker_results: list[WorkerResult],
    revision_notes: list[str],
) -> str:
    worker_block = ""
    if worker_results:
        worker_block = (
            "\n\nInternal same-provider findings, already validated as non-final evidence summaries:\n"
            + json.dumps([item.model_dump() for item in worker_results], ensure_ascii=False)
        )
    repair_block = ""
    if revision_notes:
        repair_block = (
            "\n\nInternal quality notes for this revision. Address them without mentioning them:\n"
            + "\n".join(f"- {note}" for note in revision_notes)
        )
    prompt = (
        "Mode: final_answer\n"
        "Return only the final user-facing answer. Cite source numbers like [1].\n\n"
        f"Question: {question}\n\n"
        f"Retrieved sources:\n{sources_block}\n\n"
        f"Source context:\n{source_context}"
        f"{worker_block}"
        f"{repair_block}\n\n"
        "Answer now."
    )
    try:
        answer = _complete_chat(
            kb.claude_opus_chat_client,
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
        )
    except Exception as exc:
        raise ProviderError("Claude Opus Premium mode failed to produce an answer.") from exc
    if not answer.strip():
        raise ProviderError("Claude Opus Premium mode returned an empty answer.")
    return answer.strip()


def _run_opus_judge(
    *,
    kb: KnowledgeBase,
    question: str,
    sources_block: str,
    source_context: str,
    answer: str,
    iteration: int,
) -> JudgeResult | None:
    bundle = get_role_prompt_bundle("opus_judge", visibility="judge")
    prompt = (
        "Return only the internal JSON object requested by your role.\n"
        "Evaluate only the question, source cards, and candidate answer below.\n\n"
        f"Iteration: {iteration}\n\n"
        f"Question: {question}\n\n"
        f"Retrieved sources:\n{sources_block}\n\n"
        f"Source context:\n{source_context}\n\n"
        f"Candidate answer:\n{answer}\n"
    )
    try:
        payload = _parse_json_object(
            _complete_chat(
                kb.claude_opus_judge_client,
                [
                    {"role": "system", "content": bundle.system_prompt},
                    {"role": "user", "content": prompt},
                ],
            )
        )
        payload = _normalize_judge_payload(payload, iteration=iteration)
        judge = validate_judge_result(payload)
    except (ValidationError, ValueError, ProviderError, AttributeError) as exc:
        logger.info("claude_premium judge unavailable reason=%s", type(exc).__name__)
        return None
    if judge.iteration != iteration:
        return judge.model_copy(update={"iteration": iteration})
    return judge


def _normalize_judge_payload(payload: dict[str, Any], *, iteration: int) -> dict[str, Any]:
    normalized = dict(payload)
    verdict = normalized.get("verdict")
    if isinstance(verdict, str):
        normalized["verdict"] = verdict.lower()
    notes = normalized.get("dimension_notes")
    if notes is None:
        normalized["dimension_notes"] = {}
    elif not isinstance(notes, dict):
        normalized["dimension_notes"] = {"grounding": str(notes)}
    revision_notes = normalized.get("revision_notes")
    if revision_notes is None:
        normalized["revision_notes"] = []
    elif isinstance(revision_notes, str):
        normalized["revision_notes"] = [revision_notes]
    normalized.setdefault("unknown", False)
    normalized["iteration"] = iteration
    return normalized


def _complete_chat(client, messages: list[dict[str, str]]) -> str:
    if hasattr(client, "complete_chat"):
        return str(client.complete_chat(messages)).strip()
    return "".join(client.stream_chat(messages)).strip()


def _parse_json_object(text: str) -> dict[str, Any]:
    raw = text.strip()
    if raw.startswith("```"):
        lines = raw.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        raw = "\n".join(lines).strip()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        parsed = _extract_first_json_object(raw)
    if isinstance(parsed, dict) and isinstance(parsed.get("structured_output"), dict):
        parsed = parsed["structured_output"]
    if not isinstance(parsed, dict):
        raise ValueError("Expected JSON object.")
    return parsed


def _extract_first_json_object(raw: str) -> object:
    decoder = json.JSONDecoder()
    for index, char in enumerate(raw):
        if char != "{":
            continue
        try:
            parsed, _end = decoder.raw_decode(raw[index:])
        except json.JSONDecodeError:
            continue
        return parsed
    raise ValueError("Expected JSON object.")
