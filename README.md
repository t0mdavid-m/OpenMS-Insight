# Streamlit Vue Components

Interactive visualization components for Streamlit backed by Vue.js.

## Features

- **Cross-component selection linking** via shared identifiers
- **Polars LazyFrame support** for efficient data handling
- **Save/load components** to disk with preprocessed data
- **Table component** (TabulatorTable) with filtering, sorting, go-to
- **Line plot component** (PlotlyLineplot) with highlighting and zoom

## Installation

```bash
pip install streamlit-vue-components
```

## Quick Start

```python
import streamlit as st
import polars as pl
from streamlit_vue_components import Table, LinePlot

# Load data
data = pl.scan_csv("my_data.csv")

# Create a table with interactivity
table = Table(
    data=data,
    interactivity={'item': 'item_id'},
    column_definitions=[
        {'field': 'item_id', 'title': 'ID', 'sorter': 'number'},
        {'field': 'name', 'title': 'Name'},
        {'field': 'value', 'title': 'Value', 'sorter': 'number'},
    ],
    title="My Table",
)

# Render the table
table()

# Create a linked line plot
plot = LinePlot(
    data=data,
    interactivity={'item': 'item_id'},
    x_column='x',
    y_column='y',
    title="My Plot",
)

# Render the plot
plot()
```

## Cross-Component Linking

Components are linked through shared identifiers in the `interactivity` dict:

```python
# These components share the 'spectrum' identifier
# When a row is selected in the table, the plot filters to show
# only data where its 'scan' column matches the selected value

table = Table(
    data=scan_table,
    interactivity={'spectrum': 'id'},  # identifier 'spectrum' maps to column 'id'
    ...
)

plot = LinePlot(
    data=spectrum_data,
    interactivity={'spectrum': 'scan'},  # identifier 'spectrum' maps to column 'scan'
    ...
)
```

## Save/Load Components

```python
# Save component with preprocessed data
table.save("my_table.svcomp")

# Load component
from streamlit_vue_components import load_component
loaded_table = load_component("my_table.svcomp")
loaded_table()
```

## Development

### Building the Vue Component

```bash
cd js-component
npm install
npm run dev    # Development with hot reload
npm run build  # Production build
```

### Development Mode

Set environment variables for development:

```bash
export SVC_DEV_MODE=true
export SVC_DEV_URL=http://localhost:5173
```

## Architecture

See [ARCHITECTURE_PLAN.md](../ARCHITECTURE_PLAN.md) for detailed design documentation.
