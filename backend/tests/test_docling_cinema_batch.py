from __future__ import annotations

import json
from pathlib import Path

from app import docling_cinema_batch as subject


def make_pdf(root: Path, relative: str, body: bytes = b"%PDF fixture") -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    return path


def patch_probe_and_hash(monkeypatch, probes: dict[str, subject.PdfProbe]) -> None:
    def fake_probe(path: Path, *, max_pages: int = subject.DEFAULT_PROBE_PAGES) -> subject.PdfProbe:
        return probes[path.name]

    def fake_hash(path: Path) -> str:
        digest = f"{path.name}:hash"
        return digest.encode().hex().ljust(64, "0")[:64]

    monkeypatch.setattr(subject, "probe_pdf", fake_probe)
    monkeypatch.setattr(subject, "sha256_file", fake_hash)


def test_inventory_classifies_a_c_b_and_large_rows(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "cinema"
    clean = make_pdf(root, "teaching/glossary.pdf", b"a" * 100)
    canonical = make_pdf(root, "history/canonical.pdf", b"b" * 100)
    weak = make_pdf(root, "scans/scan.pdf", b"c" * 100)
    probes = {
        clean.name: subject.PdfProbe(page_count=30, sampled_text_chars=2_000),
        canonical.name: subject.PdfProbe(page_count=320, sampled_text_chars=3_000),
        weak.name: subject.PdfProbe(page_count=80, sampled_text_chars=10),
    }
    patch_probe_and_hash(monkeypatch, probes)

    rows = subject.inventory_source(root)

    by_name = {Path(row.source_relative_path).name: row for row in rows}
    assert by_name["glossary.pdf"].docling_level == "A"
    assert by_name["glossary.pdf"].selection_reason == "clean_short_text_first"
    assert by_name["canonical.pdf"].docling_level == "C"
    assert by_name["canonical.pdf"].is_large is True
    assert by_name["scan.pdf"].docling_level == "B"
    assert by_name["scan.pdf"].text_probe_status == "weak"


def test_inventory_blocks_path_outside_source_root(tmp_path: Path) -> None:
    root = tmp_path / "cinema"
    root.mkdir()
    outside = tmp_path / "outside.pdf"
    outside.write_bytes(b"pdf")

    try:
        subject.inventory_source(root, only_relative_paths=["../outside.pdf"])
    except ValueError as exc:
        assert "path_outside_source_root" in str(exc)
    else:
        raise AssertionError("expected outside path rejection")


def test_inventory_marks_duplicate_hashes_visible(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "cinema"
    first = make_pdf(root, "a/first.pdf")
    second = make_pdf(root, "b/second.pdf")
    probes = {
        first.name: subject.PdfProbe(page_count=40, sampled_text_chars=2_000),
        second.name: subject.PdfProbe(page_count=40, sampled_text_chars=2_000),
    }
    monkeypatch.setattr(subject, "probe_pdf", lambda path, *, max_pages=3: probes[path.name])
    monkeypatch.setattr(subject, "sha256_file", lambda _path: "a" * 64)

    rows = subject.inventory_source(root)

    assert [row.status for row in rows] == ["queued", "skipped_duplicate_in_run"]
    assert len(rows) == 2


def test_select_smoke_rows_picks_one_per_lane(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "cinema"
    make_pdf(root, "a/clean.pdf")
    make_pdf(root, "b/main.pdf")
    make_pdf(root, "c/scan.pdf")
    probes = {
        "clean.pdf": subject.PdfProbe(page_count=20, sampled_text_chars=2_000),
        "main.pdf": subject.PdfProbe(page_count=220, sampled_text_chars=2_000),
        "scan.pdf": subject.PdfProbe(page_count=20, sampled_text_chars=2),
    }
    patch_probe_and_hash(monkeypatch, probes)

    rows = subject.inventory_source(root)
    smoke = subject.select_smoke_rows(rows)

    assert [row.docling_level for row in smoke] == ["A", "C", "B"]


def test_run_batch_dry_run_writes_manifests_without_runner(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "cinema"
    make_pdf(root, "a/clean.pdf")
    patch_probe_and_hash(monkeypatch, {"clean.pdf": subject.PdfProbe(page_count=20, sampled_text_chars=2_000)})
    rows = subject.inventory_source(root)

    def failing_runner(*_args, **_kwargs):
        raise AssertionError("runner should not be called")

    result = subject.run_batch(root, rows, tmp_path / "run", runner=failing_runner)

    assert Path(result["manifest_path"]).exists()
    assert Path(result["retry_path"]).read_text(encoding="utf-8") == ""
    summary = json.loads(Path(result["summary_path"]).read_text(encoding="utf-8"))
    assert summary["apply"] is False
    assert summary["by_status"] == {"queued": 1}


def test_run_batch_apply_uses_fake_runner_and_validates_output(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "cinema"
    make_pdf(root, "a/clean.pdf")
    patch_probe_and_hash(monkeypatch, {"clean.pdf": subject.PdfProbe(page_count=20, sampled_text_chars=2_000)})
    rows = subject.inventory_source(root)

    def fake_runner(
        row: subject.InventoryRow,
        _source: Path,
        output_root: Path,
        _level: subject.DoclingLevel,
    ) -> subject.RunnerResult:
        output_dir = output_root / row.source_sha256[:8]
        output_dir.mkdir(parents=True)
        (output_dir / "document.md").write_text("Good extracted text. " * 40, encoding="utf-8")
        return subject.RunnerResult(ok=True, output_dir=output_dir)

    result = subject.run_batch(root, rows, tmp_path / "run", apply=True, runner=fake_runner)

    summary = json.loads(Path(result["summary_path"]).read_text(encoding="utf-8"))
    assert summary["by_status"] == {"converted": 1}
    output_index = Path(result["output_index_path"]).read_text(encoding="utf-8")
    assert "clean.pdf" in output_index


def test_run_batch_failed_runner_writes_retry_manifest(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "cinema"
    make_pdf(root, "a/clean.pdf")
    patch_probe_and_hash(monkeypatch, {"clean.pdf": subject.PdfProbe(page_count=20, sampled_text_chars=2_000)})
    rows = subject.inventory_source(root)

    def fake_runner(
        row: subject.InventoryRow,
        _source: Path,
        output_root: Path,
        _level: subject.DoclingLevel,
    ) -> subject.RunnerResult:
        return subject.RunnerResult(ok=False, output_dir=output_root / row.source_sha256[:8], stderr="boom")

    result = subject.run_batch(root, rows, tmp_path / "run", apply=True, runner=fake_runner)

    summary = json.loads(Path(result["summary_path"]).read_text(encoding="utf-8"))
    retry = Path(result["retry_path"]).read_text(encoding="utf-8")
    assert summary["by_status"] == {"failed": 1}
    assert "boom" in retry


def test_inventory_resume_skips_existing_success_from_manifest(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "cinema"
    make_pdf(root, "a/clean.pdf")
    patch_probe_and_hash(monkeypatch, {"clean.pdf": subject.PdfProbe(page_count=20, sampled_text_chars=2_000)})
    initial_rows = subject.inventory_source(root)
    initial_rows[0].status = "converted"
    run_dir = tmp_path / "run"
    subject.write_artifacts(run_dir, initial_rows, subject.summary_payload(initial_rows, run_dir=run_dir, apply=True, smoke=False))

    resumed_rows = subject.inventory_source(root, existing_successes=subject.load_existing_successes(run_dir))

    assert resumed_rows[0].status == "skipped_existing"


def test_validate_output_warns_on_tiny_markdown(tmp_path: Path) -> None:
    output = tmp_path / "out"
    output.mkdir()
    (output / "document.md").write_text("tiny", encoding="utf-8")
    row = subject.InventoryRow(
        row_number=1,
        source_relative_path="topic/long.pdf",
        topic_folder="topic",
        source_root_label="cinema",
        source_sha256="a" * 64,
        bytes=10,
        page_count=50,
        sampled_text_chars=1_000,
        docling_level="C",
        selection_reason="main_cinema_hybrid_default",
        is_large=False,
        text_probe_status="healthy",
    )

    result = subject.validate_output(row, output)

    assert result.status == "validation_warning"
    assert result.reason == "markdown_too_small_for_pdf"


def test_run_docling_passes_level_and_output_root(tmp_path: Path, monkeypatch) -> None:
    source = make_pdf(tmp_path, "cinema/topic/file.pdf")
    row = subject.InventoryRow(
        row_number=1,
        source_relative_path="topic/file.pdf",
        topic_folder="topic",
        source_root_label="cinema",
        source_sha256="a" * 64,
        bytes=10,
        page_count=10,
        sampled_text_chars=1_000,
        docling_level="C",
        selection_reason="main_cinema_hybrid_default",
        is_large=False,
        text_probe_status="healthy",
    )
    calls = []

    class Result:
        returncode = 0
        stdout = "ok"
        stderr = ""

    def fake_run(cmd, **_kwargs):
        calls.append(cmd)
        return Result()

    monkeypatch.setattr(subject.shutil, "which", lambda name: "/bin/docling" if name == "docling" else None)
    monkeypatch.setattr(subject.subprocess, "run", fake_run)

    result = subject.run_docling(row, source, tmp_path / "run" / "outputs", "C")

    assert result.ok is True
    assert calls == [["/bin/docling", "C", str(source), "--output", str(result.output_dir)]]
    assert result.output_dir.is_relative_to(tmp_path / "run" / "outputs")
