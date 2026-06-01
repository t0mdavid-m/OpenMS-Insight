# Python interface for FLASHApp-ported components

This document describes the Python-facing interfaces for the FLASHApp ports
added to OpenMS-Insight, with signature summaries, usage examples, and
user-visible behavior differences.

## Shared conventions

- **`cache_id`** is required for all components and identifies on-disk cache
  storage at `{cache_path}/{cache_id}/`.
- Most components accept **`data`** (a `polars.LazyFrame`) or **`data_path`**
  (parquet path). `data_path` enables subprocess preprocessing to minimize memory.
- Components that link to other components use **`StateManager`** identifiers
  via `filters` and/or `interactivity`.

## DensityPlot

**Purpose:** Static dual-KDE score distribution plot (target vs decoy).

**Signature:**

```python
DensityPlot(
    cache_id: str,
    data: pl.LazyFrame | None = None,
    data_path: str | None = None,
    mode: str | None = None,  # "deconv" or "tnt" (raw mode)
    score_column: str | None = None,
    td_type_column: str = "TargetDecoyType",
    accession_column: str = "accession",
    density_target: pl.LazyFrame | None = None,
    density_decoy: pl.LazyFrame | None = None,
    cache_path: str = ".",
    regenerate_cache: bool = False,
    x_column: str = "x",
    y_column: str = "y",
    title: str | None = "FDR Plot",
    x_label: str | None = None,
    y_label: str | None = None,
    target_name: str | None = None,
    decoy_name: str | None = None,
    target_color: str | None = None,
    decoy_color: str | None = None,
)
```

**Example (raw / Deconv):**

```python
density = DensityPlot(
    cache_id="exp1_fdr",
    data=deconv_rows,
    mode="deconv",
    title="FDR Plot",
)
density(state_manager=state_manager)
```

**Example (raw / TnT):**

```python
density = DensityPlot(
    cache_id="exp1_id_fdr",
    data=proteoform_rows,
    mode="tnt",
)
```

**Example (precomputed):**

```python
density = DensityPlot(
    cache_id="exp1_fdr",
    density_target=target_kde_xy,
    density_decoy=decoy_kde_xy,
)
```

**User-visible differences:**

- **No cross-component linking.** `filters`/`interactivity` are ignored and removed.
- Two input modes: raw KDE computation or precomputed `{x,y}` frames.
- Axis label is always **"QScore"** by default to match FLASHApp.

## FeatureView

**Purpose:** FLASHQuant feature-group table + 3D mass-trace plot.

**Signature:**

```python
FeatureView(
    cache_id: str,
    data: pl.LazyFrame | None = None,
    data_path: str | None = None,
    cache_path: str = ".",
    regenerate_cache: bool = False,
    title: str | None = None,
    plot_title: str = "Feature group signals",
    line_color: str = "#3366CC",
    plot_height: int = 800,
    x_axis_title: str = "m/z",
    y_axis_title: str = "retention time",
    z_axis_title: str = "intensity",
    selection_identifier: str = "selectedFeatureGroupIndex",
    column_definitions: list[dict[str, str]] | None = None,
)
```

**Example:**

```python
feature_view = FeatureView(
    cache_id="flashquant",
    data=feature_groups_lf,  # includes Charges/MZs/RTs/Intensities list columns
    plot_height=800,
)
feature_view(state_manager=state_manager)
```

**User-visible differences:**

- **Standalone:** the selection is internal to the component and does not
  publish/consume any shared identifiers.
- The `MZs`/`RTs`/`Intensities` columns are expected as **comma-joined strings** per
  trace (same as FLASHQuant); these are split in Vue.
- The 3D plot uses **per-charge traces** and `-1e3` sentinel values to break
  line segments (FLASHApp parity).

## Scatter3D

**Purpose:** 3D signal/noise stick plot for precursor signals.

**Signature:**

```python
Scatter3D(
    cache_id: str,
    data: pl.LazyFrame | None = None,
    data_path: str | None = None,
    scan_filter: str = "index",
    signal_column: str = "SignalPeaks",
    noisy_column: str = "NoisyPeaks",
    cache_path: str = ".",
    regenerate_cache: bool = False,
    title: str = "Precursor Signals",
    signal_color: str = "#3366CC",
    noise_color: str = "#DC3912",
    height: int = 800,
    config: dict[str, object] | None = None,
)
```

**Example:**

```python
scatter = Scatter3D(
    cache_id="precursor_signals",
    data=threedim_sn_lf,
    scan_filter="index",
)
scatter(state_manager=state_manager)
```

**User-visible differences:**

- **Consumes** `scanIndex` (value filter) and `massIndex` (array subscript).
  `massIndex` is **not** a column filter; it indexes nested peak arrays after
  `scanIndex` is applied.
- **No interactivity output.** The component never sets selections.

## InternalFragmentMap

**Purpose:** Internal-fragment map over a peptide/protein sequence.

**Signature:**

```python
InternalFragmentMap(
    cache_id: str,
    sequence_data: pl.LazyFrame | str | None = None,
    sequence_data_path: str | None = None,
    peaks_data: pl.LazyFrame | None = None,
    peaks_data_path: str | None = None,
    filters: dict[str, str] | None = None,
    modifications: list[tuple[int, int, float]] | None = None,
    tolerance: float = 10.0,
    tolerance_ppm: bool = True,
    ion_colors: dict[str, str] | None = None,
    cache_path: str = ".",
    title: str | None = "Internal Fragment Map",
    height: int = 400,
)
```

**Example (FLASHTnT):**

```python
ifm = InternalFragmentMap(
    cache_id="ifm",
    sequence_data=proteoform_lf,  # includes sequence + proteoform_index
    filters={"proteinIndex": "proteoform_index"},
    peaks_data=deconv_peaks_lf,   # optional, used for observed mass filtering
)
ifm(state_manager=state_manager)
```

**Example (FLASHDeconv single sequence):**

```python
ifm = InternalFragmentMap(cache_id="ifm", sequence_data="PEPTIDESEQUENCE")
```

**User-visible differences:**

- **Consumer-only:** uses `filters` to select a sequence but does not emit any
  selection state.
- `sequence_data` can be a **single string** (static sequence) or a frame with a
  `sequence` column.
- Optional `peaks_data` lets Vue hide theoretical fragments that have no
  observed mass within tolerance.

## LinePlot (tagger extension)

The base `LinePlot` interface is unchanged; the following optional arguments
enable tagger parity:

```python
LinePlot(
    # ... existing args ...
    x2_column: str | None = None,
    y2_column: str | None = None,
    highlight2_column: str | None = None,
    annotation2_column: str | None = None,
    signal_peak_column: str | None = None,
    tag_filters: dict[str, str] | None = None,
    tag_mass_column: str | None = None,
    tag_tolerance: float = 1e-5,
)
```

**Example (second series + tag overlay):**

```python
lineplot = LinePlot(
    cache_id="spectrum",
    data=peaks_lf,
    filters={"scanIndex": "scan_id"},
    x_column="MonoMass",
    y_column="SumIntensity",
    x2_column="MonoMass_Anno",
    y2_column="SumIntensity_Anno",
    highlight2_column="IsAnnotated",
    annotation2_column="IonLabel",
    signal_peak_column="IsSignalPeak",
    tag_filters={"selectedTag": "tag_id"},
    tag_mass_column="MonoMass",
    tag_tolerance=1e-5,
)
lineplot(state_manager=state_manager)
```

**User-visible differences:**

- The second series only renders when **both** `x2_column` and `y2_column` are set.
- `tag_filters` expects the selection value to be a **list of masses** (the
  selected tag’s mass list), which is matched against `tag_mass_column`.
- `signal_peak_column` renders a distinct marker for signal membership.

## SequenceView (coverage + fixed modifications)

**Signature additions:** `settings` and `compute_fixed_mods` are now supported.

```python
SequenceView(
    cache_id: str,
    sequence_data: pl.LazyFrame | tuple[str, int] | str | None = None,
    sequence_data_path: str | None = None,
    peaks_data: pl.LazyFrame | None = None,
    peaks_data_path: str | None = None,
    filters: dict[str, str] | None = None,
    interactivity: dict[str, str] | None = None,
    deconvolved: bool = False,
    annotation_config: dict[str, object] | None = None,
    settings: dict[str, object] | None = None,
    compute_fixed_mods: bool = False,
    cache_path: str = ".",
    title: str | None = None,
    height: int = 400,
)
```

**Example (TnT-style settings + coverage):**

```python
sequence_view = SequenceView(
    cache_id="seq_view",
    sequence_data=proteoform_lf,  # may include coverage/maxCoverage columns
    peaks_data=deconv_peaks_lf,
    filters={"proteinIndex": "proteoform_index"},
    settings={"tolerance": 10.0, "ion_types": ["b", "y"]},
)
```

**Example (fixed mods in Deconv mode):**

```python
sequence_view = SequenceView(
    cache_id="seq_view",
    sequence_data=("PEPTIDE", 2),
    peaks_data=peaks_lf,
    compute_fixed_mods=True,
)
```

**User-visible differences:**

- `sequence_data` may include optional **`coverage`** (per-residue list) and
  **`maxCoverage`** (scalar) columns for shading; if absent, no coverage overlay
  is shown (backward compatible).
- `fixed_modifications` can be provided in the data; otherwise setting
  `compute_fixed_mods=True` computes FLASHDeconv-style C/M fixed mods.
- When `settings` is provided, `settings["tolerance"]` overrides the annotation
  tolerance (treated as **ppm**) and `settings["ion_types"]` sets the default
  ion selections in the Vue UI.

## Summary of user-facing handling differences

- **Static vs linked components:** DensityPlot and FeatureView are standalone
  and ignore `filters`/`interactivity`. Scatter3D and InternalFragmentMap
  **consume** selection state but never emit it.
- **Mass-index behavior:** Scatter3D’s `massIndex` acts as an **array subscript**
  into nested peak lists, not a filter on a column.
- **Optional coverage/fixed mods:** SequenceView now consumes optional coverage
  columns and fixed modifications without changing the legacy two-column input.
- **Tagger overlay:** LinePlot can overlay a second series and highlight tags
  using a list-of-masses selection rather than a single scalar selection.
