# Phase 2 — API Simplification & Generalization Plan

**Status:** read-only analysis / change plan. No code changed by this document.
**Scope:** lock a minimal-but-powerful 7-component public surface
(`Table`, `Heatmap`, `LinePlot`, `MirrorPlot`, `VolcanoPlot`, `SequenceView`, `Plot3D`)
plus the cross-cutting `__init__.py` / `StateManager` / naming / docs surface.

**Phase-1 invariant (HARD CONSTRAINT):** every proposal below must preserve
Phase-1 feature parity with FLASHApp. Components already WORK; Phase 2 is about
*shape* (minimal mandatory params, modular optional/render-time extensions,
consistent naming, no FLASHApp leakage, broadly-useful concepts promoted to clean
generic interfaces). Each change carries a **Parity safety** note.

**Priority legend:** **MUST** = clear usability win, low risk. **OPTIONAL** =
nice-to-have. Items tagged **BUG** are correctness gaps found during the audit and
should land regardless of the cosmetic pass.

---

## Cross-cutting design decisions (apply to ALL units)

These three recurring patterns drive most per-unit changes; defined once here and
referenced below.

### D1 — Presentation config should be RENDER-TIME, not cache-invalidating
Every plot component stores `title`, `x_label`, `y_label` (and friends) in
`_get_cache_config()`, so changing a label **invalidates the on-disk cache and
re-runs preprocessing**. These values never affect the preprocessed data — they are
pure passthrough to `_get_component_args()`. The model already proven by
`VolcanoPlot` (thresholds via `__call__`) and `Plot3D` (`mode` via `__call__`) is the
target: **labels/titles/colors are render-time.**

Recommended mechanism: a small render-time override surface rather than ad-hoc
`__call__` kwargs per component. Two viable shapes (pick ONE, library-wide):
- **(a)** add `title=`, `x_label=`, `y_label=` to `BaseComponent.__call__`, stored on
  `self` before `render_component` (exactly how `VolcanoPlot`/`Plot3D` already store
  render-time values), and DROP them from `_get_cache_config()`.
- **(b)** a single `with_labels(title=, x_label=, y_label=)` chainable setter (matches
  the existing `with_styling`/`with_annotations` idiom) + drop from cache config.

**Parity safety:** behavior identical (same args reach Vue); only cache-invalidation
granularity changes. Risk: an OLD cache that hashed the label still validates (labels
leave the hash) — acceptable, labels are re-sent every render from the live instance.
Must keep them in the *manifest* `config` (for reconstruction-mode) but OUT of
`_compute_config_hash()`. NOTE: `_get_cache_config()` currently feeds BOTH the hash and
the stored manifest config — splitting "stored config" from "hash-affecting config"
is the enabling refactor (see `api:surface` S4).

### D2 — One column-role naming vocabulary
Column-name parameters are spelled six different ways across components (table below
in `api:surface` C1). Converge on a single vocabulary so a user who learns one
component can predict the others.

### D3 — Don't leak FLASHApp vocabulary into generic params
Several params are named/located for FLASHApp's top-down proteomics recipe rather than
a generic MS viewer (`signal_peaks_column`, `mz_column`, `x_pos_scaling_factor`,
`tag_payload_key`, Plot3D mass/charge/intensity defaults, density `target`/`decoy`).
The fix is rarely "remove" (that breaks parity) — it's "group + document as a clearly
optional, mode-scoped extension," so the generic core stays small.

---

## api:table

`openms_insight/components/table.py` — `Table.__init__` (L71–173).

**Overall:** the busiest constructor (13 component-specific params after the 8 shared
ones) but the params are individually sensible and well-documented. The wins are
grouping/render-timing, not removal. The `with_*` formatter chain (L1024–1162) is
already a clean, generic, well-documented extension surface — **leave it alone.**

### Simplicity
- **MUST — make `title` render-time (D1).** `table.py:82` (init), `:186` (cache config),
  `:1010` (args). `title` is pure passthrough.
  - before: `Table(..., title="Scans")` → cache rebuild on title change.
  - after: `table(state_manager=sm, title="Scans")` (or `with_labels`); drop `"title"`
    from `_get_cache_config`.
  - **Parity safety:** none at risk — same `args["title"]` reaches Vue.
- **OPTIONAL — collapse the pagination trio into render-time where possible.**
  `pagination` (L130) + `page_size` (L132) are legitimately cache-affecting (they shape
  the streamed parquet row-group strategy via `_get_row_group_size`? — actually they do
  NOT; row-group size is filter-driven). `page_size` only changes slicing at render
  time (`_prepare_vue_data` reads `page_size` from pagination state, L620). Consider
  moving `page_size` to render-time/`__call__`. LOW priority — current default (100) is
  fine and few callers retune it.
  - **Parity safety:** keep `pagination=True` default; only relax *when* page_size binds.
- **OPTIONAL — `pagination_identifier` is auto-derived (`{cache_id}_page`, L150) and
  rarely overridden.** Keep the param (needed for multiple independent tables sharing a
  cache_id prefix) but it can move out of the "common" doc section into "advanced."

### Consistency
- **MUST — adopt the unified label override (D1) so `title` matches every other plot.**
  Today `Table.title` is config-time while `VolcanoPlot.title` is effectively static and
  `Plot3D`/`Heatmap` titles are config-time too — unify all at once.
- **Already consistent / DO NOT churn:** `filters` / `filter_defaults` / `interactivity`
  use the canonical identifier→column mapping; `index_field`, `go_to_fields`,
  `initial_sort`, `default_row` are table-idiomatic and have no analog elsewhere.

### Reusability / generalization
- Table is the most generic component already — nothing FLASHApp-specific leaks in.
- **OPTIONAL (docs):** the custom formatters (`scientific`, `signed`, `badge`, `fixed`,
  `placeholder`) are documented in README and `component.ts` (L50–55) but the
  `with_*` Python helpers (`with_fixed_format`, `with_placeholder`, `with_money_format`,
  `with_progress_bar`) are NOT in README. Surface them so the generic formatter story is
  discoverable. The `badge` formatter (categorical→color pill) is broadly useful and
  worth a one-line callout as the canonical "categorical coloring in a table" answer.

**Verdict:** mostly clean. Single MUST = render-time `title` (part of the library-wide
D1 sweep). Everything else OPTIONAL.

---

## api:heatmap

`openms_insight/components/heatmap.py` — `Heatmap.__init__` (L67–211). The widest
*surface area for confusion*: 24 component params, several overlapping downsampling
knobs, and two confirmed cache bugs.

### Simplicity
- **MUST — make `title` / `x_label` / `y_label` / `colorscale` / `reversescale` /
  `intensity_label` render-time (D1).** Lines `:85–89,97` (init), `:232–239` (cache
  config), `:1184–1202` (args). None affect the preprocessed levels; all are pure Vue
  passthrough. `colorscale`/`reversescale` retuning currently forces a full
  multi-resolution rebuild of a million-point cache — the worst-cost instance of the D1
  problem in the library.
  - before: changing `colorscale` rebuilds every level on disk.
  - after: `heatmap(state_manager=sm, colorscale="Viridis")`; drop the six keys from the
    hash. `with_styling(colorscale=, x_label=, y_label=)` (L1209) ALREADY exists for the
    chained form — extend it to cover `reversescale`/`intensity_label`/`title` and route
    render-time.
  - **Parity safety:** identical Vue args. The big win is *not* invalidating the cache;
    must keep these in the manifest for reconstruction (see D1 / surface S4).
- **MUST (BUG) — `reversescale` is dropped on reconstruction-from-cache.**
  It is in `_get_cache_config()` (`:233`) but **never restored in
  `_restore_cache_config()`** (`:243–266` — grep confirms 0 occurrences of
  `self._reversescale = config...`). A heatmap created with `reversescale=True`
  (README's e-value recipe, L283) silently reverts to `False` when later reconstructed
  with only `cache_id`/`cache_path`. **This is a Phase-1 parity break for the e-value /
  "bright = best" recipe.** Fix = add `self._reversescale = config.get("reversescale",
  False)`. (If D1 moves `reversescale` to render-time, this bug dissolves — but until
  then it's a real defect; ship the one-liner regardless.)
- **MUST (BUG/doc) — `min_points` default mismatch.** Code default is `10000`
  (`:80`, `:117`, restore `:248`); README says `20000` in two places (L249, and the
  cascading doc L256). Pick one and align code+README+docstring. (Lower default = fewer
  points to the browser; just make the docs truthful.)
- **MUST — consolidate the three overlapping downsampling-strategy booleans.**
  `use_streaming` (L91, default True), `use_simple_downsample` (L90, default False), and
  the implicit "eager" path form a 3-way strategy selected by two booleans with an
  illegal/ambiguous combination. `_preprocess` (L282–299) dispatches:
  `categorical_filters? → streaming? → eager`. Replace the two booleans with ONE
  `downsample: Literal["streaming","eager","simple"] = "streaming"`.
  - before: `use_streaming=True, use_simple_downsample=False` (what does
    `use_streaming=False, use_simple_downsample=True` mean? — it works, but the matrix
    is unobvious).
  - after: `downsample="streaming"` (default) | `"eager"` | `"simple"`.
  - **Parity safety:** keep the same three code paths; this is a pure surface rename.
    Map old→new in `_restore_cache_config` for cache back-compat (read both old keys when
    the new key is absent).
- **OPTIONAL — `display_aspect_ratio` + `x_bins` + `y_bins` are an expert triad.**
  `x_bins`/`y_bins` auto-compute from `display_aspect_ratio` when None
  (`_preprocess_streaming` L591). They're correctly cache-affecting. Keep, but demote to
  an "advanced binning" doc group — the default path needs none of them.
- **OPTIONAL — `zoom_identifier` (L84) defaults to `"heatmap_zoom"`, a *shared* default.**
  Two heatmaps on one page with default identifiers will fight over zoom state. Either
  auto-derive (`f"{cache_id}_zoom"`, matching `pagination_identifier`'s pattern) or
  document the collision. LOW risk but a real footgun. **Parity safety:** single-heatmap
  pages (FLASHApp) unaffected by an auto-derived default.

### Consistency
- **MUST — `intensity_column` vs the generic value-axis (D2/C1).** Heatmap's color axis
  is `intensity_column`; Plot3D's is `z_column`; Volcano's is `pvalue_column`. See
  `api:surface` C1 for the unified proposal. At minimum, `intensity_label` (L97) is the
  colorbar label and should follow whatever label convention D1 lands on.
- **MUST — `category_column` / `category_colors` are the canonical categorical-coloring
  surface (good!).** Mirror this EXACT naming wherever categorical coloring appears
  (Plot3D's `series_column`/`series_colors` is the same concept under a different name —
  see C1). Pick one pair of names and use it in both.
- **Already consistent:** `filters`/`interactivity` canonical; `min_points` is unique to
  heatmap and clear.

### Reusability / generalization
- **`categorical_filters`** (per-value compression levels for constant point counts,
  L92/L140) is a genuinely generic, powerful idea (constant-payload-under-filter) but is
  documented only in the docstring and the cascading design doc. Promote to README as a
  first-class feature — any large MS heatmap with a small-cardinality facet (ion-mobility
  bin, sample group, charge) benefits. No FLASHApp leakage; the example just happens to
  cite `im_dimension`.
- No FLASHApp-specific concepts leak into the constructor itself. Good.

**Verdict:** highest-value unit. Two BUG fixes (`reversescale` restore, `min_points`
doc) + the downsample-boolean consolidation + the D1 sweep (biggest cache-cost win in
the whole library). `categorical_filters`/`category_*` are clean — promote, don't churn.

---

## api:lineplot

`openms_insight/components/lineplot.py` — `LinePlot.__init__` (L102–271). The
**largest, most mode-overloaded** surface: one constructor carries `default` + `density`
+ `tagger` modes with ~14 mode-specific params flattened at the top level. The module
also exports excellent generic helpers at the bottom (L1582–1854).

### Simplicity
- **MUST — make `title` / `x_label` / `y_label` render-time (D1).** `:114–116` (init),
  `:285–287` (cache), `:1061–1062` (args). `with_styling` (L1140) already exists — add a
  labels path.
- **MUST — group the mode-specific params out of the flat top level.** Today `default`
  callers see `group_column`, `target_value`, `decoy_value`, `kde_from`, `kde_points`
  (density) AND `signal_peaks_column`, `mz_column`, `mz_intensity_column`,
  `tag_payload_key`, `mass_match_tol`, `title_level1`, `x_label_level1`,
  `x_pos_scaling_factor` (tagger) — 13 params that are inert for the mode they're using.
  Two acceptable shapes:
  - **(a)** keep `mode=` but accept a single `mode_config: dict` for the per-mode keys
    (validated per mode), shrinking the visible signature to the generic core
    (`x_column`, `y_column`, labels, `highlight_column`, `annotation_column`, `styling`,
    `config`, `mode`, `mode_config`).
  - **(b)** factory classmethods (`LinePlot.density(...)`, `LinePlot.tagger(...)`) that
    take only their own params and set `mode` internally — mirrors the existing
    `from_sequence_view` classmethod idiom (L1422).
  - **Parity safety:** both keep the three code paths byte-identical; only the *call
    shape* changes. The internal `_MANAGED_CONFIG_KEYS` set (L34–61) already enumerates
    exactly these keys — it becomes the schema for `mode_config`. Recommend (b): it makes
    the generic `LinePlot(...)` genuinely minimal and quarantines FLASHApp-flavored params
    inside `.tagger(...)`.
- **OPTIONAL — `config=` (extra Plotly config, L120) vs `styling=` (L119) vs `**kwargs`**
  is a three-way passthrough that's hard to reason about. Document the precedence (the
  `_MANAGED_CONFIG_KEYS` filtering at L1078 is subtle). No behavior change needed.

### Consistency
- **MUST — render-time `mode` switching parity with Plot3D.** `Plot3D` lets you switch
  trace `mode` at render time via `__call__` (`plot3d.py:360`) with **no cache rebuild**;
  `LinePlot.mode` is config-time only and cache-affecting (`:291`). For `default` ↔
  `tagger` ↔ `density` a rebuild is justified (different preprocessing), so this is NOT a
  literal unification — but the *word* `mode` now means "render-time switch" in Plot3D and
  "cache-time variant" in LinePlot. **Recommendation:** keep both, but document the
  distinction explicitly, OR rename Plot3D's render-time `mode`→`trace_mode` to free the
  word `mode` for "cache-time variant selector" library-wide. (See `api:plot3d`.)
- **MUST — labels (D1) + `highlight_column`/`annotation_column` naming** align with
  MirrorPlot (which copies them verbatim — good) and with whatever C1 lands.
- **density `x_label`/`y_label` defaulting is surprising:** `_get_component_args_density`
  (L1091–1092) silently substitutes `"QScore"`/`"Density"` when the label equals the
  column name. That's a FLASHApp-specific default leaking into a generic mode. Make the
  generic default neutral (`x_column`/`y_column`) and let the FLASHApp page pass
  `"QScore"` explicitly.

### Reusability / generalization
- **KEEP & PROMOTE — the generic per-peak annotation overlay.**
  `set_peak_annotations([{x, text, color?, hover?, group?, y?}])` (L1244) + the
  `PeakAnnotation` TS type (`component.ts:190`) + the `compute_charge_annotations`
  producer (L1808) are EXACTLY the "broadly-useful concept promoted to a clean generic
  interface" the orchestrator asked for (ORCHESTRATOR_NOTES §"charge annotations"). This
  is well done. **Action:** document it in README (currently undocumented) as the generic
  "multiple labeled overlays in data coordinates" API; note that `compute_charge_*` is the
  MS-specific *producer* layered on top, so other viewers can reuse the descriptor API
  without the charge math.
- **FLASHApp leakage to quarantine (via the mode_config/factory grouping above):**
  `signal_peaks_column` doc explicitly says "FLASHApp layout `[peak_index, mz, intensity,
  charge]`" (L189, and `compute_tagger_charges` L1711); `x_pos_scaling_factor=27.5` is an
  "oracle level-1 charge-label scaling" magic number (L137/L200); `tag_payload_key`,
  `mass_match_tol`, `title_level1`, `x_label_level1` are all tagger-only. These are
  legitimate (they back the `tagger` parity feature) but must NOT sit in the generic
  constructor — move behind `.tagger(...)`.
- **The pure helpers (`compute_tagger_segments`, `compute_charge_cog`,
  `compute_tagger_charges`, `compute_tagger_level1_spectrum`, L1650–1805)** are correctly
  module-level and testable. They are tagger-specific; they should NOT be in `__all__`
  (and aren't). `compute_charge_annotations` (generic-ish producer) is the only one worth
  exporting — decide deliberately (see surface S3).

**Verdict:** the single biggest *surface-shrink* opportunity. The generic annotation
overlay is a model citizen (promote in docs). MUST: D1 labels + mode-param grouping +
neutralize density label defaults. The tagger math is parity-critical — group, don't
remove.

---

## api:mirrorplot

`openms_insight/components/mirrorplot.py` — `MirrorPlot.__init__` (L41–183).
A focused, well-structured component. The per-side filter design is deliberate and good.

### Simplicity
- **MUST — make `title` / `title_top` / `title_bottom` / `x_label` / `y_label`
  render-time (D1).** `:62–66` (init), `:312–316` (cache), `:529–534` (args). All pure
  passthrough. (`title_top`/`title_bottom` are in-figure labels — same treatment.)
- **OPTIONAL — `title` vs `title_top`/`title_bottom` overlap.** Docstring says `title` is
  "superseded by title_top/title_bottom if set" (L106) yet `_get_component_args` sends all
  three independently (L529–531); the supersede logic actually lives in Vue. Fine, but the
  three-title model is mildly confusing — document that `title` is the overall plot title
  and top/bottom are the per-half in-figure captions (they don't actually supersede).

### Consistency
- **MUST — `filters_top`/`filters_bottom`/`filter_defaults_top`/`filter_defaults_bottom`
  is the ONE intentional, well-justified deviation from the canonical single `filters`.**
  It's correct (two independent halves) and clearly documented. **Keep as-is; do not try
  to unify with the base `filters`.** The constructor already builds the union for the
  base class (L151–162) — clean.
- **MUST — shared `highlight_column`/`annotation_column`/`x_column`/`y_column` are copied
  verbatim from LinePlot.** Good — keep them lockstep with LinePlot under C1.
- **Already consistent:** the per-side dynamic-annotation setters
  (`set_top_dynamic_annotations`/`set_bottom_dynamic_annotations`/
  `clear_dynamic_annotations(side=)`, L550–606) are a clean, symmetric, well-documented
  API. The `__call__` SequenceView wiring (`sequence_view_top_key`/`_bottom_key`,
  L689–748) mirrors LinePlot's single-side wiring correctly. **Do not churn.**

### Reusability / generalization
- No FLASHApp-specific leakage. The component is expressed entirely in generic
  paired-spectrum terms (README even lists generic use cases: experimental vs theoretical,
  sample vs reference, MS1 vs MS2). Model unit.
- **OPTIONAL — MirrorPlot does NOT have the generic `set_peak_annotations` overlay** that
  LinePlot has, only the keyed `_dynamic_annotations`. If the per-peak descriptor overlay
  (LinePlot) is promoted as the generic standard, consider adding it to MirrorPlot too for
  symmetry. LOW priority (no parity requirement).

**Verdict:** already clean and coherent. Only MUST is the D1 label sweep (shared with
every plot). The per-side filter model and per-side annotation setters are exemplary —
explicitly leave them untouched.

---

## api:volcanoplot

`openms_insight/components/volcanoplot.py` — `VolcanoPlot.__init__` (L52–137),
`__call__` (L338–374). **The reference implementation for render-time params** — its
thresholds-via-`__call__` pattern is exactly the D1 model. Smallest, cleanest plot.

### Simplicity
- **MUST — make `title` / `x_label` / `y_label` and the three colors
  (`up_color`/`down_color`/`ns_color`) + `show_threshold_lines`/`threshold_line_style`
  render-time (D1).** `:65–72` (init), `:166–179` (cache), `:323–330` (args). They're
  all pure Vue passthrough and currently cache-affecting (`_get_cache_config` L166), so
  changing a color rebuilds the `-log10(p)` cache for no reason. This is mildly ironic
  given the component already pioneered render-time thresholds — finish the job for the
  presentation params too.
  - **Parity safety:** identical Vue args; thresholds already prove the pattern works.
- **Already exemplary — DO NOT touch:** `fc_threshold`/`p_threshold`/`max_labels` via
  `__call__` (L343–345) with an explicit "NOT included — render-time params" comment in
  `_get_component_config_hash_inputs` (L163). This is the template the rest of the library
  should copy.

### Consistency
- **MUST — `log2fc_column` / `pvalue_column` naming vs the generic x/y convention (C1).**
  Volcano uses domain-specific axis names (`log2fc_column` for x, `pvalue_column` for y).
  This is *defensible* (a volcano plot IS log2FC-vs-pvalue by definition) but it's the
  outlier vs `x_column`/`y_column` everywhere else. **Recommendation:** keep the
  domain-specific names (they aid discoverability for the volcano use case) BUT note in C1
  that this is a deliberate, documented exception — don't "fix" it into `x_column`.
- **MUST — color naming.** `up_color`/`down_color`/`ns_color` are bespoke; Heatmap uses
  `category_colors` (a dict), Plot3D uses `series_colors` (a dict), MirrorPlot/LinePlot
  use a `styling` dict. Three different shapes for "category→color." See C1: prefer the
  `*_colors` dict convention. Volcano's three fixed categories could stay as named params
  (they're a fixed enum) but should at least be reachable via a `category_colors`-style
  dict for consistency, OR moved into a `styling` dict like the line plots.
- **`_neglog10p_column` is an internal computed name** (`"_neglog10_pvalue"`, L125) —
  correctly private. Fine.

### Reusability / generalization
- No FLASHApp leakage; this is a generic proteomics/transcriptomics component.
- **`_get_component_config_hash_inputs()` (L157) is a private one-off** that overlaps with
  `_get_cache_config()` (L166) — it is computed but, per grep, not actually wired into the
  base hash (base uses `_get_cache_config`). This dead/duplicative method is confusing;
  fold its intent into the surface-S4 "hash config vs stored config" split and delete the
  one-off. **Parity safety:** it's not on the hash path, so removing it changes nothing.

**Verdict:** cleanest plot; the render-time-threshold pattern is the gold standard to
propagate. MUST = finish D1 for the presentation params + tidy the dead
`_get_component_config_hash_inputs`. Naming exceptions (`log2fc_column`/`pvalue_column`)
are acceptable if documented.

---

## api:sequenceview

`openms_insight/components/sequenceview.py` — `SequenceView.__init__` (L643–839).
**The structural outlier:** it does NOT subclass `BaseComponent`; it hand-rolls the
entire cache/reconstruction/`__call__` contract (L723–839, L1318–1394) with its own
`CACHE_VERSION` (L18), its own `.cache_config.json` (vs the base `manifest.json`), its own
`_cache_exists`/`_load_from_cache`/`_create_cache`. This is the largest source of
surface drift in the library.

### Simplicity
- **MUST — `height` is a CONSTRUCTOR param (L656) AND a `__call__` param (L1364).**
  It is cache-config (`_get_cache_config` L848) so it invalidates the cache, yet every
  other component treats `height` as render-time only (`BaseComponent.__call__` L503,
  `DEFAULT_COMPONENT_HEIGHT`). **Make `height` render-time only** (drop from `__init__`
  and from `_get_cache_config`). This is the clearest single inconsistency in the file.
  - **Parity safety:** `__call__(height=)` already exists and is honored (L1385); the
    constructor copy is redundant. Existing callers that passed `height=` to the
    constructor must move it to the call — a breaking change, but Phase 2 permits these.
    The constructor `height != 400` check at L739 (part of the `has_config` guard) also
    simplifies.
- **MUST — make `title` render-time (D1).** `:655` (init), `:849` (cache), `:1326`
  (args). Pure passthrough.
- **OPTIONAL — `sequence_data` accepts 3 shapes** (LazyFrame | `(str,int)` tuple | str,
  L646, parsed L803–810). This is friendly but the tri-modal type is a small complexity
  tax. Keep (the static-string path is genuinely convenient for demos) but it's the kind
  of thing to NOT replicate elsewhere.

### Consistency
- **MUST — converge the cache/reconstruction contract with `BaseComponent`.** Right now:
  - SequenceView raises plain `ValueError` on cache-miss/mode-misuse (L751, L757) whereas
    the base raises `CacheMissError` (`base.py:118,124`). Callers catching `CacheMissError`
    to drive the "create vs reconstruct" flow will MISS SequenceView. **Align on
    `CacheMissError`.**
  - It reimplements the `has_config`-guard reconstruction logic (L731–760) that
    `BaseComponent.__init__` already encodes (`base.py:104–129`) — divergent and a
    maintenance hazard (the ORCHESTRATOR_NOTES explicitly call out
    `sequenceview.py`/`SequenceView Vue` as a shared serialization point).
  - **Recommended:** make `SequenceView(BaseComponent)` with `_preprocess` writing the two
    sub-frames (sequences/peaks) into the standard manifest, OR (lighter) at minimum (i)
    raise `CacheMissError`, (ii) reuse the base `data`/`data_path` mode words instead of the
    bespoke `sequence_data`/`peaks_data`(+`_path`) quartet where feasible. Full
    re-parenting is the higher-value but higher-risk option — gate behind a parity run of
    `tests/test_sequenceview*.py`.
  - **Parity safety:** SequenceView has the richest parity surface (coverage, terminal +
    internal fragments, proteoform terminals). Any re-parenting MUST be validated against
    `tests/test_sequenceview.py` + `test_sequenceview_internal.py` and the
    `sequenceview-internal.md` golden values. If risk is too high for Phase 2, ship ONLY
    the `CacheMissError` alignment + render-time `height`/`title` (low risk) and leave
    re-parenting as a tracked follow-up.
- **MUST — `filters` present but NO `interactivity`-style asymmetry to flag, AND no
  `filter_defaults` param.** SequenceView auto-sets every filter's default to `None`
  (L781–783, L884–885) and exposes no `filter_defaults` arg, unlike every other component.
  Either expose `filter_defaults` for parity, or document why it's fixed to None.

### Reusability / generalization
- **KEEP & PROMOTE — several genuinely generic proteomics concepts already cleanly
  surfaced here:**
  - `coverage_column` + `normalize_coverage` (L558) — per-residue coverage gradient, a
    general proteomics concept (the code comment L536–551 explicitly argues this). Clean,
    optional, off-by-default. Promote to README.
  - `internal_fragments` + `compute_internal_fragment_data` (L456) + the ported fragment
    math (L375–489) — generic internal-fragment enumeration, well-isolated as pure
    functions. Good.
  - `proteoform_start_column`/`proteoform_end_column` (L660–661) — truncated/undetermined
    terminals, a general top-down concept.
  - The component returns a `SequenceViewResult` (L602) whose `.annotations` DataFrame is
    THE cross-component fragment-map linkage consumed by LinePlot/MirrorPlot via
    `get_component_annotations` — the central reusable "fragment map → spectrum annotation"
    bridge. Document this linkage as a first-class generic pattern (see surface S2).
- **FLASHApp leakage:** minimal. The defaults (`ion_types: ["b","y"]`, internal families
  `["by","bz","cy"]`) are standard proteomics, not FLASHApp-only. The pyOpenMS dependency
  is correctly optional (fallback parsers L54, L170). Good.
- **Discoverability gap:** `SequenceViewResult` IS exported (`__init__.py:12,37`) but its
  role as the annotation source for linked plots is undocumented in README.

**Verdict:** functionally rich and the generalizations (coverage, internal fragments,
proteoform terminals, the annotations-result bridge) are clean. The cost is structural:
it's a parallel re-implementation of the base contract. MUST (low-risk): render-time
`height`+`title`, `CacheMissError` alignment, `filter_defaults` parity. SHOULD
(higher-risk, gate on tests): re-parent onto `BaseComponent` to kill the contract drift.

---

## api:plot3d

`openms_insight/components/plot3d.py` — `Plot3D.__init__` (L68–177), `__call__`
(L355–383). Newest component; cleanly modeled on the cache-first contract and already
demonstrates render-time `mode`. The main issues are MS-domain defaults leaking into a
"generic" component and naming drift vs Heatmap.

### Simplicity
- **MUST — make `title` / `x_label` / `y_label` / `z_label` and the styling triad
  (`series_colors`, `camera_eye`, `stem`/`stem_baseline`, `y_dtick`/`y_tick0`)
  render-time (D1).** `:83–93` (init), `:222–230` (cache), `:343–348` (args). The
  component already separates render-time (`mode`) from cache config correctly (comment
  L231 "mode is NOT included — render-time") — extend that discipline to all the
  presentation params, which currently sit in `_get_cache_config` (L211–232) and needlessly
  invalidate the cached point set.
  - **Parity safety:** identical Vue args; `mode` already proves the split.
- **OPTIONAL — `stem`/`stem_baseline`/`y_dtick`/`y_tick0`/`camera_eye` are FLASHApp-S/N-plot
  framing defaults** (the docstring calls `stem_baseline=-100000.0` an "oracle magic
  baseline", L137; `camera_eye={x:2.5,...}` is the oracle framing, L140). They're correctly
  optional with sensible defaults, but they're an expert cluster — group them in docs under
  "advanced 3D framing" rather than the headline params.

### Consistency
- **MUST — `series_column`/`series_colors` (L76/L87) duplicate Heatmap's
  `category_column`/`category_colors` concept under different names.** Both mean "discrete
  categorical column → color map." Per C1, converge on ONE pair. Recommendation: adopt
  `category_column`/`category_colors` (Heatmap's spelling) since "category" is the generic
  term and "series" is Plotly-specific.
  - rename: `Plot3D.series_column → category_column`, `series_colors → category_colors`.
  - **Parity safety:** add the new names, accept the old as deprecated aliases for one
    release, restore-from-cache reading both keys. The DEFAULT map
    (`{"Signal":..,"Noise":..}`, L27) is a FLASHApp default — keep it as the *default value*
    but the *param name* should be generic.
- **MUST — `z_column` (value axis) vs Heatmap `intensity_column` (value axis) (C1).**
  Plot3D's third axis is conceptually the same "value/intensity" axis Heatmap colors by.
  Resolve under C1's value-axis decision.
- **MUST — render-time `mode` naming.** `Plot3D.mode` (render-time, "lines"/"markers"/
  "lines+markers") collides conceptually with `LinePlot.mode` (cache-time variant). Either
  rename Plot3D's to `trace_mode` (frees `mode` to mean "cache-time variant" library-wide)
  or document the divergence. See `api:lineplot` C1.

### Reusability / generalization
- **MS-domain defaults leak into the generic signature:** `x_column="mass"`,
  `y_column="charge"`, `z_column="intensity"` (L71–73), `x_label="Mass"`/`y_label="Charge"`/
  `z_label="Intensity"` (L151–153). For a *generic* 3D scatter these defaults presume the
  FLASHQuant precursor-S/N recipe. **Recommendation:** keep the defaults (they make the
  parity recipe a one-liner) but the docstring should lead with the generic
  "x/y/z scatter" framing and present the mass/charge/intensity defaults as the MS preset.
  Same for `DEFAULT_SERIES_COLORS`/`DEFAULT_CAMERA_EYE`/`DEFAULT_PLOT3D_HEIGHT` (L27–31) —
  fine as defaults, just frame them as the preset, not the contract.
- `hover_columns` (L95), `log_z` (L94), `drop_nonpositive_z` (L92) are clean generic knobs.

**Verdict:** structurally clean and already render-time-aware for `mode`. MUST: D1 sweep
for the presentation params + converge `series_*`→`category_*` + resolve the value-axis and
`mode`-word naming with C1. The S/N framing defaults are fine as a documented preset.

---

## api:surface  (`__init__.py` / `StateManager` / naming / docs)

`openms_insight/__init__.py` (L1–42), `core/state.py`, `core/base.py`, README, `docs/`,
`js-component/src/types/component.ts`.

### S1 — `__all__` / exports coherence
`openms_insight/__init__.py` is mostly clean. Findings:
- **MUST (consistency) — `SequenceViewResult` is exported (L12,37) but no other component
  exports its result type**, because no other component HAS one (they return raw Vue
  selection state). That's fine, but document `SequenceViewResult` (see S2) so its presence
  in `__all__` is self-explanatory.
- **OPTIONAL — `get_component_annotations` / `clear_component_annotations` are exported
  (L19,40–41) as "Utilities"** but `set_*`-side (the producer) lives as instance methods.
  These two functions are the *consumer* half of the cross-component annotation bridge;
  they're correctly public. Add a docstring/README section (S2) so the pair reads as an
  intentional public API, not an internal leak.
- **OPTIONAL — `register_component`/`get_component_class` (L17,27–28) are exported** but are
  really an internal serialization mechanism (the registry, `registry.py`). They're harmless
  but expand the public surface; consider demoting to a `openms_insight.core` import path or
  documenting them as "advanced/extension" so the headline surface is the 7 components +
  `StateManager`.
- **MUST — the module docstring (L2–5) still says "Streamlit Vue Components"** (the old
  generic name) while the package is `openms_insight` / "OpenMS-Insight." Align the
  docstring with the product name.

### S2 — Document the two CROSS-CUTTING generic patterns (currently under-documented)
These are the library's two most reusable cross-component ideas and neither is in README:
- **MUST — Cross-component annotation bridge (fragment-map → spectrum).** Producer:
  `SequenceView` returns `SequenceViewResult.annotations`; transport:
  `get_component_annotations(key)` (`bridge.py:113`); consumers:
  `LinePlot(sequence_view_key=...)` (`lineplot.py:1526`),
  `MirrorPlot(sequence_view_top_key=/bottom_key=)` (`mirrorplot.py:694`). Document this as a
  named, generic pattern ("compute annotations in one component, render them in another via a
  shared key"). It's MS-agnostic plumbing.
- **MUST — Generic per-peak annotation overlay.** `LinePlot.set_peak_annotations` +
  `PeakAnnotation` (TS) + `compute_charge_annotations` producer. Document the descriptor
  contract (`{x, text, color?, hover?, group?, y?}`) as the generic "labeled overlays in data
  coordinates" API, with the charge-COG producer as the MS-specific helper on top.
- **OPTIONAL — categorical coloring** appears in 3 components (Heatmap `category_*`, Plot3D
  `series_*`, Table `badge` formatter, Volcano `up/down/ns_color`). Once C1 unifies the
  spelling, document "categorical coloring" once as a cross-component capability.

### S3 — Naming conventions (the unified vocabulary)

**C1 — Column-role parameters.** Current spellings (grep-confirmed):

| Role | Heatmap | Plot3D | LinePlot | MirrorPlot | Volcano | SequenceView |
|---|---|---|---|---|---|---|
| x axis | `x_column` | `x_column` | `x_column` | `x_column` | `log2fc_column` | — |
| y axis | `y_column` | `y_column` | `y_column` | `y_column` | `pvalue_column` | — |
| value/3rd | `intensity_column` | `z_column` | — | — | (pvalue) | — |
| category | `category_column` | `series_column` | `group_column` (density) | — | (3 fixed colors) | — |
| label/name | — | — | `annotation_column` | `annotation_column` | `label_column` | — |
| highlight | — | — | `highlight_column` | `highlight_column` | — | — |

- **MUST — value/3rd axis:** pick ONE of `intensity_column` vs `z_column`. Recommendation:
  keep `x_column`/`y_column`/`z_column` as the *geometric* axis names (used by the 3D plot)
  and treat Heatmap's color as `intensity_column` (it's a *color* channel, not a geometric
  axis) — BUT then both should accept the generic alias. Simplest defensible rule:
  **geometric axes = `{x,y,z}_column`; color/weight channel = `intensity_column`** and
  Heatmap keeps `intensity_column` (it has no z geometry). Document this rule so Plot3D's
  `z` and Heatmap's `intensity` are understood as different roles, not an accident.
- **MUST — category column:** unify `category_column`/`category_colors` across Heatmap +
  Plot3D (rename Plot3D `series_*`). LinePlot density's `group_column` is the same concept
  for the two-series case — at minimum cross-reference it; ideally rename to `category_column`
  too (with `target_value`/`decoy_value` staying as the value selectors).
- **MUST — labels:** `label_column` (Volcano) is the point-label/name column; `annotation_column`
  (LinePlot/MirrorPlot) is the per-row highlight-label column. These ARE different roles
  (hover/point label vs annotation text on highlighted peaks) — keep both but document the
  distinction; do NOT merge.
- **ACCEPTED EXCEPTION:** Volcano's `log2fc_column`/`pvalue_column` stay domain-named
  (documented as a deliberate exception in C1).

**C2 — Title/label params (D1 mechanism).** `title`/`x_label`/`y_label`(/`z_label`) are
spelled consistently already — the inconsistency is *timing* (config vs render). C2 = the D1
sweep makes them uniformly render-time across all 7.

**C3 — Color params.** Three shapes today: dict (`category_colors`, `series_colors`), bespoke
named (`up_color`/`down_color`/`ns_color`), nested `styling` dict (LinePlot/MirrorPlot).
- **MUST — prefer the `*_colors: Dict[str,str]` (value→color) convention** for categorical
  coloring (Heatmap/Plot3D already do). Volcano's fixed-enum colors may stay named but should
  also be reachable via a dict for symmetry. The line-plot `styling` dict is a richer
  multi-aspect object (highlight/selected/unhighlighted + annotationColors) — keep it for the
  stick plots; just don't introduce a 4th shape.

**C4 — Selection params.** `filters`/`filter_defaults`/`interactivity` are PERFECTLY
consistent across all `BaseComponent` subclasses (the canonical identifier→column mapping).
The only deviations are *intentional and documented*: MirrorPlot's per-side
`filters_top`/`filters_bottom` and SequenceView's fixed-None `filter_defaults`. **Do not
churn C4** beyond exposing SequenceView's `filter_defaults` (see api:sequenceview).

**C5 — `*_identifier` state keys.** `zoom_identifier` (Heatmap, default shared
`"heatmap_zoom"`), `pagination_identifier` (Table, default derived `{cache_id}_page`),
`tag_payload_key` (LinePlot tagger). Inconsistent: one is a shared literal, one is derived,
one is a `_key` suffix not `_identifier`. **MUST — pick one convention:** auto-derive from
`cache_id` (the Table pattern is the safe one) and use the `_identifier` suffix uniformly
(rename tagger's `tag_payload_key`→`tag_identifier` for consistency, within the tagger
factory). Heatmap's shared `"heatmap_zoom"` default is the footgun called out in api:heatmap.

### S4 — Split "hash-affecting config" from "stored config" (enables D1 cleanly)
`_get_cache_config()` is used for BOTH `_compute_config_hash()` (cache *validity*) AND the
manifest `config` (reconstruction *restore*), see `base.py:201–205,317`. That coupling is WHY
labels/colors currently invalidate the cache: to *restore* a label on reconstruction it must be
in the manifest, but being in the manifest puts it in the hash.
- **MUST (enabler) — introduce a second hook**, e.g. `_get_render_config()` (stored in manifest,
  NOT hashed) vs `_get_cache_config()` (hashed). Then D1 moves labels/colors/titles to
  `_get_render_config()`: still restored on reconstruction, no longer cache-invalidating.
- **Parity safety:** purely additive to the base contract; existing `_get_cache_config`
  overrides keep working. Each component then just relocates presentation keys from one hook to
  the other. This single base change unlocks the D1 wins in table/heatmap/lineplot/mirrorplot/
  volcanoplot/plot3d without per-component `__call__` plumbing. **This is the highest-leverage
  change in the plan.**
- Also folds away Volcano's dead `_get_component_config_hash_inputs` (api:volcanoplot).

### S5 — StateManager
`core/state.py` is robust (counter-based conflict resolution, pagination/selection counter
split, session id). Findings:
- **OPTIONAL — `counter` property + legacy single-counter migration (L109–111, L221–230,
  L82–84)** are pure backward-compat for an OLD on-disk/session format. If Phase 2 is allowed a
  clean break, this legacy path can be deleted to simplify. If not, leave it — it's isolated and
  harmless. (Tag MUST-NOT-churn unless a clean break is sanctioned.)
- **OPTIONAL — `_is_pagination_identifier` keys off the `"_page"` suffix (L62–64).** This couples
  StateManager to the Table's identifier naming convention. If C5 standardizes `_identifier`
  suffixes, make the pagination-vs-selection distinction explicit (e.g. a registered set) rather
  than string-suffix sniffing. LOW priority.
- **Already clean:** the public methods (`get/set/clear_selection`, `get_all_selections`,
  `get_state_for_vue`, `update_from_vue`, `clear`) are a tight, generic, well-documented surface.
  `session_key` param supports independent component groups. Do not churn.
- **NOTE (docs):** `docs/state-ownership-filtering.md` documents a REMOVED feature. Keep as a
  design note but add a banner that it is not part of the current public surface (it already says
  "Removed Feature" in the title — sufficient).

### S6 — Component naming / `component.ts` parity
- **MUST — `component.ts` is a SHARED serialization file** (ORCHESTRATOR_NOTES §"Serialization
  order"). Any rename from C1/C3/C5 (e.g. `seriesColumn`→`categoryColumn`,
  `intensityColumn`/`zColumn`) must update the matching camelCase TS arg in lockstep:
  `Plot3DComponentArgs.seriesColumn/seriesColors` (`component.ts:365–367`),
  `HeatmapComponentArgs.intensityColumn` (`:236`), plus the App.vue dispatch. Serialize these
  edits (see Implementation order).
- **OPTIONAL — TS `mode` unions** already encode the LinePlot vs Plot3D `mode` divergence
  (`LinePlotComponentArgs.mode: 'default'|'tagger'` at `:87` vs
  `Plot3DComponentArgs.mode: 'lines'|'markers'|'lines+markers'` at `:369`). If `mode` is renamed
  to `trace_mode` for Plot3D (api:plot3d), update the TS field too.

**Verdict (surface):** `__init__.py`, `StateManager`, and the selection vocabulary (C4) are
already clean — call them out as DO-NOT-CHURN. The high-value surface work is: **S4** (the
config-split enabler for the whole D1 sweep), **S2** (document the two reusable cross-component
patterns), and the **C1/C3/C5** naming unifications (which ripple into `component.ts`).

---

## Already-clean inventory (DO NOT CHURN)

- `filters` / `filter_defaults` / `interactivity` canonical mapping across every
  `BaseComponent` subclass (C4).
- `VolcanoPlot` render-time thresholds via `__call__` — the reference pattern.
- `MirrorPlot` per-side filters + per-side dynamic-annotation setters + SequenceView wiring.
- `Table` `with_*` formatter chain; the per-peak `PeakAnnotation` overlay + `compute_charge_*`
  producers (LinePlot); `categorical_filters` + `category_*` (Heatmap).
- `SequenceView` generalizations (coverage / internal fragments / proteoform terminals / the
  `SequenceViewResult` annotation bridge) — promote in docs, don't rework the math.
- `StateManager` public surface; the registry mechanism (works, just over-exported).

---

## Implementation order (serialize the shared-file edits)

Shared files that force serialization: `openms_insight/__init__.py`, `core/base.py`,
`js-component/src/types/component.ts` (+ `App.vue`). Recommended sequence:

1. **S4 first — base.py config split (`_get_render_config` vs `_get_cache_config`).**
   Enabler for every D1 change; touches `core/base.py` (shared) once. No component visible
   change yet. Run the full cache-contract tests
   (`test_cache_config_contract`, `test_cache_reconstruction`, `test_component_args_contract`).
2. **Heatmap BUG fixes (independent, ship anytime): `reversescale` restore + `min_points` doc.**
   Local to `heatmap.py` + README; no shared-file contention.
3. **D1 sweep per component** (table → heatmap → lineplot → mirrorplot → volcanoplot → plot3d),
   each relocating presentation keys to `_get_render_config()` + optional `with_labels`/`__call__`.
   These are per-file (no cross-component shared edits) so they can proceed in any order AFTER S4,
   but keep them one-component-per-change for reviewability.
4. **Naming unifications (C1/C3/C5) — SERIALIZE because they touch `component.ts` + App.vue:**
   a. Plot3D `series_*` → `category_*`, `mode` → `trace_mode` (if adopted): edit `plot3d.py`
      THEN `component.ts` (`Plot3DComponentArgs`) THEN App.vue in one change.
   b. Value-axis rule (Heatmap `intensity_column` vs Plot3D `z_column`) — mostly documentation;
      if any rename, same serialized file trio.
   c. C5 identifier convention (auto-derive + `_identifier` suffix; tagger `tag_payload_key` →
      `tag_identifier`): `lineplot.py`/`heatmap.py` + `component.ts`.
5. **LinePlot mode-param grouping (factory `.density`/`.tagger` or `mode_config`)** — large but
   `lineplot.py`-local; do AFTER the lineplot D1 + C5 edits to avoid re-touching the same regions.
6. **SequenceView:** ship the LOW-risk items (render-time `height`+`title`, `CacheMissError`
   alignment, `filter_defaults` exposure) early; gate the OPTIONAL `BaseComponent` re-parenting on
   a full `test_sequenceview*` + `sequenceview-internal.md` golden run (highest parity risk).
7. **Surface/docs (S1, S2, S6):** `__init__.py` docstring/name fix + README sections for the two
   cross-component patterns + the promoted features (categorical_filters, coverage, internal
   fragments, annotation bridge). Do LAST so docs describe the final names.

Throughout: each change carries its parity-safety note above; nothing here removes a Phase-1
capability — the sweep is shape (timing, naming, grouping, docs) plus two genuine bug fixes.
