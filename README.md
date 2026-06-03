# OpenMS-Insight

[![PyPI version](https://badge.fury.io/py/openms-insight.svg)](https://badge.fury.io/py/openms-insight)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![Tests](https://github.com/t0mdavid-m/OpenMS-Insight/actions/workflows/tests.yml/badge.svg)](https://github.com/t0mdavid-m/OpenMS-Insight/actions/workflows/tests.yml)

Interactive visualization components for mass spectrometry data in Streamlit, backed by Vue.js.

## Features

- **Cross-component selection linking** via shared identifiers
- **Memory-efficient preprocessing** via subprocess isolation
- **Automatic disk caching** with config-based invalidation
- **Cache reconstruction** - components can be restored from cache without re-specifying configuration
- **Render-time presentation** - titles/labels/colors are passed at render time and do **not** rebuild the cache

The public surface is **seven visualization components** plus a `StateManager`
for cross-component state:

| Component | Backend | Purpose |
|-----------|---------|---------|
| `Table` | Tabulator.js | Server-side pagination, filtering, sorting, go-to, CSV export, custom formatters |
| `LinePlot` | Plotly.js | Stick-style mass spectra with highlighting, annotations, zoom (+ `density` / `tagger` modes) |
| `MirrorPlot` | Plotly.js | Paired-spectrum comparison with independent per-side filtering and shared click selection |
| `Heatmap` | Plotly scattergl | 2D scatter with multi-resolution downsampling for millions of points |
| `VolcanoPlot` | Plotly.js | Differential expression with render-time significance thresholds |
| `SequenceView` | Vue | Peptide/protein view with fragment-ion matching, coverage, internal fragments, auto-zoom |
| `Plot3D` | Plotly scatter3d | 3D scatter / stem plot with categorical coloring and a render-time trace mode |

`StateManager`, `SequenceViewResult`, `get_component_annotations` /
`clear_component_annotations` round out the import surface.

## Installation

```bash
pip install openms-insight
```

## Quick Start

```python
import streamlit as st
from openms_insight import (
    Table, LinePlot, MirrorPlot, Heatmap, VolcanoPlot, SequenceView, Plot3D,
    StateManager,
)

# Create state manager for cross-component linking
state_manager = StateManager()

# Create a table - clicking a row sets the 'item' selection
table = Table(
    cache_id="items_table",
    data_path="items.parquet",
    interactivity={'item': 'item_id'},
    column_definitions=[
        {'field': 'item_id', 'title': 'ID', 'sorter': 'number'},
        {'field': 'name', 'title': 'Name'},
    ],
)
table(state_manager=state_manager)

# Create a linked plot - filters by the selected 'item'
plot = LinePlot(
    cache_id="values_plot",
    data_path="values.parquet",
    filters={'item': 'item_id'},
    x_column='x',
    y_column='y',
)
plot(state_manager=state_manager)
```

## Cross-Component Linking

Components communicate through **identifiers** using three mechanisms:

- **`filters`**: INPUT - filter this component's data by the selection
- **`filter_defaults`**: INPUT - default value when selection is None
- **`interactivity`**: OUTPUT - set a selection when user clicks

```python
# Master table: no filters, sets 'spectrum' on click
master = Table(
    cache_id="spectra",
    data_path="spectra.parquet",
    interactivity={'spectrum': 'scan_id'},  # Click -> sets spectrum=scan_id
)

# Detail table: filters by 'spectrum', sets 'peak' on click
detail = Table(
    cache_id="peaks",
    data_path="peaks.parquet",
    filters={'spectrum': 'scan_id'},        # Filters where scan_id = selected spectrum
    interactivity={'peak': 'peak_id'},      # Click -> sets peak=peak_id
)

# Plot: filters by 'spectrum', highlights selected 'peak'
plot = LinePlot(
    cache_id="plot",
    data_path="peaks.parquet",
    filters={'spectrum': 'scan_id'},
    interactivity={'peak': 'peak_id'},
    x_column='mass',
    y_column='intensity',
)

# Table with filter defaults - shows unannotated data when no identification selected
annotations = Table(
    cache_id="annotations",
    data_path="annotations.parquet",
    filters={'identification': 'id_idx'},
    filter_defaults={'identification': -1},  # Use -1 when identification is None
)
```

---

## Config vs. Render-Time Parameters

Component parameters fall into two classes:

- **Data-shaping (cache-keyed) config** - columns, transforms, downsampling,
  binning, mode selection, etc. These determine the *preprocessed data on disk*.
  Changing any of them **invalidates the on-disk cache and re-runs
  preprocessing**.
- **Render-time (presentation) config** - titles, axis/colorbar labels, colors
  and colorscales, `VolcanoPlot` thresholds, `Plot3D` `trace_mode`, and `height`.
  These are pure passthrough to the Vue layer. Changing them does **not** rebuild
  the cache (they are still persisted in the cache manifest so a cache-only
  reconstruction restores the look).

Render-time values can be supplied either at construction (they are simply not
hashed) or, for the per-render switches, via the component's `__call__`:

```python
# Construction-time presentation (not cache-keyed): retuning a label/color is free
heatmap = Heatmap(cache_id="h", data_path="peaks.parquet",
                  x_column='rt', y_column='mz', intensity_column='intensity',
                  colorscale='Viridis', title="Peak Map")   # no cache rebuild on change

# Per-render switches via __call__ (the reference pattern):
volcano(state_manager=sm, fc_threshold=1.0, p_threshold=0.05, max_labels=20)  # thresholds
plot3d(state_manager=sm, trace_mode='markers', height=800)                    # 3D trace mode
component(state_manager=sm, height=500)                                       # height (all components)
```

`VolcanoPlot.__call__(fc_threshold=, p_threshold=, max_labels=)` and
`Plot3D.__call__(trace_mode=)` are the reference implementations - they let you
adjust a slider instantly with no preprocessing.

> Note: `title` is render-time (a pure Vue passthrough) on **every** component,
> `Table` included - it lives in `_get_render_config()`, so retuning it never
> rebuilds the cache. The rest of `Table`'s config (column definitions,
> pagination, etc.) remains data-shaping.

---

## Reusable Generic Interfaces

These cross-component patterns are MS-agnostic plumbing that any viewer built on
this library can reuse.

### Value-based cross-linking (`filters` / `interactivity` + `StateManager`)

Every component speaks the same identifier->column vocabulary:
`interactivity` is the OUTPUT (a click writes a selection), `filters` is the
INPUT (filter this component by a selection), and `filter_defaults` supplies a
value when a selection is `None`. A shared `StateManager` routes selections
between components by identifier name. (`MirrorPlot` is the one intentional
variation - it takes per-side `filters_top` / `filters_bottom` with a single
shared `interactivity`.) See
[Cross-Component Linking](#cross-component-linking).

### Per-peak annotation overlay (`LinePlot.set_peak_annotations`)

A flat list of self-describing label descriptors in data coordinates -
`{x, text, color?, hover?, group?, y?}` - drawn independently of the per-row
`annotation_column`. Generic enough for any "multiple labeled overlays" need; the
MS-specific `compute_charge_annotations` producer layers charge math on top. See
[LinePlot](#per-peak-annotation-overlay-generic).

### Categorical coloring (`category_column` / `category_colors`)

One vocabulary for "discrete category column -> color map", shared by `Heatmap`
and `Plot3D` (one trace/color per distinct value). The `Table` `badge` formatter
is the table-cell equivalent (category -> colored pill).

### Table formatter chain (`with_fixed_format` / `with_placeholder` / ...)

Chainable `with_*` helpers (`with_money_format`, `with_fixed_format`,
`with_placeholder`, `with_progress_bar`) attach reusable cell formatters to a
`Table` without hand-writing `formatterParams`. See
[Table](#table).

### Fragment-map -> spectrum annotation bridge

`SequenceView` returns a `SequenceViewResult` whose `.annotations` DataFrame
(`peak_id, highlight_color, annotation`) is published under the component's render
key. A linked plot consumes it by key - no shared data plumbing required:

```python
sv = SequenceView(cache_id="seq", sequence_data=seqs_df, peaks_data=peaks_df,
                  filters={'spectrum': 'scan_id'}, interactivity={'peak': 'peak_id'})
plot = LinePlot.from_sequence_view(sv, cache_id="spectrum", title="Annotated Spectrum")

sv(key="sv", state_manager=sm)                                   # produces annotations
plot(key="plot", state_manager=sm, sequence_view_key="sv")       # consumes them by key
```

The same bridge feeds `MirrorPlot` per side via
`MirrorPlot.__call__(sequence_view_top_key=, sequence_view_bottom_key=)`. The
transport functions `get_component_annotations(key)` /
`clear_component_annotations()` are the public consumer half (exported from the
package); `SequenceView` is the producer. The "compute annotations in one
component, render them in another via a shared key" pattern is itself generic -
it carries no MS-specific assumptions.

The `SequenceView` coverage gradient (`coverage_column`), internal-fragment map
(`internal_fragments`), and proteoform terminal markers
(`proteoform_start_column` / `proteoform_end_column`) are general top-down /
proteomics concepts surfaced as opt-in features (see
[SequenceView](#sequenceview)).

---

## Components

### Table

Interactive table using Tabulator.js with filtering dialogs, sorting, pagination, and CSV export.

Minimal "hello world" - a cache id and data are the only required arguments
(columns auto-generate from the data schema):

```python
Table(cache_id="spectra_table", data_path="spectra.parquet")
```

Common extensions (cross-linking, explicit columns, navigation, pagination):

```python
Table(
    cache_id="spectra_table",
    data_path="spectra.parquet",
    interactivity={'spectrum': 'scan_id'},
    column_definitions=[
        {'field': 'scan_id', 'title': 'Scan', 'sorter': 'number'},
        {'field': 'rt', 'title': 'RT (min)', 'sorter': 'number', 'hozAlign': 'right',
         'formatter': 'money', 'formatterParams': {'precision': 2, 'symbol': ''}},
        {'field': 'precursor_mz', 'title': 'm/z', 'sorter': 'number'},
    ],
    index_field='scan_id',
    go_to_fields=['scan_id'],
    initial_sort=[{'column': 'scan_id', 'dir': 'asc'}],
    default_row=0,
    pagination=True,
    page_size=100,
)
```

**Key parameters:**
- `column_definitions`: List of Tabulator column configs (field, title, sorter, formatter, etc.)
- `index_field`: Column used as unique row identifier (default: 'id')
- `go_to_fields`: Columns available in "Go to" navigation
- `initial_sort`: Default sort configuration
- `pagination`: Enable server-side pagination (default: True). Only the current page of data is sent to the browser, dramatically reducing memory usage for large datasets.
- `page_size`: Rows per page (default: 100)

**Custom formatters:**
In addition to Tabulator's built-in formatters, these custom formatters are available:
- `scientific`: Exponential notation (e.g., "1.23e-05") - use `formatterParams: {precision: 3}`
- `signed`: Explicit +/- prefix (e.g., "+1.234") - use `formatterParams: {precision: 3, showPositive: true}`
- `badge`: Colored pill/badge for categorical values - use `formatterParams: {colorMap: {"Up": "#FF0000"}, defaultColor: "#888"}`

```python
column_definitions=[
    {'field': 'pvalue', 'title': 'P-value', 'formatter': 'scientific', 'formatterParams': {'precision': 2}},
    {'field': 'log2fc', 'title': 'Log2 FC', 'formatter': 'signed', 'formatterParams': {'precision': 3}},
    {'field': 'regulation', 'title': 'Status', 'formatter': 'badge',
     'formatterParams': {'colorMap': {'Up': '#d62728', 'Down': '#1f77b4', 'NS': '#888888'}}},
]
```

The `badge` formatter is the canonical "categorical coloring in a table" answer
(a category->color pill), mirroring `category_colors` in Heatmap/Plot3D.

**Chainable formatter helpers:**
The same formatters are reachable as a chainable Python API on a `Table`
instance (each returns `self`), so you can attach formatters without hand-writing
`formatterParams`:

```python
table = (
    Table(cache_id="results", data_path="results.parquet")
    .with_money_format('rt', precision=2)             # currency/money formatter
    .with_fixed_format('mass', precision=4, min_length=4)  # fixed decimals, length-guarded
    .with_placeholder('id_idx', sentinels=(-1,), text='-')  # sentinel -> placeholder text
    .with_progress_bar('coverage', min_val=0, max_val=100)  # progress bar
)
```

### LinePlot

Stick-style line plot using Plotly.js for mass spectra visualization.

Minimal "hello world" - just a cache id, data, and the x/y columns:

```python
LinePlot(
    cache_id="spectrum_plot",
    data_path="peaks.parquet",
    x_column='mass',
    y_column='intensity',
)
```

Common extensions (cross-linking, highlights, labels, styling):

```python
LinePlot(
    cache_id="spectrum_plot",
    data_path="peaks.parquet",
    filters={'spectrum': 'scan_id'},        # follow the selected spectrum
    interactivity={'peak': 'peak_id'},      # click a peak -> sets 'peak'
    x_column='mass',
    y_column='intensity',
    highlight_column='is_annotated',        # bool/int column: which peaks to highlight
    annotation_column='ion_label',          # text column: label on highlighted peaks
    title="MS/MS Spectrum",                 # title/labels are render-time (not cached)
    x_label="m/z",
    y_label="Intensity",
    styling={
        'highlightColor': '#E4572E',
        'selectedColor': '#F3A712',
        'unhighlightedColor': 'lightblue',
    },
)
```

**Key parameters:**
- `x_column`, `y_column`: Column names for x/y values (default `'x'` / `'y'`)
- `highlight_column`: Boolean/int column indicating which points to highlight
- `annotation_column`: Text column for labels on highlighted points
- `styling`: Color configuration dict (`highlightColor`, `selectedColor`, `unhighlightedColor`, `annotationBackground`)
- `title`, `x_label`, `y_label`: Render-time labels (axis labels default to the column name)

#### LinePlot modes

`LinePlot` carries three modes. The default `LinePlot(...)` constructor is the
generic stick spectrum; the two specialized modes have their own grouped
parameters and are best constructed via factory classmethods (equivalent to
passing `mode=...` to the constructor). `mode` is **cache-keyed** (each mode
preprocesses differently).

- **`LinePlot(...)`** (default, `mode="default"`) - classic stick spectrum (above).

- **`LinePlot.density(...)`** - two-series target/decoy KDE / FDR plot:

  ```python
  LinePlot.density(
      cache_id="qscore_density",
      data=density_df,                  # tidy {x, y, category}
      x_column='qscore',
      y_column='density',
      category_column='group',          # column holding the target/decoy label
      target_value='target',
      decoy_value='decoy',              # decoy series may be absent
      kde_from={'score': 'qscore', 'label': 'group'},  # optional: build KDE from raw scores
      kde_points=200,
      title="Q-score Density",
  )
  ```

- **`LinePlot.tagger(...)`** - sequence-tag overlay with drill-down (top-down
  proteomics recipe; quarantines the FLASHApp-flavored params):

  ```python
  LinePlot.tagger(
      cache_id="augmented_spectrum",
      data=per_scan_df,                 # per-scan list-column frame
      filters={'spectrum': 'scan_id'},
      interactivity={'tagger_mass': 'peak_id'},  # drill-down selection
      x_column='MonoMass',              # list-column of deconvolved masses
      y_column='SumIntensity',          # list-column of intensities
      signal_peaks_column='SignalPeaks',# list[mass][peak] = [peak_index, mz, intensity, charge]
      mz_column='Mzs',
      mz_intensity_column='MzIntensities',
      tag_identifier='tag',             # selection key carrying the opaque TagData payload
  )
  ```

#### Per-peak annotation overlay (generic)

`set_peak_annotations([...])` draws **multiple** labels at arbitrary x positions
in data coordinates, independent of the per-row `annotation_column` model. Each
descriptor is `{x, text, color?, hover?, group?, y?}`. This is generic MS-agnostic
plumbing - any viewer can use it for labeled overlays:

```python
plot = LinePlot(cache_id="spectrum", data=peaks_df, x_column='mz', y_column='intensity')
plot.set_peak_annotations([
    {'x': 802.5, 'text': 'z=12', 'color': '#E4572E', 'group': 'charge'},
    {'x': 968.1, 'text': 'z=10', 'color': '#E4572E', 'group': 'charge'},
])
plot(state_manager=state_manager)
```

The MS-specific *producer* `compute_charge_annotations(signal_peaks_for_mass, color=...)`
(in `openms_insight.components.lineplot`) groups a mass's raw signal peaks by
charge and emits one intensity-weighted center-of-gravity label per charge - layer
it on top of the generic descriptor API when you need the charge math.

### MirrorPlot

Two stick-style spectra rendered against a shared x-axis with the bottom half flipped, used for comparing paired spectra (experimental vs. theoretical, sample vs. reference, MS1 vs. MS2 fragments). Each half is filtered independently, while clicks on either half feed into one shared selection.

```python
from openms_insight import MirrorPlot

mirror = MirrorPlot(
    cache_id="mirror",
    data_path="peaks.parquet",
    filters_top={'spectrum_a': 'scan_id'},      # top half follows spectrum_a
    filters_bottom={'spectrum_b': 'scan_id'},   # bottom half follows spectrum_b
    interactivity={'selected_peak': 'peak_id'}, # click in either half -> shared
    x_column='mass',
    y_column='intensity',                       # positive for both halves
    highlight_column='is_annotated',
    annotation_column='ion_label',
    title_top="Experimental",
    title_bottom="Reference",
    x_label="m/z",
    y_label="Intensity",
)
mirror(state_manager=state_manager, height=600)
```

**Key parameters:**
- `filters_top` / `filters_bottom`: Per-side filter mappings (independent selections drive each half)
- `filter_defaults_top` / `filter_defaults_bottom`: Per-side default values when the corresponding selection is `None`
- `interactivity`: Shared across both halves — a click in either half writes the same identifier
- `x_column`, `y_column`: Shared schema. Provide y values as positive numbers; the bottom half is flipped at render time
- `highlight_column`, `annotation_column`: Shared schema for highlights and label text
- `title`, `title_top`, `title_bottom`, `x_label`, `y_label`: **Render-time presentation** (not cache-keyed). `title_top`/`title_bottom` are in-figure labels for each half (rendered inside the plot, not above it); `title` is the overall plot title.
- `styling`: Color dict with `highlightColor`, `selectedColor`, `unhighlightedColor` (same defaults as LinePlot)

**Behavior:**
- The y-axis auto-rescales to the maximum visible peak when zooming, and overlapping annotation labels are re-evaluated at the new pixel/data ratio so previously hidden labels reappear when there is room (matches LinePlot's zoom behavior)
- Tick labels show absolute intensity on both sides — the bottom half is flipped only for layout, not for the displayed values
- Marker traces are kept in addition to stick shapes so Plotly fires `plotly_click` events; the click handler picks the side via `curveNumber` and routes the row's interactivity column value to the shared selection
- `set_top_dynamic_annotations(...)` / `set_bottom_dynamic_annotations(...)` allow another component (e.g. a `SequenceView`) to push fragment-ion annotations into one half without invalidating the cache

### Heatmap

2D scatter heatmap using Plotly scattergl with multi-resolution downsampling for large datasets (millions of points).

Minimal "hello world" - a cache id, data, and the three columns:

```python
Heatmap(
    cache_id="peaks_heatmap",
    data_path="all_peaks.parquet",
    x_column='retention_time',
    y_column='mass',
    intensity_column='intensity',
)
```

Common extensions (cross-linking, binning, presentation):

```python
Heatmap(
    cache_id="peaks_heatmap",
    data_path="all_peaks.parquet",
    x_column='retention_time',
    y_column='mass',
    intensity_column='intensity',
    interactivity={'spectrum': 'scan_id', 'peak': 'peak_id'},
    min_points=30000,
    x_bins=400,
    y_bins=50,
    title="Peak Map",                       # title/labels/colorscale are render-time
    x_label="Retention Time (min)",
    y_label="m/z",
    colorscale='Portland',
)
```

**Key parameters:**
- `x_column`, `y_column`, `intensity_column`: Column names for axes and color
- `min_points`: Target number of points to display (default: 10000). Cache levels are built at 2x this value; the final downsample at render time reduces to `min_points`.
- `downsample`: Downsampling strategy, one of `"streaming"` (default, lowest init memory), `"eager"` (levels computed upfront), or `"simple"` (top-N, no scipy). Data-shaping (cache-keyed).
- `x_bins`, `y_bins`: Advanced binning. Grid resolution for spatial binning; auto-computed from `display_aspect_ratio` when left as `None`.
- `categorical_filters`: List of filter identifiers that get per-value compression levels, so a constant point count is sent to the browser regardless of the filter selection. Use for small-cardinality facets (<20 unique values, e.g. an ion-mobility bin, sample group, or charge). Example: `['im_dimension']`.
- `log_scale`: Use log10 color mapping (default: True). Set to False for linear. **Data-shaping (cache-keyed).**
- `low_values_on_top`: Prioritize low values during downsampling and display them on top (default: False). Use for scores where lower = better (e.g., e-values, PEP, q-values). **Data-shaping (cache-keyed).**

**Render-time (presentation) parameters** - changing these does *not* rebuild the cache:
- `title`, `x_label`, `y_label`: Plot/axis labels (axis labels default to the column name).
- `colorscale`: Plotly colorscale name (default: 'Portland').
- `reversescale`: Invert colorscale direction (default: False).
- `intensity_label`: Custom colorbar label (default: 'Intensity').

> Note: `use_streaming` / `use_simple_downsample` are deprecated booleans kept for back-compat; prefer the single `downsample=` enum.

> Note: `zoom_identifier` defaults to `f"{cache_id}_zoom"`, derived per-instance, so two heatmaps on one page have independent zoom state out of the box. Pass an explicit `zoom_identifier=` only when you deliberately want multiple heatmaps to *share* zoom state.

**Linear scale example:**
```python
Heatmap(
    cache_id="psm_scores",
    data_path="psm_data.parquet",
    x_column='rt',
    y_column='mz',
    intensity_column='score',
    log_scale=False,              # Linear color mapping
    intensity_label='Score',      # Custom colorbar label
    colorscale='Blues',
)
```

**Low values on top (PSM scores):**
For identification results where lower scores indicate better matches (e.g., e-values, PEP, q-values), use `low_values_on_top=True` to preserve low-scoring points during downsampling and display them on top of high-scoring points:

```python
Heatmap(
    cache_id="psm_evalue",
    data_path="psm_data.parquet",
    x_column='rt',
    y_column='mz',
    intensity_column='e_value',
    log_scale=True,               # Log scale for e-values
    low_values_on_top=True,       # Keep/show low e-values (best hits)
    reversescale=True,            # Bright color = low value = best
    intensity_label='E-value',
    colorscale='Portland',
)
```

**Categorical mode:**
Use `category_column` for discrete coloring by category instead of continuous intensity colorscale:

```python
Heatmap(
    cache_id="samples_heatmap",
    data_path="samples.parquet",
    x_column='retention_time',
    y_column='mass',
    intensity_column='intensity',
    category_column='sample_group',  # Color by category instead of intensity
    category_colors={                 # Optional custom colors
        'Control': '#1f77b4',
        'Treatment_A': '#ff7f0e',
        'Treatment_B': '#2ca02c',
    },
)
```

### VolcanoPlot

Interactive volcano plot for differential expression analysis with significance thresholds.

```python
from openms_insight import VolcanoPlot

VolcanoPlot(
    cache_id="de_volcano",
    data_path="differential_expression.parquet",
    log2fc_column='log2FC',
    pvalue_column='pvalue',
    label_column='protein_name',       # Optional: labels for significant points
    filters={'comparison': 'comparison_id'},
    interactivity={'protein': 'protein_id'},
    title="Differential Expression",
    x_label="Log2 Fold Change",
    y_label="-log10(p-value)",
    up_color='#d62728',               # Color for up-regulated
    down_color='#1f77b4',             # Color for down-regulated
    ns_color='#888888',               # Color for not significant
)(
    state_manager=state_manager,
    fc_threshold=1.0,                  # Fold change threshold (render-time)
    p_threshold=0.05,                  # P-value threshold (render-time)
    max_labels=20,                     # Max labels to show
)
```

**Key parameters:**
- `log2fc_column`: Column with log2 fold change values (default `'log2FC'`). **Data-shaping (cache-keyed).** Domain-named by design - a volcano plot *is* log2FC-vs-p-value.
- `pvalue_column`: Column with p-values (default `'pvalue'`; automatically converted to -log10). **Data-shaping (cache-keyed).**
- `label_column`: Optional column for point labels. **Data-shaping (cache-keyed).**
- `title`, `x_label`, `y_label`, `up_color`, `down_color`, `ns_color`, `show_threshold_lines`, `threshold_line_style`: **Render-time presentation** (changing them does not rebuild the cache). Default colors are red `#E74C3C` / blue `#3498DB` / gray `#95A5A6`.
- `fc_threshold`, `p_threshold`, `max_labels`: Significance thresholds and label cap, **passed via `__call__`** (defaults `1.0` / `0.05` / `10`).

**Render-time thresholds:** `fc_threshold`, `p_threshold`, and `max_labels` are passed via `__call__()`, not `__init__()`. This allows instant threshold adjustment without cache invalidation - the reference pattern for render-time parameters across the library.

### SequenceView

Peptide sequence visualization with fragment ion matching. Supports both dynamic (filtered by selection) and static sequences.

```python
# Dynamic: sequence from DataFrame filtered by selection
SequenceView(
    cache_id="peptide_view",
    sequence_data_path="sequences.parquet",  # columns: scan_id, sequence, precursor_charge
    peaks_data_path="peaks.parquet",         # columns: scan_id, peak_id, mass, intensity
    filters={'spectrum': 'scan_id'},
    interactivity={'peak': 'peak_id'},
    deconvolved=False,  # peaks are m/z values, consider charge states
    title="Fragment Coverage",
)

# Static: single sequence with optional peaks
SequenceView(
    cache_id="static_peptide",
    sequence_data=("PEPTIDEK", 2),  # (sequence, charge) tuple
    peaks_data=peaks_df,            # Optional: LazyFrame with mass, intensity columns
    deconvolved=True,               # peaks are neutral masses
)

# Simplest: just a sequence string
SequenceView(
    cache_id="simple_seq",
    sequence_data="PEPTIDEK",  # charge defaults to 1
)
```

**Key parameters:**
- `sequence_data`: LazyFrame, (sequence, charge) tuple, or sequence string
- `sequence_data_path`: Path to parquet with sequence data
- `peaks_data` / `peaks_data_path`: Optional peak data for fragment matching
- `deconvolved`: If False (default), peaks are m/z and matching considers charge states
- `annotation_config`: Dict with `ion_types` (default `["b", "y"]`), `tolerance` (default 20.0), `tolerance_ppm`, `neutral_losses`, `colors`
- `filter_defaults`: Default values when a filter selection is None (matches the canonical `filter_defaults` of the other components; any unlisted filter identifier defaults to `None`)
- `title`, `height`: Render-time presentation (passing them does not require data; they are not part of the reconstruction guard)

**Generic proteoform/coverage extensions (off by default):**
- `coverage_column`: Name of a column holding a per-residue coverage list (one numeric entry per residue). When set, the component normalises it (per residue / max) and renders a per-residue coverage gradient plus a coverage scale legend.
- `internal_fragments`: If True, also render an internal-fragment map below the terminal map. Theoretical internals are enumerated in Python and matched in Vue. Cache-invalidating (like `deconvolved`).
- `internal_fragment_config`: Optional overrides - `min_length` (5), `ion_types` (`["by", "bz", "cy"]`), `tolerance` (10.0), `tolerance_ppm`, `remove_terminal_collisions`, `terminal_collision_ppm`.
- `proteoform_start_column` / `proteoform_end_column`: Columns holding 0-based proteoform terminal residue indices for truncated/undetermined N/C-termini (negative = undetermined, rendered as a "??" marker).

**Features:**
- Automatic fragment ion matching (a/b/c/x/y/z ions)
- Configurable mass tolerance (ppm or Da)
- Neutral loss support (-H2O, -NH3)
- Auto-zoom for short sequences (<=20 amino acids)
- Fragment coverage statistics
- Click-to-select peaks with cross-component linking
- Returns a `SequenceViewResult` whose `.annotations` DataFrame is the source for the cross-component fragment-map -> spectrum annotation bridge (see [Reusable generic interfaces](#reusable-generic-interfaces))

```python
result = sequence_view(key="sv", state_manager=state_manager)
# result.annotations -> Polars DataFrame (peak_id, highlight_color, annotation)
```

### Plot3D

Generic 3D scatter / stem plot using Plotly scatter3d. Reproduces the
top-down "precursor Signal/Noise 3D plot" in a generic, cache-first form: input
is a tidy frame with **one row per plotted point**, and each point is drawn as a
vertical stem. The mass/charge/intensity column defaults and the
Signal/Noise category colors are an MS preset, not a contract - override them for
any x/y/z scatter.

Minimal "hello world":

```python
from openms_insight import Plot3D

Plot3D(
    cache_id="precursor_signals",
    data=tidy_points_df,   # one row per point; defaults: x='mass', y='charge', z='intensity'
)
```

With categorical coloring and selection-driven filtering:

```python
Plot3D(
    cache_id="precursor_signals",
    data=tidy_points_df,
    x_column='mass',
    y_column='charge',
    z_column='intensity',
    category_column='series',                 # one trace per category (e.g. Signal/Noise)
    category_colors={'Signal': '#3366CC', 'Noise': '#DC3912'},
    filters={'spectrum': 'scan', 'mass': 'mass_index'},
    filter_defaults={'spectrum': -1},         # empty frame when no scan selected
    title="Precursor Signals",
)(
    state_manager=state_manager,
    trace_mode='lines',                       # render-time: 'lines'|'markers'|'lines+markers'
    height=800,
)
```

**Key parameters:**
- `x_column`, `y_column`, `z_column`: Geometric axes (defaults `'mass'`, `'charge'`, `'intensity'`). **Data-shaping (cache-keyed).**
- `category_column` / `category_colors`: Categorical coloring - one trace per distinct value, colored via the value->color map (same vocabulary as `Heatmap`). Default colors `{'Signal': '#3366CC', 'Noise': '#DC3912'}`.
- `drop_nonpositive_z` (default True), `log_z` (default False), `hover_columns`: Data-shaping knobs.
- `title`, `x_label`, `y_label`, `z_label`: Render-time labels (default "Mass" / "Charge" / "Intensity").
- `trace_mode`: Plotly trace mode (`"lines"` default), **render-time**-overridable via `__call__` with no cache rebuild.
- `stem`, `stem_baseline`, `y_dtick`, `y_tick0`, `camera_eye`: Advanced 3D-framing presets (render-time). Default camera eye `{'x': 2.5, 'y': 0, 'z': 0.2}`.
- Default component height is **800** (not the global 400 default).

---

## Shared Component Arguments

All components accept these common arguments:

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `cache_id` | `str` | **Required** | Unique identifier for disk cache |
| `data_path` | `str` | `None` | Path to parquet file (preferred for memory efficiency) |
| `data` | `pl.LazyFrame` | `None` | Polars LazyFrame (alternative to data_path) |
| `filters` | `Dict[str, str]` | `None` | Map identifier -> column for filtering |
| `filter_defaults` | `Dict[str, Any]` | `None` | Default values when selection is None |
| `interactivity` | `Dict[str, str]` | `None` | Map identifier -> column for click actions |
| `cache_path` | `str` | `"."` | Base directory for cache storage |
| `regenerate_cache` | `bool` | `False` | Force cache regeneration |
| `height` | `int` | `400` | Component height in pixels (render-time parameter) |

## Memory-Efficient Preprocessing

When working with large datasets (especially heatmaps with millions of points), use `data_path` instead of `data` to enable subprocess preprocessing:

```python
# Subprocess preprocessing (recommended for large datasets)
# Memory is fully released after cache creation
heatmap = Heatmap(
    data_path="large_peaks.parquet",  # triggers subprocess
    cache_id="peaks_heatmap",
    ...
)

# In-process preprocessing (for smaller datasets or debugging)
# Memory may be retained by allocator after preprocessing
heatmap = Heatmap(
    data=pl.scan_parquet("large_peaks.parquet"),  # runs in main process
    cache_id="peaks_heatmap",
    ...
)
```

**Why this matters:** Memory allocators like mimalloc (used by Polars) retain freed memory for performance. For large datasets, this can cause memory usage to stay high even after preprocessing completes. Running preprocessing in a subprocess guarantees all memory is returned to the OS when the subprocess exits.

## Cache Reconstruction

Components can be reconstructed from cache using only `cache_id` and `cache_path`. All configuration is restored from the cached manifest:

```python
# First run: create component with data and config
table = Table(
    cache_id="my_table",
    data_path="data.parquet",
    filters={'spectrum': 'scan_id'},
    column_definitions=[...],
    cache_path="./cache",
)

# Subsequent runs: reconstruct from cache only
table = Table(
    cache_id="my_table",
    cache_path="./cache",
)
# All config (filters, column_definitions, etc.) restored from cache
```

## Rendering

All components are callable. Pass a `StateManager` to enable cross-component linking:

```python
from openms_insight import StateManager

state_manager = StateManager()

table(state_manager=state_manager, height=300)
plot(state_manager=state_manager, height=400)
```

---

## Development

For a comprehensive guide to the internal architecture, conventions, and pitfalls, see [CONTRIBUTING.md](CONTRIBUTING.md).

### Building the Vue Component

```bash
cd js-component
npm install
npm run build
```

### Development Mode (Hot Reload)

```bash
# Terminal 1: Vue dev server
cd js-component
npm run dev

# Terminal 2: Streamlit with dev mode
SVC_DEV_MODE=true SVC_DEV_URL=http://localhost:5173 streamlit run app.py
```

### Debug Mode

Enable hash tracking logs to debug data synchronization issues:

```bash
SVC_DEBUG_HASH=true streamlit run app.py
```

### Running Tests

```bash
# Python tests
pip install -e ".[dev]"
pytest tests/ -v

# TypeScript type checking
cd js-component
npm run type-check
```

### Linting and Formatting

```bash
# Python
ruff check .
ruff format .

# JavaScript/TypeScript
cd js-component
npm run lint
npm run format
```
