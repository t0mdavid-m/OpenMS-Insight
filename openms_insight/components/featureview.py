"""FeatureView component (FLASHQuant) — feature-group table + 3D mass-trace plot.

Port of FLASHApp's ``FLASHQuantView.vue``. The shipped FLASHApp component is a
**"Feature groups" Tabulator table (10 columns) + ONE 3D ``scatter3d`` plot**
(m/z x retention time x intensity), with **one trace per CHARGE** (not per
isotope), line color ``#3366CC``, ``-1e3`` sentinel z-values bracketing every
mass trace so Plotly does not connect separate traces, plot title
``"Feature group signals"`` and height ``800``.

This component is *self-contained* and *single-experiment*: it embeds its own
feature-group table + 3D plot and manages an **internal** selection identifier
(the selected feature-group row index). It does NOT cross-link to any other
component's state — nothing is consumed from or emitted to other components.

The per-feature-group trace data is kept in the original **comma-string**
encoding (``MZs``/``RTs``/``Intensities`` are lists where each element is a
comma-joined point string). The Vue side splits on ``,`` and inserts the
``-1e3`` sentinels, exactly mirroring ``trace3DgraphData`` in the original
``.vue``. We deliberately keep this encoding rather than exploding to long
format (lower risk for parity; preserves the sentinel-segment logic).
"""

from typing import Any, Dict, List, Optional, Sequence

import polars as pl

from ..core.base import BaseComponent
from ..core.registry import register_component

# Sentinel z-value used to break Plotly line segments between separate mass
# traces of the same charge. Mirrors the literal -1000 used in the original
# FLASHQuantView.vue (`-1e3`).
SENTINEL_INTENSITY: float = -1000.0

# Default line color for every charge trace (matches the original .vue).
DEFAULT_LINE_COLOR: str = "#3366CC"

# The 10 distinct feature-group table columns, in source order. The original
# .vue listed "Feature Group Quantity" twice (a known source artifact); we
# reproduce a single column. (title, field) pairs.
FEATURE_GROUP_COLUMN_DEFINITIONS: List[Dict[str, str]] = [
    {"title": "Index", "field": "FeatureGroupIndex"},
    {"title": "Monoisotopic Mass", "field": "MonoisotopicMass"},
    {"title": "Average Mass", "field": "AverageMass"},
    {"title": "Start Retention Time (FWHM)", "field": "StartRetentionTime(FWHM)"},
    {"title": "End Retention Time (FWHM)", "field": "EndRetentionTime(FWHM)"},
    {"title": "Feature Group Quantity", "field": "FeatureGroupQuantity"},
    {"title": "Min Charge", "field": "MinCharge"},
    {"title": "Max Charge", "field": "MaxCharge"},
    {"title": "Most Abundant Charge", "field": "MostAbundantFeatureCharge"},
    {"title": "Isotope Cosine Score", "field": "IsotopeCosineScore"},
]


def _split_floats(comma_string: Any) -> List[float]:
    """Split a comma-joined point string into a list of floats.

    Mirrors the Vue ``.split(',').map(parseFloat)``. Tolerant of values that are
    already a list/array (returns floats), ``None``/empty (returns ``[]``), and
    non-finite tokens (parsed to ``float('nan')`` like JS ``parseFloat`` for
    unparseable tokens would give ``NaN``; here we skip empty tokens).
    """
    if comma_string is None:
        return []
    # Already a sequence of numbers (e.g. ragged arrays) — coerce directly.
    if isinstance(comma_string, (list, tuple)):
        out: List[float] = []
        for tok in comma_string:
            try:
                out.append(float(tok))
            except (TypeError, ValueError):
                continue
        return out
    s = str(comma_string).strip()
    if s == "":
        return []
    out = []
    for tok in s.split(","):
        tok = tok.strip()
        if tok == "":
            continue
        try:
            out.append(float(tok))
        except ValueError:
            # JS parseFloat would yield NaN; we skip to avoid poisoning max().
            continue
    return out


def compute_trace_3d_data(
    feature_group: Dict[str, Any],
    line_color: str = DEFAULT_LINE_COLOR,
    sentinel: float = SENTINEL_INTENSITY,
) -> Dict[str, Any]:
    """Port of ``trace3DgraphData`` for a single selected feature group.

    Groups the feature group's mass traces by **charge**, splits the
    comma-string ``MZs``/``RTs``/``Intensities`` for each trace into float
    arrays, brackets every trace with a ``sentinel`` z-value (before and after)
    so Plotly does not connect separate traces, and emits one ``scatter3d``
    line trace per unique charge.

    Args:
        feature_group: A single feature-group record (dict-like) carrying at
            least ``Charges`` (list of ints) and ``MZs``/``RTs``/``Intensities``
            (lists of comma-joined point strings), aligned by trace index.
        line_color: Line color for every trace (default ``#3366CC``).
        sentinel: Sentinel z-value used to separate traces (default ``-1000``).

    Returns:
        Dict with::

            {
                "traces": [ {x, y, z, mode, line:{color}, type, name}, ... ],
                "maximumIntensity": float,  # max over all z (real points)
            }

        On an empty/missing feature group, ``traces`` is ``[]`` and
        ``maximumIntensity`` is ``0`` (avoids ``-inf``).
    """
    if not feature_group:
        return {"traces": [], "maximumIntensity": 0.0}

    charges = feature_group.get("Charges")
    if charges is None:
        return {"traces": [], "maximumIntensity": 0.0}
    charges = list(charges)
    if len(charges) == 0:
        return {"traces": [], "maximumIntensity": 0.0}

    # NOTE: do NOT use `... or []` here — these may be numpy arrays (when the
    # row comes from a pandas DataFrame), whose truth value is ambiguous.
    def _as_seq(value: Any) -> Sequence[Any]:
        if value is None:
            return []
        return value

    mzs_strings: Sequence[Any] = _as_seq(feature_group.get("MZs"))
    rts_strings: Sequence[Any] = _as_seq(feature_group.get("RTs"))
    intys_strings: Sequence[Any] = _as_seq(feature_group.get("Intensities"))

    # Unique charges, preserving first-seen order (mirrors `new Set(...)`).
    unique_charges: List[int] = []
    seen = set()
    for c in charges:
        ci = int(c)
        if ci not in seen:
            seen.add(ci)
            unique_charges.append(ci)

    # Per-charge accumulators.
    trace_objects: Dict[int, Dict[str, List[float]]] = {
        c: {"mzs": [], "rts": [], "intys": []} for c in unique_charges
    }

    for index, charge in enumerate(charges):
        charge = int(charge)
        current_mzs = (
            _split_floats(mzs_strings[index]) if index < len(mzs_strings) else []
        )
        current_rts = (
            _split_floats(rts_strings[index]) if index < len(rts_strings) else []
        )
        current_intys = (
            _split_floats(intys_strings[index]) if index < len(intys_strings) else []
        )

        acc = trace_objects[charge]

        # Leading sentinel: x/y take the first point, z = sentinel.
        # (Mirrors the .vue, which pushes currentMzs[0]/currentRts[0]/-1000.)
        if current_mzs:
            acc["mzs"].append(current_mzs[0])
        else:
            acc["mzs"].append(float("nan"))
        if current_rts:
            acc["rts"].append(current_rts[0])
        else:
            acc["rts"].append(float("nan"))
        acc["intys"].append(sentinel)

        # Real points.
        acc["mzs"].extend(current_mzs)
        acc["rts"].extend(current_rts)
        acc["intys"].extend(current_intys)

        # Trailing sentinel. NOTE: the original .vue uses `currentMzs[-1]` which
        # in JS is `undefined` (not the last element). The trailing x/y are
        # therefore irrelevant — only z = sentinel matters to break the line.
        # We push NaN for x/y (Plotly treats NaN as a gap) and z = sentinel.
        acc["mzs"].append(float("nan"))
        acc["rts"].append(float("nan"))
        acc["intys"].append(sentinel)

    # maximumIntensity = max over all z (real intensities dominate the
    # sentinels). Guard against an all-empty selection (avoid -inf / ValueError).
    all_intys: List[float] = []
    for acc in trace_objects.values():
        all_intys.extend(acc["intys"])
    finite_intys = [v for v in all_intys if v == v]  # drop NaN
    maximum_intensity = max(finite_intys) if finite_intys else 0.0
    if maximum_intensity == sentinel:
        # Only sentinels present (no real points) — clamp to 0 like a blank plot.
        maximum_intensity = 0.0

    traces: List[Dict[str, Any]] = []
    for charge, feature in trace_objects.items():
        traces.append(
            {
                "x": feature["mzs"],
                "y": feature["rts"],
                "z": feature["intys"],
                "mode": "lines",
                "line": {"color": line_color},
                "type": "scatter3d",
                "name": f"Charge: {charge}",
            }
        )

    return {"traces": traces, "maximumIntensity": float(maximum_intensity)}


@register_component("featureview")
class FeatureView(BaseComponent):
    """FLASHQuant feature-group view: a table + a 3D mass-trace plot.

    This is a **standalone, single-experiment** component. It embeds its own
    "Feature groups" table and a 3D ``scatter3d`` plot. Selecting a feature-group
    row redraws the 3D plot client-side (one ``scatter3d`` line trace per unique
    charge in that group). There is **no cross-component state**: nothing is
    consumed from, or emitted to, other components — the selection is an internal
    round-trip handled entirely in Vue.

    Example::

        fv = FeatureView(
            cache_id="flashquant",
            data=quant_lazyframe,   # rows = feature groups, with list columns
        )
        fv(state_manager=state, height=800)
    """

    _component_type: str = "featureview"

    def __init__(
        self,
        cache_id: str,
        data: Optional[pl.LazyFrame] = None,
        data_path: Optional[str] = None,
        cache_path: str = ".",
        regenerate_cache: bool = False,
        title: Optional[str] = None,
        plot_title: str = "Feature group signals",
        line_color: str = DEFAULT_LINE_COLOR,
        plot_height: int = 800,
        x_axis_title: str = "m/z",
        y_axis_title: str = "retention time",
        z_axis_title: str = "intensity",
        selection_identifier: str = "selectedFeatureGroupIndex",
        column_definitions: Optional[List[Dict[str, str]]] = None,
        **kwargs,
    ):
        """Initialize the FeatureView component.

        Args:
            cache_id: Unique identifier for this component's cache (MANDATORY).
            data: Polars LazyFrame (or pandas DataFrame) where each row is a
                feature group. Must carry the scalar feature-group columns and
                the array columns ``Charges``/``MZs``/``RTs``/``Intensities``
                (and optionally ``IsotopeIndices``/``CentroidMzs``). ``MZs``/
                ``RTs``/``Intensities`` elements are comma-joined point strings.
            data_path: Path to a parquet file (alternative to ``data``).
            cache_path: Base path for cache storage. Default ".".
            regenerate_cache: If True, regenerate the cache even if valid.
            title: Optional title shown above the feature-group table.
            plot_title: 3D plot title (default "Feature group signals").
            line_color: Line color for every charge trace (default "#3366CC").
            plot_height: 3D plot height in pixels (default 800).
            x_axis_title / y_axis_title / z_axis_title: 3D scene axis titles
                (defaults "m/z" / "retention time" / "intensity").
            selection_identifier: Internal-only selection state key for the
                selected feature-group row index. Not consumed by any other
                component.
            column_definitions: Override for the 10 feature-group columns.
                Defaults to ``FEATURE_GROUP_COLUMN_DEFINITIONS``.
            **kwargs: Forwarded for subprocess reconstruction.
        """
        self._title = title
        self._plot_title = plot_title
        self._line_color = line_color
        self._plot_height = plot_height
        self._x_axis_title = x_axis_title
        self._y_axis_title = y_axis_title
        self._z_axis_title = z_axis_title
        self._selection_identifier = selection_identifier
        self._column_definitions = (
            column_definitions
            if column_definitions is not None
            else [dict(c) for c in FEATURE_GROUP_COLUMN_DEFINITIONS]
        )

        # Accept a pandas DataFrame for convenience (FLASHQuant parse emits one).
        if data is not None and not isinstance(data, (pl.LazyFrame, pl.DataFrame)):
            data = pl.from_pandas(data).lazy()
        elif isinstance(data, pl.DataFrame):
            data = data.lazy()

        super().__init__(
            cache_id=cache_id,
            data=data,
            data_path=data_path,
            # No external filters/interactivity — standalone component.
            filters=None,
            filter_defaults=None,
            interactivity=None,
            cache_path=cache_path,
            regenerate_cache=regenerate_cache,
            # Pass component-specific params for subprocess recreation.
            title=title,
            plot_title=plot_title,
            line_color=line_color,
            plot_height=plot_height,
            x_axis_title=x_axis_title,
            y_axis_title=y_axis_title,
            z_axis_title=z_axis_title,
            selection_identifier=selection_identifier,
            column_definitions=self._column_definitions,
            **kwargs,
        )

    def _validate_mappings(self) -> None:
        """Validate that the configured table columns exist in the data.

        Standalone component: no filter/interactivity columns to validate, but
        we do warn (raise) if none of the configured table fields are present —
        a strong signal the input frame is not a FLASHQuant feature-group frame.
        """
        if self._raw_data is None:
            return  # Reconstruction from cache.

        column_names = set(self._raw_data.collect_schema().names())
        configured = [c["field"] for c in self._column_definitions if "field" in c]
        present = [f for f in configured if f in column_names]
        if configured and not present:
            raise ValueError(
                "FeatureView: none of the configured table columns "
                f"{configured} are present in the data. "
                f"Available columns: {sorted(column_names)}"
            )

    def _preprocess(self) -> None:
        """Cache the full feature-group frame (scalar + list columns).

        No sorting/filtering: the whole table is sent once and the 3D redraw is
        a client-side operation in Vue (mirroring the original .vue, which never
        round-trips to Python for the plot).
        """
        # Keep lazy — base class streams to parquet. List columns (Charges, MZs,
        # RTs, Intensities, ...) survive as Arrow lists and parse to JS arrays.
        self._preprocessed_data["data"] = self._raw_data

    def _get_vue_component_name(self) -> str:
        return "PlotlyFeatureView"

    def _get_data_key(self) -> str:
        return "quant_data"

    def get_state_dependencies(self) -> List[str]:
        """No external state affects the data payload.

        The selected feature-group index drives only a client-side 3D redraw and
        does NOT change the data sent from Python, so it is intentionally
        excluded here (otherwise selection would needlessly invalidate cache).
        """
        return []

    def _get_cache_config(self) -> Dict[str, Any]:
        return {
            "title": self._title,
            "plot_title": self._plot_title,
            "line_color": self._line_color,
            "plot_height": self._plot_height,
            "x_axis_title": self._x_axis_title,
            "y_axis_title": self._y_axis_title,
            "z_axis_title": self._z_axis_title,
            "selection_identifier": self._selection_identifier,
            "column_definitions": self._column_definitions,
        }

    def _restore_cache_config(self, config: Dict[str, Any]) -> None:
        self._title = config.get("title")
        self._plot_title = config.get("plot_title", "Feature group signals")
        self._line_color = config.get("line_color", DEFAULT_LINE_COLOR)
        self._plot_height = config.get("plot_height", 800)
        self._x_axis_title = config.get("x_axis_title", "m/z")
        self._y_axis_title = config.get("y_axis_title", "retention time")
        self._z_axis_title = config.get("z_axis_title", "intensity")
        self._selection_identifier = config.get(
            "selection_identifier", "selectedFeatureGroupIndex"
        )
        self._column_definitions = config.get(
            "column_definitions",
            [dict(c) for c in FEATURE_GROUP_COLUMN_DEFINITIONS],
        )

    def _prepare_vue_data(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Send the full feature-group table to Vue.

        Standalone: no filtering. Returns the whole table as a pandas DataFrame
        (with list columns preserved) under ``quant_data``.
        """
        from ..preprocessing.filtering import compute_dataframe_hash

        data = self._preprocessed_data.get("data")
        if data is None:
            data = self._raw_data
        if isinstance(data, pl.LazyFrame):
            df = data.collect()
        else:
            df = data

        if df is None:
            return {"quant_data": None, "_hash": "empty"}

        data_hash = compute_dataframe_hash(df)
        return {"quant_data": df.to_pandas(), "_hash": data_hash}

    def _get_component_args(self) -> Dict[str, Any]:
        args: Dict[str, Any] = {
            "componentType": self._get_vue_component_name(),
            "title": self._title or "Feature groups",
            "columnDefinitions": self._column_definitions,
            "tableIndexField": "FeatureGroupIndex",
            "defaultRow": 0,
            "plotTitle": self._plot_title,
            "lineColor": self._line_color,
            "plotHeight": self._plot_height,
            "xAxisTitle": self._x_axis_title,
            "yAxisTitle": self._y_axis_title,
            "zAxisTitle": self._z_axis_title,
            "sentinelIntensity": SENTINEL_INTENSITY,
            "selectionIdentifier": self._selection_identifier,
        }
        # Forward any extra config without clobbering explicit args.
        for key, val in self._config.items():
            if key not in args:
                args[key] = val
        return args
