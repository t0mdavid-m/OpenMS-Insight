"""3D scatter (Precursor/Mass signals) component — FLASHApp ``Plotly3Dplot`` parity.

Mirrors the FLASHApp ``Plotly3Dplot.vue`` "Precursor Signals" plot:

- Two ``scatter3d`` *line* traces drawn as vertical sticks: Signal (``#3366CC``)
  and Noise (``#DC3912``).
- Axes: Mass (x = mz*charge), Charge (y, dtick 1, tick0 0), Intensity (z, 0..max).
- ``scanIndex`` is a column-value filter (``index == scanIndex``).
- ``massIndex`` is a POST-FILTER ARRAY SUBSCRIPT into the per-row nested
  ``SignalPeaks``/``NoisyPeaks`` arrays (mirroring ``update.py:142-146``), NOT a
  plain value filter.

Source of truth (FLASHApp):
- ``src/components/plotly/3Dplot/Plotly3Dplot.vue`` (trace/layout/stick math)
- ``src/render/update.py`` lines ~135-147 (scanIndex empty-default + massIndex subscript)
- ``src/parse/deconv.py`` ~189-199 (``threedim_SN_plot`` columns)
- ``src/parse/masstable.py`` :252 (record tuple ``(peak_index, mz, intensity, charge)``)
"""

from typing import Any, Dict, List, Optional

import polars as pl

from ..core.base import BaseComponent
from ..core.registry import register_component


@register_component("scatter3d")
class Scatter3D(BaseComponent):
    """3D Signal/Noise stick plot for a selected scan (and optionally one mass).

    The component is a *consumer* of selection state: it filters its per-scan
    data by ``scanIndex`` (column value) and, when ``massIndex`` is set, isolates
    a single mass's peak set via an array subscript into the nested peak columns.
    It emits no selection of its own.

    Input schema (one row per deconv scan), mirroring ``threedim_SN_plot``:
        - ``index`` (int): scan/deconv row index — the ``scanIndex`` filter target.
        - ``SignalPeaks`` / ``NoisyPeaks``: nested ``list[list[list[float]]]``
          (outer = per-mass, middle = per-charge-peak, inner = the 4-tuple
          ``(peak_index, mz, intensity, charge)``).
        - ``PrecursorScan`` is carried but unused by the 3D render.

    Example::

        scatter = Scatter3D(
            cache_id="precursor_signals",
            data=threedim_sn_df,
            scan_filter="index",
            title="Precursor Signals",
        )
        scatter(key="scatter3d", state_manager=state_manager)
    """

    _component_type: str = "scatter3d"

    # State identifiers (fixed — these mirror the FLASHApp StateTracker keys).
    SCAN_STATE_KEY = "scanIndex"
    MASS_STATE_KEY = "massIndex"

    def __init__(
        self,
        cache_id: str,
        data: Optional[pl.LazyFrame] = None,
        data_path: Optional[str] = None,
        # Schema
        scan_filter: str = "index",
        signal_column: str = "SignalPeaks",
        noisy_column: str = "NoisyPeaks",
        # Optional precursor cross-scan lookup (FLASHApp getPrecursorSignal parity).
        # All four must be present in the data for the lookup to activate; if any is
        # absent the component falls back to the legacy "own scan's nested peaks"
        # behavior (backward compatible).
        scan_column: Optional[str] = None,
        precursor_scan_column: Optional[str] = None,
        precursor_mass_column: Optional[str] = None,
        mono_mass_column: Optional[str] = None,
        precursor_mass_tol: float = 1e-2,
        # Cache
        cache_path: str = ".",
        regenerate_cache: bool = False,
        # Labels / visuals
        title: str = "Precursor Signals",
        signal_color: str = "#3366CC",
        noise_color: str = "#DC3912",
        height: int = 800,
        config: Optional[Dict[str, Any]] = None,
        **kwargs,
    ):
        """Initialize the Scatter3D component.

        Args:
            cache_id: Unique identifier for this component's cache (MANDATORY).
            data: Polars LazyFrame with one row per scan. Optional if cache exists.
            data_path: Path to parquet file (preferred for large datasets).
            scan_filter: Column name holding the scan/deconv row index that
                ``scanIndex`` filters on. Default ``"index"``.
            signal_column: Nested column with per-mass signal peaks.
            noisy_column: Nested column with per-mass noisy peaks.
            scan_column: OPTIONAL. Column holding the real (file) scan number used
                to match a row against another row's ``precursor_scan_column``.
                Mirrors the legacy ``Scan`` field. Required (together with the
                other three precursor params) to enable the MS2 precursor lookup.
            precursor_scan_column: OPTIONAL. Column on the SELECTED row holding the
                scan number of its precursor (MS1) scan. Mirrors ``PrecursorScan``.
                A value of 0 (or null) means "not an MS2 scan" -> blank scene.
            precursor_mass_column: OPTIONAL. Column on the SELECTED row holding the
                precursor monoisotopic mass to match against the precursor scan's
                ``mono_mass_column`` array. Mirrors ``PrecursorMass``.
            mono_mass_column: OPTIONAL. Per-mass array column (one entry per mass,
                aligned with ``signal_column``/``noisy_column``) on the PRECURSOR
                scan's row; the index where ``MonoMass[i] ≈ PrecursorMass`` selects
                which mass's peaks to render. Mirrors ``MonoMass``.
            precursor_mass_tol: Absolute tolerance for the ``MonoMass`` vs
                ``PrecursorMass`` match (default ``1e-2``, mirroring legacy).
            cache_path: Base path for cache storage. Default "." (current dir).
            regenerate_cache: If True, regenerate cache even if valid cache exists.
            title: Plot title (component name; the Vue render shows the dynamic
                "Precursor signals" / "Mass signals" string per FLASHApp).
            signal_color: Hex color for the Signal trace (default ``#3366CC``).
            noise_color: Hex color for the Noise trace (default ``#DC3912``).
            height: Plot height in px (default 800).
            config: Additional Plotly config options.
            **kwargs: Forwarded to BaseComponent for subprocess recreation.
        """
        # BaseComponent's subprocess path re-instantiates with filters=/filter_defaults=
        # kwargs; pop them so super().__init__ doesn't receive them twice.
        kwargs.pop("filters", None)
        kwargs.pop("filter_defaults", None)
        kwargs.pop("interactivity", None)

        self._scan_filter = scan_filter
        self._signal_column = signal_column
        self._noisy_column = noisy_column
        self._scan_column = scan_column
        self._precursor_scan_column = precursor_scan_column
        self._precursor_mass_column = precursor_mass_column
        self._mono_mass_column = mono_mass_column
        self._precursor_mass_tol = precursor_mass_tol
        self._title = title
        self._signal_color = signal_color
        self._noise_color = noise_color
        self._height = height
        self._plot_config = config or {}

        # scanIndex is a value filter on the scan_filter column. massIndex is NOT a
        # value filter (it's a post-filter array subscript), so it is intentionally
        # NOT part of `filters`.
        # Only pass `filters` in creation mode — in reconstruction mode (no data)
        # BaseComponent rejects any config args and restores them from the manifest.
        has_data = data is not None or data_path is not None
        scan_filters = (
            {self.SCAN_STATE_KEY: scan_filter}
            if (has_data or regenerate_cache)
            else None
        )
        super().__init__(
            cache_id=cache_id,
            data=data,
            data_path=data_path,
            filters=scan_filters,
            cache_path=cache_path,
            regenerate_cache=regenerate_cache,
            scan_filter=scan_filter,
            signal_column=signal_column,
            noisy_column=noisy_column,
            scan_column=scan_column,
            precursor_scan_column=precursor_scan_column,
            precursor_mass_column=precursor_mass_column,
            mono_mass_column=mono_mass_column,
            precursor_mass_tol=precursor_mass_tol,
            title=title,
            signal_color=signal_color,
            noise_color=noise_color,
            height=height,
            config=config,
            **kwargs,
        )

    # ------------------------------------------------------------------ validation
    def _precursor_lookup_columns(self) -> Optional[List[str]]:
        """Return the four precursor-lookup column names if all are configured.

        Returns ``None`` when any of the four optional columns is unset, signalling
        that the legacy "own scan's nested peaks" behavior should be used instead.
        """
        cols = [
            self._scan_column,
            self._precursor_scan_column,
            self._precursor_mass_column,
            self._mono_mass_column,
        ]
        if any(c is None for c in cols):
            return None
        return cols  # type: ignore[return-value]

    def _precursor_lookup_enabled(self) -> bool:
        """True iff all four precursor columns are configured AND present in data."""
        cols = self._precursor_lookup_columns()
        if cols is None:
            return False
        source = self._get_source_lazyframe()
        if source is None:
            # Reconstruction mode without data: trust the configured columns.
            return True
        present = set(source.collect_schema().names())
        return all(c in present for c in cols)

    def _validate_mappings(self) -> None:
        """Validate the scan filter column and the nested peak columns exist.

        The four optional precursor-lookup columns are validated only when ALL
        four are configured; if any precursor column is configured but missing
        from the data we raise (mis-wiring), but leaving them all unset is fine
        (backward-compatible fallback).
        """
        if self._raw_data is None:
            return  # reconstruction mode

        schema = self._raw_data.collect_schema()
        column_names = schema.names()

        for col_name, label in [
            (self._scan_filter, "scan_filter"),
            (self._signal_column, "signal_column"),
            (self._noisy_column, "noisy_column"),
        ]:
            if col_name not in column_names:
                raise ValueError(
                    f"{label} '{col_name}' not found in data. "
                    f"Available columns: {column_names}"
                )

        precursor_cols = [
            (self._scan_column, "scan_column"),
            (self._precursor_scan_column, "precursor_scan_column"),
            (self._precursor_mass_column, "precursor_mass_column"),
            (self._mono_mass_column, "mono_mass_column"),
        ]
        configured = [(c, lbl) for c, lbl in precursor_cols if c is not None]
        if configured and len(configured) != len(precursor_cols):
            missing = [lbl for c, lbl in precursor_cols if c is None]
            raise ValueError(
                "Precursor cross-scan lookup requires all four columns to be set "
                f"(scan_column, precursor_scan_column, precursor_mass_column, "
                f"mono_mass_column); missing: {missing}"
            )
        for col_name, label in configured:
            if col_name not in column_names:
                raise ValueError(
                    f"{label} '{col_name}' not found in data. "
                    f"Available columns: {column_names}"
                )

    # ------------------------------------------------------------------ preprocess
    def _preprocess(self) -> None:
        """Sort by the scan filter column for predicate pushdown; keep nested arrays."""
        data = self._raw_data
        if self._scan_filter in data.collect_schema().names():
            data = data.sort(self._scan_filter)
        self._preprocessed_data["data"] = data

    def _get_row_group_size(self) -> int:
        # Nested per-scan rows are heavy; small groups help index-pushdown.
        return 1_000

    # ------------------------------------------------------------------ identity
    def _get_vue_component_name(self) -> str:
        return "Plotly3DScatter"

    def _get_data_key(self) -> str:
        return "scatter3dData"

    def get_state_dependencies(self) -> List[str]:
        """Both scanIndex and massIndex affect the rendered data → cache key."""
        return [self.SCAN_STATE_KEY, self.MASS_STATE_KEY]

    # ------------------------------------------------------------------ cache cfg
    def _get_cache_config(self) -> Dict[str, Any]:
        return {
            "scan_filter": self._scan_filter,
            "signal_column": self._signal_column,
            "noisy_column": self._noisy_column,
            "scan_column": self._scan_column,
            "precursor_scan_column": self._precursor_scan_column,
            "precursor_mass_column": self._precursor_mass_column,
            "mono_mass_column": self._mono_mass_column,
            "precursor_mass_tol": self._precursor_mass_tol,
            "title": self._title,
            "signal_color": self._signal_color,
            "noise_color": self._noise_color,
            "height": self._height,
            "plot_config": self._plot_config,
        }

    def _restore_cache_config(self, config: Dict[str, Any]) -> None:
        self._scan_filter = config.get("scan_filter", "index")
        self._signal_column = config.get("signal_column", "SignalPeaks")
        self._noisy_column = config.get("noisy_column", "NoisyPeaks")
        self._scan_column = config.get("scan_column")
        self._precursor_scan_column = config.get("precursor_scan_column")
        self._precursor_mass_column = config.get("precursor_mass_column")
        self._mono_mass_column = config.get("mono_mass_column")
        self._precursor_mass_tol = config.get("precursor_mass_tol", 1e-2)
        self._title = config.get("title", "Precursor Signals")
        self._signal_color = config.get("signal_color", "#3366CC")
        self._noise_color = config.get("noise_color", "#DC3912")
        self._height = config.get("height", 800)
        self._plot_config = config.get("plot_config", {})

    # ------------------------------------------------------------------ data prep
    def _get_source_lazyframe(self) -> Optional[pl.LazyFrame]:
        data = self._preprocessed_data.get("data")
        if data is None:
            data = self._raw_data
        if data is None:
            return None
        if isinstance(data, pl.DataFrame):
            data = data.lazy()
        return data

    @staticmethod
    def _subscript(cell: Any, mass_index: int) -> Any:
        """Mirror update.py:142-146 — return cell[mass_index] if in range else None."""
        if cell is None:
            return None
        try:
            n = len(cell)
        except TypeError:
            return None
        if n > mass_index >= 0:
            return cell[mass_index]
        # Negative indices: FLASHApp uses len(peaks) > mass_index only (Python negative
        # subscripts would wrap); guard against that and treat as out-of-range.
        return None

    def _prepare_vue_data(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Filter by scanIndex (value) and apply the massIndex array subscript.

        Returns a plain JSON-serializable payload (not a DataFrame) under
        ``scatter3dData`` so the JS store forwards the nested arrays untouched
        and the Vue stick builder reproduces ``getSignalNoiseObject`` exactly.
        """
        scan_index = state.get(self.SCAN_STATE_KEY)
        mass_index = state.get(self.MASS_STATE_KEY)

        # Empty / None scanIndex → blank scene (mirror update.py:138-139).
        if scan_index is None:
            return {
                "scatter3dData": {
                    "hasSelection": False,
                    "massSelected": False,
                    "signalPeaks": None,
                    "noisyPeaks": None,
                },
                "_hash": f"blank_{scan_index}_{mass_index}",
            }

        data = self._get_source_lazyframe()
        if data is None:
            return {
                "scatter3dData": {
                    "hasSelection": False,
                    "massSelected": False,
                    "signalPeaks": None,
                    "noisyPeaks": None,
                },
                "_hash": "no_data",
            }

        mass_selected = mass_index is not None

        # Precursor cross-scan lookup (FLASHApp getPrecursorSignal parity):
        # only when no mass is selected AND all four precursor columns are wired.
        if not mass_selected and self._precursor_lookup_enabled():
            return self._resolve_precursor_signal(data, scan_index)

        # Value filter: index == scanIndex (mirror update.py:141).
        filtered = (
            data.filter(pl.col(self._scan_filter) == scan_index)
            .select([self._signal_column, self._noisy_column])
            .collect()
        )

        if filtered.height == 0:
            return {
                "scatter3dData": {
                    "hasSelection": True,
                    "massSelected": mass_selected,
                    "signalPeaks": None,
                    "noisyPeaks": None,
                },
                "_hash": f"empty_{scan_index}_{mass_index}",
            }

        # Take the first matching row (one row per scan).
        signal_cell = filtered[self._signal_column][0]
        noisy_cell = filtered[self._noisy_column][0]
        signal_peaks = signal_cell.to_list() if signal_cell is not None else None
        noisy_peaks = noisy_cell.to_list() if noisy_cell is not None else None

        if mass_selected:
            # Array subscript into the per-mass arrays (mirror update.py:142-146).
            signal_peaks = self._subscript(signal_peaks, mass_index)
            noisy_peaks = self._subscript(noisy_peaks, mass_index)

        return {
            "scatter3dData": {
                "hasSelection": True,
                "massSelected": mass_selected,
                "signalPeaks": signal_peaks,
                "noisyPeaks": noisy_peaks,
            },
            "_hash": f"scatter3d_{scan_index}_{mass_index}",
        }

    def _resolve_precursor_signal(
        self, data: pl.LazyFrame, scan_index: Any
    ) -> Dict[str, Any]:
        """Resolve the precursor scan's matching mass peaks for a selected MS2 scan.

        Mirrors ``Plotly3Dplot.vue::getPrecursorSignal`` exactly:

        1. From the SELECTED row, read ``precursor_scan_column`` (PrecursorScan)
           and ``precursor_mass_column`` (PrecursorMass). A precursor scan of 0
           or null means "not MS2" -> blank scene.
        2. Find the row whose ``scan_column`` (Scan) == that PrecursorScan. If none
           -> blank scene.
        3. In that precursor row's ``mono_mass_column`` (MonoMass) array, find the
           index ``i`` where ``abs(MonoMass[i] - PrecursorMass) < precursor_mass_tol``.
        4. Render the precursor row's ``signal_column[i]`` / ``noisy_column[i]``
           (a single mass's per-peak list -> number[][]). No match -> blank scene.

        The result is reported with ``massSelected=False`` so the Vue title stays
        "Precursor signals"; the peak arrays are already a single mass's records.
        """
        blank = {
            "scatter3dData": {
                "hasSelection": True,
                "massSelected": False,
                "signalPeaks": None,
                "noisyPeaks": None,
            },
            "_hash": f"precursor_blank_{scan_index}",
        }

        # 1. Selected row's precursor scan + precursor mass.
        selected = (
            data.filter(pl.col(self._scan_filter) == scan_index)
            .select([self._precursor_scan_column, self._precursor_mass_column])
            .collect()
        )
        if selected.height == 0:
            return blank

        precursor_scan = selected[self._precursor_scan_column][0]
        precursor_mass = selected[self._precursor_mass_column][0]
        # PrecursorScan == 0 / null -> not an MS2 scan -> nothing to draw.
        if precursor_scan is None or precursor_scan == 0 or precursor_mass is None:
            return blank

        # 2. Locate the precursor scan's row by its real Scan number.
        precursor_row = (
            data.filter(pl.col(self._scan_column) == precursor_scan)
            .select([self._mono_mass_column, self._signal_column, self._noisy_column])
            .collect()
        )
        if precursor_row.height == 0:
            return blank

        mono_cell = precursor_row[self._mono_mass_column][0]
        mono_masses = mono_cell.to_list() if mono_cell is not None else None
        if not mono_masses:
            return blank

        # 3. Match PrecursorMass against the precursor scan's MonoMass array.
        target = float(precursor_mass)
        tol = self._precursor_mass_tol
        match_index = None
        for i, mono in enumerate(mono_masses):
            if mono is None:
                continue
            if abs(float(mono) - target) < tol:
                match_index = i
                break
        if match_index is None:
            return blank

        # 4. That mass's signal/noise peaks (guard out-of-range subscripts).
        signal_cell = precursor_row[self._signal_column][0]
        noisy_cell = precursor_row[self._noisy_column][0]
        signal_all = signal_cell.to_list() if signal_cell is not None else None
        noisy_all = noisy_cell.to_list() if noisy_cell is not None else None
        signal_peaks = self._subscript(signal_all, match_index)
        noisy_peaks = self._subscript(noisy_all, match_index)
        if signal_peaks is None and noisy_peaks is None:
            return blank

        return {
            "scatter3dData": {
                "hasSelection": True,
                "massSelected": False,
                "signalPeaks": signal_peaks,
                "noisyPeaks": noisy_peaks,
            },
            "_hash": (f"precursor_{scan_index}_{precursor_scan}_{match_index}"),
        }

    # ------------------------------------------------------------------ args
    def _get_component_args(self) -> Dict[str, Any]:
        args: Dict[str, Any] = {
            "componentType": self._get_vue_component_name(),
            "title": self._title or "",
            "signalColor": self._signal_color,
            "noiseColor": self._noise_color,
            "height": self._height,
            "config": self._plot_config,
        }
        for key, val in self._config.items():
            if key not in args:
                args[key] = val
        return args
