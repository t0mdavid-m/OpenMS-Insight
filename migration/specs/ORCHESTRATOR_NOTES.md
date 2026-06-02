# Orchestrator notes — cross-cutting decisions for Phase 1 implementation

These decisions OVERRIDE the individual specs where they conflict. Impl agents must read this.

## Dependency / data-flow decisions

1. **LinePlot `mode="density"` consumes a PRECOMPUTED density frame — do NOT add scipy as a
   hard dependency.** In FLASHApp the KDE is computed upstream at parse time
   (`FLASHApp/src/parse/tnt.py::fdr_density_distribution` via `scipy.stats.gaussian_kde`) and the
   render layer only READS the precomputed `density_target`/`density_decoy` arrays
   (`FLASHApp/src/render/initialize.py:172-181`). So the component's default path takes a tidy
   long `{x, y, group}` frame and just draws it. Any `kde_from=` convenience must be a LAZY
   optional import (`import scipy` inside the branch, clear error if missing) — scipy must NOT
   become a required install of openms-insight. Prefer omitting built-in KDE entirely if it adds
   surface; the precomputed-frame path is what achieves parity.

## Serialization order (shared files: component.ts, App.vue, lineplot.py, PlotlyLineplot.vue)

All impl work funnels through `js-component/src/types/component.ts` (and several share
`App.vue` / `lineplot.py` / `PlotlyLineplot.vue`). Impl agents run **SEQUENTIALLY**, never in
parallel, in this order:
1. **Plot3D** (new files + App.vue/component.ts/__init__.py).
2. **LinePlot COMBINED** = tagger + density + per-peak charge annotations, in ONE agent (they all
   edit `lineplot.py` + `PlotlyLineplot.vue` + `component.ts`; splitting them would collide).
3. **Table formatters** (formatters.ts, table.py, component.ts, TabulatorTable.vue).
4. **SequenceView internal_fragments** (sequenceview.py, SequenceView Vue, sequence-data.ts).

## Parity behavior to match exactly (charge annotations — generic PeakAnnotation API)

- Oracle for the plain spectrum is `PlotlyLineplotUnified.vue` `annotationData()` m/z branch.
- For the SELECTED mass only: read nested `SignalPeaks[massIdx][k] = [peak_index, mz, intensity,
  charge]`, group peaks by `charge` (tuple index 3), compute the **intensity-weighted
  center-of-gravity m/z per charge group**, place a `z={charge}` text label + colored rect at that
  COG x. Use the oracle's **all-or-nothing overlap suppression**.
- API: generic render-time `set_peak_annotations([{x, text, color?, hover?, group?}])` (data
  coords), COG computed Python-side (testable; no JS re-derivation of the tuple layout). Keep the
  existing single `annotation_column` path for the Deconvolved-Spectrum mass labels.
- This is a GENERIC, reusable annotation overlay (good for any MS viewer), not FLASHApp-specific.

## Formatters (Table)

- Add two GENERIC named registry formatters to `js-component/src/components/tabulator/formatters.ts`:
  - `fixed` — reproduces `toFixedFormatter(4)` INCLUDING the `toString().length > 4` guard
    (no padding when the rendered value is already short).
  - `placeholder` — generalizes the inline `-1 → "-"` to a configurable sentinel.
- column_definitions must stay JSON-serializable (they round-trip through the disk cache) — that is
  WHY inline JS formatters become named registry entries.

## General

- Public API stays minimal + generic (reusable by other MS viewers). No FLASHApp-only concepts in
  the library; promote broadly-useful ideas into clean generic interfaces.
- Do NOT touch `migration/` (harness/baselines) or `FLASHApp/` or the read-only Vue oracle repo.
- Do NOT git commit/push. The orchestrator runs the gate, refreshes the `public_api` parity
  baseline (intentional 6→7 component drift), and records the ledger centrally.
