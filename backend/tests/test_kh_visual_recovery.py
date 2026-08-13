from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import uuid
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "dantedash_kh_visual_recovery.py"


def load_module():
    spec = importlib.util.spec_from_file_location("dantedash_kh_visual_recovery", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class FakeCollection:
    def __init__(self, rows):
        self.rows = rows

    def count(self):
        return len(self.rows)

    def get(self, *, limit, offset, include):
        del include
        page = self.rows[offset : offset + limit]
        return {
            "ids": [row["node_id"] for row in page],
            "metadatas": [row["metadata"] for row in page],
            "documents": [row["document"] for row in page],
            "embeddings": [row["embedding"] for row in page],
        }


def asset(node_id: str, *, artifact_type: str = "legacy", document: str = "alpha", **extra):
    metadata = {
        "id": node_id,
        "file_id": node_id,
        "node_id": node_id,
        "artifact_type": artifact_type,
        "embedding_model": "voyage-multimodal-3.5",
        "payload_hash": "a" * 64,
    }
    return {
        "node_id": node_id,
        "document": document,
        "artifact_type": artifact_type,
        "metadata": metadata,
        **extra,
    }


def audit_payload(module, manifest_file: Path, assets, *, actual_ids=()):
    return {
        "status": "degraded",
        "collection_name": "visual_memory__voyage_multimodal_3_5_1024",
        "embedding_family": "voyage_multimodal_3_5_1024",
        "dimension": 1024,
        "manifest_count": len(assets),
        "vector_count": len(actual_ids),
        "foreign_vector_count": 2,
        "total_vector_count": len(actual_ids) + 2,
        "manifest_file_sha256": module.sha256_file(manifest_file),
        "manifest_content_digest": module.canonical_digest(sorted(assets, key=lambda row: row["node_id"])),
        "foreign_point_digest": "b" * 64,
        "collection_digest": "c" * 64,
        "dantedash_point_ids": list(actual_ids),
        "drift": {"point_conflict_ids": []},
    }


def test_dantedash_point_id_matches_kh_uuid5_contract() -> None:
    module = load_module()

    assert module.dantedash_point_id(" node-a ") == str(
        uuid.uuid5(uuid.NAMESPACE_URL, "dantedash:node-a")
    )


def test_parse_audit_requires_actual_vector_ids_for_nonempty_scope(tmp_path: Path) -> None:
    module = load_module()
    payload = {
        "status": "degraded",
        "collection_name": "visual_memory__voyage_multimodal_3_5_1024",
        "embedding_family": "voyage_multimodal",
        "dimension": 1024,
        "manifest_count": 1,
        "vector_count": 1,
        "foreign_vector_count": 0,
        "total_vector_count": 1,
        "manifest_digest": "a" * 64,
        "foreign_point_digest": "b" * 64,
        "collection_digest": "c" * 64,
        "drift": {},
    }

    with pytest.raises(module.RecoveryError, match="audit_vector_ids_missing"):
        module.parse_audit(payload, ["node-a"])


def test_build_stage_a_binds_rows_documents_payloads_vectors_and_evidence() -> None:
    module = load_module()
    manifest = [asset("node-a")]
    collection = FakeCollection(
        [
            {
                "node_id": "node-a",
                "document": "alpha",
                "metadata": {"id": "node-a"},
                "embedding": [0.25] * 1024,
            }
        ]
    )

    receipt, rows = module.build_stage_a(
        collection,
        manifest,
        database_digest="d" * 64,
        historical_evidence={"verified": True},
    )

    assert receipt.status == "certified"
    assert receipt.row_count == 1
    assert receipt.dimension == 1024
    assert all(len(value) == 64 for value in (receipt.row_digest, receipt.payload_digest, receipt.vector_digest))
    assert module.decode_stage_a_vector(rows[0]) == [0.25] * 1024


def test_build_stage_a_fails_closed_on_wrong_dimension() -> None:
    module = load_module()
    collection = FakeCollection(
        [{"node_id": "node-a", "document": "alpha", "metadata": {}, "embedding": [0.25] * 8}]
    )

    receipt, rows = module.build_stage_a(
        collection,
        [asset("node-a")],
        database_digest="d" * 64,
        historical_evidence={"verified": True},
    )

    assert receipt.status == "blocked"
    assert rows == []
    assert receipt.blockers == ("chroma_vector_contract_mismatch:node-a",)


def test_stage_b_builds_complete_no_provider_inventory(tmp_path: Path) -> None:
    module = load_module()
    image = tmp_path / "source.png"
    image.write_bytes(b"immutable-image")
    image_hash = hashlib.sha256(image.read_bytes()).hexdigest()
    image_asset = asset(
        "image-a",
        artifact_type="docling_extracted_image",
        source_path=str(image),
        source_sha256=image_hash,
    )
    image_asset["metadata"]["artifact_sha256"] = image_hash
    assets = [
        image_asset,
        asset("card-a", artifact_type="qwen_reviewed_visual_card"),
        asset("page-a", artifact_type="docling_page_package"),
    ]

    receipt, rows = module.build_stage_b_inventory(assets, [], [])

    assert receipt.status == "inventory_certified_embedding_pending"
    assert receipt.row_count == 3
    assert receipt.by_artifact_type == {
        "docling_extracted_image": 1,
        "docling_page_package": 1,
        "qwen_reviewed_visual_card": 1,
    }
    assert {row["adapter_state"] for row in rows} == {"inventory_only_no_provider_calls"}
    assert next(row for row in rows if row["node_id"] == "image-a")["input_sha256"] == image_hash


def test_stage_b_blocks_before_embedding_when_source_hash_changes(tmp_path: Path) -> None:
    module = load_module()
    image = tmp_path / "source.png"
    image.write_bytes(b"changed")
    image_asset = asset(
        "image-a",
        artifact_type="docling_extracted_image",
        source_path=str(image),
        source_sha256="d" * 64,
    )
    image_asset["metadata"]["artifact_sha256"] = "d" * 64

    receipt, rows = module.build_stage_b_inventory([image_asset], [], [])

    assert receipt.status == "blocked"
    assert receipt.blockers == ("image-a:immutable_image_hash_mismatch",)
    assert rows[0]["blockers"] == ["immutable_image_hash_mismatch"]


def test_private_run_directory_rejects_symlink_root(tmp_path: Path) -> None:
    module = load_module()
    real = tmp_path / "real"
    real.mkdir()
    linked = tmp_path / "linked"
    linked.symlink_to(real, target_is_directory=True)

    with pytest.raises(module.RecoveryError, match="symlink_output_path_refused"):
        module.create_private_run_dir(linked, "visual-recovery-20260813T120000Z-1234abcd")


def test_batch_plan_is_deterministic_and_exact_replay_skips_every_batch() -> None:
    module = load_module()
    run_id = "visual-recovery-20260813T120000Z-1234abcd"
    rows = [{"node_id": "node-b", "value": 2}, {"node_id": "node-a", "value": 1}]

    first = module.plan_recovery_batches(run_id, rows, batch_size=1)
    replay = module.plan_recovery_batches(
        run_id,
        rows,
        batch_size=1,
        settled_batch_digests=[batch.source_bundle_digest for batch in first],
    )

    assert [batch.batch_id for batch in replay] == [batch.batch_id for batch in first]
    assert [batch.state for batch in replay] == ["settled_replay_skip", "settled_replay_skip"]
    assert sum(batch.state == "pending" for batch in replay) == 0


def test_batch_plan_rejects_unknown_settled_digest() -> None:
    module = load_module()

    with pytest.raises(module.RecoveryError, match="settled_batch_not_in_source_bundle"):
        module.plan_recovery_batches(
            "visual-recovery-20260813T120000Z-1234abcd",
            [{"node_id": "node-a"}],
            batch_size=1,
            settled_batch_digests=["f" * 64],
        )


def test_plan_dry_run_writes_owner_only_immutable_bundles_without_mutation(tmp_path: Path, monkeypatch) -> None:
    module = load_module()
    chroma_dir = tmp_path / "chroma"
    chroma_dir.mkdir()
    (chroma_dir / "chroma.sqlite3").write_bytes(b"stable-db")
    assets = [asset("node-a")]
    manifest = tmp_path / "dantedash.json"
    manifest.write_text(
        json.dumps(
            {
                "asset_count": 1,
                "assets": assets,
                "kb_slug": "dantedash",
                "embedding_family": "voyage_multimodal_3_5_1024",
                "embedding_dimension": 1024,
            }
        ),
        encoding="utf-8",
    )
    collection = FakeCollection(
        [{"node_id": "node-a", "document": "alpha", "metadata": {}, "embedding": [0.5] * 1024}]
    )
    monkeypatch.setattr(module, "_open_chroma_collection", lambda *_args: collection)
    monkeypatch.setattr(module, "validate_historical_evidence", lambda *_args: {"verified": True})
    parser = module.build_parser()
    args = parser.parse_args(
        [
            "--manifest",
            str(manifest),
            "--chroma-dir",
            str(chroma_dir),
            "--output-root",
            str(tmp_path / "runs"),
        ]
    )

    result = module.plan_recovery(args, audit_raw=audit_payload(module, manifest, assets))

    assert result["mode"] == "dry_run"
    assert result["mutation_performed"] is False
    assert result["provider_calls_performed"] == 0
    run_dir = tmp_path / "runs" / result["run_id"]
    plan = json.loads((run_dir / "plan.json").read_text(encoding="utf-8"))
    assert plan["stage_a"]["status"] == "certified"
    assert plan["stage_b"]["row_count"] == 0
    assert (run_dir / "stage-a-source-bundle.jsonl").stat().st_mode & 0o777 == 0o400
    assert (run_dir / "ledger.jsonl").stat().st_mode & 0o777 == 0o600
