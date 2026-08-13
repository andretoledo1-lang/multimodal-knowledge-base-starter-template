#!/usr/bin/env python3
"""Audit a fail-closed, delta-only Dante visual vector recovery.

The command performs no network mutations and no provider calls. Stage A audits
whether existing Chroma vectors are bound by an exact provenance receipt. Stage
B inventories immutable sources. There is deliberately no execution adapter.
"""
from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import math
import os
import re
import secrets
import struct
import subprocess
import sys
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable, Mapping, Protocol, Sequence
from urllib.parse import urlparse

import httpx


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.kb_parity import classify_vector_drift  # noqa: E402
from app.knowledge_hub_client import sanitize_public_payload  # noqa: E402


SCHEMA_VERSION = "dantedash_kh_visual_recovery_audit.v1"
EMBEDDING_FAMILY = "voyage_multimodal_3_5_1024"
EMBEDDING_MODEL = "voyage-multimodal-3.5"
EMBEDDING_DIMENSION = 1024
DEFAULT_COLLECTION = "dante_multimodal_kb"
DEFAULT_RECOVERY_ROOT = REPO_ROOT / "backend" / "runtime_reports" / "visual-recovery"
DEFAULT_MANIFEST = Path("/Users/vidigal/.knowledge-hub/manifests/visual-memory/dantedash.json")
DEFAULT_CHROMA = REPO_ROOT / "chroma_db"
DEFAULT_EVIDENCE_COMMIT = "a933ab8"
DEFAULT_EVIDENCE_SNAPSHOT = REPO_ROOT / "snapshots" / "DEEP_MEMORY_DANTEDASH_003.md"
RUN_ID_RE = re.compile(r"^visual-recovery-\d{8}T\d{6}Z-[0-9a-f]{8}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
STAGE_B_ROLES = {
    "docling_extracted_image": "source_image",
    "qwen_reviewed_visual_card": "reviewed_visual_card",
    "docling_page_package": "page_package",
}


class RecoveryError(RuntimeError):
    """A safe, stable recovery blocker."""


class CollectionLike(Protocol):
    def get(self, **kwargs: Any) -> Mapping[str, Any]: ...

    def count(self) -> int: ...


@dataclass(frozen=True)
class AuditEvidence:
    collection_name: str
    embedding_family: str
    dimension: int
    manifest_count: int
    vector_count: int
    total_vector_count: int
    foreign_vector_count: int
    manifest_file_sha256: str
    manifest_content_digest: str
    foreign_point_digest: str
    collection_digest: str
    actual_ids: tuple[str, ...]
    conflict_ids: tuple[str, ...]


@dataclass(frozen=True)
class StageAReceipt:
    status: str
    row_count: int
    database_digest: str
    node_id_digest: str
    row_digest: str
    document_digest: str
    payload_digest: str
    vector_digest: str
    embedding_family: str
    embedding_model: str
    dimension: int
    historical_evidence_digest: str
    blockers: tuple[str, ...]


@dataclass(frozen=True)
class StageBInventory:
    status: str
    row_count: int
    by_artifact_type: dict[str, int]
    matrix_digest: str
    blockers: tuple[str, ...]


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def generate_run_id() -> str:
    return "visual-recovery-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + secrets.token_hex(4)


def canonical_digest(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_manifest(path: Path) -> list[dict[str, Any]]:
    if path.is_symlink() or not path.is_file():
        raise RecoveryError("manifest_not_regular_file")
    try:
        raw_manifest = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise RecoveryError("manifest_unreadable") from exc
    try:
        payload = json.loads(raw_manifest)
    except json.JSONDecodeError as exc:
        raise RecoveryError("manifest_json_invalid") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("assets"), list):
        raise RecoveryError("manifest_schema_invalid")
    assets = [dict(item) for item in payload["assets"] if isinstance(item, dict)]
    node_ids = [str(item.get("node_id") or "").strip() for item in assets]
    if len(assets) != len(payload["assets"]) or any(not item for item in node_ids):
        raise RecoveryError("manifest_asset_invalid")
    if len(node_ids) != len(set(node_ids)):
        raise RecoveryError("manifest_node_ids_not_unique")
    if int(payload.get("asset_count") or len(assets)) != len(assets):
        raise RecoveryError("manifest_asset_count_mismatch")
    if payload.get("kb_slug") != "dantedash":
        raise RecoveryError("manifest_kb_slug_mismatch")
    if payload.get("embedding_family") != EMBEDDING_FAMILY:
        raise RecoveryError("manifest_embedding_family_mismatch")
    if int(payload.get("embedding_dimension") or 0) != EMBEDDING_DIMENSION:
        raise RecoveryError("manifest_embedding_dimension_mismatch")
    return sorted(assets, key=lambda item: str(item["node_id"]))


def manifest_content_digest(assets: Sequence[Mapping[str, Any]]) -> str:
    return canonical_digest(list(assets))


def dantedash_point_id(node_id: str) -> str:
    normalized = str(node_id).strip()
    if not normalized:
        raise RecoveryError("node_id_empty")
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"dantedash:{normalized}"))


def parse_audit(raw: Mapping[str, Any], manifest_ids: Sequence[str]) -> AuditEvidence:
    data = raw.get("data") if isinstance(raw.get("data"), Mapping) else raw
    if not isinstance(data, Mapping):
        raise RecoveryError("audit_response_invalid")
    status = str(data.get("status") or "").lower()
    if status not in {"ok", "ready", "unready", "degraded", "searchable_degraded"}:
        raise RecoveryError("audit_status_unavailable")
    drift = data.get("drift") if isinstance(data.get("drift"), Mapping) else {}
    actual_raw = data.get("dantedash_point_ids")
    if not isinstance(actual_raw, list):
        actual_raw = drift.get("actual_ids") if isinstance(drift.get("actual_ids"), list) else None
    vector_count = _required_nonnegative_int(data, "vector_count")
    if actual_raw is None:
        missing = drift.get("missing_ids")
        stale = drift.get("stale_ids") or []
        if isinstance(missing, list) and isinstance(stale, list):
            missing_set = {str(item) for item in missing}
            expected_points = {dantedash_point_id(node_id) for node_id in manifest_ids}
            actual_raw = sorted((expected_points - missing_set) | {str(item) for item in stale})
        elif vector_count == 0:
            actual_raw = []
        else:
            raise RecoveryError("audit_vector_ids_missing")
    conflict_raw = drift.get("point_conflict_ids")
    if conflict_raw is None:
        conflict_raw = drift.get("conflict_ids")
    if conflict_raw is None:
        conflict_raw = data.get("point_conflict_ids")
    if conflict_raw is None:
        conflict_raw = data.get("conflict_ids", [])
    foreign_collision_raw = drift.get("foreign_collision_ids")
    if foreign_collision_raw is None:
        foreign_collision_raw = data.get("foreign_collision_ids", [])
    if not isinstance(conflict_raw, list) or not isinstance(foreign_collision_raw, list):
        raise RecoveryError("audit_conflict_ids_invalid")
    actual_ids = tuple(sorted(str(item) for item in actual_raw))
    conflict_ids = tuple(sorted({str(item) for item in conflict_raw + foreign_collision_raw}))
    if len(actual_ids) != len(set(actual_ids)) or len(actual_ids) != vector_count:
        raise RecoveryError("audit_vector_count_mismatch")
    foreign_digest = str(data.get("foreign_point_digest") or "")
    collection_digest = str(data.get("collection_digest") or "")
    manifest_file_sha256 = str(data.get("manifest_file_sha256") or data.get("manifest_digest") or "")
    manifest_content_digest = str(data.get("manifest_content_digest") or data.get("manifest_digest") or "")
    if not all(
        SHA256_RE.fullmatch(value)
        for value in (foreign_digest, collection_digest, manifest_file_sha256, manifest_content_digest)
    ):
        raise RecoveryError("audit_digest_invalid")
    return AuditEvidence(
        collection_name=str(data.get("collection_name") or ""),
        embedding_family=str(data.get("embedding_family") or ""),
        dimension=_required_positive_int(data, "dimension"),
        manifest_count=_required_nonnegative_int(data, "manifest_count"),
        vector_count=vector_count,
        total_vector_count=_required_nonnegative_int(data, "total_vector_count"),
        foreign_vector_count=_required_nonnegative_int(data, "foreign_vector_count"),
        manifest_file_sha256=manifest_file_sha256,
        manifest_content_digest=manifest_content_digest,
        foreign_point_digest=foreign_digest,
        collection_digest=collection_digest,
        actual_ids=actual_ids,
        conflict_ids=conflict_ids,
    )


def validate_audit_contract(audit: AuditEvidence, manifest_ids: Sequence[str], collection_name: str) -> None:
    if audit.collection_name != collection_name:
        raise RecoveryError("audit_collection_mismatch")
    if audit.embedding_family != EMBEDDING_FAMILY or audit.dimension != EMBEDDING_DIMENSION:
        raise RecoveryError("audit_embedding_contract_mismatch")
    if audit.manifest_count != len(manifest_ids):
        raise RecoveryError("audit_manifest_count_mismatch")
    if audit.total_vector_count != audit.vector_count + audit.foreign_vector_count:
        raise RecoveryError("audit_total_count_mismatch")
    expected_point_ids = [dantedash_point_id(node_id) for node_id in manifest_ids]
    drift = classify_vector_drift(
        expected_point_ids,
        audit.actual_ids,
        conflict_ids=audit.conflict_ids,
    )
    if drift.conflict_ids:
        raise RecoveryError("audit_point_conflicts_present")


def fetch_audit(
    base_url: str,
    *,
    actions_bearer_token: str | None,
    client: httpx.Client | None = None,
) -> dict[str, Any]:
    if not _is_loopback_http_url(base_url):
        raise RecoveryError("knowledge_hub_loopback_required")
    if not actions_bearer_token:
        raise RecoveryError("knowledge_hub_actions_bearer_required")
    owned = client is None
    http = client or httpx.Client(
        timeout=30.0,
        follow_redirects=False,
        trust_env=False,
    )
    try:
        response = http.get(
            f"{base_url.rstrip('/')}/dantedash/packages/audit",
            headers={"Authorization": f"Bearer {actions_bearer_token}"},
        )
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise RecoveryError("knowledge_hub_audit_unavailable") from exc
    finally:
        if owned:
            http.close()
    if not isinstance(payload, dict):
        raise RecoveryError("audit_response_invalid")
    return payload


def validate_historical_evidence(repo_root: Path, commit: str, snapshot: Path) -> dict[str, Any]:
    if not re.fullmatch(r"[0-9a-f]{7,40}", commit):
        raise RecoveryError("historical_commit_invalid")
    if snapshot.is_symlink() or not snapshot.is_file():
        raise RecoveryError("historical_snapshot_missing")
    try:
        commit_source = subprocess.run(
            ["git", "show", f"{commit}:backend/app/kb.py"],
            cwd=repo_root,
            text=True,
            capture_output=True,
            timeout=15,
            check=True,
        ).stdout
    except (OSError, subprocess.SubprocessError) as exc:
        raise RecoveryError("historical_commit_unavailable") from exc
    snapshot_text = snapshot.read_text(encoding="utf-8")
    current_source = (repo_root / "backend" / "app" / "kb.py").read_text(encoding="utf-8")
    required = (EMBEDDING_MODEL, str(EMBEDDING_DIMENSION))
    if not all(term in commit_source for term in required):
        raise RecoveryError("historical_commit_contract_mismatch")
    if not all(term in snapshot_text for term in required):
        raise RecoveryError("historical_snapshot_contract_mismatch")
    if not all(term in current_source for term in required):
        raise RecoveryError("current_embedding_contract_mismatch")
    return {
        "commit": commit,
        "commit_source_sha256": hashlib.sha256(commit_source.encode("utf-8")).hexdigest(),
        "snapshot_sha256": sha256_file(snapshot),
        "current_source_sha256": sha256_file(repo_root / "backend" / "app" / "kb.py"),
        "embedding_family": EMBEDDING_FAMILY,
        "embedding_model": EMBEDDING_MODEL,
        "dimension": EMBEDDING_DIMENSION,
        "evidence_strength": "indirect_specific_workspace_chain",
    }


def digest_file_tree(root: Path) -> str:
    if root.is_symlink() or not root.is_dir():
        raise RecoveryError("chroma_database_directory_invalid")
    entries: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise RecoveryError("chroma_database_symlink_refused")
        if not path.is_file() or path.name.endswith(".lock"):
            continue
        entries.append(
            {
                "relative_path": path.relative_to(root).as_posix(),
                "size": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    if not entries:
        raise RecoveryError("chroma_database_empty")
    return canonical_digest(entries)


def build_stage_a(
    collection: CollectionLike,
    manifest_assets: Sequence[Mapping[str, Any]],
    *,
    database_digest: str,
    historical_evidence: Mapping[str, Any],
) -> tuple[StageAReceipt, list[dict[str, Any]]]:
    manifest_by_id = {str(item["node_id"]): item for item in manifest_assets}
    rows: list[dict[str, Any]] = []
    blockers: list[str] = ["chroma_vector_provenance_unverified"]
    collection_count = int(collection.count())
    offset = 0
    page_size = 128
    while offset < collection_count:
        payload = collection.get(
            limit=page_size,
            offset=offset,
            include=["metadatas", "documents", "embeddings"],
        )
        ids = [str(item) for item in payload.get("ids") or []]
        metadatas = payload.get("metadatas") or []
        documents = payload.get("documents") or []
        embeddings = payload.get("embeddings")
        embeddings = [] if embeddings is None else embeddings
        if not ids:
            break
        if not (len(ids) == len(metadatas) == len(documents) == len(embeddings)):
            raise RecoveryError("chroma_page_shape_mismatch")
        for node_id, raw_meta, raw_document, raw_embedding in zip(
            ids, metadatas, documents, embeddings, strict=True
        ):
            asset = manifest_by_id.get(node_id)
            if asset is None:
                blockers.append(f"chroma_id_not_in_manifest:{node_id}")
                continue
            document = str(raw_document or "")
            if document != str(asset.get("document") or ""):
                blockers.append(f"chroma_document_mismatch:{node_id}")
                continue
            metadata = dict(raw_meta or {})
            asset_meta = dict(asset.get("metadata") or {})
            for identity_field in ("id", "file_id", "node_id"):
                value = metadata.get(identity_field)
                expected_value = asset_meta.get(identity_field)
                if value not in (None, "") and expected_value not in (None, "") and value != expected_value:
                    blockers.append(f"chroma_identity_mismatch:{node_id}:{identity_field}")
            if metadata.get("payload_hash") and metadata.get("payload_hash") != asset_meta.get("payload_hash"):
                blockers.append(f"chroma_payload_hash_mismatch:{node_id}")
            vector = _embedding_to_float_list(raw_embedding)
            if len(vector) != EMBEDDING_DIMENSION or any(not math.isfinite(value) for value in vector):
                blockers.append(f"chroma_vector_contract_mismatch:{node_id}")
                continue
            packed = struct.pack(f">{len(vector)}f", *vector)
            rows.append(
                {
                    "node_id": node_id,
                    "document_sha256": hashlib.sha256(document.encode("utf-8")).hexdigest(),
                    "source_metadata_digest": canonical_digest(metadata),
                    "payload_identity_digest": canonical_digest(
                        {"document": document, "metadata": asset_meta, "node_id": node_id}
                    ),
                    "vector_sha256": hashlib.sha256(packed).hexdigest(),
                }
            )
        offset += len(ids)
    rows.sort(key=lambda item: item["node_id"])
    if len(rows) != collection_count:
        blockers.append("chroma_collection_pagination_incomplete")
    node_id_digest = canonical_digest([row["node_id"] for row in rows])
    row_digest = canonical_digest(
        [
            {
                "node_id": row["node_id"],
                "source_metadata_digest": row["source_metadata_digest"],
            }
            for row in rows
        ]
    )
    document_digest = canonical_digest(
        [{"node_id": row["node_id"], "sha256": row["document_sha256"]} for row in rows]
    )
    payload_digest = canonical_digest(
        [
            {"node_id": row["node_id"], "sha256": row["payload_identity_digest"]}
            for row in rows
        ]
    )
    vector_digest = canonical_digest(
        [{"node_id": row["node_id"], "sha256": row["vector_sha256"]} for row in rows]
    )
    receipt = StageAReceipt(
        status="blocked",
        row_count=len(rows),
        database_digest=database_digest,
        node_id_digest=node_id_digest,
        row_digest=row_digest,
        document_digest=document_digest,
        payload_digest=payload_digest,
        vector_digest=vector_digest,
        embedding_family=EMBEDDING_FAMILY,
        embedding_model=EMBEDDING_MODEL,
        dimension=EMBEDDING_DIMENSION,
        historical_evidence_digest=canonical_digest(historical_evidence),
        blockers=tuple(sorted(blockers)),
    )
    return receipt, rows


def build_stage_b_inventory(
    manifest_assets: Sequence[Mapping[str, Any]],
    stage_a_ids: Iterable[str],
    qdrant_actual_ids: Iterable[str],
) -> tuple[StageBInventory, list[dict[str, Any]]]:
    stage_a_set = set(stage_a_ids)
    actual_set = set(qdrant_actual_ids)
    rows: list[dict[str, Any]] = []
    blockers: list[str] = []
    counts: dict[str, int] = {}
    for asset in manifest_assets:
        node_id = str(asset["node_id"])
        if node_id in stage_a_set:
            continue
        artifact_type = str(asset.get("artifact_type") or "")
        role = STAGE_B_ROLES.get(artifact_type)
        row_blockers: list[str] = []
        if role is None:
            row_blockers.append("adapter_not_supported")
        document = str(asset.get("document") or "")
        metadata = dict(asset.get("metadata") or {})
        if not document.strip():
            row_blockers.append("canonical_document_missing")
        raw_payload_hash = metadata.get("payload_hash")
        if isinstance(raw_payload_hash, str) and SHA256_RE.fullmatch(raw_payload_hash):
            payload_hash = raw_payload_hash
            payload_hash_origin = "manifest_metadata_unverified"
            payload_hash_state = "present_unverified"
        else:
            payload_hash = ""
            payload_hash_origin = "missing_or_invalid"
            payload_hash_state = "invalid_or_missing"
            row_blockers.append("payload_hash_invalid")
        input_kind = "canonical_text"
        input_sha256 = hashlib.sha256(document.encode("utf-8")).hexdigest()
        immutable_source = "manifest_asset"
        source_locator = f"manifest://{node_id}"
        byte_size = len(document.encode("utf-8"))
        if role == "source_image":
            input_kind = "image_bytes"
            source_path = Path(str(asset.get("source_path") or ""))
            immutable_source = "source_file"
            source_locator = str(source_path)
            if source_path.is_symlink() or not source_path.is_file():
                row_blockers.append("immutable_image_source_missing")
                input_sha256 = ""
                byte_size = 0
            else:
                input_sha256 = sha256_file(source_path)
                byte_size = source_path.stat().st_size
                expected = str(metadata.get("artifact_sha256") or asset.get("source_sha256") or "")
                if input_sha256 != expected:
                    row_blockers.append("immutable_image_hash_mismatch")
        if row_blockers:
            blockers.extend(f"{node_id}:{blocker}" for blocker in row_blockers)
        counts[artifact_type or "unknown"] = counts.get(artifact_type or "unknown", 0) + 1
        rows.append(
            {
                "node_id": node_id,
                "artifact_type": artifact_type,
                "role": role or "unsupported",
                "input_kind": input_kind,
                "immutable_source": immutable_source,
                "source_locator": source_locator,
                "input_sha256": input_sha256,
                "input_bytes": byte_size,
                "document_sha256": hashlib.sha256(document.encode("utf-8")).hexdigest(),
                "payload_hash": payload_hash,
                "payload_hash_origin": payload_hash_origin,
                "payload_hash_state": payload_hash_state,
                "payload_identity_digest": canonical_digest(
                    {"document": document, "metadata": metadata, "node_id": node_id}
                ),
                "embedding_family": EMBEDDING_FAMILY,
                "embedding_model": EMBEDDING_MODEL,
                "dimension": EMBEDDING_DIMENSION,
                "qdrant_state": "present_unverified" if node_id in actual_set else "missing",
                "adapter_state": "inventory_only_no_provider_calls",
                "blockers": sorted(row_blockers),
            }
        )
    rows.sort(key=lambda item: item["node_id"])
    status = "inventory_unverified" if not blockers else "blocked"
    return (
        StageBInventory(
            status=status,
            row_count=len(rows),
            by_artifact_type=dict(sorted(counts.items())),
            matrix_digest=canonical_digest(rows),
            blockers=tuple(sorted(blockers)),
        ),
        rows,
    )


def audit_recovery(args: argparse.Namespace, *, audit_raw: Mapping[str, Any] | None = None) -> dict[str, Any]:
    manifest_path = Path(args.manifest)
    assets = load_manifest(manifest_path)
    manifest_ids = [str(item["node_id"]) for item in assets]
    manifest_file_digest = sha256_file(manifest_path)
    local_manifest_digest = manifest_content_digest(assets)
    audit = parse_audit(
        audit_raw
        or fetch_audit(
            args.knowledge_hub_base_url,
            actions_bearer_token=os.getenv("KNOWLEDGE_HUB_ACTIONS_BEARER_TOKEN", "").strip() or None,
        ),
        manifest_ids,
    )
    validate_audit_contract(audit, manifest_ids, args.collection)
    if audit.manifest_file_sha256 != manifest_file_digest:
        raise RecoveryError("audit_manifest_file_digest_mismatch")
    if audit.manifest_content_digest != local_manifest_digest:
        raise RecoveryError("audit_manifest_content_digest_mismatch")
    historical = validate_historical_evidence(
        Path(args.repo_root), args.historical_commit, Path(args.historical_snapshot)
    )
    chroma_dir = Path(args.chroma_dir)
    database_digest_before = digest_file_tree(chroma_dir)
    collection = _open_chroma_collection(chroma_dir, args.chroma_collection)
    stage_a, stage_a_rows = build_stage_a(
        collection,
        assets,
        database_digest=database_digest_before,
        historical_evidence=historical,
    )
    database_digest_after = digest_file_tree(chroma_dir)
    if database_digest_after != database_digest_before:
        raise RecoveryError("chroma_database_changed_during_audit")
    expected_point_ids = [dantedash_point_id(node_id) for node_id in manifest_ids]
    drift = classify_vector_drift(expected_point_ids, audit.actual_ids, conflict_ids=audit.conflict_ids)
    actual_point_ids = set(audit.actual_ids)
    for row in stage_a_rows:
        row["qdrant_state"] = (
            "present_unverified"
            if dantedash_point_id(row["node_id"]) in actual_point_ids
            else "missing"
        )
    actual_node_ids = [node_id for node_id in manifest_ids if dantedash_point_id(node_id) in actual_point_ids]
    stage_b, stage_b_rows = build_stage_b_inventory(
        assets,
        (row["node_id"] for row in stage_a_rows),
        actual_node_ids,
    )
    run_id = generate_run_id()
    run_dir = create_private_run_dir(run_id)
    blockers = {
        "audit_only_no_mutation_path",
        *(f"stage_a:{blocker}" for blocker in stage_a.blockers),
        *(f"stage_b:{blocker}" for blocker in stage_b.blockers),
    }
    summary: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "generated_at": utc_now(),
        "mode": "dry_run",
        "status": "blocked",
        "blockers": sorted(blockers),
        "mutation_performed": False,
        "provider_calls_performed": 0,
        "collection_name": audit.collection_name,
        "collection_contract": {
            "embedding_family": audit.embedding_family,
            "dimension": audit.dimension,
        },
        "manifest": {
            "count": len(assets),
            "file_sha256": manifest_file_digest,
            "content_digest": local_manifest_digest,
            "kh_manifest_file_sha256": audit.manifest_file_sha256,
            "kh_manifest_content_digest": audit.manifest_content_digest,
        },
        "baseline": {
            "dantedash_vector_count": audit.vector_count,
            "foreign_vector_count": audit.foreign_vector_count,
            "total_vector_count": audit.total_vector_count,
            "foreign_point_digest": audit.foreign_point_digest,
            "collection_digest": audit.collection_digest,
            "expected_id_digest": drift.expected_id_digest,
            "actual_id_digest": drift.actual_id_digest,
            "missing_count": len(drift.missing_ids),
            "stale_count": len(drift.stale_ids),
            "conflict_count": len(drift.conflict_ids),
            "content_exactness": "unverified",
        },
        "stage_a": asdict(stage_a),
        "stage_b": asdict(stage_b),
        "evidence": {
            "historical": dict(historical),
            "stage_a_rows": stage_a_rows,
            "stage_b_rows": stage_b_rows,
        },
    }
    summary["audit_digest"] = canonical_digest(summary)
    audit_path = run_dir / "audit-summary.json"
    write_json_once(audit_path, summary)
    freeze_file(audit_path)
    public = sanitize_public_payload({key: value for key, value in summary.items() if key != "evidence"})
    if not isinstance(public, dict):
        raise RecoveryError("public_summary_invalid")
    public["run_artifacts"] = {
        "run_id": run_id,
        "audit_summary": audit_path.name,
    }
    return public


def create_private_run_dir(run_id: str) -> Path:
    if not RUN_ID_RE.fullmatch(run_id):
        raise RecoveryError("run_id_invalid")
    root = DEFAULT_RECOVERY_ROOT.expanduser()
    if not root.is_absolute():
        raise RecoveryError("output_root_must_be_absolute")
    _reject_symlink_components(root)
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    root.chmod(0o700)
    resolved_root = root.resolve(strict=True)
    run_dir = resolved_root / run_id
    if run_dir.exists() or run_dir.is_symlink():
        raise RecoveryError("run_directory_exists")
    run_dir.mkdir(mode=0o700)
    if run_dir.parent != resolved_root:
        raise RecoveryError("run_path_escape")
    return run_dir


def write_json_once(path: Path, payload: Mapping[str, Any]) -> None:
    _write_bytes_once(path, (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8"))


def freeze_file(path: Path) -> None:
    if path.is_symlink() or not path.is_file():
        raise RecoveryError("bundle_freeze_target_invalid")
    path.chmod(0o400)


def _write_bytes_once(path: Path, data: bytes) -> None:
    if path.parent.is_symlink() or path.exists() or path.is_symlink():
        raise RecoveryError("artifact_overwrite_refused")
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    path.chmod(0o600)


def _reject_symlink_components(path: Path) -> None:
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current = current / part
        if current.exists() and current.is_symlink():
            raise RecoveryError("symlink_output_path_refused")


def _open_chroma_collection(chroma_dir: Path, collection_name: str) -> CollectionLike:
    try:
        import chromadb

        client = chromadb.PersistentClient(path=str(chroma_dir))
        return client.get_collection(collection_name)
    except Exception as exc:  # noqa: BLE001 - normalized, secret-free blocker.
        raise RecoveryError("chroma_collection_unavailable") from exc


def _embedding_to_float_list(value: Any) -> list[float]:
    if hasattr(value, "tolist"):
        value = value.tolist()
    if not isinstance(value, list):
        return []
    try:
        return [float(item) for item in value]
    except (TypeError, ValueError):
        return []


def _is_loopback_http_url(value: str) -> bool:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password:
        return False
    if parsed.hostname == "localhost":
        return True
    try:
        return bool(parsed.hostname and ipaddress.ip_address(parsed.hostname).is_loopback)
    except ValueError:
        return False


def _required_nonnegative_int(data: Mapping[str, Any], key: str) -> int:
    try:
        value = int(data[key])
    except (KeyError, TypeError, ValueError) as exc:
        raise RecoveryError(f"audit_{key}_invalid") from exc
    if value < 0:
        raise RecoveryError(f"audit_{key}_invalid")
    return value


def _required_positive_int(data: Mapping[str, Any], key: str) -> int:
    value = _required_nonnegative_int(data, key)
    if value < 1:
        raise RecoveryError(f"audit_{key}_invalid")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--chroma-dir", default=str(DEFAULT_CHROMA))
    parser.add_argument("--chroma-collection", default=DEFAULT_COLLECTION)
    parser.add_argument("--collection", default="visual_memory__voyage_multimodal_3_5_1024")
    parser.add_argument("--knowledge-hub-base-url", default="http://127.0.0.1:8080")
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument("--historical-commit", default=DEFAULT_EVIDENCE_COMMIT)
    parser.add_argument("--historical-snapshot", default=str(DEFAULT_EVIDENCE_SNAPSHOT))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = audit_recovery(args)
    except RecoveryError as exc:
        print(json.dumps({"ok": False, "status": "blocked", "blocker": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
