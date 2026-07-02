# Docling Cinema Batches

This runbook covers the safe Docling conversion layer for the external cinema PDF corpus. It prepares extraction outputs for later Knowledge Hub, LightRAG, multimodal, or CAG work. It does not ingest anything by itself.

## Scope

The batch runner reads an external source root, inventories PDFs, classifies each file into a Docling lane, writes manifests, and optionally runs bounded conversion jobs. Source PDFs are read-only inputs.

Do not use this workflow to mutate Knowledge Hub, LightRAG, multimodal, Qdrant, Postgres, Redis, Chroma, vault files, Notion, or CAG packs. Those surfaces need a separate ingest plan after Docling outputs are reviewed.

## Lanes

| Lane | Use | Selection signal |
|---|---|---|
| Level A | Clean short text-first PDFs | Healthy text probe, short page count, modest file size |
| Level C | Main cinema corpus | Default for books, manuals, visual theory, directing, editing, and layout-rich PDFs |
| Level B | Rescue and OCR-heavy PDFs | Weak text probe, probe errors, scanned PDFs, failed C output, or high-value OCR needs |

Large files are flagged separately even when their lane is C. Run them as isolated shards so a single slow conversion does not block the rest of the corpus.

## Safe Operating Shape

Start with inventory or dry-run. Review the manifest before any apply run. Then run a smoke set with one representative file per lane. Only after the smoke artifacts look healthy should an operator run bounded batches.

Generated artifacts live under `logs/docling-runs/<run-id>/`:

- `docling-cinema-batch-summary.json`
- `docling-cinema-batch-manifest.tsv`
- `docling-cinema-batch-retry.jsonl`
- `docling-cinema-batch-output-index.jsonl`
- `outputs/`

The manifest uses source-relative paths and source hashes. It should not expose machine-specific source roots.

## Review Checklist

- Every PDF has one manifest row.
- Level C is the dominant lane unless the corpus has changed materially.
- Level B rows are explainable by weak text probes, probe errors, scan-heavy content, or retries.
- Smoke includes A, C, and B when those lanes exist.
- Failed rows appear in the retry artifact.
- Validation warnings are reviewed before downstream ingest.
- No downstream store was mutated by this workflow.

## Handoff

After conversion, a separate plan should decide what enters Knowledge Hub classic, LightRAG KH-native, multimodal, and CAG packs. That plan should use the output index, retry list, validation summary, source hashes, and any manual quality review notes from this run.
