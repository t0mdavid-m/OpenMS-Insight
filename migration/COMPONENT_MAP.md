# COMPONENT_MAP — FLASHApp visualizations → OpenMS-Insight components

Phase 1.1 deliverable. Maps every FLASHApp visualization onto an OpenMS-Insight
target, names the **read-only oracle** for each, and classifies the work as
*verify-existing* vs *new-code*. Detailed implementable specs for the new-code
items live in `specs/*.md`.

Oracles:
- Old Vue: `/home/user/openms-streamlit-vue-component/src/components/…`
- Old FLASHApp render layer: `/home/user/FLASHApp/src/render/…`
  (`update.py` = authoritative index→value selection oracle).

## Mapping table

| FLASHApp viz (old Vue) | Insight target | Kind | Spec |
|---|---|---|---|
| `PlotlyHeatmap` ×4 (MS1/MS2 × raw/deconv) | `Heatmap` | verify-existing (+MS2-scoping check) | this file |
| `Tabulator{Scan,Mass,Protein,Tag}Table` | `Table` + ported formatters | mixed (formatters = new) | `specs/table-formatters-and-annotations.md` |
| `PlotlyLineplot` (deconv/anno stick) | `LinePlot` (+ generic charge annotations) | mixed (annotations = new) | `specs/table-formatters-and-annotations.md` |
| `PlotlyLineplotTagger` (de-novo tag overlay) | `LinePlot` `mode="tagger"` | NEW | `specs/lineplot-modes.md` |
| `FDRPlotly` (target/decoy KDE) | `LinePlot` `mode="density"` | NEW | `specs/lineplot-modes.md` |
| `SequenceView` | `SequenceView` | verify-existing | this file |
| `InternalFragmentMap` | `SequenceView` `internal_fragments=True` | NEW (port fragment math to Python) | `specs/sequenceview-internal.md` |
| `Plotly3Dplot` (precursor S/N) | `Plot3D` | NEW component | `specs/plot3d.md` |
| `FLASHQuantView` | page recipe: `Table(interactivity=feature)` + `Plot3D(filters=feature)` | recipe | this file |

## Verify-existing units — status from code review

### Heatmap (units: log, multi-res, zoom, categorical, interactivity)
The Insight `Heatmap` (`openms_insight/components/heatmap.py`) already exposes parity
surface for all five; remaining parity work is a **Vue-render diff vs. the oracle**, not
new Python:
- **log** — `log_scale: bool = True` (log10 color mapping). ✓ API present.
- **multi-res** — `min_points` + cascading `compute_compression_levels` /
  `downsample_2d_streaming`; cascading↔from-scratch equivalence proven in
  `tests/test_heatmap_cascading.py`. ✓
- **zoom** — `zoom_identifier` + `_make_zoom_cache_key({xRange,yRange})` re-resolves on
  zoom. ✓ API present.
- **categorical** — `categorical_filters` (per-value compression → constant point counts)
  and `category_column`/`category_colors`; covered by `tests/test_categorical_heatmap.py`. ✓
- **interactivity** — `interactivity={'spectrum':'scan_id','peak':'mass'}` value-based
  click-linking. ✓
- ⚠️ **Review must still diff** PlotlyHeatmap.vue for: MS1/MS2 scoping (old code ships 4
  heatmaps; confirm MS2 is expressed via `filters`/`categorical_filters`, not a 4th
  component), colorbar/log visual parity, hover content, and SVG export.

### SequenceView baseline (units: coverage, terminal-frags)
`openms_insight/components/sequenceview.py` already renders coverage + terminal fragments
(`tests/test_sequenceview.py`). Review diffs SequenceView.vue + AminoAcidCell/
ProteinTerminalCell against the Insight Vue. (Internal fragments = new; see spec.)

### Table baseline (units: pagination, row-select, go-to, filters)
`openms_insight/components/table.py` provides server-side pagination, row selection →
value-based cross-link, filters. Review diffs against `TabulatorTable.vue`. (Custom
column formatters = new; see spec.)

### LinePlot baseline (units: stick, highlight, zoom, svg, click)
`openms_insight/components/lineplot.py` provides stick rendering, `highlight_column`,
zoom, SVG export, click→selection. Review diffs against `PlotlyLineplot.vue`.
(Per-peak charge-state annotation = new; see spec.)

### quant-recipe
Not a component — a page recipe. `Table(interactivity={'feature': <feature_id>})` linked to
`Plot3D(filters={'feature': <feature_id>})`. Python must flatten FLASHQuant's comma-split
`MZs/RTs/Intensities` into one tidy row per point. Oracle: `flashQuant/FLASHQuantView.vue`
+ `FLASHApp/content/FLASHQuant/FLASHQuantViewer.py`. Depends on `Plot3D` (spec).

## New-code units — see specs

- `specs/plot3d.md` — new `Plot3D` component (Python + Vue + types + tests).
- `specs/lineplot-modes.md` — `LinePlot` `mode="tagger"` and `mode="density"`.
- `specs/sequenceview-internal.md` — `SequenceView internal_fragments=True` (+ ported math).
- `specs/table-formatters-and-annotations.md` — Tabulator formatter port + generic LinePlot
  per-peak charge-state annotation API.

## Shared integration points (merge-managed by the orchestrator)

New components/modes converge on these shared files — edited centrally to avoid conflicts:
- `openms_insight/__init__.py` (public exports; `Plot3D`)
- `js-component/src/App.vue` (componentType dispatch switch)
- `js-component/src/types/component.ts` (typed component args)
- `migration/parity_diff.py` baselines (`public_api` will intentionally drift 6→7 components)
