# Spec: Table cell formatters + LinePlot per-peak charge annotations (FLASHApp → OpenMS-Insight parity)

Two independent parity items, one spec file:

- **ITEM A** — port FLASHApp's custom Tabulator **table formatters** into Insight's `Table`.
- **ITEM B** — add **per-peak charge-state annotations** to Insight's `LinePlot` stick spectrum
  (the plain deconv/anno spectrum only).

Scope guard: this spec does **not** cover the LinePlot *tagger* / *deconvolved-peaks-highlight* /
*density* modes or `SequenceView` (separately specced). It covers only (A) formatters and (B) the
plain-spectrum charge labels.

Oracles (read-only, never edited):
- Formatters: `/home/user/openms-streamlit-vue-component/src/components/tabulator/tabulator-formatters.ts`
  and the table Vue files `TabulatorScanTable.vue`, `TabulatorMassTable.vue`,
  `TabulatorProteinTable.vue`, `TabulatorTagTable.vue`, `TabulatorTable.vue` (same dir).
- Charge annotations: `/home/user/openms-streamlit-vue-component/src/components/plotly/lineplot/PlotlyLineplotUnified.vue`
  (the unified component is what renders "Annotated Spectrum" / "Deconvolved Spectrum"; the legacy
  `PlotlyLineplot.vue` is the simple non-annotated fallback). Data-flow oracle:
  `/home/user/FLASHApp/src/render/update.py`.

Insight targets (extend these):
- `Table`: `/home/user/OpenMS-Insight/openms_insight/components/table.py`,
  JS `/home/user/OpenMS-Insight/js-component/src/components/tabulator/{TabulatorTable.vue,formatters.ts}`.
- `LinePlot`: `/home/user/OpenMS-Insight/openms_insight/components/lineplot.py`,
  JS `/home/user/OpenMS-Insight/js-component/src/components/plotly/PlotlyLineplot.vue`.
- Contract: `/home/user/OpenMS-Insight/openms_insight/core/base.py`; types
  `/home/user/OpenMS-Insight/js-component/src/types/component.ts`.

Design rule (from `migration/README.md` Phase 1/2): reproduce the oracle exactly, but express it as a
**generic, reusable** surface — no FLASHApp-specific hacks in the library.

---

# ITEM A — Table cell formatters

## A.1 Enumeration of every oracle formatter

The old Vue app has exactly **one shared formatter module** plus **inline anonymous formatters** in
column definitions. There are no sparklines, no links, no progress bars, no star/tickCross usage in
the FLASHApp tables. Full inventory:

### A.1.1 `toFixedFormatter` (the only file-defined formatter)

`tabulator-formatters.ts` (entire file):

```ts
import type { CellComponent } from 'tabulator-tables'

export const toFixedFormatter = (decimalPlaces?: number) => (cell: CellComponent) => {
  return cell.getValue().toString().length > 4
    ? (cell.getValue() as number).toFixed(decimalPlaces ?? 4)
    : cell.getValue()
}
```

Exact rendering rules (load-bearing — reproduce precisely):
- It is a **factory**: `toFixedFormatter(decimalPlaces?)`. Default `decimalPlaces = 4`.
- **Guard:** only reformats when `cell.getValue().toString().length > 4`. So short representations
  (e.g. `12`, `1.5`, `-1`, `100`) are returned **unchanged** (no trailing zeros added); only longer
  numbers (e.g. `1234.56789`) are truncated to `N` decimals via `Number.toFixed(N)`.
- Returns the raw value (any type) when the guard is false — i.e. it never coerces non-numbers and
  never pads. This is *fixed-decimals-with-min-length-guard*, **not** plain `toFixed`.
- Every call site uses the no-arg form `toFixedFormatter()` ⇒ 4 decimals.

### A.1.2 Inline anonymous "missing-value sentinel" formatter (`-1 → "-"`)

Appears **4 times**, identical body, defined inline in column defs:

```ts
formatter: function (cell) {
  const value = cell.getValue();
  return value == -1 ? '-' : value;
}
```

Rendering rule: if the cell value equals `-1` (loose `==`), render the string `'-'`; otherwise render
the raw value unchanged. Used to display "no value" for sentinel `-1` masses/q-values.

### A.1.3 Per-table column → formatter map (every custom formatter, every column it serves)

| Oracle table (file) | Column `field` | Column `title` | Formatter | Exact rendering |
|---|---|---|---|---|
| `TabulatorScanTable.vue` | `RT` | Retention time | `toFixedFormatter()` | 4 dp if `len(str)>4`, else raw |
| `TabulatorScanTable.vue` | `PrecursorMass` | Precursor Mass | `toFixedFormatter()` | 4 dp / guarded |
| `TabulatorMassTable.vue` | `MonoMass` | Monoisotopic mass | `toFixedFormatter()` | 4 dp / guarded |
| `TabulatorMassTable.vue` | `SumIntensity` | Sum intensity | `toFixedFormatter()` | 4 dp / guarded |
| `TabulatorMassTable.vue` | `CosineScore` | Cosine score | `toFixedFormatter()` | 4 dp / guarded |
| `TabulatorMassTable.vue` | `SNR` | SNR | `toFixedFormatter()` | 4 dp / guarded |
| `TabulatorMassTable.vue` | `QScore` | QScore | `toFixedFormatter()` | 4 dp / guarded |
| `TabulatorProteinTable.vue` | `ProteoformMass` | Mass | inline `-1 → '-'` (A.1.2) | `'-'` if `==-1` else raw |
| `TabulatorProteinTable.vue` | `ProteoformLevelQvalue` | Q-Value (Proteoform Level) | inline `-1 → '-'` (A.1.2) | `'-'` if `==-1` else raw |
| `TabulatorTagTable.vue` | `Nmass` | N mass | inline `-1 → '-'` (A.1.2) | `'-'` if `==-1` else raw |
| `TabulatorTagTable.vue` | `Cmass` | C mass | inline `-1 → '-'` (A.1.2) | `'-'` if `==-1` else raw |

Columns with **no** custom formatter (raw display, included for completeness — these need only
`sorter`/`hozAlign`, not a formatter): `id`, `Scan`, `MSLevel`, `#Masses`, `MinCharges`, `MaxCharges`,
`MinIsotopes`, `MaxIsotopes` (Mass/Scan tables); `accession`, `description`, `length`,
`MatchingFragments`, `ModCount`, `TagCount`, `Score` (Protein table); `StartPos`, `EndPos`,
`TagSequence`, `Length`, `Score`, `DeltaMass` (Tag table).

Other oracle behaviors that are **structural, not formatters** (out of scope for this item, noted so
they aren't mistaken for formatters): `headerTooltip` strings on most columns, `responsive: N`
priorities (Protein table), `initialSort` (`Score desc`), `go-to-fields`, and the Protein table's
"Best per spectrum" checkbox + `filterBestPerSpectrum`. Header tooltips are already supported by
Insight column defs (`headerTooltip` passthrough); the rest belong to other units.

### A.1.4 Charge / mass display, badges, colors, sparklines, links

**None exist** in the oracle tables. Charge columns (`MinCharges`, `MaxCharges`) render as plain
integers. There is no badge, color, sparkline, link, or icon formatter anywhere in the FLASHApp
Tabulator code. The instruction to include "charge badge / mass / boolean-flag" formatters is a
**generalization requirement** (build a reusable set), *not* an oracle reproduction — these are added
as optional generic formatters in A.2.3, but only `fixed` and `placeholder` are required for FLASHApp
parity.

## A.2 Expressing these in Insight's Table API

### A.2.1 What Insight already has (do not duplicate)

`openms_insight/components/table.py` accepts `column_definitions` (raw Tabulator dicts) and serializes
them to Vue verbatim via `_get_component_args()["columnDefinitions"]`. It also has chainable helpers
`with_column_formatter()`, `with_money_format()`, `with_progress_bar()`.

`js-component/src/components/tabulator/formatters.ts` already defines a **string-name → function
registry** (`customFormatters`) with `scientific`, `signed`, `badge`, plus `isCustomFormatter()` /
`getCustomFormatter()`. `TabulatorTable.vue` (lines 560–576) resolves string formatter names to these
functions at column-build time:

```ts
if (typeof colDef.formatter === 'string' && isCustomFormatter(colDef.formatter)) {
  const customFormatter = getCustomFormatter(colDef.formatter)
  if (customFormatter) { colDef.formatter = customFormatter }
}
```

So the parity mechanism is: **Python sends `formatter: "<name>"` (+ optional `formatterParams`); Vue
swaps the name for a registered function.** We extend the registry, not the resolution logic.

> Important contract constraint: formatters MUST be expressible as JSON-serializable column-definition
> dicts. The cache layer (`base.py._save_to_cache`) and the args contract only persist
> `column_definitions` if they are JSON-serializable (anonymous JS functions are **not**). The oracle's
> inline `function(cell){…}` formatters therefore CANNOT be ported as-is — they must become **named
> registry formatters** keyed by string. This is the crux of Item A.

### A.2.2 Required new generic formatters (FLASHApp parity set)

Add two named formatters to the JS registry. Both are generic and reusable by any MS table.

1. **`fixed`** — reproduces `toFixedFormatter`.
   - Params: `{ precision?: number = 4, minLength?: number = 4 }`.
   - Rule (must match oracle exactly): let `v = cell.getValue()`. If `v` is null/undefined/`''`
     return `''`. If `String(v).length > minLength` and `v` is numeric, return
     `Number(v).toFixed(precision)`; otherwise return `v` unchanged (no padding, original type/string).
   - Default `minLength = 4` and `precision = 4` reproduce `toFixedFormatter()` (the
     `.toString().length > 4` guard, 4 dp). Exposing `minLength` keeps it generic (set `minLength: 0`
     for unconditional `toFixed`).

2. **`placeholder`** — reproduces the inline `-1 → '-'` formatter, generalized.
   - Params: `{ sentinels?: Array<number|string> = [-1], text?: string = '-', loose?: boolean = true }`.
   - Rule: if `cell.getValue()` matches any sentinel (loose `==` when `loose`, else strict `===`),
     render `text`; else render the raw value. Default `sentinels:[-1], text:'-'` reproduces the oracle.
   - Composability note: the oracle never combines `-1→'-'` with `toFixed` on the same column. If a
     future column needs both, prefer doing the sentinel substitution in Python (emit a string column)
     OR add a `placeholder` wrapper param `then?: "<formatterName>"`. **Not required for parity** —
     keep them separate to mirror the oracle 1:1.

### A.2.3 Optional generic formatters (generalization, Phase 2 — not needed for FLASHApp parity)

Provided so the registry is a complete, reusable MS-table set. Implement if cheap; they are not gating
for Item A parity. (`scientific`, `signed`, `badge` already exist.)

- **`charge`** — render an integer charge as a badge/superscript, params
  `{ style?: "badge"|"plain"|"superscript" = "plain", sign?: "+"|"-"|"none" = "+", colorMap?, defaultColor?, textColor? }`.
  `plain` + `sign:"+"` ⇒ `"3+"`. `badge` reuses the `badge` pill styling. Default `plain` matches the
  oracle's plain-integer charge columns, so adding this changes nothing for FLASHApp unless opted in.
- **`mass`** — alias of `fixed` with mass-friendly defaults (`precision:4, minLength:0`) and optional
  `{ unit?: string }` suffix (e.g. `" Da"`). Purely a convenience wrapper over `fixed`.
- **`boolean` / `flag`** — render bool/0-1 as `tickCross`-style glyphs (`"✓"`/`"✗"`) or a `badge`,
  params `{ trueText?: "✓", falseText?: "✗", trueColor?, falseColor? }`. No oracle usage; generic only.

All optional formatters follow the same `(cell, params) => string|HTMLElement` signature and register by
name; none require Python-side changes beyond passing `formatter`/`formatterParams`.

### A.2.4 Python ergonomics (optional, recommended)

The existing string-formatter mechanism already works with **zero** Python changes — a user can write
`column_definitions=[{"field":"MonoMass","formatter":"fixed","formatterParams":{"precision":4}}]`.
For ergonomics and to mirror `with_money_format`, add thin chainable helpers to `table.py` (each just
calls the existing `with_column_formatter`):

```python
def with_fixed_format(self, field, precision=4, min_length=4) -> "Table":
    return self.with_column_formatter(field, "fixed",
                                      {"precision": precision, "minLength": min_length})

def with_placeholder(self, field, sentinels=(-1,), text="-", loose=True) -> "Table":
    return self.with_column_formatter(field, "placeholder",
                                      {"sentinels": list(sentinels), "text": text, "loose": loose})

# optional (A.2.3):
def with_charge_format(self, field, style="plain", sign="+") -> "Table":
    return self.with_column_formatter(field, "charge", {"style": style, "sign": sign})
```

These are convenience only; `column_definitions` with raw `formatter` strings remain the canonical path
and the one exercised by tests.

## A.3 File-by-file change list (Item A)

| File | Change |
|---|---|
| `js-component/src/components/tabulator/formatters.ts` | Add `fixedFormatter`, `placeholderFormatter` (+ optional `chargeFormatter`, `massFormatter`, `booleanFormatter`); add their `*FormatterParams` interfaces; register them in `customFormatters` (`fixed`, `placeholder`, `charge`, `mass`, `boolean`). No change to `isCustomFormatter`/`getCustomFormatter`. |
| `js-component/src/components/tabulator/TabulatorTable.vue` | **No logic change** — the lines 570–576 name→function resolution already handles new names. (Verify new names round-trip; add a short comment listing supported formatter names.) |
| `openms_insight/components/table.py` | (Optional) add `with_fixed_format`, `with_placeholder`, `with_charge_format` chainable helpers next to `with_money_format`. Cache config already serializes `column_definitions`; no change to `_get_cache_config`/`_restore_cache_config`. |
| `js-component/src/types/component.ts` | No required change (`columnDefinitions: ColumnDefinition[]` already carries `formatter`/`formatterParams`). Optionally document the supported custom-formatter names in a comment near `TableComponentArgs`. |
| FLASHApp call sites (Phase 3, not this repo) | Replace oracle inline `function(cell){…}` and `toFixedFormatter()` with `{"formatter":"fixed",…}` / `{"formatter":"placeholder",…}` in the migrated column definitions. |

---

# ITEM B — LinePlot per-peak charge-state annotations (plain spectrum)

## B.1 Behaviors to preserve from the oracle

The plain spectrum is `PlotlyLineplotUnified.vue` with `title === 'Annotated Spectrum'`
(x-axis `m/z`, x-column `MonoMass_Anno`, y-column `SumIntensity_Anno`) — i.e. `isAnnotatedSpectraMode`
/ `xAxisLabel === 'm/z'`. (The `Deconvolved Spectrum` title uses `Monoisotopic Mass` and shows **mass
labels**, not charge labels — that's the existing Insight `annotation_column` path, not this item.)

### B.1.1 Where the charge labels come from (data)

For the **selected mass**, the per-charge isotope envelope is read from the nested `SignalPeaks`
column of the selected scan. Inner peak tuple layout (cross-checked against the FLASHApp parser and the
oracle's `signal.length >= 4` access, lines 397–406 / 779–789):

```
SignalPeaks[massIndex][k] = [ peak_index(0), mz(1), intensity(2), charge(3) ]
```

The oracle builds `HighlightData` for the selected mass: `mzs = signal[1]`, `intensity = signal[2]`,
`charges = signal[3]` (lines 838–862). `update.py` confirms `SignalPeaks` is the per-scan,
per-mass-indexed signal array (Precursor-Signals branch slices `df['SignalPeaks'][mass_index]`), and
that `Annotated Spectrum` data is the selected scan's row.

### B.1.2 Per-charge label text, placement, color (the parity core)

Oracle `annotationData()` m/z branch (lines 816–908):

1. Take the selected mass's `{mzs, charges, intensity}`.
2. **Group by charge state** into `Map<charge, {mz,intensity}[]>` (lines 848–862).
3. Per charge group compute an **intensity-weighted center-of-gravity m/z** (the label's x):
   ```ts
   const summedIntensity = mzIntensity.reduce((s,v)=>s+v.intensity, 0)
   const centerOfGravity = mzIntensity.map(v => (v.intensity/summedIntensity)*v.mz)
   const mass = centerOfGravity.reduce((s,v)=>s+v, 0)   // == Σ(w_i * mz_i)
   ```
4. Draw, per visible charge group:
   - a **rect shape** (the colored badge background) spanning
     `x0 = cog − 0.5*xpos_scaling … x1 = cog + 0.5*xpos_scaling`, `y0 = ypos_low … y1 = ypos_high`,
     `fillcolor = styling.annotationColors.massButton` (`#E4572E`), `line.width = 0`.
   - a **text annotation** `text = "z=" + charge` at `(x = cog, y = ypos)`, `showarrow:false`,
     `font.size:15`.
5. **Placement constants** (shared with mass-label path), from `getAnnotationPositioning` (lines
   582–615) where `ymax = yRange[1]/1.8`: `ypos_low = ymax*1.18`, `ypos = ymax*1.25`,
   `ypos_high = ymax*1.32`; horizontal half-width `xpos_scaling = (1200/plotWidth)*xrangeWidth/xPosScalingFactor`.
6. **Overlap suppression** (lines 864–902 + `computeAnnotationBoxes` 1303–1347 + `testBoxesOverlapForRange`):
   each charge group → one box `{x:cog, width:xpos_scaling, height:ypos_high−ypos_low}`; if **any two
   boxes overlap** in data space (with 1% x-pad and 10% y-pad), **all** charge labels are hidden
   (boolean all-or-nothing). Only boxes flagged `visible` are drawn.
7. Charge labels are shown **only for the currently selected mass** (`selectedMassIndex`); with no
   selection the m/z branch returns empty (lines 822–836). The selected isotope peaks themselves are
   colored via the highlight/selected traces (`highlightColor`/`selectedColor`), the rest `unhighlightedColor`.

> Note the asymmetry vs. Insight's current behavior: Insight draws **one label per peak** from a
> single annotation string. The oracle, for **one** selected peak, fans out into **multiple** charge
> labels at COG positions that are **not** peak x-positions. A single `annotation_column` string per
> row cannot express this. Hence a small generic annotation API is required (B.2), not a column rename.

### B.1.3 Hover content

- The **mass-label** path adds an invisible hover marker with `hovertext = mass.toFixed(2)`
  (lines 937–948). For the charge path the oracle does **not** add a dedicated hover trace — hover on
  the underlying isotope sticks shows default `x+y`. Insight's current LinePlot already uses
  `hoverinfo: 'x+y'` on traces, which matches. **Preserve:** for charge annotations, hover surfaces
  the underlying m/z + intensity (`x+y`); optionally enrich label hover with `"z=N, m/z=…"` (generic,
  see B.2.4) but base parity only needs the per-charge text label + the `x+y` stick hover.

### B.1.4 What is explicitly NOT in scope here

Sequence arrows, amino-acid letters, `Δ=…Da` arrow hovers, the back-button, tagger highlighting, and
`deconvolvedPeaksHighlightMode` (whole-spectrum highlight) all live in the unified component too but
belong to the tagger/SequenceView units. This item ports **only** the `z=charge` labels of the plain
Annotated Spectrum.

## B.2 Generic LinePlot annotation API design

Insight's current model (keep it; it stays the path for the **Deconvolved Spectrum** mass labels):
`annotation_column` (per-row label string) + `highlight_column` (per-row bool) + dynamic annotations
keyed by `peak_id` (`set_dynamic_annotations`), rendered by `PlotlyLineplot.vue.annotatedPeaks` /
`annotationBoxData` (overlap-resolved, one label per peak).

The charge case needs **multiple labels per selected peak at arbitrary x with per-label color**. Add a
generic, render-time **annotation set** that is independent of the per-row column model.

### B.2.1 Schema: `PeakAnnotation` (generic, per-label, not per-row)

A flat list of label descriptors, each fully self-describing in data coordinates:

```
PeakAnnotation = {
  "x": float,                 # data x of the label (e.g. intensity-weighted COG m/z)
  "text": str,                # label text (e.g. "z=12")
  "color"?: str,             # badge fill; default styling.annotationColors.massButton
  "hover"?: str,             # optional hover text for an (invisible) hover point at (x, ypos)
  "group"?: str|int,         # optional group id (used for overlap-suppression scoping)
  "y"?: float                 # optional explicit label y (default: computed ypos band)
}
```

This is deliberately **not** charge-specific: any caller can emit `{x, text, color}` triplets. Charge
labels are just `text="z="+charge`, `x=COG`, `color=massButton`. Mass labels could equally be expressed
this way, but we keep the existing column path for them to avoid churn.

### B.2.2 Config vs render-time

- **Render-time, not cached.** Charge labels depend on the *selection* (which mass) and on data that is
  filtered per spectrum; they must not be baked into the parquet cache. Use the same
  pattern as the existing `set_dynamic_annotations` (stored on the instance, applied in
  `_prepare_vue_data`, stripped before caching via `_strip_dynamic_columns`).
- New instance setter on `LinePlot`:
  ```python
  def set_peak_annotations(self, annotations: Optional[list[dict]]) -> "LinePlot": ...
  def clear_peak_annotations(self) -> "LinePlot": ...
  ```
  storing `self._peak_annotations: Optional[list[dict]]` (init `None` in `__init__` and
  `_restore_cache_config`, like `_dynamic_annotations`). These are **label descriptors**, already in
  final data coordinates — Python (or the caller) does the grouping + COG math, so the Vue side stays a
  dumb renderer. (Computing COG in Python keeps the heavy logic testable and avoids re-deriving the
  `SignalPeaks` tuple layout in JS.)
- **Optional config flag** for callers who want JS-side auto-derivation from columns instead of
  precomputed labels: `charge_annotation` config (see B.2.5). Default off; precomputed `PeakAnnotation`
  list is the parity path.

### B.2.3 Input contract for the FLASHApp parity producer (Phase 3, illustrative)

The migrated FLASHApp page computes labels from `SignalPeaks` for the selected mass and calls
`set_peak_annotations`:

```python
groups = {}                       # charge -> list[(mz, intensity)]
for _, mz, inten, charge in signal_peaks[selected_mass_index]:
    groups.setdefault(int(charge), []).append((mz, inten))
labels = []
for charge, pts in groups.items():
    tot = sum(i for _, i in pts) or 1.0
    cog = sum((i / tot) * mz for mz, i in pts)     # intensity-weighted COG m/z (matches oracle)
    labels.append({"x": cog, "text": f"z={charge}", "color": "#E4572E",
                   "hover": f"z={charge}"})
lineplot.set_peak_annotations(labels)
```

The library itself ships no `SignalPeaks` knowledge — it only consumes the generic `PeakAnnotation`
list. (This is the "generic API, not a FLASHApp hack" requirement satisfied.)

### B.2.4 Rendering plan (Vue)

In `PlotlyLineplot.vue`, add a parallel annotation source that does **not** depend on
`highlight_mask`/`annotations` row arrays:

- Read `peakAnnotations: PeakAnnotation[]` from the data payload
  (`streamlitDataStore.allDataForDrawing.peakAnnotations`, sent by `_prepare_vue_data`).
- Reuse the existing y-band math (`ymax = yRange[1]/1.8`, `ypos_low/ypos/ypos_high = ymax*{1.18,1.25,1.32}`)
  and `pixelWidthToDataUnits` already present in the component.
- For each annotation build a box `{x, width = measured-text-width→dataUnits (or xpos_scaling), height}`
  and run the **existing** greedy/overlap logic. To match the oracle's *all-or-nothing* hiding for
  charge labels, scope overlap by `group`: if the producer marks them all with the same `group` (or we
  detect they came from `peakAnnotations`), apply the oracle rule "any overlap ⇒ hide all in group".
  (Default greedy per-label hiding is acceptable and arguably better; the spec REQUIRES at least that
  overlapping charge labels do not render on top of each other. Document the chosen rule and assert it
  in tests.)
- Emit:
  - `shapes`: one `rect` per visible annotation, `x0 = x − w/2 … x1 = x + w/2`,
    `y0 = ypos_low … y1 = ypos_high`, `fillcolor = annotation.color ?? styling.highlightColor`,
    `line.width:0`. (Oracle uses `massButton`=`#E4572E`=`highlightColor`.)
  - `annotations`: text at `(x, ypos)`, `text = annotation.text`, `showarrow:false`,
    `font:{size:14, color:'white'}` (oracle uses size 15 black text on a colored rect; Insight's
    existing peak labels use size 14 white-on-fill — keep Insight's white-on-fill for visual
    consistency with its mass labels; record this as an intentional, minor styling deviation).
  - optional invisible hover marker at `(x, ypos)` with `hovertext = annotation.hover` when present
    (mirrors the oracle's mass-button hover trace).
- Merge these `shapes`/`annotations` with the existing `annotationShapes`/`peakAnnotations` outputs in
  `layout()` (concatenate). The column-based path and the descriptor-based path coexist.
- Re-render triggers: add `peakAnnotations` to the `_plotConfig`/data watchers (the component already
  re-renders on `allDataForDrawing.plotData` and `_plotConfig` deep-watch; ensure the new array is part
  of the watched payload, e.g. carried inside `_plotConfig` or its own watched key).

### B.2.5 Optional: JS-side auto-derivation (generalization, not parity-gating)

For callers who prefer to ship raw signal columns instead of precomputed labels, add an optional config:
```
config.chargeAnnotation = {
  enabled: bool,                 # default false
  chargeColumn: str,            # per-peak charge
  groupColumn: str,             # which mass/peak a row belongs to (for grouping)
  weightColumn?: str,           # intensity for COG weighting (default yColumn)
  selectionIdentifier?: str,    # only annotate the selected group
  labelTemplate?: str = "z={charge}"
}
```
When enabled, Vue groups the *currently selected* group's rows by `chargeColumn`, computes the
COG with `weightColumn`, and synthesizes `PeakAnnotation`s itself — reproducing the oracle's JS-side
computation exactly. This is the "direct map" alternative; it is **optional**. Parity is met by either
(a) precomputed `set_peak_annotations`, or (b) this flag. Recommend shipping (a) for parity and (b) as
a Phase-2 generalization.

## B.3 `_prepare_vue_data` + `_get_component_args` + types changes

### B.3.1 `openms_insight/components/lineplot.py`

- `__init__`: init `self._peak_annotations: Optional[list[dict]] = None` (alongside
  `_dynamic_annotations`). Do **not** add to `_get_cache_config` (render-time, not cached).
- `_restore_cache_config`: set `self._peak_annotations = None`.
- Add `set_peak_annotations(self, annotations)` / `clear_peak_annotations(self)` (store on instance;
  return `self`).
- `_prepare_vue_data`: after computing `df_pandas`/`data_hash`, if `self._peak_annotations` is not None,
  attach `result["peakAnnotations"] = self._peak_annotations` and fold a stable digest into the hash
  (mirror the existing `ann_hash` pattern: `data_hash = f"{data_hash}_{md5(json.dumps(labels))[:8]}"`)
  so the frontend re-renders when labels change.
- `_strip_dynamic_columns`: also `vue_data.pop("peakAnnotations", None)` so cached base data is clean
  (same reasoning as stripping `_dynamic_*`).
- `_apply_fresh_annotations` (cache-hit path in `bridge.py`): re-attach `peakAnnotations` from the
  current instance (parallel to how it re-applies dynamic annotations), so a cache hit still carries the
  current selection's labels.
- (Optional B.2.5) `_get_component_args`: pass `chargeAnnotation` config through under `config` if set.

### B.3.2 `_get_component_args`

No required change for the precomputed path (labels travel in `_prepare_vue_data`'s payload, not in
static args). If B.2.5 is implemented, include `config.chargeAnnotation` in the returned `config` dict.

### B.3.3 `js-component/src/types/component.ts`

- Add an exported type:
  ```ts
  export interface PeakAnnotation {
    x: number
    text: string
    color?: string
    hover?: string
    group?: string | number
    y?: number
  }
  ```
- Extend `LinePlotComponentArgs` / the line-plot data payload typing to allow `peakAnnotations?: PeakAnnotation[]`
  (it arrives via `allDataForDrawing`, so type it where `PlotData` / the data store payload is typed; at
  minimum add `peakAnnotations?: PeakAnnotation[]` to the data payload interface used by
  `PlotlyLineplot.vue`).
- (Optional B.2.5) add `chargeAnnotation?` to `LinePlotConfig`.

### B.3.4 Vue file

- `js-component/src/components/plotly/PlotlyLineplot.vue`: implement B.2.4 (new computed
  `descriptorAnnotationShapes` / `descriptorPeakAnnotations`, merged into `layout().shapes/annotations`;
  read `peakAnnotations` from the store; add to watchers).

## B.4 File-by-file change list (Item B)

| File | Change |
|---|---|
| `openms_insight/components/lineplot.py` | `_peak_annotations` field; `set_peak_annotations`/`clear_peak_annotations`; attach `peakAnnotations` + hash in `_prepare_vue_data`; strip in `_strip_dynamic_columns`; re-attach in `_apply_fresh_annotations`. (Optional) pass `chargeAnnotation` config. |
| `openms_insight/rendering/bridge.py` | Ensure cache-hit path re-applies `peakAnnotations` (calls `_apply_fresh_annotations`) — verify no stripping of the new key on the cached branch. |
| `js-component/src/components/plotly/PlotlyLineplot.vue` | Render descriptor annotations (shapes+labels+optional hover), merge into layout, watch `peakAnnotations`. |
| `js-component/src/types/component.ts` | `PeakAnnotation` type; `peakAnnotations?` on the line-plot payload; (optional) `chargeAnnotation?` on `LinePlotConfig`. |
| FLASHApp producer (Phase 3, other repo) | Compute charge groups + COG from `SignalPeaks` for the selected mass; call `set_peak_annotations`. |

---

# Tests

## T.A — Item A (formatters)

JS unit tests (Vitest, `js-component`):
- `fixedFormatter`: `12 → 12` (len ≤ 4, unchanged), `1.5 → 1.5`, `-1 → -1`, `1234.56789 → "1234.5679"`
  (4 dp), `null/undefined/'' → ''`, non-numeric string passthrough; `minLength:0` forces
  `1.5 → "1.5000"`; `precision:2` ⇒ `1234.56789 → "1234.57"`.
- `placeholderFormatter`: `-1 → "-"`, `5 → 5`, `"-1" == -1 → "-"` under `loose:true` (and NOT under
  `loose:false`), custom `sentinels:[0,-1], text:"n/a"`.
- (If implemented) `chargeFormatter` `3 → "3+"` (plain/`sign:+`), badge style returns HTML span;
  `booleanFormatter` `true → "✓"`, `false → "✗"`.
- Registry: `isCustomFormatter('fixed') === true`, `isCustomFormatter('placeholder') === true`,
  `getCustomFormatter('fixed')` returns a function. Resolution in `TabulatorTable.vue` swaps the string
  for the function (assert column def `formatter` becomes a function for `"fixed"`).

Python tests (`tests/`):
- New `tests/test_table_formatters.py`: build a `Table` with
  `column_definitions=[{"field":"mass","formatter":"fixed","formatterParams":{"precision":4}},
  {"field":"q","formatter":"placeholder","formatterParams":{"sentinels":[-1],"text":"-"}}]`; assert
  `_get_component_args()["columnDefinitions"]` round-trips the `formatter` **string** and
  `formatterParams` unchanged (JSON-serializable; survives cache write/reload via a second `Table(...)`
  reconstruction from cache).
- Assert `with_fixed_format`/`with_placeholder` (if added) set the expected `formatter`/`formatterParams`
  on the matching column (mirror existing `with_money_format` expectations).

## T.B — Item B (charge annotations)

Python (`tests/test_lineplot_charge_annotations.py`, plus extend the contract suites):
- `set_peak_annotations([{ "x":1000.5,"text":"z=12","color":"#E4572E"}, …])` then `_prepare_vue_data({})`
  returns a dict with `"peakAnnotations"` equal to the list, and an `_hash` that **differs** from the
  no-annotation hash (hash incorporates labels). Still satisfies the existing
  `test_prepare_vue_data_contract` invariant (dict + string `_hash`).
- `clear_peak_annotations()` ⇒ `"peakAnnotations"` absent (or empty) and hash reverts.
- `_strip_dynamic_columns({"plotData":df,"peakAnnotations":[…]})` removes `peakAnnotations`
  (cache cleanliness) — parallels existing `_strip_dynamic_columns` test expectations.
- Cache reconstruction: a `LinePlot` reloaded from cache has `_peak_annotations is None` (render-time
  state not persisted) and does not error.
- COG correctness helper (pure function, if the COG math is factored into a Python util): two isotope
  peaks `(mz=1000, i=3),(mz=1001, i=1)` ⇒ `cog == 1000.25` (intensity-weighted), label `"z=12"`.
- Add `LinePlot` to any existing parametrized contract test that should also exercise the
  annotation-carrying payload (mirrors `test_prepare_vue_data_contract.py` / `test_component_args_contract.py`).

JS (Vitest):
- Given `args` + store payload with `peakAnnotations=[{x:1000.5,text:"z=12"},{x:1000.7,text:"z=11"}]`,
  the computed `layout().annotations` includes texts `"z=12"`/`"z=11"` and `layout().shapes` includes
  matching colored rects at the band y `[ypos_low, ypos_high]`.
- Overlap rule: two annotations whose boxes overlap in data space do **not** both render (assert the
  visible count drops; if group-scoped all-or-nothing is chosen, assert **both** hidden when they
  overlap, matching the oracle).
- Color: annotation with `color:"#123456"` produces a shape `fillcolor:"#123456"`; missing color falls
  back to `styling.highlightColor`.
- Hover: annotation with `hover:"z=12, m/z=1000.5"` adds an (invisible) hover point carrying that text;
  underlying stick traces keep `hoverinfo:'x+y'`.

## T.gate

Both items must pass the Phase-1 machine gate (`migration/run_review.py gate`): `pytest`,
`npm run build` (TS must compile — hence the `component.ts` additions), and `parity_diff.py` structural
probes. No oracle files are modified.

---

## Open questions / decisions recorded

1. **Charge-label COG math location.** Spec puts it in the Python producer (testable, no JS re-derivation
   of `SignalPeaks` tuple layout). The optional B.2.5 config moves it to JS for callers shipping raw
   columns. Recommend Python-side for parity.
2. **Overlap hiding: all-or-nothing (oracle) vs greedy (Insight current).** Spec requires overlapping
   charge labels never stack; recommends honoring the oracle's group-scoped all-or-nothing for charge
   labels while leaving the existing greedy per-peak resolution for mass labels. Final choice must be
   asserted in T.B JS tests.
3. **Label font (oracle size-15 black-on-fill vs Insight size-14 white-on-fill).** Spec keeps Insight's
   white-on-fill for consistency with its existing mass labels; flagged as an intentional minor
   deviation, not a parity break (text content + position + badge color are preserved).
4. **Sentinel + toFixed composition.** Oracle never combines them; spec keeps `fixed` and `placeholder`
   separate (1:1 with oracle). A `placeholder.then` chain is noted as a future option only.
