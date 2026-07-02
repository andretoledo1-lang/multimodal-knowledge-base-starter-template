"""Manifest-first Docling batch planning for external cinema PDFs."""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import shutil
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Iterable, Literal, Sequence

from pypdf import PdfReader

SCHEMA_VERSION = "docling_cinema_batch.v1"
RUN_PREFIX = "docling-cinema-batch"
DEFAULT_ARTIFACT_ROOT = Path("logs/docling-runs")
DEFAULT_OUTPUT_ROOT_NAME = "outputs"
LARGE_BYTES_THRESHOLD = 50 * 1024 * 1024
LARGE_PAGES_THRESHOLD = 250
LEVEL_A_MAX_PAGES = 120
LEVEL_A_MAX_BYTES = 25 * 1024 * 1024
WEAK_TEXT_PROBE_CHARS = 400
DEFAULT_PROBE_PAGES = 3

DoclingLevel = Literal["A", "B", "C"]
RowStatus = Literal[
    "queued",
    "smoke_selected",
    "skipped_existing",
    "skipped_duplicate_in_run",
    "converted",
    "failed",
    "validation_warning",
    "needs_review",
]
Runner = Callable[["InventoryRow", Path, Path, DoclingLevel], "RunnerResult"]


@dataclass(frozen=True)
class PdfProbe:
    page_count: int | None
    sampled_text_chars: int
    error: str = ""


@dataclass
class InventoryRow:
    row_number: int
    source_relative_path: str
    topic_folder: str
    source_root_label: str
    source_sha256: str
    bytes: int
    page_count: int | None
    sampled_text_chars: int
    docling_level: DoclingLevel
    selection_reason: str
    is_large: bool
    text_probe_status: str
    status: RowStatus = "queued"
    output_relative_path: str = ""
    error: str = ""


@dataclass(frozen=True)
class RunnerResult:
    ok: bool
    output_dir: Path
    stdout: str = ""
    stderr: str = ""
    returncode: int = 0


@dataclass(frozen=True)
class ValidationResult:
    status: RowStatus
    reason: str
    markdown_chars: int
    output_files: int


def default_run_id() -> str:
    return f"{RUN_PREFIX}-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}"


def inventory_source(
    source_root: Path,
    *,
    only_relative_paths: Sequence[str] | None = None,
    probe_pages: int = DEFAULT_PROBE_PAGES,
    existing_successes: set[tuple[str, str]] | None = None,
) -> list[InventoryRow]:
    root = _resolve_source_root(source_root)
    files = discover_pdfs(root, only_relative_paths=only_relative_paths)
    existing_successes = existing_successes or set()
    rows: list[InventoryRow] = []
    seen_hashes: set[str] = set()
    for index, path in enumerate(files, 1):
        relative_path = path.relative_to(root).as_posix()
        digest = sha256_file(path)
        probe = probe_pdf(path, max_pages=probe_pages)
        level, reason = classify_doc(path, probe)
        status: RowStatus = "queued"
        if (digest, level) in existing_successes:
            status = "skipped_existing"
        elif digest in seen_hashes:
            status = "skipped_duplicate_in_run"
        else:
            seen_hashes.add(digest)
        rows.append(
            InventoryRow(
                row_number=index,
                source_relative_path=relative_path,
                topic_folder=_topic_folder(relative_path),
                source_root_label=root.name,
                source_sha256=digest,
                bytes=path.stat().st_size,
                page_count=probe.page_count,
                sampled_text_chars=probe.sampled_text_chars,
                docling_level=level,
                selection_reason=reason,
                is_large=is_large_pdf(path, probe.page_count),
                text_probe_status=text_probe_status(probe),
                status=status,
            )
        )
    return rows


def load_existing_successes(run_dir: Path) -> set[tuple[str, str]]:
    manifest_path = run_dir / "docling-cinema-batch-manifest.tsv"
    if not manifest_path.exists():
        return set()
    successes: set[tuple[str, str]] = set()
    with manifest_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        for row in reader:
            status = row.get("status", "")
            source_sha256 = row.get("source_sha256", "")
            level = row.get("docling_level", "")
            if status in {"converted", "validation_warning", "needs_review"} and source_sha256 and level in {"A", "B", "C"}:
                successes.add((source_sha256, level))
    return successes


def discover_pdfs(source_root: Path, *, only_relative_paths: Sequence[str] | None = None) -> list[Path]:
    root = _resolve_source_root(source_root)
    if only_relative_paths:
        files = []
        for relative in only_relative_paths:
            path = (root / relative).resolve()
            if not path.is_relative_to(root):
                raise ValueError(f"path_outside_source_root: {relative}")
            if not path.is_file():
                raise FileNotFoundError(path)
            if path.suffix.lower() != ".pdf":
                raise ValueError(f"unsupported_non_pdf: {relative}")
            files.append(path)
        return sorted(files, key=lambda item: item.relative_to(root).as_posix().lower())
    return sorted(
        [path for path in root.rglob("*.pdf") if path.is_file()],
        key=lambda item: item.relative_to(root).as_posix().lower(),
    )


def _resolve_source_root(source_root: Path) -> Path:
    root = source_root.expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise ValueError(f"source_root_not_found: {source_root}")
    return root


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def probe_pdf(path: Path, *, max_pages: int = DEFAULT_PROBE_PAGES) -> PdfProbe:
    try:
        reader = PdfReader(str(path))
        page_count = len(reader.pages)
        sampled_text = []
        for page in reader.pages[: max(1, max_pages)]:
            sampled_text.append(page.extract_text() or "")
        return PdfProbe(page_count=page_count, sampled_text_chars=len("\n".join(sampled_text).strip()))
    except Exception as exc:  # noqa: BLE001
        return PdfProbe(page_count=None, sampled_text_chars=0, error=f"{type(exc).__name__}: {str(exc)[:300]}")


def classify_doc(path: Path, probe: PdfProbe) -> tuple[DoclingLevel, str]:
    if probe.error:
        return "B", "probe_error_rescue"
    if probe.sampled_text_chars < WEAK_TEXT_PROBE_CHARS:
        return "B", "weak_text_probe_rescue"
    page_count = probe.page_count or 0
    if page_count <= LEVEL_A_MAX_PAGES and path.stat().st_size <= LEVEL_A_MAX_BYTES:
        return "A", "clean_short_text_first"
    return "C", "main_cinema_hybrid_default"


def is_large_pdf(path: Path, page_count: int | None) -> bool:
    return path.stat().st_size >= LARGE_BYTES_THRESHOLD or (page_count or 0) >= LARGE_PAGES_THRESHOLD


def text_probe_status(probe: PdfProbe) -> str:
    if probe.error:
        return "probe_error"
    if probe.sampled_text_chars < WEAK_TEXT_PROBE_CHARS:
        return "weak"
    return "healthy"


def select_smoke_rows(rows: Sequence[InventoryRow]) -> list[InventoryRow]:
    selected: list[InventoryRow] = []
    for level in ("A", "C", "B"):
        row = next((item for item in rows if item.status == "queued" and item.docling_level == level), None)
        if row:
            selected.append(row)
    return selected


def run_batch(
    source_root: Path,
    rows: Sequence[InventoryRow],
    run_dir: Path,
    *,
    apply: bool = False,
    smoke: bool = False,
    levels: set[DoclingLevel] | None = None,
    limit: int | None = None,
    runner: Runner | None = None,
) -> dict[str, object]:
    root = _resolve_source_root(source_root)
    run_dir.mkdir(parents=True, exist_ok=True)
    output_root = run_dir / DEFAULT_OUTPUT_ROOT_NAME
    runner = runner or run_docling
    planned = [row for row in rows if row.status == "queued" and (levels is None or row.docling_level in levels)]
    if smoke:
        planned = select_smoke_rows(planned)
        for row in planned:
            row.status = "smoke_selected"
    if limit is not None:
        planned = planned[:limit]

    if apply:
        for row in planned:
            row.status = "queued" if row.status == "smoke_selected" else row.status
            source_path = root / row.source_relative_path
            try:
                result = runner(row, source_path, output_root, row.docling_level)
            except Exception as exc:  # noqa: BLE001
                row.status = "failed"
                row.error = f"{type(exc).__name__}: {str(exc)[:500]}"
                continue
            row.output_relative_path = result.output_dir.relative_to(run_dir).as_posix() if result.output_dir.is_relative_to(run_dir) else ""
            if not result.ok:
                row.status = "failed"
                row.error = _runner_error(result)
                continue
            validation = validate_output(row, result.output_dir)
            row.status = validation.status
            row.error = "" if validation.status == "converted" else validation.reason
    summary = summary_payload(rows, run_dir=run_dir, apply=apply, smoke=smoke)
    write_artifacts(run_dir, rows, summary)
    return {
        "summary_path": str(run_dir / "docling-cinema-batch-summary.json"),
        "manifest_path": str(run_dir / "docling-cinema-batch-manifest.tsv"),
        "retry_path": str(run_dir / "docling-cinema-batch-retry.jsonl"),
        "output_index_path": str(run_dir / "docling-cinema-batch-output-index.jsonl"),
        "summary": summary,
        "output_root": str(output_root),
    }


def run_docling(row: InventoryRow, source_path: Path, output_root: Path, level: DoclingLevel) -> RunnerResult:
    executable = shutil.which("docling")
    if not executable:
        raise FileNotFoundError("docling executable not found on PATH")
    output_dir = output_root / f"{_safe_output_stem(row.source_relative_path)}-{level.lower()}"
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    cmd = [executable, level, str(source_path), "--output", str(output_dir)]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)  # noqa: S603
    return RunnerResult(
        ok=result.returncode == 0,
        output_dir=output_dir,
        stdout=result.stdout[-2000:],
        stderr=result.stderr[-2000:],
        returncode=result.returncode,
    )


def validate_output(row: InventoryRow, output_dir: Path) -> ValidationResult:
    if not output_dir.exists() or not output_dir.is_dir():
        return ValidationResult(status="failed", reason="missing_output_dir", markdown_chars=0, output_files=0)
    files = [path for path in output_dir.rglob("*") if path.is_file()]
    markdown_chars = 0
    for path in files:
        if path.suffix.lower() in {".md", ".markdown"}:
            markdown_chars += len(path.read_text(encoding="utf-8", errors="replace").strip())
    if markdown_chars == 0:
        return ValidationResult(status="failed", reason="missing_markdown_output", markdown_chars=0, output_files=len(files))
    if row.docling_level == "B" and row.text_probe_status == "weak" and markdown_chars < WEAK_TEXT_PROBE_CHARS:
        return ValidationResult(
            status="needs_review",
            reason="weak_probe_without_ocr_coverage_signal",
            markdown_chars=markdown_chars,
            output_files=len(files),
        )
    min_expected = 200 if (row.page_count or 0) <= 5 else 500
    if markdown_chars < min_expected:
        return ValidationResult(
            status="validation_warning",
            reason="markdown_too_small_for_pdf",
            markdown_chars=markdown_chars,
            output_files=len(files),
        )
    return ValidationResult(status="converted", reason="ok", markdown_chars=markdown_chars, output_files=len(files))


def write_artifacts(run_dir: Path, rows: Sequence[InventoryRow], summary: dict[str, object]) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "docling-cinema-batch-summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (run_dir / "docling-cinema-batch-manifest.tsv").write_text(rows_to_tsv(rows), encoding="utf-8")
    _write_jsonl(run_dir / "docling-cinema-batch-retry.jsonl", (asdict(row) for row in rows if row.status == "failed"))
    _write_jsonl(
        run_dir / "docling-cinema-batch-output-index.jsonl",
        (asdict(row) for row in rows if row.status in {"converted", "validation_warning", "needs_review"}),
    )


def summary_payload(rows: Sequence[InventoryRow], *, run_dir: Path, apply: bool, smoke: bool) -> dict[str, object]:
    by_status: dict[str, int] = {}
    by_level: dict[str, int] = {}
    for row in rows:
        by_status[row.status] = by_status.get(row.status, 0) + 1
        by_level[row.docling_level] = by_level.get(row.docling_level, 0) + 1
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_dir.name,
        "apply": apply,
        "smoke": smoke,
        "total_files": len(rows),
        "large_files": sum(1 for row in rows if row.is_large),
        "weak_text_probe_files": sum(1 for row in rows if row.text_probe_status == "weak"),
        "by_status": dict(sorted(by_status.items())),
        "by_level": dict(sorted(by_level.items())),
        "selected_bytes": sum(row.bytes for row in rows),
        "finished_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def rows_to_tsv(rows: Sequence[InventoryRow]) -> str:
    output = io.StringIO()
    fields = list(InventoryRow.__dataclass_fields__.keys())
    writer = csv.DictWriter(output, fieldnames=fields, delimiter="\t")
    writer.writeheader()
    for row in rows:
        writer.writerow(asdict(row))
    return output.getvalue()


def _write_jsonl(path: Path, rows: Iterable[dict[str, object]]) -> None:
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def _runner_error(result: RunnerResult) -> str:
    detail = result.stderr.strip() or result.stdout.strip() or f"returncode={result.returncode}"
    return detail[:500]


def _topic_folder(relative_path: str) -> str:
    parts = Path(relative_path).parts
    return parts[0] if parts else ""


def _safe_output_stem(relative_path: str) -> str:
    stem = Path(relative_path).with_suffix("").as_posix().lower()
    safe = "".join(char if char.isalnum() else "-" for char in stem)
    return "-".join(part for part in safe.split("-") if part)[:160] or "document"


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--artifact-root", type=Path, default=DEFAULT_ARTIFACT_ROOT)
    parser.add_argument("--only-relative-path", action="append", default=[])
    parser.add_argument("--level", action="append", choices=["A", "B", "C"], default=[])
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--apply", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None, *, runner: Runner | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    run_id = args.run_id or default_run_id()
    run_dir = args.artifact_root.expanduser().resolve() / run_id
    rows = inventory_source(
        args.source_root,
        only_relative_paths=args.only_relative_path,
        existing_successes=load_existing_successes(run_dir),
    )
    levels = set(args.level) if args.level else None
    result = run_batch(
        args.source_root,
        rows,
        run_dir,
        apply=args.apply,
        smoke=args.smoke,
        levels=levels,
        limit=args.limit,
        runner=runner,
    )
    print(json.dumps(result["summary"], indent=2, sort_keys=True))
    summary = result["summary"]
    failed = int(summary.get("by_status", {}).get("failed", 0)) if isinstance(summary.get("by_status"), dict) else 0
    return 0 if failed == 0 else 1
