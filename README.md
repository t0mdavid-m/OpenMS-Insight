# OpenMS-Insight

[![PyPI version](https://badge.fury.io/py/openms-insight.svg)](https://badge.fury.io/py/openms-insight)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)

Interactive visualization components for mass spectrometry data in Streamlit, backed by Vue.js.

## Features

- **Cross-component selection linking** via shared identifiers
- **Polars LazyFrame support** for efficient data handling
- **Automatic disk caching** with config-based invalidation
- **Table component** (Tabulator.js) with filtering, sorting, go-to, pagination
- **Line plot component** (Plotly.js) with highlighting, annotations, zoom
- **Heatmap component** (Plotly scattergl) with multi-resolution downsampling
- **Sequence view component** for peptide/protein visualization

## Installation

```bash
pip install openms-insight
```

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
    interactivity={'spectrum': 'scan_id'},  # Click -> sets spectrum=scan_id
)

# Detail table: filters by 'spectrum', sets 'peak' on click
detail = Table(
    cache_id="peaks",
    data=peaks_data,
    filters={'spectrum': 'scan_id'},        # Filters where scan_id = selected spectrum
    interactivity={'peak': 'peak_id'},      # Click -> sets peak=peak_id
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

## Components

### Table

Interactive table using Tabulator.js with filtering dialogs, sorting, pagination, and CSV export.

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

### LinePlot

Stick-style line plot using Plotly.js for mass spectra visualization.

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
)
```

### Heatmap

2D scatter heatmap using Plotly scattergl with multi-resolution downsampling for large datasets (millions of points).

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
)
```

### SequenceView

Peptide/protein sequence visualization with fragment ion matching.

```python
SequenceView(
    cache_id="peptide_view",
    sequence="PEPTIDEK",
    observed_masses=[147.1, 244.2, 359.3, 456.4],
    peak_ids=[0, 1, 2, 3],
    precursor_mass=944.5,
    interactivity={'peak': 'peak_id'},
    title="Fragment Coverage",
)
```

---

## Shared Component Arguments

All components accept these common arguments:

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `cache_id` | `str` | **Required** | Unique identifier for disk cache |
| `data` | `pl.LazyFrame` | `None` | Polars LazyFrame with source data |
| `filters` | `Dict[str, str]` | `None` | Map identifier -> column for filtering |
| `interactivity` | `Dict[str, str]` | `None` | Map identifier -> column for click actions |
| `cache_path` | `str` | `"."` | Base directory for cache storage |

## Rendering

All components are callable. Pass a `StateManager` to enable cross-component linking:

```python
from streamlit_vue_components import StateManager

state_manager = StateManager()

table(state_manager=state_manager, height=300)
plot(state_manager=state_manager, height=400)
```

---

## Development

### Building the Vue Component

```bash
cd js-component
npm install
npm run build
```

### Development Mode

```bash
cd js-component
npm run dev

# In another terminal:
export SVC_DEV_MODE=true
export SVC_DEV_URL=http://localhost:5173
streamlit run app.py
```
