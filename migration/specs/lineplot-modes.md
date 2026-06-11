# Spec: Two new LinePlot modes — `mode="tagger"` and `mode="density"`

Status: implementable spec (Phase 1 parity). Analysis only.

Targets to change:
- Python: `openms_insight/components/lineplot.py`
- Vue: `js-component/src/components/plotly/PlotlyLineplot.vue` (+ one new sibling
  `PlotlyDensityPlot.vue`), `js-component/src/App.vue`,
  `js-component/src/types/component.ts`, `js-component/src/stores/selection.ts`
- Tests: `tests/test_lineplot_tagger.py`, `tests/test_lineplot_density.py`,
  `tests/integration/test_tagger_drilldown.py`

Oracles (read-only, reproduce behavior):
- Tagger: `/home/user/openms-streamlit-vue-component/src/components/plotly/lineplot/PlotlyLineplotTagger.vue`
- Unified superset: `/home/user/openms-streamlit-vue-component/src/components/plotly/lineplot/PlotlyLineplotUnified.vue`
- Plain baseline: `/home/user/openms-streamlit-vue-component/src/components/plotly/lineplot/PlotlyLineplot.vue`
- Density/FDR: `/home/user/openms-streamlit-vue-component/src/components/plotly/lineplot/FDR_plotly.vue`
- Tagger data feed: `/home/user/openms-streamlit-vue-component/src/components/tabulator/TabulatorTagTable.vue` (builds `TagData`), `/home/user/openms-streamlit-vue-component/src/stores/selection.ts` (`TagData` shape)
- FLASHApp data origin: `/home/user/FLASHApp/src/render/initialize.py`, `update.py`, `components.py`; KDE producer `/home/user/FLASHApp/src/parse/deconv.py` (`fdr_density_distribution`) and `/home/user/FLASHApp/src/parse/tnt.py`; tagger per-scan columns `/home/user/FLASHApp/src/parse/deconv.py` (`combined_spectrum`) and `/home/user/FLASHApp/src/parse/masstable.py` (`_compute_peak_cells`, `SignalPeaks`).

---

## 0. Design principle: `mode` selects behavior; heavy math moves to Python

The existing `LinePlot` (`mode="default"`, implicit) keeps today's behavior verbatim.
Add a constructor arg `mode: str = "default"` accepting `"default" | "tagger" | "density"`.
`mode` is **config-time** (cache-affecting, in `_get_cache_config`) because it changes
the tidy schema, the Vue dispatch string, and `get_state_dependencies()`.

The oracle does all per-charge center-of-gravity math, mass→peak position matching, and
KDE in Vue or in a parse step. For parity *with less Vue*, this spec moves every
heavy/numeric step into Python, emitting **tidy long-format frames** the Vue layer just
draws:

- **density**: Python runs `scipy.stats.gaussian_kde` (same as the oracle parse step) and
  emits one long frame `{x, y, group}` with `group ∈ {"target","decoy"}`. Vue splits by
  `group` into two line traces. No KDE in Vue.
- **tagger**: Python pre-explodes `SignalPeaks` and pre-computes, per drill-down level, the
  highlight masks, the per-charge center-of-gravity label positions, and the sequence-arrow
  segments — emitting tidy frames keyed by a stable `peak_id`. Vue keeps only the stateful
  *navigation* (which level / which mass is open) and the stick/annotation rendering, reading
  precomputed positions instead of recomputing `findNearest`, COG, or reversed-index math.

This keeps the non-negotiable behavior identical while removing the ~600-line numeric core
from Vue. The drill-down **state** stays in Vue (it is interaction state, not data) but routes
through the generic `selection.ts` store, never a bespoke FLASH store.

---

## MODE A — `mode="density"` (target/decoy FDR KDE)

### A.1 Behaviors to preserve (oracle `FDR_plotly.vue`)

- Two series on one axes: **target** and **decoy**.
- Colors: target `green`, decoy `red` (oracle `marker: { color: 'green' }` / `'red'`).
- Mode `lines+markers`, `type: 'scatter'` for both (oracle lines 84/93).
- Legend **on**; names exactly `"Target QScores"` and `"Decoy QScores"` (oracle lines 86/95).
  Make the noun configurable (`scoreLabel`) since FLASHTnT reuses this view for
  `ProteoformLevelQvalue`, but default to `QScore`.
- Axis titles: x = `"QScore"`, y = `"Density"` (oracle lines 62/65). x `showgrid:false`,
  y `showgrid:true`, `rangemode:'nonnegative'`, `fixedrange:true` (oracle 63–69).
- Title `<b>{title}</b>` (oracle 58), height 400, SVG export button filename `FDR-plot`
  (oracle 112–124).
- Decoy may be **empty** (oracle FLASHApp emits `pd.DataFrame(columns=['x','y'])` when no
  decoys, deconv.py:235 / tnt.py:241). Empty decoy ⇒ target-only plot, no error.
- No click/selection, no zoom-state, no per-charge math. Purely two static curves.

### A.2 KDE math — done in Python (parity with the oracle parse step)

Oracle `deconv.py::fdr_density_distribution` (quoted):

```python
target_qscores = df[df['TargetDecoyType'] == 0]['Qscore'].dropna()
x_target = np.linspace(target_qscores.min(), target_qscores.max(), 200)
kde_target = gaussian_kde(target_qscores)
density_target = pd.DataFrame({'x': x_target, 'y': kde_target(x_target)})
...
decoy_qscores = df[df['TargetDecoyType'] > 0]['Qscore'].dropna()
if len(decoy_qscores) > 0:
    x_decoy = np.linspace(decoy_qscores.min(), decoy_qscores.max(), 200)
    kde_decoy = gaussian_kde(decoy_qscores)
    density_decoy = pd.DataFrame({'x': x_decoy, 'y': kde_decoy(x_decoy)})
else:
    density_decoy = pd.DataFrame(columns=['x', 'y'])
```

(`tnt.py::fdr_density_distribution` is identical except the target/decoy split is by
`accession.str.startswith('DECOY_')` over `ProteoformLevelQvalue`.)

The new `LinePlot(mode="density")` accepts data in **either** of two shapes and normalizes
to the tidy emit frame in `_preprocess`:

1. **Pre-binned tidy (preferred, no SciPy at render):** long frame with columns
   `{x_column, y_column, group_column}` and `group ∈ {"target","decoy"}` — exactly what a
   FLASHApp parse step already produces by `pd.concat` of the two density DataFrames with a
   `group` label. Python passes it straight through.
2. **Raw scores (`kde_from` set):** a frame with a numeric score column + a
   target/decoy label column. Python runs the *same* `gaussian_kde` + `np.linspace(min,max,200)`
   per group at preprocess time and produces the tidy long frame. This collapses the
   oracle's separate parse step into the component so callers can pass raw scores.

Resulting cached/emit schema is always tidy long: `{ x: float, y: float, group: str }`.

### A.3 Python API (`mode="density"`)

```python
LinePlot(
    cache_id="fdr",
    data=density_long_df,        # tidy {x, y, group} OR raw scores (+ kde_from)
    mode="density",
    x_column="x",                # default "x"
    y_column="y",                # default "y"
    group_column="group",        # NEW (density only); default "group"
    target_value="target",       # NEW; label that maps to the target series
    decoy_value="decoy",         # NEW; label for the decoy series
    # KDE-from-raw (optional):
    kde_from=None,               # NEW; e.g. {"score": "Qscore", "label": "TargetDecoyType"}
    kde_points=200,              # NEW; np.linspace count (oracle = 200)
    title="FDR Plot",
    x_label="QScore",            # default "QScore"
    y_label="Density",           # default "Density"
    styling={"targetColor": "green", "decoyColor": "red"},
    config={"scoreLabel": "QScore"},   # noun in legend ("{scoreLabel} ... ")
)(key="fdr", state_manager=sm)
```

- All density params are **config-time** (cache-affecting). No render-time `__call__` args
  beyond the inherited `key/state_manager/height`.
- No `filters`/`interactivity` for density (static plot). `get_state_dependencies()` returns
  `[]` so the curve is cached once per dataset.

### A.4 `_prepare_vue_data` additions (density branch)

- Project to `[x_column, y_column, group_column]`; ignore selection `state` (no filters).
- Emit the tidy frame under data key `plotData` (so the Arrow column-parse path in
  `streamlit-data.ts` line 137 `key.startsWith('plotData')` applies).
- `_hash` = hash of `(mode, x_column, y_column, group_column, row count, target/decoy value
  set)` — stable, since data does not depend on state.
- `_plotConfig` carries `{ mode: "density", xColumn, yColumn, groupColumn, targetValue,
  decoyValue }`.

Return:
```python
{ "plotData": df_pandas, "_hash": data_hash,
  "_plotConfig": {"mode": "density", "xColumn": ..., "yColumn": ...,
                  "groupColumn": ..., "targetValue": ..., "decoyValue": ...} }
```

### A.5 `_get_component_args` keys (density)

```python
{
  "componentType": "PlotlyDensityPlot",   # new sibling dispatch
  "mode": "density",
  "title": title,
  "xLabel": self._x_label,                # "QScore"
  "yLabel": self._y_label,                # "Density"
  "xColumn": self._x_column,
  "yColumn": self._y_column,
  "groupColumn": self._group_column,
  "targetValue": self._target_value,
  "decoyValue": self._decoy_value,
  "scoreLabel": config.get("scoreLabel", "QScore"),
  "styling": {**{"targetColor": "green", "decoyColor": "red"}, **self._styling},
  "config": self._plot_config,
  "height": ...,
}
```

### A.6 Vue plan (density)

Add a **sibling** component `PlotlyDensityPlot.vue` (density is a different plot family —
two full continuous curves, legend on, no stick/annotation/zoom machinery; folding it into
`PlotlyLineplot.vue` would bloat that file with an unrelated branch). Dispatch via a new
`componentType: "PlotlyDensityPlot"`.

Behavior:
- Read `plotData` as columns `{ x:[…], y:[…], group:[…] }` from
  `streamlitDataStore.allDataForDrawing.plotData` (same source as `PlotlyLineplot.vue` line
  105). Column names come from `args` (`xColumn`/`yColumn`/`groupColumn`).
- Split rows where `group === targetValue` → target trace (green, `lines+markers`,
  name `` `${scoreLabel} (Target)` ``), `group === decoyValue` → decoy trace (red, name
  `` `${scoreLabel} (Decoy)` ``). Drop the decoy trace if it has 0 rows.
- Layout: copy oracle `FDR_plotly.vue` layout (legend on, x `showgrid:false`, y
  `showgrid:true`+`rangemode:'nonnegative'`+`fixedrange:true`, title `<b>…</b>`, height 400),
  themed via `streamlitDataStore.theme` like the Insight `PlotlyLineplot.vue` (oracle FDR
  hard-codes white; Insight should theme it — minor, allowed improvement).
- SVG export button, filename `args.title || 'FDR-plot'`.
- No store reads/writes, no click handlers.

`App.vue` dispatch switch — add:
```ts
case 'PlotlyDensityPlot':
  return PlotlyDensityPlot
```
(import alongside the other plotly components, lines 28–33 / register in `components`).

`component.ts` — add typed args:
```ts
export interface DensityPlotComponentArgs extends BaseComponentArgs {
  componentType: 'PlotlyDensityPlot'
  mode: 'density'
  title?: string
  xLabel?: string
  yLabel?: string
  xColumn: string
  yColumn: string
  groupColumn: string
  targetValue: string
  decoyValue: string
  scoreLabel?: string
  styling?: { targetColor?: string; decoyColor?: string }
  config?: Record<string, unknown>
  height?: number
}
```
Add `DensityPlotComponentArgs` to the `ComponentArgs` union (line 233).

`selection.ts` — **no change** for density (no interactivity).

### A.7 Tests (density) — `tests/test_lineplot_density.py`

Mirror `test_prepare_vue_data_contract.py` + `test_volcanoplot.py`. Add a fixture
`sample_density_data` (tidy long, target+decoy) and `sample_density_scores` (raw scores +
label) in `conftest.py`.

- `test_prepare_vue_data_returns_dict_with_hash`: density returns dict with str `_hash`.
- `test_emits_tidy_long_with_group`: `plotData` has `group_column` with values ⊆
  `{target_value, decoy_value}`.
- `test_kde_from_raw_scores`: with `kde_from`, output has exactly `2*kde_points` rows for a
  two-class input (200 per group, matching oracle) and `y >= 0` everywhere.
- `test_empty_decoy_ok`: target-only input → only `target_value` rows; no exception
  (parity with `pd.DataFrame(columns=['x','y'])`).
- `test_component_args`: `componentType == "PlotlyDensityPlot"`, `mode == "density"`,
  `xLabel == "QScore"`, `yLabel == "Density"`, styling has `targetColor`/`decoyColor`.
- `test_state_dependencies_empty`: `get_state_dependencies() == []` (static).
- `test_cache_config_roundtrip`: `mode`, `group_column`, `target_value`, `decoy_value`,
  `kde_from`, `kde_points` survive `_get_cache_config`/`_restore_cache_config`.

---

## MODE B — `mode="tagger"` (de-novo sequence-tag overlay + stateful drill-down)

This is the hardest port. The oracle is a single stateful spectrum that switches between
two **levels** and recomputes everything from `per_scan_data` + `selectionStore.selectedTag`.

### B.1 The exact interaction model (oracle `PlotlyLineplotTagger.vue`)

There are **two drill-down levels**, encoded by `args.title` which the component mutates:

- **Level 0 — "Augmented Deconvolved Spectrum"** (x = `MonoMass`, "Monoisotopic Mass").
  Sticks of the deconvolved spectrum. The currently selected tag's fragment masses are
  highlighted: orange `#E4572E` for tag-member masses, gold `#F3A712` for the two masses
  flanking the within-tag residue the user selected (`reversedSelectedAA`). Above the peaks,
  per highlighted mass, a **mass button** (rect + label `mass.toFixed(2)`) is drawn; between
  consecutive mass buttons a **sequence arrow** with the residue letter and a hover
  `Δ=<delta> Da` is drawn (oracle lines 393–540).
- **Level 1 — "Augmented Annotated Spectrum"** (x = `m/z`). Entered by **clicking a
  highlighted mass button** at level 0. Shows the *raw* m/z signal peaks that make up that
  one selected mass, grouped by charge; each charge cluster gets a charge label `z=<charge>`
  positioned at its **intensity-weighted center of gravity** (oracle 330–373). A round
  **back button** (`↩`) returns to level 0 (oracle template line 3; `showBackButton` true only
  at this level, line 82–84).

State variables in the oracle:
- `selectedMass: number | undefined` — index (into `highlightedValues`) of the mass whose
  m/z cluster is open at level 1. `undefined` ⇒ level 0.
- `manual` / `manual_xRange` — user zoom override (oracle 56–58, 705–731).
- The **incoming** selection comes from the store: `selectedScan` (`selectedScanIndex`),
  and `selectedTag: TagData` with fields `{ sequence, nTerminal, masses, selectedAA,
  startPos, endPos }` (oracle store `TagData`, set by `TabulatorTagTable.vue`).

Click handler (oracle `onPlotClick`, 679–696): on a click whose `x` equals a highlighted
mass, set `selectedMass = i`, switch title to "Augmented Annotated Spectrum", redraw.
Watches on `selectedScan` and `selectedTag` (657–667) **reset** to level 0
(`title = "Augmented Deconvolved Spectrum"`, `selectedMass = undefined`). In the Unified
oracle the same reset is `resetManualState()` which also calls
`selectionStore.updateSelectedMass(undefined)` (Unified 1570–1581) — i.e. the open mass is a
**store-backed selection**, not purely local. We adopt the Unified approach: the open mass is
a generic selection so it round-trips through Python and survives reruns.

Per-charge math at level 1 (oracle 345–373), to reproduce exactly:
```
group raw peaks of the selected mass by charge
for each charge z:
  summedIntensity = Σ intensity
  COG = Σ (intensity/summedIntensity) * mz          # intensity-weighted mean m/z
  draw rect [COG ± 0.5*xpos_scaling] and label "z="+z at COG
```
`xpos_scaling = (xRange[1]-xRange[0]) / 27.5` at level 1 (oracle `xPosScalingFactor` 284–286;
Unified generalizes to plot-width-aware `computeXposScalingFactor`).

The reversed-index subtlety (oracle 204–214, quoted):
> A tag's fragment masses arrive in descending order, so the rendered tag letters use a
> reversed index (`sequence.length - 1 - i`). Reverse the selected within-tag index into that
> same space so the highlight lands on the residue the user selected instead of its mirror
> position.
```ts
reversedSelectedAA = (tag.sequence.length - 1) - tag.selectedAA
```
This selects which mass(es) get the **gold** color: a mass at highlighted-index `i` is gold
iff `reversedSelectedAA === i || reversedSelectedAA === i-1`; the sequence arrow at `i` is
gold iff `reversedSelectedAA === i` (oracle 257–266, 397–402, 451–456). This must be
preserved exactly.

Zoom (oracle `xRange`, 586–611; `computeYRange`, 732–752):
- Level 0 default range fits to the highlighted masses; if their span exceeds
  `maxAnnotationRange = 27.5*30` it centers on the highlighted-mass centroid with a fixed
  offset (oracle 599–609).
- Level 1 default range fits to the selected mass's m/z cluster
  `[min(mzs)*0.98, max(mzs)*1.02]` (oracle 596–598).
- y range is always `[0, max_in_view*1.8]` (1.8 headroom for buttons), y `fixedrange:true`.
- Manual zoom: on `plotly_relayout`, clamp x≥0, recompute y to the in-view max, persist as
  `manual_xRange` (oracle 705–731). Autorange resets to full data extent.

Sticks: each peak becomes triplet `(x,x,x)`/`(-1e7, y, -1e7)` (oracle 124–179) — identical to
Insight `PlotlyLineplot.vue` `xValuesStick`/`yValuesStick` (227–234). Three line traces:
unhighlighted `lightblue`, highlighted `#E4572E`, selected `#F3A712` (oracle 553–575).

### B.2 Input data — exact columns

Per-scan source = FLASHApp `combined_spectrum` (deconv.py:166–185), one **row per scan**,
columns:
- `MonoMass: list[float]` — deconvolved monoisotopic masses (x at level 0).
- `SumIntensity: list[float]` — intensities for `MonoMass` (y at level 0).
- `SignalPeaks: list[ list[ [idx, mz, intensity, charge] ] ]` — outer index aligned to
  `MonoMass[i]`; inner list = raw m/z peaks for that mass; each peak is a 4-tuple. Layout
  from `masstable.py::_compute_peak_cells` (quoted):
  `rec = (float(pi), pmz, float(aspec_int[pi]), float(round(anno_mass / pmz)))` ⇒
  **index 0 = peak index, 1 = m/z, 2 = intensity, 3 = charge.** The oracle reads
  `signal[1]`(mz), `signal[2]`(intensity), `signal[3]`(charge) (oracle 227–231; Unified
  399–405). Schema: `pa.list_(pa.list_(pa.list_(pa.float64())))` (masstable.py:32).
- `MonoMass_Anno: list[float]`, `SumIntensity_Anno: list[float]` — the annotated (m/z) spectrum
  (used by the sibling plain `Annotated Spectrum`, not strictly by the tagger levels, but
  present in the same row; keep them addressable).

The drill-down selection = `TagData`, built in `TabulatorTagTable.vue::updateSelectedTag`
from a tag-table row (quoted essentials):
```ts
masses = (row['mzs'] as string).split(',').map(Number).filter(n => n !== 0)   // tag fragment masses
startPos / endPos  = row['StartPos'] / row['EndPos']
selectedAA (tagPos) = selectedAApos - startPos        // within-tag residue index
sequence  = row['TagSequence']
nTerminal = row['N mass'] === -1
updateTagData({ sequence, nTerminal, masses, selectedAA, startPos, endPos })
```
So the *masses to highlight* are `TagData.masses`; the oracle matches each to a `MonoMass[j]`
within `1e-5` (oracle `highlightedMassPos`, 181–203). The *residue letters* come from
`TagData.sequence` (reversed). This `TagData` is exactly the cross-component selection that
must flow through the generic store.

### B.3 Move the numeric core to Python (tidy frames per level)

Rather than reimplement the oracle's in-Vue `findNearest`/COG/reversed-index code, `LinePlot
(mode="tagger")` precomputes, **per render** (it depends on `spectrum` + `tag` selections),
two tidy frames keyed by stable `peak_id`:

1. **`plotData` (level-0 deconvolved sticks)** — long, one row per `MonoMass[i]`:
   `{ x: MonoMass[i], y: SumIntensity[i], peak_id: i,
      highlight: bool, selected: bool, mass_label: str }`
   where `highlight` = mass is in `TagData.masses` (matched within `1e-5`), `selected` = the
   reversed-index gold rule (`reversedSelectedAA == hi || reversedSelectedAA == hi-1`),
   `mass_label` = `f"{mass:.2f}"` for highlighted masses else `""`. This is exactly the
   existing LinePlot stick+highlight+annotation contract (`x_column`/`y_column`/
   `highlight_column`/`annotation_column`), so **level 0 renders through the existing
   `PlotlyLineplot.vue` highlight/annotation/stick code unchanged**.

2. **`taggerSegments` (level-0 sequence arrows)** — one row per adjacent highlighted-mass
   pair: `{ x_start, x_end, residue, delta, selected }`. `residue` = `sequence[length-1-i]`,
   `delta = |x_start - x_end|`, `selected` = `reversedSelectedAA == i`. Precomputing this in
   Python removes the arrow/`Δ` math from Vue (oracle 449–540).

3. **`taggerCharges` (level-1 m/z clusters for the open mass)** — only when the `tagger_mass`
   selection is set; long, one row per raw signal peak of the selected mass:
   `{ mz, intensity, charge, peak_id, cog, charge_label, selected }` where `cog` = the
   per-charge intensity-weighted center of gravity (computed in Python with the oracle
   formula), `charge_label` = `f"z={charge}"`, `selected` = gold rule applied to the open
   mass index. Vue draws these as sticks + per-charge labels at `cog` without recomputing COG.

All three are emitted as separate `plotData*`-prefixed Arrow tables so the
`streamlit-data.ts` column-parse path applies (it parses any key starting with `plotData`;
emit `plotData`, `plotDataTaggerSegments`, `plotDataTaggerCharges`).

> Parity safeguard: keep the matching/COG/reversed-index formulas byte-for-byte equal to the
> oracle (`1e-5` mass tolerance; `COG = Σ (I/ΣI)·mz`; `reversedSelectedAA = len-1-selectedAA`;
> gold rule `== i || == i-1` for masses, `== i` for arrows). The parity gate diffs these.

### B.4 Drill-down state through the **generic** `selection.ts` store

The Insight store is generic (`updateSelection(identifier, value)`, dynamic keys). We express
the tagger's stateful navigation with three generic identifiers (no FLASH-specific store, no
`TagData` type baked into the store):

| identifier (default)        | set by                                   | meaning                                                |
|-----------------------------|------------------------------------------|--------------------------------------------------------|
| `spectrum` (filter)         | scan/protein table click (external)      | which scan row → filters `per_scan_data`               |
| `tag` (filter)              | **Tag table** click (external)           | selected tag; carries the `TagData` payload object     |
| `tagger_mass` (interactivity)| **clicking a mass button in the plot**  | open mass index → level 1; `null` ⇒ level 0 (back btn) |

- `filters={"spectrum": "<scan col>", "tag": "<tag id col>"}`,
  `interactivity={"tagger_mass": "peak_id"}`.
- **Incoming tag**: the value stored under `tag` is the `TagData` object
  `{sequence, nTerminal, masses, selectedAA, startPos, endPos}` (the same dict the oracle's
  `TabulatorTagTable` builds). It is an opaque JSON value to the generic store — Python reads
  it from `state["tag"]` to compute the highlight masks. (This replaces the oracle's
  `selectionStore.selectedTag` getter with a generic keyed value; the TagTable component sets
  it via `updateSelection("tag", tagData)`.)
- **Drill-down click**: the plot's existing `onPlotClick` already maps a clicked peak to
  `interactivity` and calls `selectionStore.updateSelection("tagger_mass", peak_id)`
  (Insight `PlotlyLineplot.vue` 944–985). For the tagger, clicking a **mass button** (a peak
  with `highlight === true`) sets `tagger_mass = peak_id` ⇒ Python recomputes and emits
  `taggerCharges` ⇒ Vue shows level 1. The **back button** calls
  `selectionStore.updateSelection("tagger_mass", null)` ⇒ Python omits `taggerCharges` ⇒ Vue
  shows level 0.
- **Reset on new scan/tag**: parity with oracle watches (657–667) and Unified
  `resetManualState` (1570–1581). Because `tagger_mass` lives in the store and is keyed
  independently, Python applies a `filter_defaults`-style reset: when `spectrum` or `tag`
  changes, the bridge re-renders and Vue's existing data-change watcher resets `manualXRange`
  (`PlotlyLineplot.vue` 682–698). To force `tagger_mass→null` on scan/tag change, Python sets
  `filter_defaults={"tagger_mass": None}` and, in `_prepare_vue_data`, ignores a stale
  `tagger_mass` whose `peak_id` is not present in the new highlighted set (so a leftover open
  mass from a previous tag cannot persist) — reproducing the oracle reset without a bespoke
  watcher.

No new store *fields* are required — the generic dynamic-key store already supports arbitrary
identifiers including object values. The only `selection.ts` consideration: the generic
`updateSelection` JSON-clones state in `App.vue` before sending to Python (App.vue 85), so the
`TagData` object value round-trips fine. **`selection.ts` change: none required**; document
that `tag`/`tagger_mass` are conventional identifiers. (If a typed convenience is desired, add
an optional `TaggerSelectionPayload` interface in `component.ts` for documentation only — not
a store field.)

This is the crux: the oracle's bespoke `selectedTag`/`selectedTagIndex`/`selectedMass`/
`updateSelectedMass` getters+actions collapse into three generic keyed selections
(`tag`, `tagger_mass`, plus the existing `spectrum` filter), and the drill-down level is a
**derived** boolean (`tagger_mass != null`), not a stored title string.

### B.5 Python API (`mode="tagger"`)

```python
LinePlot(
    cache_id="tagger_spectrum",
    data=combined_spectrum_long,    # see schema note below
    mode="tagger",
    filters={"spectrum": "scan_id", "tag": "tag_id"},   # 'tag' carries TagData payload
    filter_defaults={"tagger_mass": None},
    interactivity={"tagger_mass": "peak_id"},
    x_column="MonoMass",            # level-0 x
    y_column="SumIntensity",        # level-0 y
    # tagger-specific column names (NEW, config-time):
    signal_peaks_column="SignalPeaks",      # list[mass][peak][idx,mz,int,charge]
    mz_column="MonoMass_Anno",              # level-1 x source (annotated m/z)
    mz_intensity_column="SumIntensity_Anno",
    tag_payload_key="tag",                  # which selection identifier holds TagData
    mass_match_tol=1e-5,                    # oracle tolerance
    title="Augmented Deconvolved Spectrum",
    x_label="Monoisotopic Mass",
    styling={"highlightColor": "#E4572E", "selectedColor": "#F3A712",
             "unhighlightedColor": "lightblue"},
)(key="tagger", state_manager=sm)
```

- Tagger column params + `mode` are **config-time** (cache-affecting → `_get_cache_config`).
- The two **levels' titles/axis labels** are *not* stored as mutable state (the oracle
  mutated `args.title`); instead Vue derives them from `tagger_mass`:
  `tagger_mass == null` ⇒ title `"Augmented Deconvolved Spectrum"`, x-label
  `"Monoisotopic Mass"`; else ⇒ `"Augmented Annotated Spectrum"`, x-label `"m/z"`
  (oracle 103–122). Provide overrides `title`/`title_level1`/`x_label`/`x_label_level1` in
  config for non-FLASH reuse.
- Data ingestion: because each scan is one row of *list* columns, `mode="tagger"` accepts the
  per-scan list-column frame and explodes it internally; `_preprocess` keeps it lazy and sorts
  by the `spectrum` filter column for predicate pushdown (matching base `_preprocess`
  behavior, lineplot.py 224–251). The list columns (`SignalPeaks`) survive caching as Arrow
  list-of-list-of-list.

`get_state_dependencies()` (tagger) → `["spectrum", "tag", "tagger_mass"]` (all three change
the emitted frames; override required because the base default returns only filter keys, and
`tagger_mass` is interactivity, not a filter — base.py 455–468 / mirrorplot precedent
get_state_dependencies).

### B.6 `_prepare_vue_data` additions (tagger branch)

Inputs: `state` carrying `spectrum`, `tag` (TagData dict), `tagger_mass` (int|None).

1. Filter `per_scan_data` to the selected `spectrum` row (existing filter path,
   `filter_and_collect_cached`, lineplot.py 304). One row.
2. Read `tag = state.get(tag_payload_key)`; extract `tag["masses"]`, `tag["sequence"]`,
   `tag["selectedAA"]`.
3. **Level-0 `plotData`**: explode `MonoMass`/`SumIntensity` to long; compute `peak_id = i`,
   `highlight` (mass within `mass_match_tol` of any `tag["masses"]`),
   `reversedSelectedAA = len(sequence) - 1 - selectedAA`, `selected` per gold rule,
   `mass_label`. Emit with column mappings `x_column`/`y_column`/`highlight_column=highlight`/
   `annotation_column=mass_label`/ interactivity `peak_id`. (Stale-`tagger_mass` guard: if
   `tagger_mass` not in the highlighted `peak_id` set, treat as `None`.)
4. **`plotDataTaggerSegments`**: adjacent highlighted-mass pairs → `{x_start,x_end,residue,
   delta,selected}` (Python loop, oracle 449–540 math).
5. **`plotDataTaggerCharges`** (only if `tagger_mass is not None`): for the selected mass index
   `m` (mapped from `tagger_mass` peak_id), take `SignalPeaks[m]`, explode to
   `{mz,intensity,charge,peak_id}`, group by charge to compute `cog` (oracle COG), attach
   `charge_label=f"z={charge}"`, `selected` gold rule.
6. `_hash` includes `spectrum`, the `tag` payload (hash of its masses+sequence+selectedAA),
   and `tagger_mass` so cache keys change with drill-down.

Return shape:
```python
{
  "plotData": df_level0_pandas,                 # sticks + highlight + mass labels
  "plotDataTaggerSegments": df_segments_pandas, # sequence arrows (level 0)
  "plotDataTaggerCharges": df_charges_pandas,   # m/z clusters (level 1; may be empty)
  "_hash": data_hash,
  "_plotConfig": { "mode": "tagger", "xColumn": ..., "yColumn": ...,
                   "highlightColumn": "highlight", "annotationColumn": "mass_label",
                   "interactivityColumns": {"peak_id": "peak_id"},
                   "level": ("annotated" if tagger_mass is not None else "deconvolved") },
}
```

### B.7 `_get_component_args` keys (tagger)

```python
{
  "componentType": "PlotlyLineplot",   # same dispatch; mode switches behavior in-component
  "mode": "tagger",
  "title": "Augmented Deconvolved Spectrum",
  "titleLevel1": "Augmented Annotated Spectrum",
  "xLabel": "Monoisotopic Mass",
  "xLabelLevel1": "m/z",
  "yLabel": "Intensity",
  "styling": {merged highlight/selected/unhighlighted + annotationColors},
  "interactivity": {"tagger_mass": "peak_id"},
  "xColumn": "MonoMass", "yColumn": "SumIntensity",
  "highlightColumn": "highlight", "annotationColumn": "mass_label",
  # tagger-specific:
  "taggerMassButtons": True,      # draw mass-button rects/labels above peaks (level 0)
  "taggerSegmentsKey": "plotDataTaggerSegments",
  "taggerChargesKey": "plotDataTaggerCharges",
  "xPosScalingFactor": 27.5,      # oracle level-1 scaling
  "config": self._plot_config,
  "height": ...,
}
```

### B.8 Vue plan (tagger): extend `PlotlyLineplot.vue` with a mode switch

Extend the existing `PlotlyLineplot.vue` (do **not** add a sibling) — level 0 is exactly the
current stick+highlight+annotation render, so we reuse all of it and add a thin tagger layer
gated by `args.mode === 'tagger'`. Rationale: maximal reuse of the already-ported stick logic;
the only additions are mass-button shapes, sequence-arrow annotations, the level-1 charge
view, and the back button.

Add to `PlotlyLineplot.vue`:
- `mode` from `args.mode` (default `'default'`).
- Computed `level`: `'annotated'` if the `tagger_mass` selection is set (read via
  `selectionStore.$state[<tagger_mass identifier>]` — generic), else `'deconvolved'`.
- Computed `title`/`xLabel`: when `mode==='tagger'`, pick `args.title/.xLabel` at level 0,
  `args.titleLevel1/.xLabelLevel1` at level 1 (replaces oracle 103–122).
- **Level 0 overlays** (`mode==='tagger'`, `taggerMassButtons`): reuse the existing
  `annotationShapes`/`peakAnnotations` (they already draw a rect+label per highlighted peak —
  this *is* the mass button) and additionally render `plotDataTaggerSegments` as Plotly
  annotations: two arrow annotations + a residue-letter annotation with hover
  `` `Δ=${delta.toFixed(2)} Da` `` per segment (port oracle 491–539; colors gold when
  `segment.selected`). Read segments from
  `streamlitDataStore.allDataForDrawing.plotDataTaggerSegments` (column-parsed).
- **Level 1 view** (`level==='annotated'`): instead of `plotData`, render
  `plotDataTaggerCharges` as sticks (`mz`/`intensity`), plus, per charge group, a rect+label
  `charge_label` at `cog` (port oracle 330–373, but `cog` is precomputed). x-range fits the
  cluster `[min(mz)*0.98, max(mz)*1.02]` (oracle 596–598). Gold vs orange via `selected`.
- **Back button**: re-add the oracle's round `↩` button (template line 3 + `.simple-button`
  style, oracle 815–838), visible only when `mode==='tagger' && level==='annotated'`; click
  → `selectionStore.updateSelection(<tagger_mass>, null)`.
- **Click**: extend existing `onPlotClick` — when `mode==='tagger'` and `level==='deconvolved'`,
  only react to clicks on a `highlight===true` peak (parity with Unified 1604–1611 “if
  (!highlightedMassPos[i]) break”), setting `tagger_mass=peak_id`. At level 1, clicks are
  inert (oracle has no level-2). Default mode keeps current behavior.
- **Zoom/y-headroom**: existing `xRange`/`yRange`/`onRelayout` already implement stick zoom
  with 1.8 headroom and x≥0 clamping (`PlotlyLineplot.vue` 239–279, 825–842) — matches oracle.
  Add the level-0 centroid-fit fallback for very wide tag spans (oracle 599–609) behind
  `mode==='tagger'`.

`App.vue` dispatch — **no change** (tagger reuses `PlotlyLineplot` / `PlotlyLineplotUnified`
cases, already mapped to `PlotlyLineplot`, App.vue 198–200).

`component.ts` — extend `LinePlotComponentArgs`:
```ts
export interface LinePlotComponentArgs extends BaseComponentArgs {
  componentType: 'PlotlyLineplotUnified' | 'PlotlyLineplot'
  mode?: 'default' | 'tagger'
  title: string
  titleLevel1?: string
  xLabel?: string
  xLabelLevel1?: string
  yLabel?: string
  styling?: LinePlotStyling
  config?: LinePlotConfig
  interactivity?: InteractivityMapping
  xColumn?: string
  yColumn?: string
  highlightColumn?: string
  annotationColumn?: string
  // tagger:
  taggerMassButtons?: boolean
  taggerSegmentsKey?: string
  taggerChargesKey?: string
  xPosScalingFactor?: number
  height?: number
}
```
Also add to `PlotData`/new interfaces:
```ts
export interface TaggerSegment { x_start: number; x_end: number; residue: string; delta: number; selected: boolean }
export interface TaggerChargePeak { mz: number; intensity: number; charge: number; cog: number; charge_label: string; selected: boolean; peak_id: number }
```
(`LinePlotConfig` already has `xPosScalingFactor`/`xPosScalingThreshold`/`showChargeLabels` —
reuse them; line 101–107.)

`selection.ts` — **no field change**. Document `tag` (TagData payload) and `tagger_mass`
(int|null) as conventional identifiers routed through the existing generic dynamic-key store.
Optionally add a doc-only `TaggerTagPayload` type in `component.ts`
(`{sequence:string; nTerminal:boolean; masses:number[]; selectedAA:number; startPos:number; endPos:number}`)
mirroring the oracle `TagData`.

### B.9 Tests (tagger)

`tests/test_lineplot_tagger.py` (mirror `test_mirrorplot_contract.py` structure):

Fixture `sample_tagger_data` in `conftest.py`: a one/two-row per-scan frame with list columns
`MonoMass`, `SumIntensity`, `SignalPeaks` (`[[ [idx,mz,int,charge], … ], …]`), `MonoMass_Anno`,
`SumIntensity_Anno`, `scan_id`, `tag_id`. A `TAG_PAYLOAD` dict
`{sequence, nTerminal, masses, selectedAA, startPos, endPos}`.

- `test_prepare_vue_data_returns_dict_with_hash`.
- `test_level0_highlights_tag_masses`: with `state={"spectrum":s,"tag":TAG_PAYLOAD}`,
  `plotData[highlight]` is True exactly for masses within `1e-5` of `TAG_PAYLOAD["masses"]`.
- `test_gold_selection_reversed_index`: the gold `selected` flags match
  `reversedSelectedAA == i || == i-1` for the configured `selectedAA` (asserts the reversed
  mapping `len-1-selectedAA`).
- `test_segments_residues_and_delta`: `plotDataTaggerSegments` residues equal
  `sequence[len-1-i]`; `delta == abs(x_start-x_end)`; one fewer row than highlighted masses.
- `test_level1_charges_only_when_mass_selected`: with `tagger_mass=None`,
  `plotDataTaggerCharges` is empty; with a valid `tagger_mass`, it contains the selected mass's
  raw peaks and `charge_label == f"z={charge}"`.
- `test_cog_intensity_weighted`: for a known charge group, `cog` equals
  `Σ(I/ΣI)*mz` (within float tol) — guards the COG port.
- `test_stale_tagger_mass_ignored`: a `tagger_mass` peak_id absent from the new highlighted
  set is treated as level 0 (reset parity).
- `test_state_dependencies`: `get_state_dependencies()` == `{"spectrum","tag","tagger_mass"}`.
- `test_component_args`: `mode=="tagger"`, `componentType=="PlotlyLineplot"`,
  `interactivity=={"tagger_mass":"peak_id"}`, `taggerMassButtons` True, scaling 27.5,
  titles/xlabels for both levels present.
- `test_cache_config_roundtrip`: `mode`, `signal_peaks_column`, `mz_column`,
  `mz_intensity_column`, `tag_payload_key`, `mass_match_tol` survive
  `_get_cache_config`/`_restore_cache_config`.
- `test_default_mode_unchanged`: `LinePlot(mode="default")` (and omitted `mode`) produces the
  current `plotData`-only payload with no tagger keys (regression guard).

`tests/integration/test_tagger_drilldown.py` (mirror `integration/test_cross_component_selection.py`):
- Simulate `updateSelection("tag", TAG_PAYLOAD)` then a peak click
  `updateSelection("tagger_mass", peak_id)`: assert the re-rendered payload now includes
  non-empty `plotDataTaggerCharges` and `_plotConfig.level == "annotated"`.
- Simulate back-button `updateSelection("tagger_mass", None)`: assert `plotDataTaggerCharges`
  empty and `_plotConfig.level == "deconvolved"`.
- Simulate scan change (`updateSelection("spectrum", other)`): assert `tagger_mass` reset
  (level back to deconvolved).

---

## File-by-file change list

Python — `openms_insight/components/lineplot.py`:
- Add `mode: str = "default"` + new ctor params: density (`group_column`, `target_value`,
  `decoy_value`, `kde_from`, `kde_points`) and tagger (`signal_peaks_column`, `mz_column`,
  `mz_intensity_column`, `tag_payload_key`, `mass_match_tol`, `title_level1`, `x_label_level1`).
  Store on `self._*`; pass through `super().__init__(**kwargs)` for subprocess recreation
  (mirror existing ctor pass-through, lineplot.py 121–141).
- `_get_cache_config` / `_restore_cache_config`: add all new fields (mirror lineplot.py
  143–176 and the mirrorplot roundtrip test contract).
- `_validate_mappings`: per-mode column existence checks (group/signal_peaks/mz columns).
- `_preprocess`: density normalization (passthrough tidy, or run `gaussian_kde` when
  `kde_from`); tagger keeps per-scan list columns lazy + sorts by `spectrum`.
- `_get_vue_component_name`: return `"PlotlyDensityPlot"` for density, else `"PlotlyLineplot"`
  (tagger reuses lineplot; default unchanged → still works via App.vue mapping).
- `_get_data_key`: `"plotData"` for all (density tidy + tagger level 0 both ride `plotData`).
- `get_state_dependencies`: override for tagger → `["spectrum","tag","tagger_mass"]`; density
  → `[]`.
- `_prepare_vue_data`: branch on `self._mode` (density §A.4, tagger §B.6, default = current).
- `_get_component_args`: branch on mode (density §A.5, tagger §B.7, default = current).
- `_build_plot_config`: include `mode` (+ `level`, `groupColumn`/`targetValue`/`decoyValue` for
  density).
- Keep `set_dynamic_annotations`/`from_sequence_view` working for default mode (no behavior
  change).

Vue:
- `js-component/src/components/plotly/PlotlyLineplot.vue` — extend with `mode`/`level`,
  tagger mass-buttons (reuse `annotationShapes`/`peakAnnotations`), sequence-arrow rendering
  from `plotDataTaggerSegments`, level-1 charge view from `plotDataTaggerCharges`, back button,
  tagger click gating (§B.8). Default mode path untouched.
- `js-component/src/components/plotly/PlotlyDensityPlot.vue` — **new** sibling: two-series KDE
  curves (green/red), legend on, themed FDR layout, SVG export, no interactivity (§A.6).
- `js-component/src/App.vue` — import `PlotlyDensityPlot`, register in `components`, add
  `case 'PlotlyDensityPlot': return PlotlyDensityPlot` (§A.6). No tagger dispatch change.
- `js-component/src/types/component.ts` — extend `LinePlotComponentArgs` (mode + tagger keys),
  add `DensityPlotComponentArgs` to the `ComponentArgs` union, add `TaggerSegment` /
  `TaggerChargePeak` / optional `TaggerTagPayload` (§A.6, §B.8).
- `js-component/src/stores/selection.ts` — **no field change**; the generic dynamic-key store
  already carries `tag` (object) and `tagger_mass` (int|null). Add only a clarifying doc
  comment naming these conventional identifiers (§B.4).

Tests:
- `tests/conftest.py` — add fixtures `sample_density_data`, `sample_density_scores`,
  `sample_tagger_data`, `TAG_PAYLOAD`.
- `tests/test_lineplot_density.py` — §A.7.
- `tests/test_lineplot_tagger.py` — §B.9.
- `tests/integration/test_tagger_drilldown.py` — §B.9 integration.
- Extend `tests/test_prepare_vue_data_contract.py` parametrization with the two new modes
  (each returns dict + str `_hash`).

Parity gate (existing harness): `python -m pytest -q`, `npm run build`
(`js-component`), `python migration/parity_diff.py` — all must stay green; the COG /
reversed-index / `1e-5` tolerance / KDE-points(200) constants are the diffed invariants.
