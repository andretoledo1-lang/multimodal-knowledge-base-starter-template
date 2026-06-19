# Knowledge Hub Cutover Certification

- Run id: `kh-cutover-certification-20260619T143442Z`
- Generated at: `2026-06-19T14:35:06.311537+00:00`
- Final score: `0.2137` / gate `0.89`
- Decision: `no_go_continue_repairs`
- Recommendation: NO-GO. Continue repairs before any Chroma disablement.

## Baseline

- DanteDash rows: `8099`
- DanteDash modalities: `{"image": 2231, "text": 4187, "video": 1681}`
- Chroma to KH relationships: `{"missing_in_kh": 8099}`
- KH active visual collection: `visual_memory__voyage_multimodal_3_5_1024`
- KH active visual points: `1750`
- KH visual manifest assets: `1754` across `12` manifests

## Score Dimensions

| Dimension | Weight | Score |
|---|---:|---:|
| inventory_coverage | 0.16 | 0.0000 |
| package_integrity | 0.14 | 0.0000 |
| vector_provenance | 0.10 | 0.8814 |
| search_parity | 0.16 | 0.0000 |
| preview_dto_library_stats | 0.12 | 0.0000 |
| chat_context_sources | 0.12 | 0.2000 |
| dual_fallback_independence | 0.10 | 0.0156 |
| safety_no_leak | 0.10 | 1.0000 |

## Hard Caps And Blockers

- Hard cap: `0.88`
- Hard cap reasons: `chat_source_or_citation_path_broken, critical_stratum_below_threshold:explicit_image_id, critical_stratum_below_threshold:semantic_visual, critical_stratum_below_threshold:film_style, critical_stratum_below_threshold:decoupage_language, critical_stratum_below_threshold:video_keyframe, critical_public_surface_check_failed, kh_public_dto_surfaces_unavailable`
- Blockers: `chat_context_sources_below_gate, chat_source_or_citation_path_broken, critical_public_surface_check_failed, critical_stratum_below_threshold:decoupage_language, critical_stratum_below_threshold:explicit_image_id, critical_stratum_below_threshold:film_style, critical_stratum_below_threshold:semantic_visual, critical_stratum_below_threshold:video_keyframe, inventory_coverage_below_gate, kh_public_dto_surfaces_unavailable, no_granular_kh_visual_package_import, no_verified_chroma_vector_reuse_path, search_parity_below_gate`

## Query Suite

| Stratum | Chroma | KH | Recall | Passed |
|---|---:|---:|---:|---|
| explicit_image_id | 5 | 2 | 0.0000 | False |
| semantic_visual | 5 | 0 | 0.0000 | False |
| film_style | 5 | 0 | 0.0000 | False |
| decoupage_language | 5 | 0 | 0.0000 | False |
| video_keyframe | 5 | 0 | 0.0000 | False |

## Import Finding

- Official full sync available: `True`
- Granular DanteDash package import available: `False`
- Verified Chroma vector reuse path available: `False`
- Mutation performed in this certification: `False`

## Missing Import Dry Run

- Candidate rows: `8099`
- Candidate modalities: `{"image": 2231, "text": 4187, "video": 1681}`
- Candidate artifact types: `{"local_media_asset": 1818, "unknown": 2094, "visual_analysis_bundle": 2094, "visual_decoupage_bundle": 2093}`
- Dry-run manifest: `backend/runtime_reports/kh-cutover/kh-missing-import-dry-run.tsv`
- Dry-run summary: `backend/runtime_reports/kh-cutover/kh-missing-import-dry-run-summary.json`
- Mutation performed: `False`
- Blocked reason: `No KH-owned granular DanteDash package import or verified Chroma vector reuse path exists yet.`

## Next Actions

- Create a KH-owned DanteDash visual package import that preserves source_sha256 and dante_image_id.
- Add or expose an official KH import surface for DanteDash package manifests instead of direct Qdrant writes.
- Either verify a safe vector-copy path or accept a targeted Voyage backfill with cost and manifest evidence.
