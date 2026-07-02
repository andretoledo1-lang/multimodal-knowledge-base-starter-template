from __future__ import annotations

from pathlib import Path

from app import docling_cinema_batch as subject


def make_pdf(root: Path, relative: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"%PDF fixture")


def test_cli_dry_run_does_not_call_runner(tmp_path: Path, monkeypatch, capsys) -> None:
    root = tmp_path / "cinema"
    make_pdf(root, "topic/clean.pdf")
    monkeypatch.setattr(
        subject,
        "probe_pdf",
        lambda _path, *, max_pages=subject.DEFAULT_PROBE_PAGES: subject.PdfProbe(page_count=10, sampled_text_chars=2_000),
    )
    monkeypatch.setattr(subject, "sha256_file", lambda _path: "a" * 64)

    def failing_runner(*_args, **_kwargs):
        raise AssertionError("runner should not be called")

    code = subject.main(
        [
            "--source-root",
            str(root),
            "--artifact-root",
            str(tmp_path / "runs"),
            "--run-id",
            "test-run",
        ],
        runner=failing_runner,
    )

    assert code == 0
    assert '"apply": false' in capsys.readouterr().out


def test_cli_apply_uses_fake_runner(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "cinema"
    make_pdf(root, "topic/clean.pdf")
    monkeypatch.setattr(
        subject,
        "probe_pdf",
        lambda _path, *, max_pages=subject.DEFAULT_PROBE_PAGES: subject.PdfProbe(page_count=10, sampled_text_chars=2_000),
    )
    monkeypatch.setattr(subject, "sha256_file", lambda _path: "a" * 64)

    def fake_runner(
        row: subject.InventoryRow,
        _source: Path,
        output_root: Path,
        _level: subject.DoclingLevel,
    ) -> subject.RunnerResult:
        output = output_root / row.source_sha256[:8]
        output.mkdir(parents=True)
        (output / "document.md").write_text("Extracted. " * 80, encoding="utf-8")
        return subject.RunnerResult(ok=True, output_dir=output)

    code = subject.main(
        [
            "--source-root",
            str(root),
            "--artifact-root",
            str(tmp_path / "runs"),
            "--run-id",
            "test-run",
            "--apply",
        ],
        runner=fake_runner,
    )

    assert code == 0
    assert (tmp_path / "runs" / "test-run" / "docling-cinema-batch-summary.json").exists()
