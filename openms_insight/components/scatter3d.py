"""3D scatter / signal-stick plot component using Plotly.js.

Ports FLASHApp's ``Plotly3Dplot`` ("Precursor Signals" S/N view) into a
reusable OpenMS-Insight component. The plot draws per-peak vertical sticks in
3D space — mass (x) vs charge (y) vs intensity (z) — split into a Signal
series and a Noise series.

Unlike the array-per-scan representation FLASHApp used (``SignalPeaks`` as a
nested ``[mass][peak][mz, charge, intensity, ...]`` array filtered by row
index), this component consumes **long format**: one row per peak, with
explicit ``scan_id`` / ``mass_id`` columns so it can be filtered by column
value through the standard ``filters`` mechanism. The two cross-link
identifiers mirror ``update.py:135-147``:

- ``scanIndex`` selects the scan whose peaks are shown.
- ``massIndex`` (optional) further isolates a single mass's signal/noisy peaks.

There is no zoom compression — 3D navigation is camera-based.
"""

from typing import Any, Dict, List, Optional

import polars as pl

from ..core.base import BaseComponent
from ..core.registry import register_component
from ..preprocessing.filtering import filter_and_collect_cached


@register_component("scatter3d")
class Scatter3D(BaseComponent):
    """
    Interactive 3D signal/noise stick plot using Plotly scatter3d.

    Each peak is drawn as a vertical line from the baseline up to its
    intensity, colored by whether it is a signal or noise peak. Designed to
    reproduce FLASHApp's precursor-signal S/N view.

    Expected long-format input columns (configurable via *_column args):
        - scan_id:   scan/spectrum identifier (filter target for ``scanIndex``)
        - mass_id:   per-scan mass index (optional filter for ``massIndex``)
        - mz:        m/z (or mass) — x-axis
        - charge:    charge state — y-axis
        - intensity: peak intensity — z-axis
        - kind:      "signal" or "noise" (string) — trace split / color

    Example:
        plot = Scatter3D(
            cache_id="precursor_signals",
            data=peaks_long_df,
            filters={"scanIndex": "scan_id", "massIndex": "mass_id"},
            filter_defaults={"massIndex": -1},     # show all masses by default
            title="Precursor Signals",
        )
        plot(key="sn3d", state_manager=state_manager)
    """

    _component_type: str = "scatter3d"

    def __init__(
        self,
        cache_id: str,
        data: Optional[pl.LazyFrame] = None,
        data_path: Optional[str] = None,
        filters: Optional[Dict[str, str]] = None,
        filter_defaults: Optional[Dict[str, Any]] = None,
        optional_filters: Optional[Dict[str, str]] = None,
        interactivity: Optional[Dict[str, str]] = None,
        cache_path: str = ".",
        regenerate_cache: bool = False,
        mz_column: str = "mz",
        charge_column: str = "charge",
        intensity_column: str = "intensity",
        kind_column: str = "kind",
        signal_value: str = "signal",
        noise_value: str = "noise",
        signal_color: str = "#3366CC",
        noise_color: str = "#DC3912",
        title: Optional[str] = None,
        x_label: str = "Mass",
        y_label: str = "Charge",
        z_label: str = "Intensity",
        config: Optional[Dict[str, Any]] = None,
        **kwargs,
    ):
        """
        Initialize the Scatter3D component.

        Args:
            cache_id: Unique identifier for this component's cache (MANDATORY).
            data: Polars LazyFrame in long format (one row per peak). Optional
                if cache exists.
            data_path: Path to parquet file (preferred for large datasets).
            filters: Mapping of identifier names to column names for *required*
                filtering. Typically {"scanIndex": "scan_id"}. A required filter
                with no selection yields an empty result (await-selection).
            filter_defaults: Default values for filters when state is None.
            optional_filters: Mapping of identifier names to column names that are
                applied ONLY when their state value is present; when absent they
                are skipped (the result is NOT emptied). Use this for the 3D
                plot's "optional massIndex" — show every mass for the selected
                scan, and isolate one mass only when massIndex is also selected.
                Typically {"massIndex": "mass_id"}.
            interactivity: Optional click mapping (usually unused for 3D nav).
            cache_path: Base path for cache storage. Default "." (current dir).
            regenerate_cache: If True, regenerate cache even if valid cache exists.
            mz_column: Column for the x-axis (m/z or mass). Default "mz".
            charge_column: Column for the y-axis (charge). Default "charge".
            intensity_column: Column for the z-axis (intensity). Default "intensity".
            kind_column: Column distinguishing signal vs noise. Default "kind".
            signal_value: Value in kind_column marking signal peaks. Default "signal".
            noise_value: Value in kind_column marking noise peaks. Default "noise".
            signal_color: Color for the Signal trace. Default "#3366CC".
            noise_color: Color for the Noise trace. Default "#DC3912".
            title: Plot title.
            x_label: X-axis (scene) label. Default "Mass".
            y_label: Y-axis (scene) label. Default "Charge".
            z_label: Z-axis (scene) label. Default "Intensity".
            config: Additional Plotly config options.
            **kwargs: Additional configuration options forwarded to Vue args.
        """
        self._optional_filters = optional_filters or {}
        self._mz_column = mz_column
        self._charge_column = charge_column
        self._intensity_column = intensity_column
        self._kind_column = kind_column
        self._signal_value = signal_value
        self._noise_value = noise_value
        self._signal_color = signal_color
        self._noise_color = noise_color
        self._title = title
        self._x_label = x_label
        self._y_label = y_label
        self._z_label = z_label
        self._plot_config = config or {}

        super().__init__(
            cache_id=cache_id,
            data=data,
            data_path=data_path,
            filters=filters,
            filter_defaults=filter_defaults,
            interactivity=interactivity,
            cache_path=cache_path,
            regenerate_cache=regenerate_cache,
            mz_column=mz_column,
            charge_column=charge_column,
            intensity_column=intensity_column,
            kind_column=kind_column,
            signal_value=signal_value,
            noise_value=noise_value,
            signal_color=signal_color,
            noise_color=noise_color,
            title=title,
            x_label=x_label,
            y_label=y_label,
            z_label=z_label,
            config=config,
            optional_filters=optional_filters,
            **kwargs,
        )

    def _get_cache_config(self) -> Dict[str, Any]:
        return {
            "optional_filters": self._optional_filters,
            "mz_column": self._mz_column,
            "charge_column": self._charge_column,
            "intensity_column": self._intensity_column,
            "kind_column": self._kind_column,
            "signal_value": self._signal_value,
            "noise_value": self._noise_value,
            "signal_color": self._signal_color,
            "noise_color": self._noise_color,
            "title": self._title,
            "x_label": self._x_label,
            "y_label": self._y_label,
            "z_label": self._z_label,
            "plot_config": self._plot_config,
        }

    def _restore_cache_config(self, config: Dict[str, Any]) -> None:
        self._optional_filters = config.get("optional_filters", {})
        self._mz_column = config.get("mz_column", "mz")
        self._charge_column = config.get("charge_column", "charge")
        self._intensity_column = config.get("intensity_column", "intensity")
        self._kind_column = config.get("kind_column", "kind")
        self._signal_value = config.get("signal_value", "signal")
        self._noise_value = config.get("noise_value", "noise")
        self._signal_color = config.get("signal_color", "#3366CC")
        self._noise_color = config.get("noise_color", "#DC3912")
        self._title = config.get("title")
        self._x_label = config.get("x_label", "Mass")
        self._y_label = config.get("y_label", "Charge")
        self._z_label = config.get("z_label", "Intensity")
        self._plot_config = config.get("plot_config", {})

    def _get_row_group_size(self) -> int:
        """Smaller row groups when filtered for better predicate pushdown."""
        return 10_000 if self._filters else 50_000

    def _validate_mappings(self) -> None:
        super()._validate_mappings()
        if self._raw_data is None:
            return
        column_names = self._raw_data.collect_schema().names()
        for col, label in [
            (self._mz_column, "mz_column"),
            (self._charge_column, "charge_column"),
            (self._intensity_column, "intensity_column"),
            (self._kind_column, "kind_column"),
        ]:
            if col not in column_names:
                raise ValueError(
                    f"{label} '{col}' not found in data. "
                    f"Available columns: {column_names}"
                )
        for identifier, col in self._optional_filters.items():
            if col not in column_names:
                raise ValueError(
                    f"optional_filters column '{col}' for identifier "
                    f"'{identifier}' not found in data. "
                    f"Available columns: {column_names}"
                )

    def get_state_dependencies(self) -> List[str]:
        """Required + optional filter identifiers all affect this plot's data."""
        deps = list(self._filters.keys())
        deps.extend(self._optional_filters.keys())
        return deps

    def _preprocess(self) -> None:
        """Sort by filter columns for predicate pushdown; keep lazy for streaming."""
        data = self._raw_data
        sort_columns = list(self._filters.values()) + list(
            self._optional_filters.values()
        )
        if sort_columns:
            data = data.sort(sort_columns)
        self._preprocessed_data["data"] = data

    def _get_vue_component_name(self) -> str:
        return "Plotly3DScatter"

    def _get_data_key(self) -> str:
        return "scatter3dData"

    def _prepare_vue_data(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Filter peaks to the selected scan (and optional mass) and return long format."""
        columns = [
            self._mz_column,
            self._charge_column,
            self._intensity_column,
            self._kind_column,
        ]
        if self._filters:
            for col in self._filters.values():
                if col not in columns:
                    columns.append(col)
        for col in self._optional_filters.values():
            if col not in columns:
                columns.append(col)

        data = self._preprocessed_data.get("data")
        if data is None:
            data = self._raw_data
        if isinstance(data, pl.DataFrame):
            data = data.lazy()

        # Apply optional filters first: only when a value is present. Unlike
        # required filters, a missing optional value is skipped (not emptied),
        # so the 3D plot shows every mass for the scan until massIndex is set.
        for identifier, column in self._optional_filters.items():
            value = state.get(identifier)
            if value is not None:
                if isinstance(value, float) and value.is_integer():
                    value = int(value)
                data = data.filter(pl.col(column) == value)

        df_pandas, data_hash = filter_and_collect_cached(
            data,
            self._filters,
            state,
            columns=columns,
            filter_defaults=self._filter_defaults,
        )

        return {"scatter3dData": df_pandas, "_hash": data_hash}

    def _get_component_args(self) -> Dict[str, Any]:
        args: Dict[str, Any] = {
            "componentType": self._get_vue_component_name(),
            "mzColumn": self._mz_column,
            "chargeColumn": self._charge_column,
            "intensityColumn": self._intensity_column,
            "kindColumn": self._kind_column,
            "signalValue": self._signal_value,
            "noiseValue": self._noise_value,
            "signalColor": self._signal_color,
            "noiseColor": self._noise_color,
            "title": self._title or "",
            "xLabel": self._x_label,
            "yLabel": self._y_label,
            "zLabel": self._z_label,
            "interactivity": self._interactivity,
            "config": self._plot_config,
        }
        # Only inject forwarded kwargs not already set, so self._config (which
        # includes title/columns passed to super().__init__) can't clobber an
        # explicit arg with a None passthrough.
        for key, val in self._config.items():
            if key not in args:
                args[key] = val
        return args
