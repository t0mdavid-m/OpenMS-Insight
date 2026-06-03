"""Plot3D component for 3D scatter/stem visualization using Plotly scatter3d.

Generic 3D scatter component that reproduces FLASHApp's "3D S/N plot" (precursor
Signal/Noise view) while fitting Insight's tidy-long, cache-first contract.

Input is a tidy LazyFrame with ONE ROW PER PLOTTED POINT (the upstream page-side
adapter flattens nested per-scan peak arrays / comma-split strings into rows). The
geometry per point matches the FLASHApp oracle exactly:

    x = mass (= m/z * charge), y = charge, z = intensity.

Two fixed categories ("Signal"/"Noise") are distinguished by a categorical
column and mapped to colors via ``category_colors`` (default Signal ``#3366CC`` /
Noise ``#DC3912``). The categorical-coloring vocabulary (``category_column`` /
``category_colors``) matches Heatmap's so the two components share one naming.
Each point is drawn as a vertical stem (drop line) reproducing the oracle's
stem-triplet construction (baseline -> peak -> baseline).
"""

from typing import Any, Dict, List, Optional

import polars as pl

from ..core.base import BaseComponent
from ..core.registry import register_component
from ..preprocessing.filtering import compute_dataframe_hash, filter_and_collect_cached

# Oracle defaults (Plotly3Dplot.vue) - the visual identity of the plot.
DEFAULT_CATEGORY_COLORS = {"Signal": "#3366CC", "Noise": "#DC3912"}
DEFAULT_CAMERA_EYE = {"x": 2.5, "y": 0, "z": 0.2}
# Default height for this component differs from the global base 400 default;
# the oracle hard-codes 800.
DEFAULT_PLOT3D_HEIGHT = 800


@register_component("plot3d")
class Plot3D(BaseComponent):
    """
    Interactive 3D scatter/stem plot using Plotly scatter3d.

    Reproduces FLASHApp's precursor Signal/Noise 3D plot in a generic,
    tidy-long, cache-first form reusable by any MS viewer.

    Features:
    - Stem (drop-line) rendering reproducing the oracle geometry
    - Per-category traces with fixed Signal/Noise colors
    - Integer charge ticks, fixed camera framing, linear axes
    - Drops non-positive intensity points
    - Selection-driven input via filters (scan/mass narrowing)
    - Optional outgoing interactivity via click -> selection store (off by default)
    - render-time ``trace_mode`` switch (lines / markers / lines+markers) with no
      cache rebuild

    Example:
        plot = Plot3D(
            cache_id="precursor_signals",
            data=tidy_points_df,
            x_column="mass",
            y_column="charge",
            z_column="intensity",
            category_column="series",
            filters={"spectrum": "scan", "mass": "mass_index"},
            filter_defaults={"spectrum": -1},
            title="Precursor Signals",
        )
        plot(state_manager=state, height=800)
    """

    _component_type: str = "plot3d"

    def __init__(
        self,
        cache_id: str,
        x_column: str = "mass",
        y_column: str = "charge",
        z_column: str = "intensity",
        data: Optional[pl.LazyFrame] = None,
        data_path: Optional[str] = None,
        category_column: Optional[str] = None,
        series_column: Optional[str] = None,
        category_name_template: Optional[str] = None,
        filters: Optional[Dict[str, str]] = None,
        filter_defaults: Optional[Dict[str, Any]] = None,
        interactivity: Optional[Dict[str, str]] = None,
        cache_path: str = ".",
        regenerate_cache: bool = False,
        trace_mode: str = "lines",
        title: Optional[str] = None,
        x_label: Optional[str] = None,
        y_label: Optional[str] = None,
        z_label: Optional[str] = None,
        category_colors: Optional[Dict[str, str]] = None,
        drop_nonpositive_z: bool = True,
        stem: bool = True,
        stem_baseline: float = -100000.0,
        y_dtick: float = 1.0,
        y_tick0: float = 0.0,
        camera_eye: Optional[Dict[str, float]] = None,
        log_z: bool = False,
        hover_columns: Optional[List[str]] = None,
        optional_filters: Optional[List[str]] = None,
        **kwargs,
    ):
        """
        Initialize the Plot3D component.

        Args:
            cache_id: Unique identifier for this component's cache (MANDATORY).
                Creates a folder {cache_path}/{cache_id}/ for cached data.
            x_column: Column for the x-axis (neutral mass). Default "mass".
            y_column: Column for the y-axis (charge state). Default "charge".
            z_column: Column for the z-axis (intensity). Default "intensity".
            data: Polars LazyFrame with tidy point data (one row per point).
                Optional if cache exists.
            data_path: Path to parquet file (preferred for large datasets).
            category_column: Optional categorical column mapping each point to a
                category ("Signal"/"Noise"). One scatter3d trace is drawn per
                distinct value, colored via ``category_colors``. Same
                categorical-coloring vocabulary as Heatmap.
            series_column: Optional column identifying sub-traces WITHIN each
                category (e.g. isotope index within a charge). Default None
                (current behavior: one continuous polyline per category). When
                set, the line BREAKS between consecutive distinct series values
                within the same category (a NaN gap is inserted) so independent
                sub-traces do not connect — while still emitting ONE trace per
                category (legend/color stay per-category). The data is stably
                sorted by ``[category_column, series_column]`` so each series'
                points are contiguous, without disturbing within-series order.
                Data-shaping (affects the emitted geometry/ordering).
            category_name_template: Optional template for the trace legend name.
                Default None (legend shows the bare category value). When set,
                each trace's name is ``category_name_template.replace("{}",
                category)`` (e.g. ``"Charge: {}"`` -> ``"Charge: 2"``).
                Presentation config (not hash-affecting).
            filters: Mapping of identifier names to column names for filtering.
                Example: {'spectrum': 'scan', 'mass': 'mass_index'}.
            filter_defaults: Default values for filters when no selection is
                present. Example: {'spectrum': -1} yields an empty frame when no
                scan is selected (parity with the oracle).
            interactivity: Mapping of identifier names to column names for clicks.
                Off by default (oracle emits no selection). When provided, a click
                routes the point's value into the selection store.
            cache_path: Base path for cache storage. Default "." (current dir).
            regenerate_cache: If True, regenerate cache even if valid cache exists.
            trace_mode: Plotly trace mode, render-time-overridable via __call__.
                One of "lines" | "markers" | "lines+markers". Default "lines".
                (Named ``trace_mode`` — not ``mode`` — so the word ``mode`` is
                reserved for cache-time variant selectors like LinePlot's.)
            title: Plot title. Default None (parity recipe passes
                "Precursor Signals").
            x_label: X-axis label. Default "Mass".
            y_label: Y-axis label. Default "Charge".
            z_label: Z-axis label. Default "Intensity".
            category_colors: Mapping of category value -> color. Default
                {"Signal": "#3366CC", "Noise": "#DC3912"}.
            drop_nonpositive_z: If True (default), drop points with z <= 0
                (oracle behavior).
            stem: If True (default), render each point as a vertical stem
                (drop line) using the oracle stem-triplet construction.
            stem_baseline: Baseline z value for stem triplets. Default -100000.0
                (oracle magic baseline, clipped by the z-axis range).
            y_dtick: y-axis tick spacing. Default 1.0 (integer charge ticks).
            y_tick0: y-axis tick origin. Default 0.0.
            camera_eye: Initial scene camera eye. Default
                {"x": 2.5, "y": 0, "z": 0.2}.
            log_z: If True, log10-transform z. Default False (parity = linear).
            hover_columns: Extra tidy columns surfaced on hover.
            **kwargs: Additional configuration options.
        """
        self._x_column = x_column
        self._y_column = y_column
        self._z_column = z_column
        self._category_column = category_column
        self._series_column = series_column
        self._category_name_template = category_name_template
        self._title = title
        self._x_label = x_label or "Mass"
        self._y_label = y_label or "Charge"
        self._z_label = z_label or "Intensity"
        self._category_colors = category_colors or dict(DEFAULT_CATEGORY_COLORS)
        self._drop_nonpositive_z = drop_nonpositive_z
        self._stem = stem
        self._stem_baseline = stem_baseline
        self._y_dtick = y_dtick
        self._y_tick0 = y_tick0
        self._camera_eye = camera_eye or dict(DEFAULT_CAMERA_EYE)
        self._log_z = log_z
        self._hover_columns = hover_columns or []
        # Identifiers (subset of filters) skipped when their selection is None, so
        # the plot shows all rows for the required filters and only narrows when the
        # optional selection is set (e.g. show all of a scan's masses until a mass
        # is clicked). Not hash-affecting (the full point set is still cached).
        self._optional_filters = optional_filters or []

        # Render-time trace-mode value (set in __call__). Default = oracle "lines".
        self._current_trace_mode = trace_mode

        super().__init__(
            cache_id=cache_id,
            data=data,
            data_path=data_path,
            filters=filters,
            filter_defaults=filter_defaults,
            interactivity=interactivity,
            cache_path=cache_path,
            regenerate_cache=regenerate_cache,
            **kwargs,
        )

    def _validate_columns(self, schema: pl.Schema) -> None:
        """Validate that required (and optional) columns exist in the schema."""
        available = set(schema.names())

        required = [self._x_column, self._y_column, self._z_column]
        missing = [col for col in required if col not in available]
        if missing:
            raise ValueError(
                f"Missing required columns: {missing}. "
                f"Available columns: {sorted(available)}"
            )

        if self._category_column and self._category_column not in available:
            raise ValueError(
                f"Category column '{self._category_column}' not found. "
                f"Available columns: {sorted(available)}"
            )

        if self._series_column and self._series_column not in available:
            raise ValueError(
                f"Series column '{self._series_column}' not found. "
                f"Available columns: {sorted(available)}"
            )

        for col in self._hover_columns:
            if col not in available:
                raise ValueError(
                    f"Hover column '{col}' not found. "
                    f"Available columns: {sorted(available)}"
                )

    def _get_cache_config(self) -> Dict[str, Any]:
        """Get HASH-AFFECTING (data-shaping) configuration.

        Only the columns and the drop/log transforms affect the cached point
        set / geometry. Presentational config (labels, colors, stem framing,
        camera) is render-time and lives in ``_get_render_config()`` so changing
        it does not invalidate the cached points.
        """
        return {
            # Data-shaping (affects cached point set / geometry)
            "x_column": self._x_column,
            "y_column": self._y_column,
            "z_column": self._z_column,
            "category_column": self._category_column,
            "series_column": self._series_column,
            "drop_nonpositive_z": self._drop_nonpositive_z,
            "log_z": self._log_z,
            "hover_columns": self._hover_columns,
            # Note: trace_mode is NOT included - it's a render-time param
        }

    def _get_render_config(self) -> Dict[str, Any]:
        """Presentation config: stored for reconstruction, excluded from hash."""
        return {
            "title": self._title,
            "x_label": self._x_label,
            "y_label": self._y_label,
            "z_label": self._z_label,
            "category_colors": self._category_colors,
            "category_name_template": self._category_name_template,
            "stem": self._stem,
            "stem_baseline": self._stem_baseline,
            "y_dtick": self._y_dtick,
            "y_tick0": self._y_tick0,
            "camera_eye": self._camera_eye,
            "optional_filters": self._optional_filters,
        }

    def _restore_cache_config(self, config: Dict[str, Any]) -> None:
        """Restore data-shaping configuration from cached config."""
        self._x_column = config.get("x_column", "mass")
        self._y_column = config.get("y_column", "charge")
        self._z_column = config.get("z_column", "intensity")
        self._category_column = config.get("category_column")
        self._series_column = config.get("series_column")
        self._drop_nonpositive_z = config.get("drop_nonpositive_z", True)
        self._log_z = config.get("log_z", False)
        self._hover_columns = config.get("hover_columns", [])

    def _restore_render_config(self, config: Dict[str, Any]) -> None:
        """Restore presentation configuration from cached config."""
        self._title = config.get("title")
        self._x_label = config.get("x_label", "Mass")
        self._y_label = config.get("y_label", "Charge")
        self._z_label = config.get("z_label", "Intensity")
        self._category_colors = config.get(
            "category_colors", dict(DEFAULT_CATEGORY_COLORS)
        )
        self._category_name_template = config.get("category_name_template")
        self._stem = config.get("stem", True)
        self._stem_baseline = config.get("stem_baseline", -100000.0)
        self._y_dtick = config.get("y_dtick", 1.0)
        self._y_tick0 = config.get("y_tick0", 0.0)
        self._camera_eye = config.get("camera_eye", dict(DEFAULT_CAMERA_EYE))
        self._optional_filters = config.get("optional_filters", [])

    def _select_columns(self) -> List[str]:
        """Build the de-duplicated list of tidy columns to keep."""
        cols = [self._x_column, self._y_column, self._z_column]
        if self._category_column:
            cols.append(self._category_column)
        if self._series_column:
            cols.append(self._series_column)
        cols += list((self._interactivity or {}).values())
        cols += list((self._filters or {}).values())
        cols += self._hover_columns
        # De-duplicate while preserving order
        return list(dict.fromkeys(cols))

    def _preprocess(self) -> None:
        """Preprocess tidy point data.

        Selects the needed columns, drops non-positive intensity points (oracle
        behavior), and optionally log10-transforms z. One row per point is kept;
        stem-triplet expansion happens client-side at render time.
        """
        if self._raw_data is None:
            raise ValueError("No data provided and no cache exists")

        self._validate_columns(self._raw_data.collect_schema())

        schema_names = self._raw_data.collect_schema().names()
        cols = [c for c in self._select_columns() if c in schema_names]
        lf = self._raw_data.select(cols)

        if self._drop_nonpositive_z:
            lf = lf.filter(pl.col(self._z_column) > 0)

        if self._log_z:
            lf = lf.with_columns(
                pl.col(self._z_column).log(10).alias(self._z_column)
            )

        # When sub-trace breaks are requested, stably sort so each series' points
        # are contiguous within its category, WITHOUT disturbing within-series
        # order (RT order from the schema explode). Only the category/series keys
        # are sort keys; ``maintain_order=True`` keeps equal-key rows in their
        # existing order. The Vue trace loop then inserts a NaN gap at each
        # series boundary (within a category) to break the line. Sorting here
        # bakes the ordering into the cache (and round-trips via series_column in
        # the cache config); polars filter/select preserve row order downstream.
        if self._series_column:
            sort_keys = []
            if self._category_column:
                sort_keys.append(self._category_column)
            sort_keys.append(self._series_column)
            lf = lf.sort(sort_keys, maintain_order=True)

        self._preprocessed_data = {"plot3dData": lf.collect()}

    def _get_vue_component_name(self) -> str:
        """Return the Vue component name."""
        return "Plotly3D"

    def _get_data_key(self) -> str:
        """Return the key used to send primary data to Vue."""
        return "plot3dData"

    def _prepare_vue_data(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Prepare filtered tidy data for the Vue component.

        Applies scan/mass narrowing via filters (matching the oracle's
        selection-driven input). Returns a pandas DataFrame for Arrow transfer.
        """
        if not self._preprocessed_data:
            self._load_from_cache()

        data = self._preprocessed_data["plot3dData"]
        df = data.collect() if isinstance(data, pl.LazyFrame) else data

        columns = self._select_columns()

        if self._filters:
            df_pandas, data_hash = filter_and_collect_cached(
                df.lazy(),
                self._filters,
                state,
                columns=columns,
                filter_defaults=self._filter_defaults,
                optional_filters=self._optional_filters,
            )
            return {"plot3dData": df_pandas, "_hash": data_hash}

        available = [c for c in columns if c in df.columns]
        sub = df.select(available)
        data_hash = compute_dataframe_hash(sub)
        return {"plot3dData": sub.to_pandas(), "_hash": data_hash}

    def _get_component_args(self) -> Dict[str, Any]:
        """Return configuration for the Vue component (camelCase keys)."""
        return {
            "componentType": self._get_vue_component_name(),
            "xColumn": self._x_column,
            "yColumn": self._y_column,
            "zColumn": self._z_column,
            "categoryColumn": self._category_column,
            "seriesColumn": self._series_column,
            "categoryColors": self._category_colors,
            "categoryNameTemplate": self._category_name_template,
            "traceMode": self._current_trace_mode,
            "stem": self._stem,
            "stemBaseline": self._stem_baseline,
            "title": self._title,
            "xLabel": self._x_label or "Mass",
            "yLabel": self._y_label or "Charge",
            "zLabel": self._z_label or "Intensity",
            "yDtick": self._y_dtick,
            "yTick0": self._y_tick0,
            "cameraEye": self._camera_eye or dict(DEFAULT_CAMERA_EYE),
            "logZ": self._log_z,
            "hoverColumns": self._hover_columns or [],
            "interactivity": self._interactivity or {},
            "height": DEFAULT_PLOT3D_HEIGHT,
        }

    def __call__(
        self,
        key: Optional[str] = None,
        state_manager: Optional[Any] = None,
        height: Optional[int] = None,
        trace_mode: Optional[str] = None,
    ) -> Any:
        """
        Render the Plot3D component.

        Args:
            key: Optional unique key for this component instance.
            state_manager: StateManager for cross-component linking.
            height: Optional height override in pixels (component default 800).
            trace_mode: Optional render-time trace mode override
                ("lines" | "markers" | "lines+markers"). Does not invalidate
                the cache.

        Returns:
            Component result for Streamlit rendering.
        """
        if trace_mode is not None:
            self._current_trace_mode = trace_mode

        # Component default height differs from the base 400 default.
        if height is None:
            height = DEFAULT_PLOT3D_HEIGHT

        return super().__call__(key=key, state_manager=state_manager, height=height)
