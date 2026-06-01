"""FLASHQuant feature-group view component using Plotly.js.

Ports FLASHApp's ``FLASHQuantView`` into a reusable OpenMS-Insight component.
The original showed a feature-group table on top and, below it, a 3D plot of
the selected feature group's mass traces (one 3D line per charge: m/z vs
retention time vs intensity).

FLASHApp stored per-feature-group **arrays** (``Charges[]``, ``RTs[]``,
``MZs[]``, ``Intensities[]`` as comma-joined strings) and exploded them on the
JS side. This component instead consumes **long format**: one row per trace
point, with an explicit ``feature_group`` column so the traces can be filtered
by column value through the standard ``filters`` mechanism. A feature-group
selector (a Table with ``interactivity={'featureGroup': 'FeatureGroupIndex'}``)
drives the ``feature_group`` filter on this component.

The component is the 3D-plot half of the original view; pair it with a Table
for the feature-group list (the same composition the original used internally).
"""

from typing import Any, Dict, List, Optional

import polars as pl

from ..core.base import BaseComponent
from ..core.registry import register_component
from ..preprocessing.filtering import filter_and_collect_cached


@register_component("featureview")
class FeatureView(BaseComponent):
    """
    Interactive FLASHQuant feature-group 3D trace view using Plotly.

    Renders the mass traces of a single selected feature group as 3D lines —
    one line per charge state — with m/z (x), retention time (y) and intensity
    (z). Filtered to the selected feature group via a ``filters`` identifier
    (typically set by a companion feature-group ``Table``).

    Expected long-format input columns (configurable via *_column args):
        - feature_group: feature-group identifier (filter target)
        - charge:        charge state (one trace per distinct value)
        - mz:            m/z — x-axis
        - rt:            retention time — y-axis
        - intensity:     intensity — z-axis
        - isotope (opt): isotope index, available for hover/coloring

    Example:
        feature_table = Table(
            cache_id="fq_groups", data=group_df,
            interactivity={"featureGroup": "FeatureGroupIndex"},
        )
        feature_view = FeatureView(
            cache_id="fq_traces", data=traces_long_df,
            filters={"featureGroup": "feature_group"},
        )
        feature_table(key="fq_tbl", state_manager=sm)
        feature_view(key="fq_view", state_manager=sm)
    """

    _component_type: str = "featureview"

    def __init__(
        self,
        cache_id: str,
        data: Optional[pl.LazyFrame] = None,
        data_path: Optional[str] = None,
        filters: Optional[Dict[str, str]] = None,
        filter_defaults: Optional[Dict[str, Any]] = None,
        interactivity: Optional[Dict[str, str]] = None,
        cache_path: str = ".",
        regenerate_cache: bool = False,
        charge_column: str = "charge",
        mz_column: str = "mz",
        rt_column: str = "rt",
        intensity_column: str = "intensity",
        isotope_column: Optional[str] = None,
        trace_color: str = "#3366CC",
        title: Optional[str] = None,
        x_label: str = "m/z",
        y_label: str = "retention time",
        z_label: str = "intensity",
        config: Optional[Dict[str, Any]] = None,
        **kwargs,
    ):
        """
        Initialize the FeatureView component.

        Args:
            cache_id: Unique identifier for this component's cache (MANDATORY).
            data: Polars LazyFrame in long format (one row per trace point).
                Optional if cache exists.
            data_path: Path to parquet file (preferred for large datasets).
            filters: Mapping of identifier names to column names for filtering.
                Typically {"featureGroup": "feature_group"}.
            filter_defaults: Default values for filters when state is None.
            interactivity: Optional click mapping (usually unused for 3D nav).
            cache_path: Base path for cache storage. Default "." (current dir).
            regenerate_cache: If True, regenerate cache even if valid cache exists.
            charge_column: Column whose distinct values define one 3D trace each.
            mz_column: Column for the x-axis (m/z). Default "mz".
            rt_column: Column for the y-axis (retention time). Default "rt".
            intensity_column: Column for the z-axis (intensity). Default "intensity".
            isotope_column: Optional isotope-index column (kept for hover).
            trace_color: Default color for traces. Default "#3366CC".
            title: Plot title. Default "Feature group signals" when None at render.
            x_label: X-axis (scene) label. Default "m/z".
            y_label: Y-axis (scene) label. Default "retention time".
            z_label: Z-axis (scene) label. Default "intensity".
            config: Additional Plotly config options.
            **kwargs: Additional configuration options forwarded to Vue args.
        """
        self._charge_column = charge_column
        self._mz_column = mz_column
        self._rt_column = rt_column
        self._intensity_column = intensity_column
        self._isotope_column = isotope_column
        self._trace_color = trace_color
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
            charge_column=charge_column,
            mz_column=mz_column,
            rt_column=rt_column,
            intensity_column=intensity_column,
            isotope_column=isotope_column,
            trace_color=trace_color,
            title=title,
            x_label=x_label,
            y_label=y_label,
            z_label=z_label,
            config=config,
            **kwargs,
        )

    def _get_cache_config(self) -> Dict[str, Any]:
        return {
            "charge_column": self._charge_column,
            "mz_column": self._mz_column,
            "rt_column": self._rt_column,
            "intensity_column": self._intensity_column,
            "isotope_column": self._isotope_column,
            "trace_color": self._trace_color,
            "title": self._title,
            "x_label": self._x_label,
            "y_label": self._y_label,
            "z_label": self._z_label,
            "plot_config": self._plot_config,
        }

    def _restore_cache_config(self, config: Dict[str, Any]) -> None:
        self._charge_column = config.get("charge_column", "charge")
        self._mz_column = config.get("mz_column", "mz")
        self._rt_column = config.get("rt_column", "rt")
        self._intensity_column = config.get("intensity_column", "intensity")
        self._isotope_column = config.get("isotope_column")
        self._trace_color = config.get("trace_color", "#3366CC")
        self._title = config.get("title")
        self._x_label = config.get("x_label", "m/z")
        self._y_label = config.get("y_label", "retention time")
        self._z_label = config.get("z_label", "intensity")
        self._plot_config = config.get("plot_config", {})

    def _get_row_group_size(self) -> int:
        return 10_000 if self._filters else 50_000

    def _validate_mappings(self) -> None:
        super()._validate_mappings()
        if self._raw_data is None:
            return
        column_names = self._raw_data.collect_schema().names()
        cols = [
            (self._charge_column, "charge_column"),
            (self._mz_column, "mz_column"),
            (self._rt_column, "rt_column"),
            (self._intensity_column, "intensity_column"),
        ]
        if self._isotope_column:
            cols.append((self._isotope_column, "isotope_column"))
        for col, label in cols:
            if col not in column_names:
                raise ValueError(
                    f"{label} '{col}' not found in data. "
                    f"Available columns: {column_names}"
                )

    def _preprocess(self) -> None:
        """Sort by filter columns for predicate pushdown; keep lazy for streaming."""
        data = self._raw_data
        if self._filters:
            sort_columns = list(self._filters.values())
            data = data.sort(sort_columns)
        self._preprocessed_data["data"] = data

    def _get_vue_component_name(self) -> str:
        return "PlotlyFeatureView"

    def _get_data_key(self) -> str:
        return "featureData"

    def _prepare_vue_data(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Filter trace points to the selected feature group and return long format."""
        columns = [
            self._charge_column,
            self._mz_column,
            self._rt_column,
            self._intensity_column,
        ]
        if self._isotope_column:
            columns.append(self._isotope_column)
        if self._filters:
            for col in self._filters.values():
                if col not in columns:
                    columns.append(col)

        data = self._preprocessed_data.get("data")
        if data is None:
            data = self._raw_data
        if isinstance(data, pl.DataFrame):
            data = data.lazy()

        df_pandas, data_hash = filter_and_collect_cached(
            data,
            self._filters,
            state,
            columns=columns,
            filter_defaults=self._filter_defaults,
        )

        return {"featureData": df_pandas, "_hash": data_hash}

    def _get_component_args(self) -> Dict[str, Any]:
        args: Dict[str, Any] = {
            "componentType": self._get_vue_component_name(),
            "chargeColumn": self._charge_column,
            "mzColumn": self._mz_column,
            "rtColumn": self._rt_column,
            "intensityColumn": self._intensity_column,
            "isotopeColumn": self._isotope_column,
            "traceColor": self._trace_color,
            "title": self._title or "Feature group signals",
            "xLabel": self._x_label,
            "yLabel": self._y_label,
            "zLabel": self._z_label,
            "interactivity": self._interactivity,
            "config": self._plot_config,
        }
        # self._config holds all kwargs forwarded to super().__init__ (incl.
        # title/columns). Only inject keys not already set so it can't clobber
        # an explicit arg (e.g. the default title) with a None passthrough.
        for key, val in self._config.items():
            if key not in args:
                args[key] = val
        return args

    @staticmethod
    def explode_traces(
        quant_df: "pl.DataFrame",
        *,
        feature_group_column: str = "FeatureGroupIndex",
        charges_column: str = "Charges",
        mzs_column: str = "MZs",
        rts_column: str = "RTs",
        intensities_column: str = "Intensities",
        isotope_column: Optional[str] = "IsotopeIndices",
    ) -> "pl.DataFrame":
        """Explode FLASHQuant per-feature-group arrays into long format.

        FLASHQuant (``connectTraceWithResult``) yields one row per feature group
        whose ``Charges``/``IsotopeIndices`` are per-trace arrays and whose
        ``MZs``/``RTs``/``Intensities`` are arrays of comma-joined point strings
        (one string per trace). This helper flattens that into one row per trace
        point with explicit columns, which is what ``FeatureView`` consumes.

        Args:
            quant_df: Polars DataFrame with one row per feature group.
            feature_group_column: Feature-group id column name.
            charges_column: Per-trace charge array column.
            mzs_column: Per-trace m/z arrays (list of comma-joined strings, or
                list of lists of floats).
            rts_column: Per-trace RT arrays (same shape as MZs).
            intensities_column: Per-trace intensity arrays (same shape as MZs).
            isotope_column: Optional per-trace isotope-index array column.

        Returns:
            Long-format Polars DataFrame with columns:
            feature_group, charge, isotope (if available), mz, rt, intensity.
        """

        def _to_floats(cell: Any) -> List[float]:
            if cell is None:
                return []
            if isinstance(cell, str):
                return [float(v) for v in cell.split(",") if v != ""]
            # Already a list/array of numbers
            return [float(v) for v in cell]

        out_fg: List[Any] = []
        out_charge: List[Any] = []
        out_iso: List[Any] = []
        out_mz: List[float] = []
        out_rt: List[float] = []
        out_int: List[float] = []

        for row in quant_df.iter_rows(named=True):
            fg = row[feature_group_column]
            charges = list(row[charges_column] or [])
            isotopes = (
                list(row[isotope_column] or [])
                if isotope_column and isotope_column in row
                else [None] * len(charges)
            )
            mzs = list(row[mzs_column] or [])
            rts = list(row[rts_column] or [])
            intensities = list(row[intensities_column] or [])

            for t, charge in enumerate(charges):
                mz_pts = _to_floats(mzs[t]) if t < len(mzs) else []
                rt_pts = _to_floats(rts[t]) if t < len(rts) else []
                int_pts = _to_floats(intensities[t]) if t < len(intensities) else []
                iso = isotopes[t] if t < len(isotopes) else None
                n = min(len(mz_pts), len(rt_pts), len(int_pts))
                for p in range(n):
                    out_fg.append(fg)
                    out_charge.append(charge)
                    out_iso.append(iso)
                    out_mz.append(mz_pts[p])
                    out_rt.append(rt_pts[p])
                    out_int.append(int_pts[p])

        result = {
            "feature_group": out_fg,
            "charge": out_charge,
            "mz": out_mz,
            "rt": out_rt,
            "intensity": out_int,
        }
        if isotope_column is not None:
            result["isotope"] = out_iso
        return pl.DataFrame(result)
