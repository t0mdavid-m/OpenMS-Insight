# Spec: `Plot3D` — OpenMS-Insight 3D scatter component (precursor S/N parity)

Unit id: `plot3d` (see `migration/units.yaml`).
Oracle (read-only, never edited): `/home/user/openms-streamlit-vue-component/src/components/plotly/3Dplot/Plotly3Dplot.vue`.
FLASHApp data-flow oracle: `/home/user/FLASHApp/src/render/{initialize,update,components}.py`, `/home/user/FLASHApp/src/parse/{deconv,masstable}.py`.

Goal: a new, **generic** Insight component `Plot3D` (Plotly `scatter3d`) that reproduces FLASHApp's
"3D S/N plot" (the *Precursor Signals* view) while fitting Insight's tidy-long, cache-first,
`cache_id`-based contract. Parity with the oracle is non-negotiable.

---

## 1. Behaviors to preserve from the oracle

### 1.1 What the oracle draws

The oracle renders **two `scatter3d` traces** ("Signal" and "Noise") from per-scan nested peak
arrays. The geometry per point is computed in `get3DplotInputFromSNRPeaks` (oracle lines 224–240):

```js
get3DplotInputFromSNRPeaks(peaks, is_signal) {
  let xs = [], ys = [], zs = []
  for (let i = 0, len = peaks.length; i < len; i++) {
    const z = peaks[i][2]          // intensity
    if (z <= 0) continue           // drop non-positive intensity
    zs.push(-100000, z, -100000)   // stem: baseline -> peak -> baseline
    const x = peaks[i][1] * peaks[i][3]   // mass = m/z * charge
    xs.push(x, x, x)
    const y = peaks[i][3]          // charge
    ys.push(y, y, y)
  }
  ...
}
```

The inner peak tuple layout `peaks[i]` is fixed by the FLASHApp parser
(`/home/user/FLASHApp/src/parse/masstable.py:252`):
`rec = (peak_index, mz, intensity, charge)` → indices **0=peak_index, 1=mz, 2=intensity, 3=charge**.

So the **axis meaning is** (must be preserved exactly):

| Plotly axis | Oracle formula           | Meaning      | Axis title |
|-------------|--------------------------|--------------|------------|
| **x**       | `mz * charge`            | neutral mass | `"Mass"`   |
| **y**       | `charge`                 | charge state | `"Charge"` |
| **z**       | `intensity`              | intensity    | `"Intensity"` |

**Stem rendering (load-bearing).** Each peak becomes a vertical line via three coordinate triplets:
`mode: 'lines'`, with `z = [-100000, intensity, -100000]` and `x`,`y` repeated 3×. This draws a
"drop line" from a large negative baseline up to the peak and back. The huge negative baseline is
clipped off-view by the z-axis range (`[0, maximumIntensity]`), so visually each peak is a stick
rising from `z=0`. **This stem-triplet construction must be reproduced** (it is the visual identity
of the plot — a 3D stick plot, not a marker cloud).

> Oracle TODO comment (line 167) notes markers are not yet drawn. We treat `lines` as the parity
> default `mode`, and expose `mode` to additionally allow `markers` / `lines+markers` (see §2.4).

### 1.2 Color / series grouping

Two fixed series, distinguished by trace `name` and `line.color` (oracle lines 101–124):

- `"Signal"` → `#3366CC` (blue)
- `"Noise"`  → `#DC3912` (red)

In tidy-long form (§2.5) this is a categorical **series column** (`series_column`, values `"Signal"`/`"Noise"`).
`Plot3D` must map series → color via a `series_colors` config defaulting to
`{"Signal": "#3366CC", "Noise": "#DC3912"}`, one trace per distinct series value, `showlegend: true`.

### 1.3 Filtering of points

- Drop any point with `intensity <= 0` (oracle line 230). Reproduce as a preprocessing filter on the
  z column.

### 1.4 Title

Oracle title (lines 39–42, 128): `<b>Precursor signals</b>` when a scan is selected and no mass is
selected; `<b>Mass signals</b>` when a mass is also selected. FLASHApp constructs the component as
`Plotly3Dplot(title="Precursor Signals")` (`initialize.py:152`, `components.py:80`). For `Plot3D`,
expose `title` config (default `None`); the parity recipe passes `title="Precursor Signals"`.
(The dynamic "Precursor signals"/"Mass signals" switch is an artifact of the oracle's two data
sources; under Insight the row source is chosen by `filters` upstream — see §1.7 — so the title is
just a config string.)

### 1.5 Scene / camera defaults (must match)

From oracle `layout()` (lines 126–147):

```js
scene: {
  xaxis: { title: 'Mass' },
  yaxis: { title: 'Charge', dtick: 1, tick0: 0 },   // integer charge ticks
  zaxis: { title: 'Intensity', range: [0, maximumIntensity] },
  camera: { eye: { x: 2.5, y: 0, z: 0.2 } },          // initial mass–intensity plane view
},
showlegend: true,
height: 800,
```

Preserve all of:
- y-axis integer ticks: `dtick: 1, tick0: 0`.
- z-axis lower bound pinned to 0; upper bound = **max z over all displayed points** (Signal ∪ Noise),
  computed client-side (`updateMaximumIntensity`, lines 161–165). This clips the `-100000` stem
  baselines so sticks visually start at 0.
- camera eye `{x: 2.5, y: 0, z: 0.2}` (the characteristic "looking down the charge axis" framing).
- default height 800 (oracle hard-codes 800; Insight's `__call__(height=...)` may override, but the
  component default is 800, **not** Insight's global 400 default).

### 1.6 No log scaling

The oracle applies **no** log transform on any axis — mass, charge, intensity are all linear.
`Plot3D` must default to linear on all three axes. (Optional `log_z` config may be offered but
defaults `False` for parity.)

### 1.7 Selection / cross-link behavior

The oracle is **selection-driven input**, not selection-emitting: it *reads* `selectedScanIndex` /
`selectedMassIndex` from the selection store and redraws; it does **not** emit a selection on click
(no `plotly_click` handler exists in the oracle). The "which scan / which mass" decision and the
index→value resolution live in FLASHApp's `update.py` (the authoritative selection oracle,
lines 135–147):

```python
elif component == 'Precursor Signals':
    scan_index = selection_store.get("scanIndex")
    mass_index = selection_store.get("massIndex")
    if scan_index is None:
        # empty frame when nothing selected
        data['per_scan_data'] = ...filter(index == -1).slice(0, 0)
    else:
        filtered_table = ...filter(index == scan_index)
        if mass_index is not None:
            # narrow nested peak arrays to the chosen mass row
            df['SignalPeaks'] = df['SignalPeaks'].apply(lambda peaks: peaks[mass_index] ...)
            df['NoisyPeaks']  = df['NoisyPeaks'].apply(lambda peaks: peaks[mass_index] ...)
```

**Insight mapping of this behavior:** the scan/mass narrowing becomes Insight **`filters`**. Because
Insight is tidy-long (one row per point, §2.5), the nested `peaks[mass_index]` narrowing is just a
filter on `mass_index` (and `scan` is a filter too). So:

- `filters={'spectrum': 'scan', 'mass': 'mass_index'}` (identifiers chosen by the page; values come
  from the upstream Table's `interactivity`).
- `filter_defaults={'spectrum': -1}` reproduces "empty when no scan selected" (no row has
  `scan == -1`, so the frame is empty — matching `update.py`'s `index == -1` empty slice).
- The "mass selected ⇒ show only that mass" path is automatic: when the `mass` filter is unset the
  component shows **all** masses of the scan (parity with the precursor view, which iterates all
  masses); when set it shows the one mass.

`Plot3D` itself supports **optional outgoing interactivity** via the standard Insight
`interactivity` mapping (so a clicked stick can drive other components), but this is **off by default**
to match the oracle (which emits nothing). When `interactivity` is provided, a `plotly_click`
handler routes the clicked point's `customdata` value to `selectionStore.updateSelection(identifier,
value)` exactly like `PlotlyMirrorPlot.vue` (lines 521–536) and `PlotlyLineplot.vue` (lines 811,
978–981). Parity default = no `interactivity` ⇒ no click handler attached.

---

## 2. Python API

New file: `openms_insight/components/plot3d.py`. Mirror `volcanoplot.py` / `heatmap.py` structure
end-to-end. Registered name `"plot3d"`; export `Plot3D` from `openms_insight/__init__.py`.

### 2.1 Class & type

```python
@register_component("plot3d")
class Plot3D(BaseComponent):
    _component_type: str = "plot3d"
```

`_get_vue_component_name()` → `"Plotly3D"` (Vue dispatch string; see §4).
`_get_data_key()` → `"plot3dData"`.

### 2.2 Constructor signature

```python
def __init__(
    self,
    cache_id: str,
    x_column: str = "mass",
    y_column: str = "charge",
    z_column: str = "intensity",
    data: Optional[pl.LazyFrame] = None,
    data_path: Optional[str] = None,
    series_column: Optional[str] = None,        # categorical -> per-series trace+color
    filters: Optional[Dict[str, str]] = None,
    filter_defaults: Optional[Dict[str, Any]] = None,
    interactivity: Optional[Dict[str, str]] = None,
    cache_path: str = ".",
    regenerate_cache: bool = False,
    mode: str = "lines",                        # render-time-overridable; "lines"|"markers"|"lines+markers"
    title: Optional[str] = None,
    x_label: Optional[str] = None,              # default "Mass"
    y_label: Optional[str] = None,              # default "Charge"
    z_label: Optional[str] = None,              # default "Intensity"
    series_colors: Optional[Dict[str, str]] = None,  # default {"Signal":"#3366CC","Noise":"#DC3912"}
    drop_nonpositive_z: bool = True,            # oracle: drop intensity <= 0
    stem: bool = True,                          # oracle stem-triplet rendering (z baseline)
    stem_baseline: float = -100000.0,           # oracle magic baseline
    y_dtick: float = 1.0,                       # integer charge ticks
    y_tick0: float = 0.0,
    camera_eye: Optional[Dict[str, float]] = None,   # default {"x":2.5,"y":0,"z":0.2}
    log_z: bool = False,                        # parity = linear
    hover_columns: Optional[List[str]] = None,  # extra tidy columns surfaced on hover
    **kwargs,
):
```

### 2.3 Config (cache-invalidating) vs render-time (`__call__`)

**Config — affects cache (goes into `_get_cache_config()`):** everything that changes the cached
preprocessed parquet or the structural meaning of the data:

`x_column, y_column, z_column, series_column, drop_nonpositive_z, log_z, hover_columns`,
plus `filters`/`interactivity` (handled by the base class).

> Rationale: these determine which rows/columns are written to cache and the per-point geometry.
> `drop_nonpositive_z` and `log_z` change the cached point set / transformed values, so they are
> config. Mirrors how Heatmap puts `log_scale`, `intensity_column` in `_get_cache_config()`.

**Also stored in cache config but purely presentational** (so reconstruction-from-cache restores the
full look without re-passing kwargs — same approach VolcanoPlot uses for its colors/labels):
`title, x_label, y_label, z_label, series_colors, stem, stem_baseline, y_dtick, y_tick0, camera_eye`.
These do not change the *data*, but storing them keeps reconstruction mode faithful (base class
forbids passing config without data in reconstruction mode — see `base.py:115–129`).

**Render-time — passed to `__call__`, NOT cache-invalidating** (mirrors VolcanoPlot's
`fc_threshold`/`p_threshold`):

- `mode` — `"lines"|"markers"|"lines+markers"`. Lets a user flip between sticks and a marker cloud
  with no cache rebuild (directly addresses the oracle's "add markers" TODO). Stored in
  `self._current_mode`, surfaced via `_get_component_args()`.
- `height` — standard base-class render arg (default 800 for this component).

`__call__` signature:

```python
def __call__(self, key=None, state_manager=None, height=None, mode=None) -> Any:
    if mode is not None:
        self._current_mode = mode
    if height is None:
        height = 800                      # component default differs from base 400
    return super().__call__(key=key, state_manager=state_manager, height=height)
```

`_restore_cache_config()` must restore every config field above with the documented defaults
(pattern copied verbatim from `volcanoplot.py:182–194` / `heatmap.py:243–266`).

`_validate_columns(schema)` (called from `_preprocess`): assert `x_column, y_column, z_column`
present; if `series_column`/`hover_columns` given, assert present. Same error style as
`volcanoplot.py:139–155`.

### 2.4 `mode` semantics

- `"lines"` + `stem=True` (default, parity): emit stem triplets (baseline→peak→baseline) per point,
  Plotly trace `mode:'lines'`. Exact oracle behavior.
- `"markers"`: one marker per point at `(x, y, z)`, no stem triplets.
- `"lines+markers"`: stems **and** a marker at the peak.

The triplet expansion can be done **client-side** in Vue (preferred — keeps the cached frame small,
one row per real point, and lets `mode` be a no-rebuild render-time switch). Python sends one tidy
row per point; Vue builds triplets when `stem` is on. This matches how `PlotlyLineplot.vue` expands
raw x/y into stick triplets at render time.

### 2.5 Tidy long-format input schema (THE flattening)

This is the central adaptation. FLASHApp stores **nested** per-scan arrays
(`/home/user/FLASHApp/src/parse/masstable.py:32–33`):

```python
('SignalPeaks', pa.list_(pa.list_(pa.list_(pa.float64())))),   # [mass_index][peak_index][field]
('NoisyPeaks',  pa.list_(pa.list_(pa.list_(pa.float64())))),
```

i.e. `SignalPeaks[mass_index][peak_index] = (peak_index, mz, intensity, charge)`, and the
`threedim_SN_plot` table is `(index, PrecursorScan, SignalPeaks, NoisyPeaks)`
(`/home/user/FLASHApp/src/parse/deconv.py:189–199`). The FLASHQuant recipe analog stores
comma-split `MZs`/`RTs`/`Intensities` strings per feature (see `units.yaml` `quant-recipe`).

**`Plot3D` consumes a flattened, tidy LazyFrame: ONE ROW PER PLOTTED POINT.** The page-side adapter
(not part of this component; lives in FLASHApp's Phase-3 render layer / a documented recipe) must
explode the nested arrays / comma-split strings into rows. Required + optional columns:

| column                | dtype     | required | source / formula |
|-----------------------|-----------|----------|------------------|
| `mass` (`x_column`)   | float     | yes      | `mz * charge` = `peaks[i][1] * peaks[i][3]` |
| `charge` (`y_column`) | int/float | yes      | `peaks[i][3]` |
| `intensity` (`z_column`) | float  | yes      | `peaks[i][2]` |
| `series` (`series_column`) | str  | optional | `"Signal"` for SignalPeaks rows, `"Noise"` for NoisyPeaks rows |
| `scan`                | int       | (filter) | `index` from `threedim_SN_plot` (drives `filters={'spectrum':'scan'}`) |
| `mass_index`          | int       | (filter) | outer index of nested array (drives `filters={'mass':'mass_index'}`) |
| `peak_index`          | int       | optional | `peaks[i][0]` (hover / interactivity key) |
| `mz`                  | float     | optional | `peaks[i][1]` (hover) |

**Canonical flattening (reference pseudocode the recipe must implement; preserves oracle math):**

```python
rows = []
for scan, sig, noisy in threedim_SN_plot.iter_rows("index","SignalPeaks","NoisyPeaks"):
    for series, cells in (("Signal", sig), ("Noise", noisy)):
        for mass_index, peaks in enumerate(cells):
            for (peak_index, mz, intensity, charge) in peaks:
                if intensity <= 0:        # oracle drop (also enforced by drop_nonpositive_z)
                    continue
                rows.append(dict(scan=scan, mass_index=mass_index, series=series,
                                 peak_index=peak_index, mz=mz,
                                 mass=mz*charge, charge=charge, intensity=intensity))
```

Notes:
- The exact key identity `mass = mz * charge`, `y = charge`, `z = intensity` is copied from the
  oracle and **must not be altered**.
- For the FLASHQuant `quant-recipe`, the same shape is produced by splitting the comma-separated
  `MZs`/`RTs`/`Intensities` strings into one row per `(feature, point)` (x/y/z chosen per that recipe;
  tracked separately as unit `quant-recipe`). `Plot3D` is agnostic to the upstream source — it only
  requires the tidy schema above.

### 2.6 `_preprocess`

```python
def _preprocess(self):
    if self._raw_data is None: raise ValueError("No data provided and no cache exists")
    self._validate_columns(self._raw_data.collect_schema())
    cols = [self._x_column, self._y_column, self._z_column]
    if self._series_column: cols.append(self._series_column)
    cols += list((self._interactivity or {}).values())
    cols += list((self._filters or {}).values())
    cols += (self._hover_columns or [])
    cols = list(dict.fromkeys(cols))                      # de-dup, preserve order
    lf = self._raw_data.select([c for c in cols if c in self._raw_data.collect_schema().names()])
    if self._drop_nonpositive_z:
        lf = lf.filter(pl.col(self._z_column) > 0)        # oracle: z <= 0 dropped
    if self._log_z:
        lf = lf.with_columns(pl.col(self._z_column).log(10).alias(self._z_column))
    self._preprocessed_data = {"plot3dData": lf.collect()}
```

(No downsampling/levels — these point sets are per-scan and small, unlike Heatmap. Keep it as simple
as VolcanoPlot's `_preprocess`.)

---

## 3. `_prepare_vue_data` and `_get_component_args`

### 3.1 `_prepare_vue_data(state)` output shape

Returns a dict keyed by the data key plus `_hash` (contract: must be `dict` with `str` `_hash` —
`tests/test_prepare_vue_data_contract.py`). Payload value is a **pandas DataFrame** (Arrow transfer),
one row per point, columns = the tidy columns selected above. Filtering by scan/mass is applied here
exactly like VolcanoPlot (`build_scatter_columns` + `filter_and_collect_cached`):

```python
def _prepare_vue_data(self, state):
    if not self._preprocessed_data: self._load_from_cache()
    data = self._preprocessed_data["plot3dData"]
    df = data.collect() if isinstance(data, pl.LazyFrame) else data
    columns = [self._x_column, self._y_column, self._z_column]
    if self._series_column: columns.append(self._series_column)
    for c in (self._hover_columns or []): columns.append(c)
    # interactivity + filter columns, de-duped (reuse build_scatter_columns-style logic)
    columns = list(dict.fromkeys(columns
                   + list((self._interactivity or {}).values())
                   + list((self._filters or {}).values())))
    if self._filters:
        df_pandas, data_hash = filter_and_collect_cached(
            df.lazy(), self._filters, state,
            columns=columns, filter_defaults=self._filter_defaults)
    else:
        avail = [c for c in columns if c in df.columns]
        sub = df.select(avail)
        data_hash = compute_dataframe_hash(sub)
        df_pandas = sub.to_pandas()
    return {"plot3dData": df_pandas, "_hash": data_hash}
```

Shape contract (for the test in §5):
- result is `dict`; `result["_hash"]` is `str`.
- `result["plot3dData"]` is a `pandas.DataFrame`.
- its columns ⊇ `{x_column, y_column, z_column}` and, if set, `series_column` and each `hover_column`.
- every row has `z_column > 0` when `drop_nonpositive_z` (since preprocessing dropped them).
- when `filter_defaults={'spectrum': -1}` and no `spectrum` in state → 0 rows (empty-frame parity).

### 3.2 `_get_component_args()` keys

Must include `componentType` (contract: `tests/test_component_args_contract.py`). camelCase keys to
match existing components:

```python
{
  "componentType": "Plotly3D",
  "xColumn": self._x_column,
  "yColumn": self._y_column,
  "zColumn": self._z_column,
  "seriesColumn": self._series_column,        # may be None
  "seriesColors": self._series_colors,        # {"Signal":"#3366CC","Noise":"#DC3912"}
  "mode": self._current_mode,                 # render-time
  "stem": self._stem,
  "stemBaseline": self._stem_baseline,
  "title": self._title,                       # omit/None ok
  "xLabel": self._x_label or "Mass",
  "yLabel": self._y_label or "Charge",
  "zLabel": self._z_label or "Intensity",
  "yDtick": self._y_dtick,                     # 1
  "yTick0": self._y_tick0,                     # 0
  "cameraEye": self._camera_eye or {"x":2.5,"y":0,"z":0.2},
  "logZ": self._log_z,
  "hoverColumns": self._hover_columns or [],
  "interactivity": self._interactivity or {},
  "height": 800,                               # component default
}
```

---

## 4. Vue plan

### 4.1 New file

`js-component/src/components/plotly/plot3d/Plotly3D.vue`
(new `plot3d/` subdir under `js-component/src/components/plotly/`, mirroring oracle's `3Dplot/` layout
and Insight's existing flat plotly components). Model structure on `PlotlyVolcano.vue`
(props `{args, index}`, `setup()` pulling `useStreamlitDataStore` + `useSelectionStore`, `computed`
`plotData`/`layout`, `renderPlot()` via `Plotly.newPlot`, ResizeObserver + frame-height update).

**`plotData` (computed):** read the tidy frame from `streamlitDataStore.allDataForDrawing.plot3dData`
(rows). Group rows by `args.seriesColumn` (if set; else single series `"Signal"`). For each group,
build one Plotly `scatter3d` trace:

- `x = mass`, `y = charge`, `z = intensity` from `args.xColumn/yColumn/zColumn`.
- If `args.stem` and `args.mode` includes `"lines"`: expand each point to the triplet
  `z:[stemBaseline, z, stemBaseline]`, `x:[x,x,x]`, `y:[y,y,y]` — **reproducing oracle
  `get3DplotInputFromSNRPeaks`** (and break the line between points with `null` separators or use
  per-point sub-traces, as the oracle pushes all triplets into one contiguous array — replicate the
  contiguous-array behavior for visual identity).
- `type:'scatter3d'`, `mode: args.mode` (default `'lines'`), `name: <series value>`,
  `line.color = args.seriesColors[series]` (Signal `#3366CC` / Noise `#DC3912`),
  and for markers `marker.color = same`.
- `customdata`: per-point interactivity column values (for click routing, §4.4).
- hover: build `hovertemplate`/`text` from `args.zLabel`, `xLabel`, `yLabel`, plus `args.hoverColumns`.

**`layout` (computed):** reproduce oracle scene exactly:

```js
{
  title: args.title ? `<b>${args.title}</b>` : undefined,
  height: args.height ?? 800,
  paper_bgcolor: theme?.backgroundColor,
  plot_bgcolor: theme?.secondaryBackgroundColor,
  font: { color: theme?.textColor, family: theme?.font },
  scene: {
    xaxis: { title: args.xLabel ?? 'Mass' },
    yaxis: { title: args.yLabel ?? 'Charge', dtick: args.yDtick ?? 1, tick0: args.yTick0 ?? 0 },
    zaxis: { title: args.zLabel ?? 'Intensity', range: [0, maxIntensity] },
    camera: { eye: args.cameraEye ?? { x: 2.5, y: 0, z: 0.2 } },
  },
  showlegend: true,
}
```

`maxIntensity` = max z over all displayed points (Signal ∪ Noise), computed in the component exactly
like oracle `updateMaximumIntensity` (lines 161–165). Pins z range `[0, maxIntensity]` so stems clip
at 0.

**Mode bar:** keep oracle's custom SVG download button (lines 168–185), filename
`'FLASHViewer-3d-plot'`, remove `toImage`/`sendDataToCloud`. (Optional but recommended for parity.)

Re-render on `args.mode` change (render-time switch) and on `allDataForDrawing.plot3dData` change —
mirror the `watch` blocks in `PlotlyVolcano.vue` (lines 381–425).

### 4.2 App.vue dispatch

Add import + registration + switch case in `js-component/src/App.vue`:

- import: `import Plotly3D from './components/plotly/plot3d/Plotly3D.vue'`
- register in `components: { ... Plotly3D }`
- in `currentComponent()` switch add: `case 'Plotly3D': return Plotly3D`

(Dispatch string `'Plotly3D'` == `_get_vue_component_name()` == `componentType` in args.)

### 4.3 component.ts typed args

Add to `js-component/src/types/component.ts`:

```ts
export interface Plot3DComponentArgs extends BaseComponentArgs {
  componentType: 'Plotly3D'
  xColumn: string
  yColumn: string
  zColumn: string
  seriesColumn?: string
  seriesColors?: Record<string, string>
  mode?: 'lines' | 'markers' | 'lines+markers'
  stem?: boolean
  stemBaseline?: number
  title?: string
  xLabel?: string
  yLabel?: string
  zLabel?: string
  yDtick?: number
  yTick0?: number
  cameraEye?: { x: number; y: number; z: number }
  logZ?: boolean
  hoverColumns?: string[]
  interactivity?: InteractivityMapping
  height?: number
}

// add to the ComponentArgs union:
export type ComponentArgs =
  | TableComponentArgs
  | LinePlotComponentArgs
  | HeatmapComponentArgs
  | SequenceViewComponentArgs
  | VolcanoPlotComponentArgs
  | MirrorPlotComponentArgs
  | Plot3DComponentArgs            // <-- new

// Optional tidy data alias (parallels HeatmapData / VolcanoData):
export type Plot3DData = Record<string, unknown>
```

### 4.4 Selection routing through stores/selection.ts

Default (parity) = no `interactivity` ⇒ **no** click handler (oracle emits nothing). When
`args.interactivity` is non-empty, attach a `plotly_click` handler in `renderPlot()` that, for the
clicked point, reads the per-point `customdata` (the interactivity column value packed in `plotData`)
and for each `[identifier, column]` calls:

```ts
this.selectionStore.updateSelection(identifier, value)
```

This is the **generic value-based** store API (`stores/selection.ts` `updateSelection(identifier,
value)` → patches `state[identifier]`, bumps counters; App.vue debounces and posts to Streamlit).
Copy the exact handler shape from `PlotlyMirrorPlot.vue` (lines 521–536):
`plotEl.removeAllListeners?.('plotly_click'); plotEl.on('plotly_click', e => { const pt = e.points[0]; ...updateSelection... })`.
No store changes are required — `selection.ts` already supports arbitrary identifiers.

### 4.5 Old-component-name compatibility (note, not a code change here)

FLASHApp's render layer currently emits `componentName == "Plotly3Dplot"` (`components.py:80`,
`initialize.py:152`). That is the **oracle/legacy** path and is *not* edited. The Insight component
uses dispatch string `"Plotly3D"`. The Phase-3 FLASHApp rebuild (separate unit) is responsible for
switching the page to construct `openms_insight.Plot3D(...)` with the tidy adapter; this spec does not
touch FLASHApp.

---

## 5. Tests to add

Add `tests/test_plot3d.py` and extend the two contract suites. Use a `sample_plot3d_data` fixture in
`tests/conftest.py` (tidy long: columns `mass, charge, intensity, series, scan, mass_index`; include
at least one `intensity <= 0` row to exercise the drop, ≥2 `series` values, ≥2 `scan` values).

1. **Component-args contract** — add `Plot3D` to the parametrize list in
   `tests/test_component_args_contract.py`:
   `(Plot3D, "sample_plot3d_data", {"x_column":"mass","y_column":"charge","z_column":"intensity"})`.
   Asserts `componentType` present, str, non-empty (will be `"Plotly3D"`).

2. **`_prepare_vue_data` contract** — add the same tuple to
   `tests/test_prepare_vue_data_contract.py`. Asserts dict + `str` `_hash`.

3. **`tests/test_plot3d.py` (new), mirroring `test_volcanoplot.py`:**
   - `test_init_with_lazyframe`: attrs `_x_column/_y_column/_z_column` set; default series colors.
   - `test_init_missing_column`: `pytest.raises(ValueError, match="not found"|"Missing required")`
     when a required column is absent (and/or via bad `filters` mapping like the volcano test).
   - `test_drop_nonpositive_z`: after preprocessing, `plot3dData` has **no** row with `intensity<=0`;
     row count == count of positive-intensity input rows.
   - `test_prepare_vue_data_shape`:
     - `result["plot3dData"]` is a `pandas.DataFrame`;
     - its columns ⊇ `{"mass","charge","intensity"}` (+ `series` when `series_column="series"`);
     - `result["_hash"]` is a non-empty `str`.
   - `test_filter_empty_when_no_selection`: with `filters={'spectrum':'scan'}`,
     `filter_defaults={'spectrum':-1}`, calling `_prepare_vue_data({})` yields **0 rows**
     (empty-frame parity with `update.py`).
   - `test_filter_selects_scan`: `_prepare_vue_data({'spectrum': <scan>})` returns only that scan's
     rows.
   - `test_component_args_keys`: `_get_component_args()` contains
     `componentType=="Plotly3D", xColumn, yColumn, zColumn, seriesColors, cameraEye=={"x":2.5,"y":0,"z":0.2}, yDtick==1, yTick0==0`.
   - `test_mode_is_render_time`: `mode` is **not** in `_get_cache_config()` (so changing it does not
     invalidate cache); after `plot3d(mode="markers")` (or setting `_current_mode`),
     `_get_component_args()["mode"] == "markers"`. (Parallels VolcanoPlot threshold render-time test.)
   - `test_cache_reconstruction`: build with data, then reconstruct with only `cache_id`+`cache_path`;
     `_get_component_args()` restores labels/colors/camera (exercises `_restore_cache_config`).

---

## 6. Concrete file-by-file change list

**New files**

| Path | What |
|------|------|
| `openms_insight/components/plot3d.py` | New `Plot3D(BaseComponent)` per §2–§3: `@register_component("plot3d")`, ctor (§2.2), `_validate_columns`, `_get_cache_config`/`_restore_cache_config`, `_preprocess`, `_get_vue_component_name`→`"Plotly3D"`, `_get_data_key`→`"plot3dData"`, `_prepare_vue_data`, `_get_component_args`, `__call__(mode=..., height default 800)`. |
| `js-component/src/components/plotly/plot3d/Plotly3D.vue` | New Vue `scatter3d` component per §4.1: tidy-frame `plotData` (per-series traces, stem triplets reproducing oracle geometry), oracle scene/camera/z-range/`maxIntensity` layout, optional `plotly_click`→`updateSelection`, custom SVG export button. |
| `tests/test_plot3d.py` | New test module per §5(3). |

**Edited files**

| Path | What |
|------|------|
| `openms_insight/__init__.py` | `from .components.plot3d import Plot3D`; add `"Plot3D"` to `__all__` (next to `Heatmap`/`VolcanoPlot`, lines 8–13, 22+). |
| `js-component/src/App.vue` | Import `Plotly3D`; add to `components: {}`; add `case 'Plotly3D': return Plotly3D` in `currentComponent()` switch. |
| `js-component/src/types/component.ts` | Add `Plot3DComponentArgs` interface; add it to the `ComponentArgs` union; optional `Plot3DData` alias (§4.3). |
| `tests/test_component_args_contract.py` | Import `Plot3D`; add parametrize tuple `(Plot3D, "sample_plot3d_data", {...})`. |
| `tests/test_prepare_vue_data_contract.py` | Import `Plot3D`; add the same parametrize tuple. |
| `tests/conftest.py` | Add `sample_plot3d_data` fixture (tidy long; one `intensity<=0` row; ≥2 series; ≥2 scans). |

**Explicitly NOT changed** (oracle / out of scope): `/home/user/openms-streamlit-vue-component/**`
(the `Plotly3Dplot.vue` oracle) and all of `/home/user/FLASHApp/**` (its render/parse layer is the
behavioral oracle; the Phase-3 page rebuild that swaps in `Plot3D` + the tidy adapter is a separate
unit — `quant-recipe` / FLASHApp/migration).

---

## 7. Parity checklist (acceptance)

- [ ] x = `mz*charge` (mass), y = `charge` (int ticks `dtick:1,tick0:0`), z = `intensity`. (oracle 232–235, 138–139)
- [ ] Two default series Signal `#3366CC` / Noise `#DC3912`; one `scatter3d` trace each; `showlegend:true`. (oracle 101–124, 145)
- [ ] Default `mode:'lines'` stem rendering with baseline `-100000` triplets; z range `[0, maxIntensity]` clips stems at 0. (oracle 224–240, 99/139, 161–165)
- [ ] Drop points with `intensity <= 0`. (oracle 230)
- [ ] Camera eye `{x:2.5,y:0,z:0.2}`; default height 800. (oracle 140–143, 131)
- [ ] No log scaling on any axis by default. (oracle — none present)
- [ ] Empty frame when no scan selected via `filter_defaults`; mass narrowing via `mass_index` filter. (update.py 135–147)
- [ ] No outgoing selection by default; optional `interactivity`→`updateSelection` when configured. (oracle emits none; mirror MirrorPlot/Lineplot)
- [ ] `mode` is render-time (no cache invalidation); `x/y/z/series/drop_nonpositive_z/log_z` are config.
- [ ] Tidy long input = one row per point (nested arrays / comma-split values flattened upstream).
