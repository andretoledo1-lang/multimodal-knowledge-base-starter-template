# Dante Visual Asset Package Contract

This document is the operating contract for agents working on Dante Multimodal
Dashboard visual assets. It describes how each image is packaged now, how it
must be packaged after the premium decoupage ingest upgrade, and how all future
visual ingests must be linked.

## Core Rule

Every image is the root of a linked asset package. Do not treat image vectors,
Gemini visual cards, premium decoupage sidecars, Markdown handoffs, and JSON
schemas as unrelated documents.

The binding keys are:

- `dante_image_id`: human-readable canonical image id, for example
  `aftersun-2022-001`.
- `source_sha256`: stable file identity for the source image.
- `linked_image_file_id`: the Chroma node id for the visual image vector.
- `preview_image_file_id`: the Chroma node id that the dashboard uses for image
  preview.
- sidecar paths: JSON and Markdown files for each analysis layer.

## Current Package Shape

Verified example: `aftersun-2022-001`.

```text
aftersun-2022-001
├── canonical identity
│   ├── dante_image_id: aftersun-2022-001
│   ├── source_sha256: 0d25ee0747336d6011c0e137427b6acae705a0826a1196e233266d84544c90c2
│   ├── category: film-stills
│   ├── group: aftersun-2022
│   └── dataset_id: dante-visual-reference-assets
│
├── original image / preview
│   ├── source file:
│   │   /Users/vidigal/Obsidian_Dante_AI_RAG_DATA/visual-reference-assets/source-assets/film-stills/aftersun-2022/aftersun-2022-001.jpg
│   ├── exists on disk: yes
│   ├── KB node:
│   │   dante_visual_img_0d25ee0747336d6011c0e137427b6aca
│   ├── modality: image
│   ├── original_name: aftersun-2022-001.jpg
│   └── preview URL:
│       /api/preview/dante_visual_img_0d25ee0747336d6011c0e137427b6aca
│
├── visual embedding
│   ├── provider: Voyage
│   ├── model: voyage-multimodal-3.5
│   ├── dimensions: 1024
│   └── status: indexed in Chroma
│
├── current Gemini analysis
│   ├── JSON card:
│   │   /Users/vidigal/Dante/commercial-film-production-kb/13-visual-reference-assets/analysis-cards/cards/film-stills/aftersun-2022/aftersun-2022-001.json
│   ├── Markdown card:
│   │   /Users/vidigal/Dante/commercial-film-production-kb/13-visual-reference-assets/analysis-cards/cards/film-stills/aftersun-2022/aftersun-2022-001.md
│   ├── schema: image_analysis_card.v1
│   ├── artifact_type: visual_analysis_bundle
│   ├── KB node:
│   │   dante_visual_card_0d25ee0747336d6011c0e137427b6aca
│   ├── linked_image_file_id:
│   │   dante_visual_img_0d25ee0747336d6011c0e137427b6aca
│   ├── preview_image_file_id:
│   │   dante_visual_img_0d25ee0747336d6011c0e137427b6aca
│   └── status: indexed in Chroma as text
│
└── premium decoupage analysis
    ├── JSON sidecar:
    │   /Users/vidigal/Dante/commercial-film-production-kb/13-visual-reference-assets/analysis-cards/decoupage/sidecars/film-stills/aftersun-2022/aftersun-2022-001.json
    ├── Markdown handoff:
    │   /Users/vidigal/Dante/commercial-film-production-kb/13-visual-reference-assets/analysis-cards/decoupage/markdown/film-stills/aftersun-2022/aftersun-2022-001.md
    ├── profile_id:
    │   art_grade_decoupage_vision_analyst.gpt55_port.v1
    ├── lens: solo
    ├── frame_type: film_frame
    ├── source right now: mock smoke only
    └── status right now: exists on disk, not indexed in Chroma yet
```

Current KB shape remains:

```json
{"total": 4188, "by_modality": {"image": 2094, "text": 2094}}
```

This means the current KB contains image nodes plus Gemini card text nodes. It
does not yet contain premium decoupage text nodes.

## Target Package Shape After The Upgrade

After the decoupage ingest patch and the real premium model run, each image
package must look like this:

```text
aftersun-2022-001
├── canonical identity
│   ├── dante_image_id: aftersun-2022-001
│   ├── source_sha256: 0d25ee0747336d6011c0e137427b6acae705a0826a1196e233266d84544c90c2
│   ├── category: film-stills
│   ├── group: aftersun-2022
│   └── dataset_id: dante-visual-reference-assets
│
├── original image / preview
│   ├── source file:
│   │   /Users/vidigal/Obsidian_Dante_AI_RAG_DATA/visual-reference-assets/source-assets/film-stills/aftersun-2022/aftersun-2022-001.jpg
│   ├── KB node:
│   │   dante_visual_img_0d25ee0747336d6011c0e137427b6aca
│   ├── modality: image
│   └── preview URL:
│       /api/preview/dante_visual_img_0d25ee0747336d6011c0e137427b6aca
│
├── visual embedding
│   ├── provider: Voyage
│   ├── model: voyage-multimodal-3.5
│   ├── dimensions: 1024
│   └── status: indexed in Chroma
│
├── current Gemini analysis
│   ├── JSON card:
│   │   analysis-cards/cards/film-stills/aftersun-2022/aftersun-2022-001.json
│   ├── Markdown card:
│   │   analysis-cards/cards/film-stills/aftersun-2022/aftersun-2022-001.md
│   ├── KB node:
│   │   dante_visual_card_0d25ee0747336d6011c0e137427b6aca
│   ├── artifact_type: visual_analysis_bundle
│   ├── modality: text
│   ├── linked_image_file_id:
│   │   dante_visual_img_0d25ee0747336d6011c0e137427b6aca
│   └── preview_image_file_id:
│       dante_visual_img_0d25ee0747336d6011c0e137427b6aca
│
└── premium decoupage analysis
    ├── JSON structured sidecar:
    │   analysis-cards/decoupage/sidecars/film-stills/aftersun-2022/aftersun-2022-001.json
    ├── Markdown curator handoff:
    │   analysis-cards/decoupage/markdown/film-stills/aftersun-2022/aftersun-2022-001.md
    ├── KB node:
    │   dante_visual_decoupage_0d25ee0747336d6011c0e137427b6aca
    ├── artifact_type: visual_decoupage_bundle
    ├── modality: text
    ├── profile_id:
    │   art_grade_decoupage_vision_analyst.gpt55_port.v1
    ├── provider:
    │   openai-decoupage
    ├── model:
    │   gpt-5.5 or the approved OpenAI vision reasoning model
    ├── schema:
    │   decoupage_sidecar
    ├── linked_image_file_id:
    │   dante_visual_img_0d25ee0747336d6011c0e137427b6aca
    ├── preview_image_file_id:
    │   dante_visual_img_0d25ee0747336d6011c0e137427b6aca
    └── searchable content:
        ├── markdown_handoff
        ├── one_line
        ├── decoupage_spine
        ├── composition
        ├── camera_lens
        ├── lighting
        ├── color
        ├── art_direction
        ├── costume
        ├── performance
        ├── registers
        ├── lineage
        ├── distinction
        ├── grounding.visible
        ├── grounding.inferred
        ├── grounding.uncertain
        ├── grounding.not_visible
        ├── proactive_adjacencies
        └── opinion
```

## Future Ingest Rules

All new ingests for this visual corpus must preserve the package shape above.

Required behavior:

1. Ingest image vectors first or confirm that the existing image node exists.
2. Derive all text-layer node ids from the same `source_sha256`.
3. Fail or mark the row `missing_linked_image` when the image node is absent.
4. Store text-layer metadata with:
   - `dataset_id`
   - `artifact_type`
   - `source_sha256`
   - `dante_image_id`
   - `linked_image_file_id`
   - `preview_image_file_id`
   - absolute JSON and Markdown sidecar paths
   - relative JSON and Markdown sidecar paths
   - `category`
   - `group`
   - source run id and ingest run id
5. Preserve separate Chroma nodes for separate layers:
   - image vector node
   - Gemini visual card node
   - premium decoupage node
6. Let the dashboard group these nodes by `dante_image_id` / `source_sha256`.
7. Do not merge all layers into one giant text document unless Andre explicitly
   asks for an export bundle. The KB should stay layered and linkable.

Recommended node ids:

```text
dante_visual_img_<source_sha256[:32]>
dante_visual_card_<source_sha256[:32]>
dante_visual_decoupage_<source_sha256[:32]>
```

If future work adds multiple decoupage lenses per image, keep the primary
`solo` node as `dante_visual_decoupage_<source_sha256[:32]>` and store extra
lens-specific nodes with an explicit suffix, for example:

```text
dante_visual_decoupage_<source_sha256[:32]>_judge
dante_visual_decoupage_<source_sha256[:32]>_confrontador
```

## Dashboard Behavior

When the package is complete, dashboard search and chat should behave as one
asset with multiple evidence layers:

- visual search can return the image node and preview;
- technical/editorial search can return the Gemini `visual_analysis_bundle`;
- deep aesthetic/curatorial search can return the decoupage
  `visual_decoupage_bundle`;
- all layers should open the same image preview through `preview_image_file_id`;
- chat should cite whichever layer best matches the question while preserving
  the linked visual context.

## Current Implementation Status

Implemented:

- decoupage prompt/profile asset;
- strict `decoupage_sidecar` schema;
- OpenAI/Responses provider wrapper;
- decoupage CLI harness;
- zero-cost mock smoke for one asset;
- documentation and tests for the provider/profile.

Not implemented yet:

- real OpenAI decoupage run;
- decoupage ingest into Chroma;
- dashboard grouped display of all linked layers;
- full-corpus premium decoupage pass.

Do not run live model calls, Chroma ingest, delete, clear, or reindex until
Andre says the system is ready for tests. Andre explicitly said he will notify
the agent when it is time to run tests.
