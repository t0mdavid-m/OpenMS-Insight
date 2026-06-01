"""Density (KDE) plot component using Plotly.js.

Renders one or more kernel-density-estimate curves in a single figure. The
canonical use case is a target-vs-decoy score distribution (FLASH FDR plot),
but the component is generic: any value column split into named series by an
optional series column produces one smooth density line per series.

The KDE is computed once at preprocessing time with
``scipy.stats.gaussian_kde`` over a fixed-size linear grid, so the cached
payload is tiny (``grid_points`` rows per series) regardless of input size.
The plot is static — it declares no ``filters`` or ``interactivity`` and does
not participate in cross-component selection.
"""

from typing import Any, Dict, List, Optional

import polars as pl

from ..core.base import BaseComponent
from ..core.registry import register_component


@register_component("densityplot")
class DensityPlot(BaseComponent):
    """
    Interactive kernel-density-estimate plot using Plotly.js.

    Features:
    - One smooth density curve per series (e.g. target vs decoy)
    - KDE computed at cache time over a fixed grid (constant payload size)
    - Per-series color and legend label configuration
    - Gracefully handles empty / degenerate series (e.g. no decoys)
    - SVG export

    The component is static: it does not filter on, or write, any selection
    state. Pass already-split data (a ``value_column`` plus an optional
    ``series_column``) and the densities are precomputed.

    Example:
        # Target/decoy FDR plot (FLASHDeconv: Qscore; FLASHTnT: q-value)
        density = DensityPlot(
            cache_id="fdr_plot",
            data=scores_df,                 # columns: score, series
            value_column="score",
            series_column="series",         # values e.g. "Target" / "Decoy"
            series_config={
                "Target": {"label": "Target QScores", "color": "green"},
                "Decoy": {"label": "Decoy QScores", "color": "red"},
            },
            title="FDR Plot",
            x_label="QScore",
            y_label="Density",
        )
        density(key="fdr", state_manager=state_manager)
    """

    _component_type: str = "densityplot"

    def __init__(
        self,
        cache_id: str,
        data: Optional[pl.LazyFrame] = None,
        data_path: Optional[str] = None,
        cache_path: str = ".",
        regenerate_cache: bool = False,
        value_column: str = "value",
        series_column: Optional[str] = None,
        series_config: Optional[Dict[str, Dict[str, Any]]] = None,
        grid_points: int = 200,
        precomputed: bool = False,
        x_curve_column: str = "x",
        y_curve_column: str = "y",
        default_series_name: str = "Density",
        title: Optional[str] = None,
        x_label: Optional[str] = None,
        y_label: str = "Density",
        show_markers: bool = True,
        config: Optional[Dict[str, Any]] = None,
        **kwargs,
    ):
        """
        Initialize the DensityPlot component.

        Args:
            cache_id: Unique identifier for this component's cache (MANDATORY).
                Creates a folder {cache_path}/{cache_id}/ for cached data.
            data: Polars LazyFrame with the raw values. Optional if cache exists.
                Must contain ``value_column`` and (if used) ``series_column``.
            data_path: Path to parquet file (preferred for large datasets).
            cache_path: Base path for cache storage. Default "." (current dir).
            regenerate_cache: If True, regenerate cache even if valid cache exists.
            value_column: Column holding the scalar values to estimate density over
                (e.g. "Qscore", "ProteoformLevelQvalue").
            series_column: Optional column whose distinct values split the data
                into separate density curves (e.g. a "Target"/"Decoy" label). If
                None, all rows form a single series named ``default_series_name``.
            series_config: Optional per-series presentation config keyed by the
                series value. Each entry may contain:
                    - "label": legend label (defaults to the series value)
                    - "color": line/marker color (CSS color string)
                The key order also defines trace draw/legend order; series present
                in the data but absent here are appended afterwards (sorted).
            grid_points: Number of evenly spaced points to evaluate the KDE on
                (default: 200, matching the FLASHApp FDR plot).
            precomputed: If True, the input already holds density CURVE points
                (``x_curve_column``/``y_curve_column``) per series — no KDE is
                run; the curves are passed through verbatim. Use this for caches
                that already store computed ``{x, y}`` densities (e.g. FLASHApp's
                ``density_target``/``density_decoy``). When True, ``series_column``
                identifies the series and ``value_column`` is ignored.
            x_curve_column: With ``precomputed``, the x (grid) column. Default "x".
            y_curve_column: With ``precomputed``, the y (density) column. Default "y".
            default_series_name: Series name used when ``series_column`` is None.
            title: Plot title displayed above the figure.
            x_label: X-axis label (defaults to ``value_column``).
            y_label: Y-axis label (default: "Density").
            show_markers: If True (default), draw "lines+markers"; else "lines".
            config: Additional Plotly config options.
            **kwargs: Additional configuration options forwarded to Vue args.
        """
        self._value_column = value_column
        self._series_column = series_column
        self._series_config = series_config or {}
        self._grid_points = grid_points
        self._precomputed = precomputed
        self._x_curve_column = x_curve_column
        self._y_curve_column = y_curve_column
        self._default_series_name = default_series_name
        self._title = title
        self._x_label = x_label or value_column
        self._y_label = y_label
        self._show_markers = show_markers
        self._plot_config = config or {}

        super().__init__(
            cache_id=cache_id,
            data=data,
            data_path=data_path,
            filters=None,
            interactivity=None,
            cache_path=cache_path,
            regenerate_cache=regenerate_cache,
            # Component-specific params for subprocess recreation
            value_column=value_column,
            series_column=series_column,
            series_config=series_config,
            grid_points=grid_points,
            precomputed=precomputed,
            x_curve_column=x_curve_column,
            y_curve_column=y_curve_column,
            default_series_name=default_series_name,
            title=title,
            x_label=x_label,
            y_label=y_label,
            show_markers=show_markers,
            config=config,
            **kwargs,
        )

    def _get_cache_config(self) -> Dict[str, Any]:
        """Get configuration that affects cache validity."""
        return {
            "value_column": self._value_column,
            "series_column": self._series_column,
            "series_config": self._series_config,
            "grid_points": self._grid_points,
            "precomputed": self._precomputed,
            "x_curve_column": self._x_curve_column,
            "y_curve_column": self._y_curve_column,
            "default_series_name": self._default_series_name,
            "title": self._title,
            "x_label": self._x_label,
            "y_label": self._y_label,
            "show_markers": self._show_markers,
            "plot_config": self._plot_config,
        }

    def _restore_cache_config(self, config: Dict[str, Any]) -> None:
        """Restore component-specific configuration from cached config."""
        self._value_column = config.get("value_column", "value")
        self._series_column = config.get("series_column")
        self._series_config = config.get("series_config") or {}
        self._grid_points = config.get("grid_points", 200)
        self._precomputed = config.get("precomputed", False)
        self._x_curve_column = config.get("x_curve_column", "x")
        self._y_curve_column = config.get("y_curve_column", "y")
        self._default_series_name = config.get("default_series_name", "Density")
        self._title = config.get("title")
        self._x_label = config.get("x_label", self._value_column)
        self._y_label = config.get("y_label", "Density")
        self._show_markers = config.get("show_markers", True)
        self._plot_config = config.get("plot_config", {})

    def _validate_mappings(self) -> None:
        """Validate that value/series columns exist in the data schema."""
        super()._validate_mappings()
        if self._raw_data is None:
            return

        column_names = self._raw_data.collect_schema().names()
        if self._precomputed:
            # Curve-passthrough mode: need the x/y curve columns, not value_column.
            for col, label in [
                (self._x_curve_column, "x_curve_column"),
                (self._y_curve_column, "y_curve_column"),
            ]:
                if col not in column_names:
                    raise ValueError(
                        f"{label} '{col}' not found in data. "
                        f"Available columns: {column_names}"
                    )
        elif self._value_column not in column_names:
            raise ValueError(
                f"value_column '{self._value_column}' not found in data. "
                f"Available columns: {column_names}"
            )
        if self._series_column and self._series_column not in column_names:
            raise ValueError(
                f"series_column '{self._series_column}' not found in data. "
                f"Available columns: {column_names}"
            )

    def _series_order(self, present: List[Any]) -> List[Any]:
        """Order series: configured keys first (in config order), then the rest
        (sorted) so output is deterministic and respects user-specified ordering."""
        present_set = list(dict.fromkeys(present))  # dedupe, preserve order
        ordered: List[Any] = []
        for key in self._series_config.keys():
            if key in present_set:
                ordered.append(key)
        for key in sorted(
            (s for s in present_set if s not in ordered), key=lambda v: str(v)
        ):
            ordered.append(key)
        return ordered

    def _compute_density(self, values: List[float]) -> Dict[str, List[float]]:
        """Compute a KDE curve for one series.

        Returns a dict with parallel ``x`` and ``y`` lists of length
        ``grid_points``. Degenerate input (fewer than 2 finite values, or zero
        variance — which makes the Gaussian kernel singular) yields empty lists,
        so the frontend simply draws nothing for that series. This mirrors the
        FLASHApp behavior of an empty decoy frame when no decoys exist.
        """
        import numpy as np

        arr = np.asarray(values, dtype="float64")
        arr = arr[np.isfinite(arr)]
        if arr.size < 2:
            return {"x": [], "y": []}

        vmin = float(arr.min())
        vmax = float(arr.max())
        # gaussian_kde inverts the covariance matrix; zero variance (all-equal
        # values, vmin == vmax) is singular and raises LinAlgError. Skip it.
        if vmax <= vmin:
            return {"x": [], "y": []}

        from scipy.stats import gaussian_kde

        try:
            kde = gaussian_kde(arr)
        except Exception:
            # np.linalg.LinAlgError (singular covariance) or any other numerical
            # failure -> treat as an empty series rather than crashing the cache.
            return {"x": [], "y": []}

        grid = np.linspace(vmin, vmax, self._grid_points)
        density = kde(grid)
        return {"x": grid.tolist(), "y": density.tolist()}

    def _preprocess_precomputed(self, df: "pl.DataFrame") -> None:
        """Pass through already-computed density curves (no KDE).

        Input rows are curve points: ``x_curve_column`` / ``y_curve_column``
        (and ``series_column`` to split). Produces the same {series, x, y}
        long-format output as the KDE path so the Vue side is identical.
        Empty series simply contribute no rows.
        """
        if self._series_column is not None and self._series_column in df.columns:
            present = df.select(pl.col(self._series_column)).to_series().to_list()
            order = self._series_order(present)
        else:
            order = [self._default_series_name]

        series_names: List[str] = []
        xs: List[float] = []
        ys: List[float] = []
        for key in order:
            if self._series_column is not None and self._series_column in df.columns:
                group = df.filter(pl.col(self._series_column) == key)
            else:
                group = df
            if group.height == 0:
                continue
            gx = group.select(pl.col(self._x_curve_column)).to_series().to_list()
            gy = group.select(pl.col(self._y_curve_column)).to_series().to_list()
            label = str(key)
            for x_val, y_val in zip(gx, gy):
                if x_val is None or y_val is None:
                    continue
                series_names.append(label)
                xs.append(float(x_val))
                ys.append(float(y_val))

        density_df = pl.DataFrame(
            {"series": series_names, "x": xs, "y": ys},
            schema={"series": pl.Utf8, "x": pl.Float64, "y": pl.Float64},
        )
        non_empty_order = [
            str(key) for key in order if str(key) in set(series_names)
        ]
        self._preprocessed_data["densityData"] = density_df
        self._preprocessed_data["series_order"] = non_empty_order

    def _preprocess(self) -> None:
        """Compute per-series KDE curves and store as a long-format frame.

        Output schema (one row per (series, grid point)):
            - series: Utf8  (series label)
            - x: Float64    (grid value)
            - y: Float64    (estimated density)
        """
        df = self._raw_data.collect()

        if self._precomputed:
            self._preprocess_precomputed(df)
            return

        # Partition rows into series
        if self._series_column is not None:
            series_values = (
                df.select(pl.col(self._series_column))
                .to_series()
                .to_list()
            )
            order = self._series_order(series_values)
            groups = {
                key: df.filter(pl.col(self._series_column) == key)
                for key in order
            }
        else:
            order = [self._default_series_name]
            groups = {self._default_series_name: df}

        series_names: List[str] = []
        xs: List[float] = []
        ys: List[float] = []
        for key in order:
            group = groups[key]
            values = group.select(pl.col(self._value_column)).to_series().to_list()
            curve = self._compute_density(values)
            label = str(key)
            for x_val, y_val in zip(curve["x"], curve["y"]):
                series_names.append(label)
                xs.append(x_val)
                ys.append(y_val)

        density_df = pl.DataFrame(
            {
                "series": series_names,
                "x": xs,
                "y": ys,
            },
            schema={"series": pl.Utf8, "x": pl.Float64, "y": pl.Float64},
        )

        # Record the series draw order (after dropping empty ones) so the
        # frontend can color/label and order traces deterministically.
        non_empty_order = [
            str(key) for key in order if str(key) in set(series_names)
        ]

        self._preprocessed_data["densityData"] = density_df
        self._preprocessed_data["series_order"] = non_empty_order

    def _get_vue_component_name(self) -> str:
        """Return the Vue component name."""
        return "PlotlyDensity"

    def _get_data_key(self) -> str:
        """Return the key used to send primary data to Vue."""
        return "densityData"

    def _prepare_vue_data(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Return the precomputed density curves.

        The data is static (no filtering), so ``state`` is ignored.
        """
        from ..preprocessing.filtering import compute_dataframe_hash

        data = self._preprocessed_data.get("densityData")
        if data is None:
            # Defensive: empty frame with the expected schema
            empty = pl.DataFrame(
                schema={"series": pl.Utf8, "x": pl.Float64, "y": pl.Float64}
            )
            return {"densityData": empty.to_pandas(), "_hash": ""}

        if isinstance(data, pl.LazyFrame):
            data = data.collect()

        data_hash = compute_dataframe_hash(data)
        return {"densityData": data.to_pandas(), "_hash": data_hash}

    def get_state_dependencies(self) -> List[str]:
        """Static plot — no state affects its data."""
        return []

    def _series_presentation(self) -> List[Dict[str, Any]]:
        """Build ordered per-series presentation (name, label, color) for Vue."""
        # Prefer the cached non-empty order; fall back to config / data order.
        order = self._preprocessed_data.get("series_order")
        if not order:
            order = [str(k) for k in self._series_config.keys()]
        # Default qualitative palette (target green / decoy red lead, matching
        # the FLASHApp FDR plot, then a few generic follow-ups).
        default_palette = [
            "green",
            "red",
            "#3366CC",
            "#FF9900",
            "#990099",
            "#0099C6",
        ]
        presentation: List[Dict[str, Any]] = []
        for idx, name in enumerate(order):
            cfg = self._series_config.get(name, {})
            presentation.append(
                {
                    "name": name,
                    "label": cfg.get("label", name),
                    "color": cfg.get("color", default_palette[idx % len(default_palette)]),
                }
            )
        return presentation

    def _get_component_args(self) -> Dict[str, Any]:
        """Get component arguments to send to Vue."""
        args: Dict[str, Any] = {
            "componentType": self._get_vue_component_name(),
            "title": self._title or "",
            "xLabel": self._x_label,
            "yLabel": self._y_label,
            "showMarkers": self._show_markers,
            "series": self._series_presentation(),
            "config": self._plot_config,
        }
        # Only inject forwarded kwargs not already set, so self._config (which
        # includes title/columns passed to super().__init__) can't clobber an
        # explicit arg with a None passthrough.
        for key, val in self._config.items():
            if key not in args:
                args[key] = val
        return args
