"""Deterministic curatorial rerank for DanteDash visual package candidates."""
from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass
from typing import Any


QUALITY_TERMS = {
    "best",
    "cinematic",
    "cinematografico",
    "cinematograficos",
    "elite",
    "excellent",
    "iconic",
    "incrivel",
    "incriveis",
    "inusitado",
    "inusitados",
    "melhor",
    "melhores",
    "premium",
    "reference",
    "s tier",
    "s-tier",
    "strong",
    "tier",
}
VISUAL_CRAFT_TERMS = {
    "aesthetic",
    "aesthetics",
    "camera",
    "composition",
    "composicao",
    "contrast",
    "color",
    "cor",
    "craft",
    "enquadramento",
    "estetica",
    "frame",
    "imagem",
    "imagens",
    "lens",
    "lente",
    "light",
    "lighting",
    "luz",
    "shot",
    "shots",
    "texture",
    "visual",
}
STOPWORDS = {
    "a",
    "as",
    "com",
    "da",
    "das",
    "de",
    "do",
    "dos",
    "e",
    "em",
    "for",
    "from",
    "me",
    "mostre",
    "of",
    "os",
    "para",
    "show",
    "s",
    "the",
    "um",
    "uma",
    "with",
}
TITLE_KEYS = ("title", "display_name", "original_name", "source_title", "document_title")
IDENTITY_KEYS = TITLE_KEYS + ("group", "film_title", "dante_image_id", "image_id", "id", "file_id", "node_id")
TEXT_KEYS = TITLE_KEYS + (
    "snippet",
    "excerpt",
    "text",
    "content",
    "chunk_text",
    "summary",
    "one_line",
    "decoupage_spine",
    "composition",
    "camera_lens",
    "lighting",
    "color",
    "art_direction",
    "performance",
    "lineage",
    "distinction",
    "opinion",
)

YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")
FRAME_RE = re.compile(r"\b(?:frame|shot|imagem|image)\s*0*(\d{1,4})\b")
NUMBER_RE = re.compile(r"\b0*(\d{1,4})\b")


@dataclass(frozen=True)
class CuratorialRerankOutcome:
    items: list[dict[str, Any]]
    intent: str
    insufficient: bool


@dataclass(frozen=True)
class _QueryFeatures:
    normalized: str
    tokens: list[str]
    years: set[str]
    frames: set[str]
    intent: str


@dataclass(frozen=True)
class _ScoredItem:
    item: dict[str, Any]
    original_index: int
    score: float
    vector_score: float
    exact_score: float
    quality_score: float
    layer_score: float
    preview_score: float
    reason: str
    package_key: str
    family_key: str


def curatorial_rerank(
    query: str,
    items: list[dict[str, Any]],
    *,
    max_per_family: int = 2,
    limit: int | None = None,
) -> CuratorialRerankOutcome:
    """Return copied KH package items ordered for visual-curatorial usefulness."""
    query_features = _query_features(query)
    intent = query_features.intent
    scored = [_score_item(query_features, item, index, intent) for index, item in enumerate(items)]
    ranked = sorted(scored, key=lambda row: (-row.score, -row.vector_score, row.original_index))
    if intent in {"quality", "visual_craft", "generic"}:
        ranked = _diversify(ranked, max_per_family=max_per_family)
    insufficient = _is_insufficient(intent, ranked)
    selected = ranked[:limit] if limit is not None else ranked
    return CuratorialRerankOutcome(
        items=[_annotate(row, intent=intent, insufficient=insufficient) for row in selected],
        intent=intent,
        insufficient=insufficient,
    )


def detect_curatorial_intent(query: str) -> str:
    return _query_features(query).intent


def _query_features(query: str) -> _QueryFeatures:
    normalized = _normalize(query)
    tokens = [
        token
        for token in _tokens(normalized)
        if token not in QUALITY_TERMS and token not in VISUAL_CRAFT_TERMS
    ]
    years = set(YEAR_RE.findall(normalized))
    frames = set(FRAME_RE.findall(normalized))
    if years or frames:
        intent = "exact"
    elif _contains_any_term(normalized, QUALITY_TERMS):
        intent = "quality"
    elif _contains_any_term(normalized, VISUAL_CRAFT_TERMS):
        intent = "visual_craft"
    else:
        intent = "generic"
    return _QueryFeatures(
        normalized=normalized,
        tokens=tokens,
        years=years,
        frames=frames,
        intent=intent,
    )


def _contains_any_term(value: str, terms: set[str]) -> bool:
    tokens = _raw_tokens(value)
    for term in terms:
        term_tokens = _raw_tokens(_normalize(term))
        if len(term_tokens) == 1 and term_tokens[0] in tokens:
            return True
        if len(term_tokens) > 1 and _contains_token_sequence(tokens, term_tokens):
            return True
    return False


def _contains_token_sequence(tokens: list[str], expected: list[str]) -> bool:
    if len(expected) > len(tokens):
        return False
    return any(tokens[index:index + len(expected)] == expected for index in range(len(tokens) - len(expected) + 1))


def _score_item(query: _QueryFeatures, item: dict[str, Any], index: int, intent: str) -> _ScoredItem:
    vector_score = _normalized_score(_first_number(item, "score", "rerank_score", "similarity", "vector_score"))
    exact_score = _exact_score(query, item)
    quality_score = _quality_score(item)
    layer_score = _layer_score(item)
    preview_score = _preview_score(item)
    if intent == "exact":
        score = (
            0.52 * exact_score
            + 0.20 * vector_score
            + 0.14 * layer_score
            + 0.08 * preview_score
            + 0.06 * quality_score
        )
    elif intent == "quality":
        score = (
            0.38 * quality_score
            + 0.24 * vector_score
            + 0.18 * layer_score
            + 0.12 * preview_score
            + 0.08 * exact_score
        )
    elif intent == "visual_craft":
        score = (
            0.28 * layer_score
            + 0.24 * exact_score
            + 0.22 * vector_score
            + 0.16 * quality_score
            + 0.10 * preview_score
        )
    else:
        score = (
            0.50 * vector_score
            + 0.20 * exact_score
            + 0.15 * layer_score
            + 0.10 * preview_score
            + 0.05 * quality_score
        )
    return _ScoredItem(
        item=item,
        original_index=index,
        score=score,
        vector_score=vector_score,
        exact_score=exact_score,
        quality_score=quality_score,
        layer_score=layer_score,
        preview_score=preview_score,
        reason=_reason(exact_score, quality_score, layer_score, preview_score),
        package_key=_package_key(item),
        family_key=_family_key(item),
    )


def _diversify(rows: list[_ScoredItem], *, max_per_family: int) -> list[_ScoredItem]:
    selected: list[_ScoredItem] = []
    overflow: list[_ScoredItem] = []
    family_counts: dict[str, int] = {}
    seen_packages: set[str] = set()
    for row in rows:
        package_seen = row.package_key in seen_packages
        family_count = family_counts.get(row.family_key, 0)
        if not package_seen and family_count < max_per_family:
            selected.append(row)
            seen_packages.add(row.package_key)
            family_counts[row.family_key] = family_count + 1
        else:
            overflow.append(row)
    return selected + overflow


def _annotate(row: _ScoredItem, *, intent: str, insufficient: bool) -> dict[str, Any]:
    item = _copy_item(row.item)
    metadata = item.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
    else:
        metadata = dict(metadata)
    metadata.update(
        {
            "curatorial_score": round(row.score, 6),
            "curatorial_intent": intent,
            "curatorial_reason": row.reason,
            "curatorial_vector_score": round(row.vector_score, 6),
            "curatorial_exact_score": round(row.exact_score, 6),
            "curatorial_quality_score": round(row.quality_score, 6),
            "curatorial_layer_score": round(row.layer_score, 6),
            "curatorial_preview_score": round(row.preview_score, 6),
        }
    )
    if insufficient:
        metadata["curatorial_insufficient_evidence"] = True
    item["metadata"] = metadata
    return item


def _is_insufficient(intent: str, rows: list[_ScoredItem]) -> bool:
    if not rows:
        return True
    best = rows[0]
    if intent == "exact":
        return best.exact_score < 0.32
    if intent in {"quality", "visual_craft"}:
        return max(best.quality_score, best.layer_score) < 0.42
    return False


def _reason(exact_score: float, quality_score: float, layer_score: float, preview_score: float) -> str:
    best = max(
        [
            ("exact-match", exact_score),
            ("quality-signal", quality_score),
            ("visual-layer", layer_score),
            ("preview-linked", preview_score),
        ],
        key=lambda item: item[1],
    )
    return best[0]


def _exact_score(query: _QueryFeatures, item: dict[str, Any]) -> float:
    candidate_norm = _normalize(" ".join(_identity_values(item)))
    identity_tokens = [
        token
        for token in query.tokens
        if not token.isdigit() and token not in query.years and token not in query.frames
    ]
    identity_score = 0.0
    if identity_tokens:
        hits = sum(1 for token in identity_tokens if token in candidate_norm)
        identity_score = hits / len(identity_tokens)

    candidate_years = set(YEAR_RE.findall(candidate_norm))
    year_mismatch = bool(query.years) and not (query.years & candidate_years)
    year_score = 0.0
    if query.years and not year_mismatch:
        year_score = 1.0

    candidate_numbers = set(NUMBER_RE.findall(candidate_norm))
    frame_score = 1.0 if query.frames and query.frames & candidate_numbers else 0.0

    if identity_tokens:
        if identity_score <= 0:
            return _clamp(min(0.20 * year_score + 0.12 * frame_score, 0.26))
        token_score = 0.70 * identity_score + 0.20 * year_score + 0.10 * frame_score
    else:
        token_score = 0.45 * year_score + 0.35 * frame_score
        if query.years or query.frames:
            token_score = min(token_score, 0.65)

    if year_mismatch:
        token_score = min(token_score * 0.55, 0.42)
    if query.frames and not frame_score:
        token_score *= 0.72

    return _clamp(token_score)


def _quality_score(item: dict[str, Any]) -> float:
    meta = _metadata(item)
    blob = _normalized_text_sample(item)
    explicit_score = _first_number(
        meta,
        "editorial_score",
        "quality_score",
        "score_editorial",
        "confidence_overall",
        "confidence",
    )
    scores = []
    if explicit_score is not None:
        scores.append(_normalized_score(explicit_score))
    tier_blob = _normalize(
        " ".join(
            str(value)
            for value in (
                meta.get("tier"),
                meta.get("editorial_tier"),
                meta.get("distinction_flag"),
                meta.get("distinction"),
            )
            if value is not None
        )
    )
    tier_blob = f"{tier_blob} {blob[:8000]}"
    if "premium_s_tier" in tier_blob or "s-tier" in tier_blob or "s tier" in tier_blob:
        scores.append(1.0)
    elif "a-tier" in tier_blob or "a tier" in tier_blob:
        scores.append(0.88)
    elif any(term in tier_blob for term in ("premium", "reference", "excellent", "iconic")):
        scores.append(0.84)
    elif any(term in tier_blob for term in ("strong", "keeper", "good")):
        scores.append(0.72)

    artifact_type, modality = _visual_fields(item)
    if artifact_type == "visual_decoupage_bundle":
        scores.append(0.78)
    elif artifact_type == "visual_analysis_bundle":
        scores.append(0.68)
    elif modality == "image":
        scores.append(0.62)
    else:
        scores.append(0.42)
    return max(scores) if scores else 0.42


def _layer_score(item: dict[str, Any]) -> float:
    artifact_type, modality = _visual_fields(item)
    if artifact_type == "visual_decoupage_bundle":
        return 1.0
    if artifact_type == "visual_analysis_bundle":
        return 0.86
    if modality == "image":
        return 0.82
    if modality == "video":
        return 0.66
    if _preview_score(item) > 0:
        return 0.72
    return 0.28


def _preview_score(item: dict[str, Any]) -> float:
    meta = _metadata(item)
    _artifact_type, modality = _visual_fields(item)
    if modality == "image":
        return 1.0
    for key in ("preview_image_file_id", "linked_image_file_id", "dante_image_id"):
        if _first_text(meta, key):
            return 1.0
    return 0.0


def _package_key(item: dict[str, Any]) -> str:
    meta = _metadata(item)
    return _normalize(
        _first_text(
            meta,
            "source_sha256",
            "dante_image_id",
            "linked_image_file_id",
            "preview_image_file_id",
            "id",
            "file_id",
            "node_id",
        )
        or _first_text(item, "node_id", "id", "file_id")
        or "unknown"
    )


def _family_key(item: dict[str, Any]) -> str:
    meta = _metadata(item)
    raw = _first_text(meta, "group", "film_title", "title", "original_name", "dante_image_id")
    raw = raw or _first_text(item, "title", "display_name", "original_name") or _package_key(item)
    normalized = _normalize(raw)
    normalized = re.sub(r"\bframe\s*\d+\b", "", normalized)
    normalized = re.sub(r"\bcontact\s*sheet\s*\d+\b", "", normalized)
    normalized = re.sub(r"[-_\s]\d{3,4}\b", "", normalized)
    return normalized.strip(" -_") or _package_key(item)


def _identity_values(item: dict[str, Any]) -> list[str]:
    meta = _metadata(item)
    values: list[str] = []
    for source in (item, meta):
        for key in IDENTITY_KEYS:
            value = source.get(key)
            if isinstance(value, str) and value.strip():
                values.append(value.strip())
    return values


def _normalized_text_sample(item: dict[str, Any], *, limit: int = 8000) -> str:
    parts: list[str] = []
    used = 0
    for value in _iter_text_values(item):
        remaining = limit - used
        if remaining <= 0:
            break
        normalized = _normalize(value[: remaining * 2])
        if not normalized:
            continue
        part = normalized[:remaining]
        parts.append(part)
        used += len(part) + 1
    return " ".join(parts)[:limit]


def _iter_text_values(item: dict[str, Any]):
    meta = _metadata(item)
    for source in (item, meta):
        for key in TEXT_KEYS:
            value = source.get(key)
            if isinstance(value, str) and value.strip():
                yield value.strip()
            elif isinstance(value, dict):
                yield from _iter_string_values(value)
            elif isinstance(value, list):
                for entry in value:
                    if isinstance(entry, str) and entry.strip():
                        yield entry.strip()
                    elif isinstance(entry, dict):
                        yield from _iter_string_values(entry)
                    elif entry is not None:
                        yield str(entry)


def _iter_string_values(value: dict[str, Any]):
    for nested in value.values():
        if isinstance(nested, str) and nested.strip():
            yield nested.strip()
        elif isinstance(nested, dict):
            yield from _iter_string_values(nested)
        elif isinstance(nested, list):
            for entry in nested:
                if isinstance(entry, str) and entry.strip():
                    yield entry.strip()
                elif isinstance(entry, dict):
                    yield from _iter_string_values(entry)
                elif entry is not None:
                    yield str(entry)


def _visual_fields(item: dict[str, Any]) -> tuple[str, str]:
    meta = _metadata(item)
    artifact_type = _first_text(meta, "artifact_type", "layer_type", "schema") or ""
    modality = _first_text(meta, "modality", "media_type") or _first_text(item, "modality", "media_type") or ""
    return artifact_type, modality


def _copy_item(item: dict[str, Any]) -> dict[str, Any]:
    copied = dict(item)
    metadata = item.get("metadata")
    if isinstance(metadata, dict):
        copied["metadata"] = dict(metadata)
    return copied


def _metadata(item: dict[str, Any]) -> dict[str, Any]:
    meta = item.get("metadata")
    return meta if isinstance(meta, dict) else {}


def _first_text(item: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _first_number(item: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = item.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, int | float):
            numeric = float(value)
            if math.isfinite(numeric):
                return numeric
        if isinstance(value, str) and value.strip():
            try:
                numeric = float(value.strip().rstrip("%"))
            except ValueError:
                continue
            if math.isfinite(numeric):
                return numeric
    return None


def _normalized_score(value: float | None) -> float:
    if value is None:
        return 0.0
    score = float(value)
    if not math.isfinite(score):
        return 0.0
    if score > 1.0 and score <= 100.0:
        score = score / 100.0
    return _clamp(score)


def _tokens(value: str) -> list[str]:
    return [token for token in re.findall(r"[a-z0-9]+", value) if token not in STOPWORDS]


def _raw_tokens(value: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", value)


def _normalize(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_text = "".join(char for char in normalized if not unicodedata.combining(char))
    return ascii_text.lower().replace("_", " ").replace("-", " ")


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))
