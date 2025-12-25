# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

OpenMS-Insight is a Streamlit component library with Vue.js frontends for mass spectrometry data visualization. It provides cross-component selection linking via shared identifiers.

## Development Commands

### Vue Component (js-component/)

```bash
cd js-component
npm install
npm run build        # Production build (outputs to dist/)
npm run dev          # Vite dev server on port 5173
npm run type-check   # TypeScript checking (vue-tsc)
npm run lint         # ESLint with auto-fix
npm run format       # Prettier formatting
```

### Python Package

```bash
pip install -e ".[dev]"    # Install with dev dependencies
ruff check .               # Lint
ruff format .              # Format
mypy openms_insight        # Type check
pytest                     # Run tests (when tests/ exists)
pytest tests/test_foo.py::test_bar  # Run single test
```

### Development Mode (Hot Reload)

Terminal 1:
```bash
cd js-component && npm run dev
```

Terminal 2:
```bash
SVC_DEV_MODE=true SVC_DEV_URL=http://localhost:5173 streamlit run your_app.py
```

### Production Build

```bash
# Build Vue component
cd js-component && npm run build && cd ..

# Copy dist to package (creates directory if needed)
mkdir -p openms_insight/js-component
cp -r js-component/dist openms_insight/js-component/

# Build Python package
python -m build
```

## Architecture

### Python <-> Vue Communication Flow

```
User Data (Polars LazyFrame)
    |
BaseComponent.__init__()
    |- Validates column mappings against schema
    |- Checks cache validity (hash of config)
    |- Runs _preprocess() if cache miss
    `- Saves to parquet cache
    |
Component.__call__() / render_component()
    |- Gets state from StateManager
    |- Calls _prepare_vue_data() (cached by filter state)
    |- Computes data hash for change detection
    |- Sends via Arrow serialization only if hash changed
    `- Triggers st.rerun() on state changes from Vue
    |
Vue Component
    |- Receives Arrow-serialized data
    |- Renders visualization (Plotly/Tabulator)
    |- Echoes data hash back for bidirectional confirmation
    `- Updates selection state on user interaction
```

### Key Abstractions

| Concept | Description |
|---------|-------------|
| **data_path** | Path to parquet file - preprocessing runs in subprocess (memory-efficient) |
| **data** | LazyFrame - preprocessing runs in-process (backward compatible) |
| **filters** | Dict `{identifier: column}` - INPUT: filters component data by selection |
| **filter_defaults** | Dict `{identifier: default_value}` - fallback when selection is None |
| **interactivity** | Dict `{identifier: column}` - OUTPUT: sets selection on click |
| **cache_id** | Mandatory unique ID for disk caching (creates folder `{cache_path}/{cache_id}/`) |
| **StateManager** | Cross-component selection state with counter-based conflict resolution |

Prefer `data_path` over `data` for large datasets - subprocess preprocessing ensures memory is released after cache creation.

### Directory Structure

```
openms_insight/
|- core/
|   |- base.py       # BaseComponent ABC (caching, validation, preprocessing)
|   |- state.py      # StateManager (session_state, conflict resolution)
|   |- registry.py   # @register_component decorator
|   `- cache.py      # Cache utilities
|- components/
|   |- table.py      # Tabulator.js table
|   |- lineplot.py   # Plotly stick plot (mass spectra)
|   |- heatmap.py    # Plotly scattergl with downsampling
|   `- sequenceview.py  # Protein sequence visualization
|- rendering/
|   `- bridge.py     # render_component(), Arrow serialization, hash-based updates
`- preprocessing/
    |- filtering.py  # Selection-based data filtering
    `- compression.py

js-component/src/
|- components/
|   |- tabulator/    # TabulatorTable.vue
|   |- plotly/       # PlotlyLineplot.vue, PlotlyHeatmap.vue
|   `- sequence/     # SequenceView.vue
|- stores/
|   |- streamlit-data.ts  # Streamlit data reception
|   `- selection.ts       # Selection state (Pinia)
`- types/            # TypeScript type definitions
```

### Adding a New Component

1. Create Python class in `openms_insight/components/` inheriting `BaseComponent`
2. Implement required abstract methods:
   - `_preprocess()` - populate `self._preprocessed_data` with parquet-ready data
   - `_get_vue_component_name()` - return Vue component name (e.g., 'TabulatorTable')
   - `_get_data_key()` - key for primary data in Vue payload
   - `_prepare_vue_data(state)` - return filtered data dict for current selection state
   - `_get_component_args()` - return config dict for Vue
3. Use `@register_component("name")` decorator
4. Create Vue component in `js-component/src/components/`
5. Register in `App.vue` `currentComponent` computed switch statement
6. Export from `openms_insight/__init__.py`

### Caching Strategy

- Components preprocess data to Parquet on first run
- Cache validity determined by config hash (CACHE_VERSION = 3)
- Hash includes: filters, interactivity, component-specific config
- Parquet uses zstd compression, 50k row groups for predicate pushdown
- Runtime data caching via per-component session cache keyed by filter state
- Type optimization at cache time: Float64→Float32, Int64→Int32 (when safe)

### State Synchronization

- StateManager uses Streamlit's `session_state` as backend
- Counter-based conflict resolution prevents stale updates
- Session ID prevents cross-tab interference
- Vue echoes data hash back - mismatch triggers data resend (handles page navigation, hot reload)
