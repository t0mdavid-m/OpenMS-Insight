# Streamlit Vue Components

Interactive visualization components for Streamlit backed by Vue.js.

## Features

- **Cross-component selection linking** via shared identifiers
- **Polars LazyFrame support** for efficient data handling
- **Automatic disk caching** with config-based invalidation
- **Table component** (Tabulator.js) with filtering, sorting, go-to, pagination
- **Line plot component** (Plotly.js) with highlighting, annotations, zoom
- **Heatmap component** (Plotly scattergl) with multi-resolution downsampling
- **Sequence view component** for peptide/protein visualization

## Quick Start

```python
import streamlit as st
import polars as pl
from streamlit_vue_components import Table, LinePlot, StateManager

# Create state manager for cross-component linking
state_manager = StateManager()

# Create a table - clicking a row sets the 'item' selection
table = Table(
    cache_id="items_table",
    data=pl.scan_parquet("items.parquet"),
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
    data=pl.scan_parquet("values.parquet"),
    filters={'item': 'item_id'},
    x_column='x',
    y_column='y',
)
plot(state_manager=state_manager)
```

## Cross-Component Linking

Components communicate through **identifiers** using two mechanisms:

- **`filters`**: INPUT - filter this component's data by the selection
- **`interactivity`**: OUTPUT - set a selection when user clicks

```python
# Master table: no filters, sets 'spectrum' on click
master = Table(
    cache_id="spectra",
    data=spectra_data,
    interactivity={'spectrum': 'scan_id'},  # Click → sets spectrum=scan_id
)

# Detail table: filters by 'spectrum', sets 'peak' on click
detail = Table(
    cache_id="peaks",
    data=peaks_data,
    filters={'spectrum': 'scan_id'},        # Filters where scan_id = selected spectrum
    interactivity={'peak': 'peak_id'},      # Click → sets peak=peak_id
)

# Plot: filters by 'spectrum', highlights selected 'peak'
plot = LinePlot(
    cache_id="plot",
    data=peaks_data,
    filters={'spectrum': 'scan_id'},
    interactivity={'peak': 'peak_id'},
    x_column='mass',
    y_column='intensity',
)
```

---

## Component Constructor Arguments

### Shared Arguments (All Components)

These arguments are available on **all** components (`Table`, `LinePlot`, `Heatmap`, `SequenceView`):

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `cache_id` | `str` | **Required** | Unique identifier for this component's disk cache. Creates folder `{cache_path}/{cache_id}/`. |
| `data` | `pl.LazyFrame \| None` | `None` | Polars LazyFrame with source data. Optional if valid cache exists. |
| `filters` | `Dict[str, str] \| None` | `None` | Mapping of identifier names to column names for filtering. When an identifier has a selection, data is filtered to rows where the column equals that value. |
| `interactivity` | `Dict[str, str] \| None` | `None` | Mapping of identifier names to column names for click actions. When user clicks/selects, sets the identifier to the clicked row's column value. |
| `cache_path` | `str` | `"."` | Base directory for cache storage. |
| `regenerate_cache` | `bool` | `False` | Force cache regeneration even if valid cache exists. |

**Example:**
```python
Table(
    cache_id="my_table",                    # Required unique ID
    data=pl.scan_parquet("data.parquet"),   # Polars LazyFrame
    filters={'parent': 'parent_id'},        # Filter by parent selection
    interactivity={'item': 'id'},           # Set item selection on click
    cache_path="./cache",                   # Store cache in ./cache/my_table/
)
```

---

### Table

Interactive table using Tabulator.js with filtering dialogs, sorting, pagination, and CSV export.

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `column_definitions` | `List[Dict] \| None` | `None` | Tabulator column definitions. Each dict can have: `field`, `title`, `sorter`, `formatter`, `formatterParams`, `headerTooltip`, `hozAlign`, `width`. Auto-generated from schema if `None`. |
| `title` | `str \| None` | `None` | Title displayed above the table. |
| `index_field` | `str` | `"id"` | Field used as row identifier for selection. Must exist in data. |
| `go_to_fields` | `List[str] \| None` | `None` | Fields available in "Go to" navigation dropdown. |
| `layout` | `str` | `"fitDataFill"` | Tabulator layout mode: `"fitData"`, `"fitDataFill"`, `"fitColumns"`, etc. |
| `default_row` | `int` | `0` | Row index to select on initial load. Use `-1` for no default selection. |
| `initial_sort` | `List[Dict] \| None` | `None` | Initial sort config: `[{'column': 'field', 'dir': 'asc'}]`. |
| `pagination` | `bool` | `True` | Enable pagination for large tables. Dramatically improves performance. |
| `page_size` | `int` | `100` | Number of rows per page when pagination enabled. |

**Example:**
```python
Table(
    cache_id="spectra_table",
    data=pl.scan_parquet("spectra.parquet"),
    interactivity={'spectrum': 'scan_id'},
    column_definitions=[
        {'field': 'scan_id', 'title': 'Scan', 'sorter': 'number'},
        {'field': 'rt', 'title': 'RT (min)', 'sorter': 'number', 'hozAlign': 'right'},
        {'field': 'precursor_mz', 'title': 'm/z', 'sorter': 'number'},
    ],
    index_field='scan_id',
    go_to_fields=['scan_id'],
    default_row=0,
    pagination=True,
    page_size=50,
)
```

---

### LinePlot

Stick-style line plot using Plotly.js for mass spectra visualization with highlighting and annotations.

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `x_column` | `str` | `"x"` | Column name for x-axis values. |
| `y_column` | `str` | `"y"` | Column name for y-axis values. |
| `title` | `str \| None` | `None` | Plot title. |
| `x_label` | `str \| None` | `None` | X-axis label. Defaults to `x_column`. |
| `y_label` | `str \| None` | `None` | Y-axis label. Defaults to `y_column`. |
| `highlight_column` | `str \| None` | `None` | Column with boolean/int indicating which points to highlight (e.g., annotated peaks). |
| `annotation_column` | `str \| None` | `None` | Column with text labels to display on highlighted points. |
| `styling` | `Dict \| None` | `None` | Style config: `highlightColor`, `selectedColor`, `unhighlightedColor`, `annotationColors`. |
| `config` | `Dict \| None` | `None` | Additional Plotly configuration options. |

**Example:**
```python
LinePlot(
    cache_id="spectrum_plot",
    data=pl.scan_parquet("peaks.parquet"),
    filters={'spectrum': 'scan_id'},
    interactivity={'peak': 'peak_id'},
    x_column='mass',
    y_column='intensity',
    highlight_column='is_annotated',
    annotation_column='ion_label',
    title="MS/MS Spectrum",
    x_label="m/z",
    y_label="Intensity",
    styling={
        'highlightColor': '#E4572E',
        'selectedColor': '#F3A712',
    },
)
```

---

### Heatmap

2D scatter heatmap using Plotly scattergl with multi-resolution downsampling for large datasets.

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `x_column` | `str` | **Required** | Column name for x-axis values. |
| `y_column` | `str` | **Required** | Column name for y-axis values. |
| `intensity_column` | `str` | `"intensity"` | Column name for intensity/color values. |
| `min_points` | `int` | `20000` | Target point count for smallest resolution level and selection threshold. |
| `x_bins` | `int` | `400` | Number of bins along x-axis for spatial downsampling. |
| `y_bins` | `int` | `50` | Number of bins along y-axis for spatial downsampling. |
| `zoom_identifier` | `str` | `"heatmap_zoom"` | State key for storing zoom range. Used for zoom-based level selection. |
| `title` | `str \| None` | `None` | Heatmap title. |
| `x_label` | `str \| None` | `None` | X-axis label. Defaults to `x_column`. |
| `y_label` | `str \| None` | `None` | Y-axis label. Defaults to `y_column`. |
| `colorscale` | `str` | `"Portland"` | Plotly colorscale name. |
| `use_simple_downsample` | `bool` | `False` | Use simple top-N downsampling instead of spatial binning. |
| `use_streaming` | `bool` | `True` | Use streaming downsampling (lazy until render). Reduces memory. |
| `categorical_filters` | `List[str] \| None` | `None` | Filter identifiers for per-value compression levels. Ensures constant point counts regardless of filter selection. |

**Example:**
```python
Heatmap(
    cache_id="peaks_heatmap",
    data=pl.scan_parquet("all_peaks.parquet"),
    x_column='retention_time',
    y_column='mass',
    intensity_column='intensity',
    interactivity={'spectrum': 'scan_id', 'peak': 'peak_id'},
    min_points=30000,
    title="Peak Map",
    x_label="Retention Time (min)",
    y_label="m/z",
    colorscale='Viridis',
)
```

---

### SequenceView

Peptide/protein sequence visualization with fragment ion matching.

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `sequence` | `str` | **Required** | Amino acid sequence (single-letter codes). Supports OpenMS modification format. |
| `observed_masses` | `List[float] \| None` | `None` | Observed peak masses from spectrum for fragment matching. |
| `peak_ids` | `List[int] \| None` | `None` | Peak IDs corresponding to `observed_masses` for interactivity linking. |
| `precursor_mass` | `float \| None` | `None` | Observed precursor mass. |
| `fixed_modifications` | `List[str] \| None` | `None` | Amino acids with fixed modifications (e.g., `['C']` for carbamidomethyl). |
| `title` | `str \| None` | `None` | Title displayed above the sequence. |
| `height` | `int` | `400` | Component height in pixels. |
| `deconvolved` | `bool` | `True` | If `True`, `observed_masses` are neutral masses. If `False`, they are m/z values. |
| `precursor_charge` | `int` | `1` | Maximum charge state for fragment matching when `deconvolved=False`. |

**Example:**
```python
SequenceView(
    cache_id="peptide_view",
    sequence="PEPTIDEK",
    observed_masses=[147.1, 244.2, 359.3, 456.4],
    peak_ids=[0, 1, 2, 3],
    precursor_mass=944.5,
    interactivity={'peak': 'peak_id'},
    title="Fragment Coverage",
    deconvolved=True,
)
```

---

## Rendering Components

All components are callable. Pass a `StateManager` to enable cross-component linking:

```python
from streamlit_vue_components import StateManager

state_manager = StateManager()

# Render components with shared state
table(state_manager=state_manager, height=300)
plot(state_manager=state_manager, height=400)
```

**Render arguments:**

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `state_manager` | `StateManager \| None` | `None` | StateManager for cross-component state. Uses default if not provided. |
| `key` | `str \| None` | `None` | Unique Streamlit component key. Auto-generated if not provided. |
| `height` | `int \| None` | `None` | Override component height in pixels. |

---

## Development

### Building the Vue Component

```bash
cd js-component
npm install
npm run dev    # Development with hot reload
npm run build  # Production build
```

### Development Mode

Set environment variables to connect to Vite dev server:

```bash
export SVC_DEV_MODE=true
export SVC_DEV_URL=http://localhost:5173
streamlit run app.py
```
