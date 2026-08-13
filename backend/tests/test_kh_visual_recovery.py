from __future__ import annotations

import hashlib
import importlib.util
import json
import struct
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


def direct_provenance_receipt(module, rows, *, database_digest: str = "d" * 64):
    ordered = sorted(rows, key=lambda row: row["node_id"])
    vector_rows = []
    for row in ordered:
        vector = [float(value) for value in row["embedding"]]
        packed = struct.pack(f">{len(vector)}f", *vector)
        vector_rows.append(
            {
                "node_id": row["node_id"],
                "sha256": hashlib.sha256(packed).hexdigest(),
            }
        )
    return {
        "evidence_strength": "direct_vector_provenance_receipt",
        "database_digest": database_digest,
        "expected_row_count": len(ordered),
        "node_id_digest": module.canonical_digest([row["node_id"] for row in ordered]),
        "vector_digest": module.canonical_digest(vector_rows),
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


def test_fetch_audit_disables_environment_proxy_routing(monkeypatch) -> None:
    module = load_module()
    captured: dict[str, object] = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            pass

        def json(self):
            return {"status": "ok"}

    class FakeHttpClient:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def get(self, url: str):
            captured["url"] = url
            return FakeResponse()

        def close(self) -> None:
            captured["closed"] = True

    monkeypatch.setenv("HTTP_PROXY", "http://proxy.example:3128")
    monkeypatch.delenv("NO_PROXY", raising=False)
    monkeypatch.setattr(module.httpx, "Client", FakeHttpClient)

    assert module.fetch_audit("http://127.0.0.1:8080") == {"status": "ok"}
    assert captured["trust_env"] is False
    assert captured["follow_redirects"] is False
    assert captured["closed"] is True


def test_build_stage_a_binds_rows_documents_payloads_vectors_and_evidence() -> None:
    module = load_module()
    manifest = [asset("node-a")]
    source_rows = [
        {
            "node_id": "node-a",
            "document": "alpha",
            "metadata": {"id": "node-a"},
            "embedding": [0.25] * 1024,
        }
    ]
    collection = FakeCollection(source_rows)

    receipt, rows = module.build_stage_a(
        collection,
        manifest,
        database_digest="d" * 64,
        historical_evidence=direct_provenance_receipt(module, source_rows),
    )

    assert receipt.status == "certified"
    assert receipt.row_count == 1
    assert receipt.dimension == 1024
    assert all(len(value) == 64 for value in (receipt.row_digest, receipt.payload_digest, receipt.vector_digest))
    assert module.decode_stage_a_vector(rows[0]) == [0.25] * 1024


def test_build_stage_a_fails_closed_on_wrong_dimension() -> None:
    module = load_module()
    source_rows = [{"node_id": "node-a", "document": "alpha", "metadata": {}, "embedding": [0.25] * 8}]
    collection = FakeCollection(source_rows)

    receipt, rows = module.build_stage_a(
        collection,
        [asset("node-a")],
        database_digest="d" * 64,
        historical_evidence=direct_provenance_receipt(module, source_rows),
    )

    assert receipt.status == "blocked"
    assert rows == []
    assert "chroma_vector_contract_mismatch:node-a" in receipt.blockers
    assert "chroma_expected_row_count_mismatch" in receipt.blockers


def test_build_stage_a_does_not_certify_indirect_provider_evidence() -> None:
    module = load_module()
    collection = FakeCollection(
        [{"node_id": "node-a", "document": "alpha", "metadata": {}, "embedding": [0.25] * 1024}]
    )

    receipt, rows = module.build_stage_a(
        collection,
        [asset("node-a")],
        database_digest="d" * 64,
        historical_evidence={"evidence_strength": "indirect_specific_workspace_chain"},
    )

    assert receipt.status == "blocked"
    assert receipt.row_count == 1
    assert len(rows) == 1
    assert receipt.blockers == ("chroma_vector_provenance_unverified",)


@pytest.mark.parametrize(
    ("field", "value", "expected_blocker"),
    [
        ("database_digest", "e" * 64, "chroma_database_digest_mismatch"),
        ("expected_row_count", 2, "chroma_expected_row_count_mismatch"),
        ("node_id_digest", "e" * 64, "chroma_node_id_digest_mismatch"),
        ("vector_digest", "e" * 64, "chroma_vector_digest_mismatch"),
    ],
)
def test_build_stage_a_requires_exact_direct_receipt_bindings(field, value, expected_blocker) -> None:
    module = load_module()
    source_rows = [
        {"node_id": "node-a", "document": "alpha", "metadata": {}, "embedding": [0.25] * 1024}
    ]
    evidence = direct_provenance_receipt(module, source_rows)
    evidence[field] = value

    receipt, _rows = module.build_stage_a(
        FakeCollection(source_rows),
        [asset("node-a")],
        database_digest="d" * 64,
        historical_evidence=evidence,
    )

    assert receipt.status == "blocked"
    assert expected_blocker in receipt.blockers


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

    receipt, rows = module.build_stage_b_inventory(assets, [], ["card-a"])

    assert receipt.status == "inventory_unverified"
    assert receipt.row_count == 3
    assert receipt.by_artifact_type == {
        "docling_extracted_image": 1,
        "docling_page_package": 1,
        "qwen_reviewed_visual_card": 1,
    }
    assert {row["adapter_state"] for row in rows} == {"inventory_only_no_provider_calls"}
    assert next(row for row in rows if row["node_id"] == "image-a")["input_sha256"] == image_hash
    card = next(row for row in rows if row["node_id"] == "card-a")
    assert card["qdrant_state"] == "present_unverified"
    assert card["payload_hash_state"] == "present_unverified"


def test_stage_b_never_derives_or_certifies_invalid_payload_hash() -> None:
    module = load_module()
    invalid = asset("card-a", artifact_type="qwen_reviewed_visual_card")
    invalid["metadata"]["payload_hash"] = "valid-looking-but-not-a-digest"

    receipt, rows = module.build_stage_b_inventory([invalid], [], [])

    assert receipt.status == "blocked"
    assert receipt.blockers == ("card-a:payload_hash_invalid",)
    assert rows[0]["payload_hash"] == ""
    assert rows[0]["payload_hash_state"] == "invalid_or_missing"


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
    module.DEFAULT_RECOVERY_ROOT = linked

    with pytest.raises(module.RecoveryError, match="symlink_output_path_refused"):
        module.create_private_run_dir("visual-recovery-20260813T120000Z-1234abcd")


def test_cli_rejects_output_root_override(tmp_path: Path) -> None:
    module = load_module()

    with pytest.raises(SystemExit):
        module.build_parser().parse_args(["--output-root", str(tmp_path)])


def test_chroma_database_digest_includes_wal_and_shm(tmp_path: Path) -> None:
    module = load_module()
    (tmp_path / "chroma.sqlite3").write_bytes(b"main")
    without_journal = module.digest_file_tree(tmp_path)
    (tmp_path / "chroma.sqlite3-wal").write_bytes(b"wal-a")
    (tmp_path / "chroma.sqlite3-shm").write_bytes(b"shm-a")
    with_journal = module.digest_file_tree(tmp_path)
    (tmp_path / "chroma.sqlite3-wal").write_bytes(b"wal-b")
    changed_journal = module.digest_file_tree(tmp_path)

    assert with_journal != without_journal
    assert changed_journal != with_journal


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
    source_rows = [{"node_id": "node-a", "document": "alpha", "metadata": {}, "embedding": [0.5] * 1024}]
    collection = FakeCollection(source_rows)
    monkeypatch.setattr(module, "_open_chroma_collection", lambda *_args: collection)
    database_digest = module.digest_file_tree(chroma_dir)
    monkeypatch.setattr(
        module,
        "validate_historical_evidence",
        lambda *_args: direct_provenance_receipt(module, source_rows, database_digest=database_digest),
    )
    monkeypatch.setattr(module, "DEFAULT_RECOVERY_ROOT", tmp_path / "runs")
    parser = module.build_parser()
    args = parser.parse_args(
        [
            "--manifest",
            str(manifest),
            "--chroma-dir",
            str(chroma_dir),
        ]
    )

    result = module.plan_recovery(
        args,
        audit_raw=audit_payload(
            module,
            manifest,
            assets,
            actual_ids=[module.dantedash_point_id("node-a")],
        ),
    )

    assert result["mode"] == "dry_run"
    assert result["mutation_performed"] is False
    assert result["provider_calls_performed"] == 0
    run_dir = tmp_path / "runs" / result["run_id"]
    plan = json.loads((run_dir / "plan.json").read_text(encoding="utf-8"))
    assert plan["stage_a"]["status"] == "certified"
    assert plan["stage_b"]["row_count"] == 0
    assert plan["baseline"]["content_exactness"] == "unverified"
    assert plan["baseline"]["zero_write_replay_claimed"] is False
    assert plan["execution"]["stage_a_supported"] is False
    assert plan["execution"]["stage_b_supported"] is False
    stage_a_row = json.loads((run_dir / "stage-a-source-bundle.jsonl").read_text(encoding="utf-8"))
    assert stage_a_row["qdrant_state"] == "present_unverified"
    assert (run_dir / "stage-a-source-bundle.jsonl").stat().st_mode & 0o777 == 0o400
    assert (run_dir / "ledger.jsonl").stat().st_mode & 0o777 == 0o600


def test_conflicting_qdrant_audit_blocks_before_plan_creation(tmp_path: Path) -> None:
    module = load_module()
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
    point_id = module.dantedash_point_id("node-a")
    raw = audit_payload(module, manifest, assets, actual_ids=[point_id])
    raw["drift"]["point_conflict_ids"] = [point_id]
    audit = module.parse_audit(raw, ["node-a"])

    with pytest.raises(module.RecoveryError, match="audit_point_conflicts_present"):
        module.validate_audit_contract(
            audit,
            ["node-a"],
            "visual_memory__voyage_multimodal_3_5_1024",
        )
