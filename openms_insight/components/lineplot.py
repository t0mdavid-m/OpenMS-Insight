"""Line plot component using Plotly.js.

Supports three rendering ``mode`` values (config-time):

- ``"default"`` (implicit): the classic stick spectrum with highlight masks,
  per-row annotation labels, click-to-select and dynamic annotations. Behavior
  is unchanged from earlier versions.
- ``"density"``: a static two-series KDE / FDR plot (target vs decoy). Consumes a
  precomputed tidy long ``{x, y, group}`` frame; an optional ``kde_from`` lazily
  imports scipy to build the curves from raw scores.
- ``"tagger"``: a stateful de-novo sequence-tag overlay with a derived two-level
  drill-down, routed entirely through the generic selection store. All heavy
  numeric work (highlight masks, intensity-weighted center-of-gravity, reversed
  sequence index, sequence-arrow segments) happens here in Python.
"""

import hashlib
import json
from typing import TYPE_CHECKING, Any, Dict, List, Optional

import polars as pl

from ..core.base import BaseComponent
from ..core.registry import register_component
from ..preprocessing.filtering import filter_and_collect_cached

if TYPE_CHECKING:
    from .sequenceview import SequenceView


# Structured constructor params stored in self._config (for subprocess
# recreation) that must NOT leak into _get_component_args as top-level args —
# they are already surfaced via dedicated camelCase args / `config`.
_MANAGED_CONFIG_KEYS = frozenset(
    {
        "x_column",
        "y_column",
        "title",
        "x_label",
        "y_label",
        "highlight_column",
        "annotation_column",
        "styling",
        "config",
        "mode",
        "category_column",
        "target_value",
        "decoy_value",
        "kde_from",
        "kde_points",
        "signal_peaks_column",
        "mz_column",
        "mz_intensity_column",
        "tag_identifier",
        "mass_match_tol",
        "title_level1",
        "x_label_level1",
        "x_pos_scaling_factor",
        "tag_data_path",
        "tag_id_column",
        "tag_sequence_column",
        "tag_masses_column",
        "tag_start_column",
        "selected_aa_identifier",
        "plot_config",
        # Selective-highlight (FLASHApp parity) constructor params. Surfaced to Vue
        # via dedicated camelCase args / the render-time payload, so they must NOT
        # also leak as snake_case top-level args.
        "highlight_selection",
        "highlight_match_column",
        "highlight_link_path",
        "highlight_link_key_column",
        "highlight_link_match_column",
        "highlight_charge_column",
        "highlight_annotation_template",
        "deconv_peaks_toggle",
        "highlight_value_column",
        "highlight_value_template",
    }
)

# Per-mode constructor parameters (and their defaults) that are accepted by
# ``LinePlot.__init__`` via **kwargs but are NOT part of the small generic
# signature. The ``.density(...)`` / ``.tagger(...)`` factory classmethods are the
# ergonomic way to supply them; they map 1:1 to these keys. Keeping them as the
# single source of truth means the manifest/_config round-trip stays byte-identical
# regardless of whether a caller used a factory or passed the keys directly.
_DENSITY_PARAM_DEFAULTS: Dict[str, Any] = {
    "category_column": "group",
    "target_value": "target",
    "decoy_value": "decoy",
    "kde_from": None,
    "kde_points": 200,
}
_TAGGER_PARAM_DEFAULTS: Dict[str, Any] = {
    "signal_peaks_column": None,
    "mz_column": None,
    "mz_intensity_column": None,
    "tag_identifier": "tag",
    "mass_match_tol": 1e-5,
    "title_level1": None,
    "x_label_level1": None,
    "x_pos_scaling_factor": 27.5,
    # Value-based tag resolution: when the ``tag_identifier`` selection carries a
    # scalar id (e.g. a Table row click) rather than an opaque TagData dict, the
    # payload is resolved from this side frame (one row per tag) by ``tag_id_column``.
    # ``tag_masses_column`` may be a list column or a comma-separated string.
    # ``selected_aa_identifier`` (+ ``tag_start_column``) maps a residue-position
    # selection to the tag-relative ``selectedAA`` (gold highlight).
    "tag_data_path": None,
    "tag_id_column": "tag_id",
    "tag_sequence_column": "sequence",
    "tag_masses_column": "masses",
    "tag_start_column": None,
    "selected_aa_identifier": None,
}

# Default-mode SELECTIVE-HIGHLIGHT parameters (FLASHApp parity). These reproduce
# the oracle's selection-driven mass-spectrum interaction in the generic default
# LinePlot. They are CONFIG (they determine which frames load + how the highlight
# is computed) and round-trip via the manifest like the density/tagger params; the
# resulting highlight itself is computed at RENDER time from the selection state
# (see ``_prepare_vue_data_default``) and is never cached.
#
# - highlight_selection: selection identifier whose value drives the selective
#   highlight (e.g. "mass"). None disables the whole new path (default OFF).
# - highlight_match_column: when set and no link path is configured, highlight
#   BASE rows where base[match_column] == state[highlight_selection] (deconvolved
#   spectrum, whose base frame carries mass_in_scan per row).
# - highlight_link_path: parquet of a highlight LINKAGE frame (annotated spectrum,
#   where highlighted peaks are a subset linked by signal-peak membership). One row
#   per (signal peak, mass it belongs to); may be 1:many per peak. Columns:
#     * highlight_link_key_column  -> matches the base frame's first-interactivity
#                                     value / index (e.g. "peak_id"),
#     * highlight_link_match_column -> the mass each peak belongs to (e.g.
#                                     "mass_in_scan"); compared to the selection,
#     * highlight_charge_column     -> the per-peak charge (for z=N labels).
# - highlight_annotation_template: charge-label text; template.format(charge).
# - deconv_peaks_toggle: enable the "Show Deconvolved Peaks" modebar button (the
#   annotated spectrum); default OFF.
# - highlight_value_column: MATCH-COLUMN path only -- when set, draw a single
#   floating value label above each selected (matched) stick, e.g. the selected
#   mass's MonoMass value on the deconvolved spectrum (oracle parity). The label
#   text is highlight_value_template.format(base[highlight_value_column]) at the
#   stick's x position. None (default) => no value label.
# - highlight_value_template: value-label text format (e.g. "{:.2f}").
_HIGHLIGHT_PARAM_DEFAULTS: Dict[str, Any] = {
    "highlight_selection": None,
    "highlight_match_column": None,
    "highlight_link_path": None,
    "highlight_link_key_column": "peak_id",
    "highlight_link_match_column": "mass_in_scan",
    "highlight_charge_column": "charge",
    "highlight_annotation_template": "z={}",
    "deconv_peaks_toggle": False,
    "highlight_value_column": None,
    "highlight_value_template": "{}",
}


@register_component("lineplot")
class LinePlot(BaseComponent):
    """
    Interactive stick plot component using Plotly.js.

    Features:
    - Stick-style peak visualization (vertical lines from baseline)
    - Highlighting of selected data points
    - Annotations with labels (mass labels, charge states, etc.)
    - Zoom controls with auto-fit to highlighted data
    - SVG export
    - Click-to-select peaks with gold highlighting
    - Cross-component linking via filters and interactivity

    LinePlots can have separate `filters` and `interactivity` mappings:
    - `filters`: Which selections filter this plot's data
    - `interactivity`: What selection is set when a peak is clicked

    Example:
        # Plot filters by spectrum, clicking selects a peak
        plot = LinePlot(
            cache_id="peaks_plot",
            data=peaks_df,
            filters={'spectrum': 'scan_id'},
            interactivity={'my_selection': 'mass'},
            x_column='mass',
            y_column='intensity',
        )
    """

    _component_type: str = "lineplot"

    # Default level-0 / level-1 labels for tagger mode (oracle parity).
    _TAGGER_TITLE_L0 = "Augmented Deconvolved Spectrum"
    _TAGGER_TITLE_L1 = "Augmented Annotated Spectrum"
    _TAGGER_XLABEL_L0 = "Monoisotopic Mass"
    _TAGGER_XLABEL_L1 = "m/z"

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
        x_column: str = "x",
        y_column: str = "y",
        title: Optional[str] = None,
        x_label: Optional[str] = None,
        y_label: Optional[str] = None,
        highlight_column: Optional[str] = None,
        annotation_column: Optional[str] = None,
        styling: Optional[Dict[str, Any]] = None,
        config: Optional[Dict[str, Any]] = None,
        # Mode selector (config-time, cache-affecting). The per-mode params for
        # ``"density"`` / ``"tagger"`` are supplied via the ``.density(...)`` /
        # ``.tagger(...)`` factory classmethods (or, equivalently, as keyword
        # arguments captured below) so the default signature stays minimal.
        mode: str = "default",
        **kwargs,
    ):
        """
        Initialize the LinePlot component.

        The default (``mode="default"``) signature is intentionally small. The
        ``"density"`` and ``"tagger"`` modes carry extra, mode-specific
        parameters; construct those via :meth:`LinePlot.density` and
        :meth:`LinePlot.tagger` rather than passing the keys here. (The factory
        keyword arguments are documented on those classmethods.)

        Args:
            cache_id: Unique identifier for this component's cache (MANDATORY).
                Creates a folder {cache_path}/{cache_id}/ for cached data.
            data: Polars LazyFrame with plot data. Optional if cache exists.
            data_path: Path to parquet file (preferred for large datasets).
            filters: Mapping of identifier names to column names for filtering.
                Example: {'spectrum': 'scan_id'}
                When 'spectrum' selection exists, plot shows only data where
                scan_id equals the selected value.
            filter_defaults: Default values for filters when state is None.
                Example: {'identification': -1}
                When 'identification' selection is None, filter uses -1 instead.
                This enables showing unannotated data when no identification selected.
            interactivity: Mapping of identifier names to column names for clicks.
                Example: {'my_selection': 'mass'}
                When a peak is clicked, sets 'my_selection' to that peak's mass.
                The selected peak is highlighted in gold (selectedColor).
            cache_path: Base path for cache storage. Default "." (current dir).
            regenerate_cache: If True, regenerate cache even if valid cache exists.
            x_column: Column name for x-axis values
            y_column: Column name for y-axis values
            title: Plot title
            x_label: X-axis label (defaults to x_column)
            y_label: Y-axis label (defaults to y_column)
            highlight_column: Optional column name containing boolean/int
                              indicating which points to highlight
            annotation_column: Optional column name containing text annotations
                               to display on highlighted points
            styling: Style configuration dict with keys:
                - highlightColor: Color for highlighted points (default: '#E4572E')
                - selectedColor: Color for clicked/selected peak (default: '#F3A712')
                - unhighlightedColor: Color for normal points (default: 'lightblue')
                - annotationBackground: Background color for annotations
            config: Additional Plotly config options
            mode: Rendering mode — ``"default"`` (classic stick spectrum),
                ``"density"`` (two-series target/decoy KDE plot), or ``"tagger"``
                (sequence-tag overlay with drill-down). Cache-affecting. Prefer the
                :meth:`density` / :meth:`tagger` factories for the latter two.
            **kwargs: The mode-specific parameters (see :meth:`density` /
                :meth:`tagger`) plus any extra Plotly pass-through config.
        """
        # Pull the mode-specific params out of **kwargs (defaults from the single
        # source of truth). Whatever remains in `kwargs` is genuine extra config.
        density_params = {
            key: kwargs.pop(key, default)
            for key, default in _DENSITY_PARAM_DEFAULTS.items()
        }
        tagger_params = {
            key: kwargs.pop(key, default)
            for key, default in _TAGGER_PARAM_DEFAULTS.items()
        }
        highlight_params = {
            key: kwargs.pop(key, default)
            for key, default in _HIGHLIGHT_PARAM_DEFAULTS.items()
        }

        self._x_column = x_column
        self._y_column = y_column
        self._title = title
        self._x_label = x_label or x_column
        self._y_label = y_label or y_column
        self._highlight_column = highlight_column
        self._annotation_column = annotation_column
        self._styling = styling or {}
        self._plot_config = config or {}

        # Mode + per-mode config
        self._mode = mode or "default"
        # density
        self._category_column = density_params["category_column"]
        self._target_value = density_params["target_value"]
        self._decoy_value = density_params["decoy_value"]
        self._kde_from = density_params["kde_from"]
        self._kde_points = density_params["kde_points"]
        # tagger
        self._signal_peaks_column = tagger_params["signal_peaks_column"]
        self._mz_column = tagger_params["mz_column"]
        self._mz_intensity_column = tagger_params["mz_intensity_column"]
        self._tag_identifier = tagger_params["tag_identifier"]
        self._mass_match_tol = tagger_params["mass_match_tol"]
        self._title_level1 = tagger_params["title_level1"]
        self._x_label_level1 = tagger_params["x_label_level1"]
        self._x_pos_scaling_factor = tagger_params["x_pos_scaling_factor"]
        # Value-based tag-payload resolution (scalar tag id -> TagData side frame).
        self._tag_data_path = tagger_params["tag_data_path"]
        self._tag_id_column = tagger_params["tag_id_column"]
        self._tag_sequence_column = tagger_params["tag_sequence_column"]
        self._tag_masses_column = tagger_params["tag_masses_column"]
        self._tag_start_column = tagger_params["tag_start_column"]
        self._selected_aa_identifier = tagger_params["selected_aa_identifier"]
        self._tag_data = (
            pl.scan_parquet(self._tag_data_path)
            if self._tag_data_path is not None
            else None
        )
        # Selective-highlight (FLASHApp parity) config.
        self._highlight_selection = highlight_params["highlight_selection"]
        self._highlight_match_column = highlight_params["highlight_match_column"]
        self._highlight_link_path = highlight_params["highlight_link_path"]
        self._highlight_link_key_column = highlight_params["highlight_link_key_column"]
        self._highlight_link_match_column = highlight_params[
            "highlight_link_match_column"
        ]
        self._highlight_charge_column = highlight_params["highlight_charge_column"]
        self._highlight_annotation_template = highlight_params[
            "highlight_annotation_template"
        ]
        self._deconv_peaks_toggle = highlight_params["deconv_peaks_toggle"]
        self._highlight_value_column = highlight_params["highlight_value_column"]
        self._highlight_value_template = highlight_params["highlight_value_template"]
        # Lazy handle to the highlight linkage frame (annotated spectrum).
        self._highlight_link = (
            pl.scan_parquet(self._highlight_link_path)
            if self._highlight_link_path is not None
            else None
        )

        # Dynamic annotations set at render time (not cached)
        self._dynamic_annotations: Optional[Dict[str, Any]] = None
        self._dynamic_title: Optional[str] = None
        # Generic render-time per-peak annotation descriptors (not cached)
        self._peak_annotations: Optional[List[Dict[str, Any]]] = None

        super().__init__(
            cache_id=cache_id,
            data=data,
            data_path=data_path,
            filters=filters,
            filter_defaults=filter_defaults,
            interactivity=interactivity,
            cache_path=cache_path,
            regenerate_cache=regenerate_cache,
            # Pass component-specific params for subprocess recreation
            x_column=x_column,
            y_column=y_column,
            title=title,
            x_label=x_label,
            y_label=y_label,
            highlight_column=highlight_column,
            annotation_column=annotation_column,
            styling=styling,
            config=config,
            mode=mode,
            # Per-mode params (round-tripped verbatim for subprocess recreation).
            **density_params,
            **tagger_params,
            **highlight_params,
            **kwargs,
        )

    def _get_cache_config(self) -> Dict[str, Any]:
        """
        Get HASH-AFFECTING (data-shaping) configuration.

        Presentation labels (title/x_label/y_label) are render-time and live in
        ``_get_render_config()`` so changing a label does not rebuild the cache.

        Returns:
            Dict of config values that affect preprocessing
        """
        return {
            "x_column": self._x_column,
            "y_column": self._y_column,
            "highlight_column": self._highlight_column,
            "annotation_column": self._annotation_column,
            "styling": self._styling,
            "plot_config": self._plot_config,
            # Mode + per-mode config
            "mode": self._mode,
            # density
            "category_column": self._category_column,
            "target_value": self._target_value,
            "decoy_value": self._decoy_value,
            "kde_from": self._kde_from,
            "kde_points": self._kde_points,
            # tagger
            "signal_peaks_column": self._signal_peaks_column,
            "mz_column": self._mz_column,
            "mz_intensity_column": self._mz_intensity_column,
            "tag_identifier": self._tag_identifier,
            "mass_match_tol": self._mass_match_tol,
            "title_level1": self._title_level1,
            "x_label_level1": self._x_label_level1,
            "x_pos_scaling_factor": self._x_pos_scaling_factor,
            "tag_data_path": self._tag_data_path,
            "tag_id_column": self._tag_id_column,
            "tag_sequence_column": self._tag_sequence_column,
            "tag_masses_column": self._tag_masses_column,
            "tag_start_column": self._tag_start_column,
            "selected_aa_identifier": self._selected_aa_identifier,
            # selective-highlight (FLASHApp parity) config
            "highlight_selection": self._highlight_selection,
            "highlight_match_column": self._highlight_match_column,
            "highlight_link_path": self._highlight_link_path,
            "highlight_link_key_column": self._highlight_link_key_column,
            "highlight_link_match_column": self._highlight_link_match_column,
            "highlight_charge_column": self._highlight_charge_column,
            "highlight_annotation_template": self._highlight_annotation_template,
            "deconv_peaks_toggle": self._deconv_peaks_toggle,
            "highlight_value_column": self._highlight_value_column,
            "highlight_value_template": self._highlight_value_template,
        }

    def _get_render_config(self) -> Dict[str, Any]:
        """Presentation labels: stored for reconstruction, excluded from hash."""
        return {
            "title": self._title,
            "x_label": self._x_label,
            "y_label": self._y_label,
        }

    def _restore_cache_config(self, config: Dict[str, Any]) -> None:
        """Restore data-shaping configuration from cached config."""
        self._x_column = config.get("x_column", "x")
        self._y_column = config.get("y_column", "y")
        self._highlight_column = config.get("highlight_column")
        self._annotation_column = config.get("annotation_column")
        self._styling = config.get("styling", {})
        self._plot_config = config.get("plot_config", {})
        # Mode + per-mode config
        self._mode = config.get("mode", "default")
        # density
        self._category_column = config.get("category_column", "group")
        self._target_value = config.get("target_value", "target")
        self._decoy_value = config.get("decoy_value", "decoy")
        self._kde_from = config.get("kde_from")
        self._kde_points = config.get("kde_points", 200)
        # tagger
        self._signal_peaks_column = config.get("signal_peaks_column")
        self._mz_column = config.get("mz_column")
        self._mz_intensity_column = config.get("mz_intensity_column")
        self._tag_identifier = config.get("tag_identifier", "tag")
        self._mass_match_tol = config.get("mass_match_tol", 1e-5)
        self._title_level1 = config.get("title_level1")
        self._x_label_level1 = config.get("x_label_level1")
        self._x_pos_scaling_factor = config.get("x_pos_scaling_factor", 27.5)
        self._tag_data_path = config.get("tag_data_path")
        self._tag_id_column = config.get("tag_id_column", "tag_id")
        self._tag_sequence_column = config.get("tag_sequence_column", "sequence")
        self._tag_masses_column = config.get("tag_masses_column", "masses")
        self._tag_start_column = config.get("tag_start_column")
        self._selected_aa_identifier = config.get("selected_aa_identifier")
        self._tag_data = (
            pl.scan_parquet(self._tag_data_path)
            if self._tag_data_path is not None
            else None
        )
        # selective-highlight (FLASHApp parity) config
        self._highlight_selection = config.get("highlight_selection")
        self._highlight_match_column = config.get("highlight_match_column")
        self._highlight_link_path = config.get("highlight_link_path")
        self._highlight_link_key_column = config.get(
            "highlight_link_key_column", "peak_id"
        )
        self._highlight_link_match_column = config.get(
            "highlight_link_match_column", "mass_in_scan"
        )
        self._highlight_charge_column = config.get("highlight_charge_column", "charge")
        self._highlight_annotation_template = config.get(
            "highlight_annotation_template", "z={}"
        )
        self._deconv_peaks_toggle = config.get("deconv_peaks_toggle", False)
        self._highlight_value_column = config.get("highlight_value_column")
        self._highlight_value_template = config.get("highlight_value_template", "{}")
        self._highlight_link = (
            pl.scan_parquet(self._highlight_link_path)
            if self._highlight_link_path is not None
            else None
        )
        # Initialize dynamic annotations (not cached)
        self._dynamic_annotations = None
        self._dynamic_title = None
        self._peak_annotations = None

    def _restore_render_config(self, config: Dict[str, Any]) -> None:
        """Restore presentation labels from cached config.

        Runs after ``_restore_cache_config`` so ``_x_column``/``_y_column`` (used
        as the label fallbacks) are already set.
        """
        self._title = config.get("title")
        self._x_label = config.get("x_label", self._x_column)
        self._y_label = config.get("y_label", self._y_column)

    def _get_row_group_size(self) -> int:
        """
        Get optimal row group size for parquet writing.

        Filtered plots use smaller row groups (10K) for better predicate
        pushdown granularity - this allows Polars to skip row groups that
        don't contain the filter value. Unfiltered plots use larger groups
        (50K) since we read all data anyway.

        Returns:
            Number of rows per row group
        """
        if self._filters:
            return 10_000  # Smaller groups for better filter performance
        return 50_000  # Larger groups for unfiltered plots

    def _validate_mappings(self) -> None:
        """Validate columns exist in data schema."""
        if self._raw_data is None:
            return  # Skip validation when reconstructing from cache

        schema = self._raw_data.collect_schema()
        column_names = schema.names()

        # Tagger mode: the interactivity column (peak_id) is SYNTHESIZED per
        # render (0..len(MonoMass)-1), not a stored column. Validate filters
        # here and skip the base interactivity-column existence check for it.
        if self._mode == "tagger":
            for identifier, column in self._filters.items():
                if column not in column_names:
                    raise ValueError(
                        f"Filter column '{column}' for identifier '{identifier}' "
                        f"not found in data. Available columns: {column_names}"
                    )
            self._validate_tagger_mappings(column_names)
            # Validate x/y list columns + optional annotation/highlight columns.
            for col_name, col_label in [
                (self._x_column, "x_column"),
                (self._y_column, "y_column"),
            ]:
                if col_name not in column_names:
                    raise ValueError(
                        f"{col_label} '{col_name}' not found in data. "
                        f"Available columns: {column_names}"
                    )
            return

        super()._validate_mappings()

        # Density mode raw-score path: x/y columns are produced by the KDE step,
        # so only the source score/label columns must exist up-front.
        if self._mode == "density":
            self._validate_density_mappings(column_names)
            return

        # Validate x and y columns exist
        for col_name, col_label in [
            (self._x_column, "x_column"),
            (self._y_column, "y_column"),
        ]:
            if col_name not in column_names:
                raise ValueError(
                    f"{col_label} '{col_name}' not found in data. "
                    f"Available columns: {column_names}"
                )

        # Validate optional columns if specified
        if self._highlight_column and self._highlight_column not in column_names:
            raise ValueError(
                f"highlight_column '{self._highlight_column}' not found in data. "
                f"Available columns: {column_names}"
            )

        if self._annotation_column and self._annotation_column not in column_names:
            raise ValueError(
                f"annotation_column '{self._annotation_column}' not found in data. "
                f"Available columns: {column_names}"
            )

    def _validate_density_mappings(self, column_names: List[str]) -> None:
        """Per-mode column existence checks for density mode."""
        if self._kde_from:
            for role in ("score", "label"):
                col = self._kde_from.get(role)
                if col is None:
                    raise ValueError(
                        f"kde_from must define '{role}' column for density mode"
                    )
                if col not in column_names:
                    raise ValueError(
                        f"kde_from {role} column '{col}' not found in data. "
                        f"Available columns: {column_names}"
                    )
        else:
            # Pre-binned tidy frame: x/y/group must exist
            for col_name, col_label in [
                (self._x_column, "x_column"),
                (self._y_column, "y_column"),
                (self._category_column, "category_column"),
            ]:
                if col_name not in column_names:
                    raise ValueError(
                        f"{col_label} '{col_name}' not found in data. "
                        f"Available columns: {column_names}"
                    )

    def _validate_tagger_mappings(self, column_names: List[str]) -> None:
        """Per-mode column existence checks for tagger mode."""
        if not self._signal_peaks_column:
            raise ValueError("tagger mode requires signal_peaks_column")
        if self._signal_peaks_column not in column_names:
            raise ValueError(
                f"signal_peaks_column '{self._signal_peaks_column}' not found in "
                f"data. Available columns: {column_names}"
            )
        for col in (self._mz_column, self._mz_intensity_column):
            if col is not None and col not in column_names:
                raise ValueError(
                    f"tagger column '{col}' not found in data. "
                    f"Available columns: {column_names}"
                )

    def _preprocess(self) -> None:
        """
        Preprocess plot data.

        Sorts by filter columns for efficient predicate pushdown, then
        collects the LazyFrame for caching by base class.
        """
        data = self._raw_data

        if self._mode == "density":
            data = self._preprocess_density(data)
        else:
            # Sort by filter columns for efficient predicate pushdown. This
            # clusters identical filter values together, enabling Polars to skip
            # row groups that don't contain the target value when filtering by
            # selection state. (Applies to default + tagger modes.)
            if self._filters:
                sort_columns = list(self._filters.values())
                data = data.sort(sort_columns)

        # Store configuration in preprocessed data for serialization
        self._preprocessed_data["plot_config"] = {
            "x_column": self._x_column,
            "y_column": self._y_column,
            "highlight_column": self._highlight_column,
            "annotation_column": self._annotation_column,
            "mode": self._mode,
        }

        # Store LazyFrame for streaming to disk (filter happens at render time)
        # Base class will use sink_parquet() to stream without full materialization
        self._preprocessed_data["data"] = data  # Keep lazy

    def _preprocess_density(self, data: pl.LazyFrame) -> pl.LazyFrame:
        """
        Normalize density-mode input to the tidy long ``{x, y, group}`` frame.

        Two input shapes are accepted:

        1. Pre-binned tidy (preferred): pass through unchanged. No scipy needed.
        2. Raw scores (``kde_from`` set): run ``scipy.stats.gaussian_kde`` per
           group (lazily imported) and emit the tidy long frame. scipy is an
           optional dependency — a clear error is raised if it is missing.
        """
        if not self._kde_from:
            # Project to the tidy schema (defensive: keep just x/y/group).
            return data.select([self._x_column, self._y_column, self._category_column])

        score_col = self._kde_from["score"]
        label_col = self._kde_from["label"]

        try:
            import numpy as np
            from scipy.stats import gaussian_kde
        except ImportError as exc:  # pragma: no cover - depends on env
            raise ImportError(
                "LinePlot(mode='density', kde_from=...) requires scipy and numpy. "
                "Install scipy, or pass a precomputed tidy {x, y, group} frame "
                "instead of using kde_from."
            ) from exc

        df = data.select([score_col, label_col]).collect()

        frames: list[pl.DataFrame] = []
        for group_value in (self._target_value, self._decoy_value):
            scores = (
                df.filter(pl.col(label_col) == group_value)[score_col]
                .drop_nulls()
                .to_numpy()
            )
            if scores.size == 0:
                # Empty group (e.g. no decoys) -> contribute no rows (oracle parity:
                # empty decoy => target-only plot).
                continue
            grid = np.linspace(scores.min(), scores.max(), self._kde_points)
            density = gaussian_kde(scores)(grid)
            frames.append(
                pl.DataFrame(
                    {
                        self._x_column: grid,
                        self._y_column: density,
                        self._category_column: [group_value] * len(grid),
                    }
                )
            )

        if frames:
            return pl.concat(frames).lazy()
        # Degenerate: no data at all -> empty tidy frame with correct schema.
        return pl.DataFrame(
            schema={
                self._x_column: pl.Float64,
                self._y_column: pl.Float64,
                self._category_column: pl.Utf8,
            }
        ).lazy()

    def _get_vue_component_name(self) -> str:
        """Return the Vue component name."""
        if self._mode == "density":
            return "PlotlyDensityPlot"
        if self._mode == "tagger":
            # Tagger reuses the line-plot dispatch; mode switches behavior in-Vue.
            return "PlotlyLineplot"
        return "PlotlyLineplotUnified"

    def _get_data_key(self) -> str:
        """Return the key used to send primary data to Vue."""
        return "plotData"

    def get_state_dependencies(self) -> List[str]:
        """
        Return list of state keys that affect this component's data.

        - density: static plot, no dependencies (cached once per dataset).
        - tagger: the ``spectrum`` filter, the ``tag`` selection (TagData payload
          or a scalar id resolved via the side frame), the ``tagger_mass``
          interactivity drill-down, and the optional residue
          ``selected_aa_identifier`` all change the emitted frames, so each is a
          dependency.
        - default: base behavior (filter identifiers).
        """
        if self._mode == "density":
            return []
        if self._mode == "tagger":
            deps = list(self._filters.keys())
            for ident in self._interactivity.keys():
                if ident not in deps:
                    deps.append(ident)
            # The tag selection and residue selection are read directly from state
            # (not via filters/interactivity column matching), so register them too.
            for ident in (self._tag_identifier, self._selected_aa_identifier):
                if ident and ident not in deps:
                    deps.append(ident)
            return deps
        deps = list(self._filters.keys())
        # The selective-highlight (FLASHApp parity) is computed at render time from
        # the highlight selection, so a change to it must invalidate this plot's
        # cache. Registering it as a dependency makes a selection change a cache
        # MISS => ``_prepare_vue_data_default`` recomputes the highlight from the
        # fresh state (the modebar toggles then switch sets client-side, no
        # round-trip). Off by default => no behavior change for existing plots.
        if self._highlight_selection and self._highlight_selection not in deps:
            deps.append(self._highlight_selection)
        return deps

    def _prepare_vue_data(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Prepare plot data for Vue component.

        Branches on ``self._mode``:
        - density: emit the tidy ``{x, y, group}`` frame (no filtering).
        - tagger: emit level-0 sticks + sequence-arrow segments + level-1 charge
          clusters, all keyed by stable ``peak_id``.
        - default: classic stick spectrum (filter + highlight + annotations).

        Args:
            state: Current selection state from StateManager

        Returns:
            Dict with primary data and ``_hash`` for change detection
        """
        if self._mode == "density":
            return self._prepare_vue_data_density(state)
        if self._mode == "tagger":
            return self._prepare_vue_data_tagger(state)
        return self._prepare_vue_data_default(state)

    def _prepare_vue_data_default(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Classic stick-spectrum payload (unchanged behavior)."""
        # Build list of columns to select (projection pushdown for efficiency)
        columns_to_select = [self._x_column, self._y_column]
        if self._highlight_column:
            columns_to_select.append(self._highlight_column)
        if self._annotation_column:
            columns_to_select.append(self._annotation_column)
        # Include columns needed for interactivity (e.g., peak_id)
        if self._interactivity:
            for col in self._interactivity.values():
                if col not in columns_to_select:
                    columns_to_select.append(col)
        # Include filter columns for filtering to work
        if self._filters:
            for col in self._filters.values():
                if col not in columns_to_select:
                    columns_to_select.append(col)
        # Selective-highlight (FLASHApp parity) needs its match column kept in the
        # base projection (the deconv spectrum highlights base rows by it).
        if self._highlight_selection and self._highlight_match_column:
            if self._highlight_match_column not in columns_to_select:
                columns_to_select.append(self._highlight_match_column)
            # The optional match-column value label (deconv MonoMass) needs its
            # source column in the projection too.
            if (
                self._highlight_value_column
                and self._highlight_value_column not in columns_to_select
            ):
                columns_to_select.append(self._highlight_value_column)

        # Get cached data (DataFrame or LazyFrame)
        data = self._preprocessed_data.get("data")
        if data is None:
            # Fallback to raw data if available
            data = self._raw_data

        # Ensure we have a LazyFrame for filtering
        if isinstance(data, pl.DataFrame):
            data = data.lazy()

        # Use cached filter+collect - returns (pandas DataFrame, hash)
        df_pandas, data_hash = filter_and_collect_cached(
            data,
            self._filters,
            state,
            columns=columns_to_select,
            filter_defaults=self._filter_defaults,
        )

        # Determine which highlight/annotation columns to use
        highlight_col = self._highlight_column
        annotation_col = self._annotation_column

        # --- Selective highlight (FLASHApp parity), SELECTION-driven, NOT cached --
        # When the new highlight params are set, compute (at render time, from the
        # fresh selection state):
        #   (a) the SELECTIVE highlight key-set (the selected mass's peaks),
        #   (b) the ALL-SIGNAL key-set (every signal peak; powers the toggle),
        #   (c) per-charge z=N labels for the selected set (COG producer).
        # (a) reuses the existing ``_dynamic_annotations`` highlight column path —
        # we merge the computed selective set into the keyed dynamic-annotation dict
        # used just below, so the SAME ``_dynamic_highlight`` column + plot-config
        # wiring renders it (identical to a caller-supplied ``set_dynamic_annotations``).
        # (b) + the toggle-default flags + button labels are passed to Vue so the
        # modebar toggles switch the drawn set client-side with NO server round-trip.
        # This supersedes the static ``highlight_column`` ONLY when configured.
        #
        # IMPORTANT: the computation is local (it does NOT mutate the instance
        # ``_dynamic_annotations``/``_peak_annotations`` attributes), so the bridge's
        # render-time-annotation machinery stays inert and the FULL payload caches
        # cleanly keyed by the highlight selection (a state dependency). A cache HIT
        # therefore means the same selection and the cached selective highlight is
        # correct verbatim.
        all_signal_keys: Optional[List[Any]] = None
        if self._highlight_selection:
            (
                selective_highlight,
                all_signal_keys,
                charge_descriptors,
            ) = self._compute_selective_highlight(df_pandas, state)
            # Merge (a) into the keyed dynamic-annotation dict consumed below. A
            # caller-supplied ``_dynamic_annotations`` still wins per key (additive,
            # no override); the selective set fills the rest.
            if selective_highlight:
                merged = dict(selective_highlight)
                if isinstance(self._dynamic_annotations, dict):
                    merged.update(self._dynamic_annotations)
                dynamic_annotations = merged
            else:
                dynamic_annotations = self._dynamic_annotations
            # (c) z=N labels: prefer a caller-supplied set, else the computed one.
            peak_annotations = (
                self._peak_annotations
                if self._peak_annotations is not None
                else charge_descriptors
            )
        else:
            dynamic_annotations = self._dynamic_annotations
            peak_annotations = self._peak_annotations

        # Apply dynamic annotations if set
        # Annotations are keyed by peak_id (stable identifier from interactivity column)
        if dynamic_annotations and len(df_pandas) > 0:
            num_rows = len(df_pandas)
            highlights = [False] * num_rows
            annotations = [""] * num_rows

            # Get the interactivity column to use for lookup (e.g., 'peak_id')
            # Use the first interactivity column as the ID column for annotation lookup
            id_column = None
            if self._interactivity:
                id_column = list(self._interactivity.values())[0]

            # Apply annotations by peak_id lookup
            if id_column and id_column in df_pandas.columns:
                peak_ids = df_pandas[id_column].tolist()
                for row_idx, peak_id in enumerate(peak_ids):
                    if peak_id in dynamic_annotations:
                        ann_data = dynamic_annotations[peak_id]
                        highlights[row_idx] = ann_data.get("highlight", False)
                        annotations[row_idx] = ann_data.get("annotation", "")
            else:
                # Fallback: use row index as key (legacy behavior)
                for idx, ann_data in dynamic_annotations.items():
                    if isinstance(idx, int) and 0 <= idx < num_rows:
                        highlights[idx] = ann_data.get("highlight", False)
                        annotations[idx] = ann_data.get("annotation", "")

            # Add dynamic columns to dataframe
            df_pandas = df_pandas.copy()
            df_pandas["_dynamic_highlight"] = highlights
            df_pandas["_dynamic_annotation"] = annotations

            # Update column names to use dynamic columns
            highlight_col = "_dynamic_highlight"
            annotation_col = "_dynamic_annotation"

            # Update hash to include dynamic annotation state
            ann_hash = hashlib.md5(
                str(sorted(dynamic_annotations.keys())).encode()
            ).hexdigest()[:8]
            data_hash = f"{data_hash}_{ann_hash}"

        # Send as DataFrame for Arrow serialization (efficient binary transfer)
        # Vue will parse and extract columns using the config
        result: Dict[str, Any] = {
            "plotData": df_pandas,
            "_hash": data_hash,
            "_plotConfig": self._build_plot_config(highlight_col, annotation_col),
        }
        # Attach generic render-time per-peak annotation descriptors (not cached).
        # Uses the LOCAL peak_annotations (caller's set, or the computed z=N labels).
        self._attach_peak_annotations(result, peak_annotations)
        # Attach the selective-highlight payload (ALL-SIGNAL set + toggle defaults +
        # button labels) so the Vue modebar toggles switch sets WITHOUT a round-trip.
        if self._highlight_selection:
            self._attach_selective_highlight(result, all_signal_keys)
        return result

    @staticmethod
    def _coerce_selection_value(sel: Any) -> Any:
        """Normalize a JSON selection scalar (float 3.0 -> int 3) for matching."""
        if isinstance(sel, float) and sel.is_integer():
            return int(sel)
        return sel

    def _compute_selective_highlight(
        self, df_pandas: "Any", state: Dict[str, Any]
    ) -> tuple:
        """
        Compute the FLASHApp-parity selective highlight from the current selection.

        Returns ``(selective_highlight, all_signal_keys, charge_descriptors)``:

        - ``selective_highlight``: ``{key: {"highlight": True}}`` for the base rows
          belonging to the selected mass (drives the orange highlight via the
          existing ``_dynamic_highlight`` column path). ``key`` is the base frame's
          first-interactivity value (e.g. ``peak_id``).
        - ``all_signal_keys``: every signal-peak key (LINK path only) — the set the
          "Show Deconvolved Peaks" toggle highlights client-side. ``None`` when no
          link frame is configured (the deconv/match-column path has no toggle).
        - ``charge_descriptors``: per-charge ``z=N`` label descriptors at each
          charge group's intensity-weighted COG m/z (LINK path only; the deconv
          spectrum emits NO charge labels). ``None`` otherwise.

        Two modes (parity with PlotlyLineplotUnified.vue ``highlightedValues``):

        * MATCH-COLUMN (deconv spectrum): highlight base rows where
          ``base[highlight_match_column] == sel``. ``base`` carries one mass per row
          (``mass_in_scan``), so the selected mass's row(s) light up directly.
        * LINK (annotated spectrum): the highlighted peaks are a SUBSET linked by
          signal-peak membership. The linkage frame has one row per
          ``(signal peak, mass)``; selective keys are the ``key_column`` values whose
          ``match_column`` equals ``sel`` (may be 1:many per peak).
        """
        sel = self._coerce_selection_value(state.get(self._highlight_selection))

        # Base ID column used to key the highlight (first interactivity column,
        # e.g. peak_id). Without it we cannot map highlight keys onto base rows.
        id_column: Optional[str] = None
        if self._interactivity:
            id_column = list(self._interactivity.values())[0]

        # ---- MATCH-COLUMN path (deconvolved spectrum) ----
        if self._highlight_link is None and self._highlight_match_column:
            selective: Dict[Any, Dict[str, Any]] = {}
            # Optional value label above each matched stick (e.g. the selected
            # mass's MonoMass value on the deconvolved spectrum -- oracle parity).
            want_label = (
                self._highlight_value_column is not None
                and self._highlight_value_column in df_pandas.columns
                and self._x_column in df_pandas.columns
            )
            value_descriptors: Optional[List[Dict[str, Any]]] = None
            if (
                sel is not None
                and id_column is not None
                and id_column in df_pandas.columns
                and self._highlight_match_column in df_pandas.columns
            ):
                match_vals = df_pandas[self._highlight_match_column].tolist()
                key_vals = df_pandas[id_column].tolist()
                x_vals = df_pandas[self._x_column].tolist() if want_label else None
                val_vals = (
                    df_pandas[self._highlight_value_column].tolist()
                    if want_label
                    else None
                )
                color = self._styling.get("highlightColor", "#E4572E")
                descriptors: List[Dict[str, Any]] = []
                for i, (key, mval) in enumerate(zip(key_vals, match_vals)):
                    if self._values_match(mval, sel):
                        selective[key] = {"highlight": True}
                        if want_label:
                            try:
                                text = self._highlight_value_template.format(
                                    val_vals[i]
                                )
                            except (ValueError, KeyError, IndexError):
                                text = str(val_vals[i])
                            descriptors.append(
                                {"x": float(x_vals[i]), "text": text, "color": color}
                            )
                if descriptors:
                    value_descriptors = descriptors
            # No link frame => no all-signal toggle / z=N labels (deconv parity);
            # the optional value label rides the same peak-annotation channel as the
            # link path's z=N labels (3rd return).
            return selective, None, value_descriptors

        # ---- LINK path (annotated spectrum) ----
        if self._highlight_link is not None:
            return self._compute_link_highlight(df_pandas, sel, id_column)

        # Highlight selection configured but neither match column nor link frame:
        # nothing to highlight (defensive). Off-by-default contract preserved.
        return {}, None, None

    @staticmethod
    def _values_match(a: Any, b: Any) -> bool:
        """Equality with float/int tolerance for mass/index selection scalars."""
        if a is None or b is None:
            return False
        if a == b:
            return True
        try:
            return float(a) == float(b)
        except (TypeError, ValueError):
            return False

    def _compute_link_highlight(
        self, df_pandas: "Any", sel: Any, id_column: Optional[str]
    ) -> tuple:
        """LINK-path selective highlight + all-signal set + z=N COG descriptors."""
        key_col = self._highlight_link_key_column
        match_col = self._highlight_link_match_column
        charge_col = self._highlight_charge_column

        # Collect the linkage frame once (cached via the component's filtering layer
        # is unnecessary here — it is a small per-spectrum side frame; we still use
        # ``filter_and_collect_cached`` for consistency with the component's caching).
        link_cols = [key_col, match_col]
        if charge_col:
            link_cols.append(charge_col)
        link_df, _ = filter_and_collect_cached(
            self._highlight_link,
            {},  # no row filters — the linkage frame is already per-context
            {},
            columns=list(dict.fromkeys(link_cols)),
        )

        # ALL-SIGNAL set: every signal-peak key in the linkage (toggle highlights
        # ALL masses' peaks). Preserve first-seen order, de-duplicated.
        all_signal_keys = (
            list(dict.fromkeys(link_df[key_col].tolist()))
            if (len(link_df) > 0 and key_col in link_df.columns)
            else []
        )

        # SELECTIVE set: linkage rows whose match value == the selected mass.
        selective: Dict[Any, Dict[str, Any]] = {}
        selected_keys: List[Any] = []
        if sel is not None and len(link_df) > 0 and match_col in link_df.columns:
            keys = link_df[key_col].tolist()
            matches = link_df[match_col].tolist()
            for key, mval in zip(keys, matches):
                if self._values_match(mval, sel):
                    if key not in selective:
                        selective[key] = {"highlight": True}
                        selected_keys.append(key)

        # z=N labels: per-charge COG over the SELECTED mass's linked peaks. Pull
        # (mz, intensity) from the base frame (x/y) joined on the key, and the
        # charge from the linkage. Mirrors compute_charge_annotations' COG producer
        # (intensity-weighted center-of-gravity m/z, oracle formula).
        charge_descriptors: Optional[List[Dict[str, Any]]] = None
        if (
            selected_keys
            and id_column is not None
            and id_column in df_pandas.columns
            and charge_col
            and charge_col in link_df.columns
        ):
            # Map base key -> (mz, intensity) from the displayed frame.
            base_mz = dict(
                zip(df_pandas[id_column].tolist(), df_pandas[self._x_column].tolist())
            )
            base_int = dict(
                zip(df_pandas[id_column].tolist(), df_pandas[self._y_column].tolist())
            )
            # signal_peaks list shaped like compute_charge_annotations input:
            # [idx, mz, intensity, charge] per selected linked peak.
            sel_set = set(selected_keys)
            keys = link_df[key_col].tolist()
            charges = link_df[charge_col].tolist()
            signal_peaks: List[List[float]] = []
            for key, chg in zip(keys, charges):
                if key not in sel_set:
                    continue
                if key not in base_mz:
                    continue
                signal_peaks.append(
                    [
                        0.0,
                        float(base_mz[key]),
                        float(base_int.get(key, 0.0)),
                        float(chg),
                    ]
                )
            if signal_peaks:
                color = self._styling.get("highlightColor", "#E4572E")
                charge_descriptors = compute_charge_annotations(
                    signal_peaks,
                    color=color,
                    template=self._highlight_annotation_template,
                )

        return selective, all_signal_keys, charge_descriptors

    def _attach_selective_highlight(
        self, result: Dict[str, Any], all_signal_keys: Optional[List[Any]]
    ) -> None:
        """
        Attach the selective-highlight client-side toggle payload to the Vue data.

        Sends the ALL-SIGNAL key-set + the id column it keys on + the two
        toggle-default flags + dynamic button labels so the Vue modebar toggles can
        switch the highlighted trace and the z=N labels WITHOUT a server round-trip.
        Folds the all-signal digest into ``_hash`` so the frontend re-renders when
        the set changes.
        """
        id_column: Optional[str] = None
        if self._interactivity:
            id_column = list(self._interactivity.values())[0]
        payload: Dict[str, Any] = {
            "idColumn": id_column,
            # ALL-SIGNAL key-set for the "Show Deconvolved Peaks" toggle. Empty
            # list (not None) when a link frame exists but is empty; None when no
            # link frame is configured (deconv path => button is suppressed anyway).
            "allSignalKeys": all_signal_keys,
            # Toggle DEFAULTS (oracle): annotations visible ON, deconv-peaks OFF.
            "annotationsVisible": True,
            "deconvolvedPeaksHighlightMode": False,
            # Button enable + dynamic titles (oracle PlotlyLineplotUnified.vue).
            "deconvPeaksToggle": bool(self._deconv_peaks_toggle),
        }
        result["selectiveHighlight"] = payload
        digest = hashlib.md5(
            json.dumps(
                {"all": all_signal_keys, "dt": bool(self._deconv_peaks_toggle)},
                sort_keys=True,
                default=str,
            ).encode()
        ).hexdigest()[:8]
        result["_hash"] = f"{result.get('_hash', '')}_sh{digest}"

    def _prepare_vue_data_density(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Static density payload: emit the tidy long ``{x, y, group}`` frame."""
        data = self._preprocessed_data.get("data")
        if data is None:
            data = self._raw_data
        if isinstance(data, pl.DataFrame):
            data = data.lazy()

        # Project to the tidy columns (ignore selection state — static plot).
        columns = [self._x_column, self._y_column, self._category_column]
        df_polars = data.select(columns).collect()
        df_pandas = df_polars.to_pandas()

        # Stable hash: data does not depend on state. Include row count + the
        # observed target/decoy value set + mode/columns.
        value_set = sorted(
            set(df_polars[self._category_column].to_list())
            if len(df_polars) > 0
            else []
        )
        hash_input = "|".join(
            [
                "density",
                self._x_column,
                self._y_column,
                self._category_column,
                str(len(df_polars)),
                str(value_set),
                str(self._target_value),
                str(self._decoy_value),
            ]
        )
        data_hash = hashlib.sha256(hash_input.encode()).hexdigest()

        return {
            "plotData": df_pandas,
            "_hash": data_hash,
            "_plotConfig": {
                "mode": "density",
                "xColumn": self._x_column,
                "yColumn": self._y_column,
                "categoryColumn": self._category_column,
                "targetValue": self._target_value,
                "decoyValue": self._decoy_value,
            },
        }

    def _resolve_tag_payload(
        self, tag_id: Any, state: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Resolve a scalar tag id to a TagData payload via the side frame.

        Looks up the row whose ``tag_id_column`` equals ``tag_id`` and builds the
        ``{sequence, masses, selectedAA}`` dict the tagger consumes. ``masses`` may
        be stored as a list column or a comma-separated string. ``selectedAA`` (the
        tag-relative residue index used for the gold highlight) is derived from a
        residue-position selection (``selected_aa_identifier``) minus the tag's
        start (``tag_start_column``) when both are available. Returns ``None`` when
        the id has no matching row (selection cleared / stale).
        """
        if self._tag_data is None or tag_id is None:
            return None
        # Tolerate float ids coming back from JSON (e.g. 3.0 -> 3).
        if isinstance(tag_id, float) and tag_id.is_integer():
            tag_id = int(tag_id)
        try:
            row = (
                self._tag_data.filter(pl.col(self._tag_id_column) == tag_id)
                .head(1)
                .collect()
            )
        except Exception:
            return None
        if row.height == 0:
            return None
        r = row.row(0, named=True)

        raw_masses = r.get(self._tag_masses_column)
        if isinstance(raw_masses, str):
            masses = [float(x) for x in raw_masses.split(",") if x.strip() != ""]
        elif raw_masses is None:
            masses = []
        else:
            masses = [float(x) for x in raw_masses]

        payload: Dict[str, Any] = {
            "sequence": r.get(self._tag_sequence_column),
            "masses": masses,
        }
        # Optional gold-residue selection: tag-relative AA = residue pos - tag start.
        if self._selected_aa_identifier and self._tag_start_column:
            aa_pos = state.get(self._selected_aa_identifier)
            start = r.get(self._tag_start_column)
            if aa_pos is not None and start is not None:
                payload["selectedAA"] = int(aa_pos) - int(start)
        return payload

    def _prepare_vue_data_tagger(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Tagger payload: explode the selected scan row into tidy frames.

        Emits three ``plotData*`` Arrow tables:
        - ``plotData``: level-0 deconvolved sticks (highlight/selected/mass_label).
        - ``plotDataTaggerSegments``: level-0 sequence arrows (one per adjacent
          highlighted pair).
        - ``plotDataTaggerCharges``: level-1 m/z clusters for the open mass
          (precomputed center-of-gravity per charge); empty unless a (valid)
          ``tagger_mass`` is selected.
        """
        import pandas as pd

        data = self._preprocessed_data.get("data")
        if data is None:
            data = self._raw_data
        if isinstance(data, pl.DataFrame):
            data = data.lazy()

        # Filter to the selected spectrum row (one row of list columns).
        # The `tag` filter identifier carries an opaque TagData payload (not a
        # column-matchable scalar), so it is EXCLUDED from row filtering — only
        # the scan/spectrum filter(s) select the row.
        row_filters = {
            ident: col
            for ident, col in self._filters.items()
            if ident != self._tag_identifier
        }
        filtered, _ = filter_and_collect_cached(
            data,
            row_filters,
            state,
            columns=None,
            filter_defaults=self._filter_defaults,
        )

        # Extract the tag payload. The 'tag' selection may carry an opaque TagData
        # dict directly, OR a scalar tag id (e.g. from a Table row click) that we
        # resolve to a TagData payload via the configured side frame.
        tag = state.get(self._tag_identifier)
        if tag is not None and not isinstance(tag, dict) and self._tag_data is not None:
            tag = self._resolve_tag_payload(tag, state)
        tag_masses, sequence, selected_aa = _parse_tag_payload(tag)

        # Pull the single scan row's list columns.
        if len(filtered) == 0:
            mono_mass: List[float] = []
            sum_intensity: List[float] = []
            signal_peaks: List[Any] = []
            anno_mz: List[float] = []
            anno_intensity: List[float] = []
        else:
            row = filtered.iloc[0]
            mono_mass = _as_float_list(row.get(self._x_column))
            sum_intensity = _as_float_list(row.get(self._y_column))
            signal_peaks = _as_list(row.get(self._signal_peaks_column))
            # Full annotated (m/z) spectrum drawn at level 1 (oracle parity):
            # MonoMass_Anno / SumIntensity_Anno (a superset of any single mass's
            # signal-peak envelope). Optional — empty when columns not configured.
            anno_mz = (
                _as_float_list(row.get(self._mz_column))
                if self._mz_column is not None
                else []
            )
            anno_intensity = (
                _as_float_list(row.get(self._mz_intensity_column))
                if self._mz_intensity_column is not None
                else []
            )

        # --- Level-0 highlight masks + gold (reversed-index) selection ---
        highlighted_pos = _highlight_mass_positions(
            mono_mass, tag_masses, self._mass_match_tol
        )
        reversed_selected_aa = _reversed_selected_aa(sequence, selected_aa)
        # Map MonoMass index -> position within the highlighted list (for the gold rule)
        idx_to_hpos = {idx: hpos for hpos, idx in enumerate(highlighted_pos)}
        highlighted_set = set(highlighted_pos)

        highlight_flags: List[bool] = []
        selected_flags: List[bool] = []
        mass_labels: List[str] = []
        for i, mass in enumerate(mono_mass):
            is_hl = i in highlighted_set
            highlight_flags.append(is_hl)
            gold = False
            if is_hl and reversed_selected_aa is not None:
                hpos = idx_to_hpos[i]
                gold = (reversed_selected_aa == hpos) or (
                    reversed_selected_aa == hpos - 1
                )
            selected_flags.append(gold)
            mass_labels.append(f"{mass:.2f}" if is_hl else "")

        df_level0 = pd.DataFrame(
            {
                self._x_column: mono_mass,
                self._y_column: sum_intensity,
                "peak_id": list(range(len(mono_mass))),
                "highlight": highlight_flags,
                "selected_gold": selected_flags,
                "mass_label": mass_labels,
            }
        )

        # --- Stale tagger_mass reset: ignore a peak_id not in the highlight set ---
        tagger_mass = state.get(self._interactivity_first_identifier())
        if tagger_mass is not None and isinstance(tagger_mass, float):
            if tagger_mass.is_integer():
                tagger_mass = int(tagger_mass)
        valid_open_mass = tagger_mass is not None and tagger_mass in highlighted_set

        # --- Level-0 sequence-arrow segments (adjacent highlighted pairs) ---
        df_segments = pd.DataFrame(
            compute_tagger_segments(
                mono_mass, highlighted_pos, sequence, reversed_selected_aa
            )
        )
        if df_segments.empty:
            df_segments = pd.DataFrame(
                columns=["x_start", "x_end", "residue", "delta", "selected"]
            )

        # --- Level-1 m/z charge clusters (only when a valid mass is open) ---
        if valid_open_mass:
            # Position of the open mass within the highlighted list (oracle index).
            open_hpos = idx_to_hpos[tagger_mass]
            open_signal_peaks = (
                signal_peaks[tagger_mass] if tagger_mass < len(signal_peaks) else []
            )
            # Per-charge COG badge clusters (z=<charge>). The BADGE gold flag uses
            # the RAW selectedAA rule (oracle Tagger.vue:322-323), distinct from
            # the STICK gold rule below which uses reversedSelectedAA.
            df_charges = pd.DataFrame(
                compute_tagger_charges(
                    open_signal_peaks,
                    selected_aa=selected_aa,
                    selected_mass_index=open_hpos,
                )
            )
            # Full annotated (m/z) spectrum drawn at level 1 (oracle parity): the
            # entire MonoMass_Anno spectrum with ONLY the open mass's m/z peaks
            # highlighted. The STICK gold flag uses reversedSelectedAA == open_hpos
            # (|| == open_hpos-1) — oracle Tagger.vue:260 (reversedSelectedAA),
            # NOT the raw selectedAA used by the charge BADGE.
            stick_gold = reversed_selected_aa is not None and (
                reversed_selected_aa == open_hpos
                or reversed_selected_aa == open_hpos - 1
            )
            df_level1 = pd.DataFrame(
                compute_tagger_level1_spectrum(
                    anno_mz,
                    anno_intensity,
                    open_signal_peaks,
                    stick_gold=stick_gold,
                    tol=self._mass_match_tol,
                )
            )
        else:
            df_charges = pd.DataFrame()
            df_level1 = pd.DataFrame()
        if df_charges.empty:
            df_charges = pd.DataFrame(
                columns=[
                    "mz",
                    "intensity",
                    "charge",
                    "peak_id",
                    "cog",
                    "charge_label",
                    "selected",
                ]
            )
        if df_level1.empty:
            df_level1 = pd.DataFrame(columns=["x", "y", "highlight", "selected_gold"])

        # --- Hash includes spectrum + tag payload + drill-down state ---
        # Use the scan/spectrum filter value (exclude the opaque tag payload key,
        # which is captured separately via tag_digest below).
        spectrum_value = None
        for ident in self._filters.keys():
            if ident == self._tag_identifier:
                continue
            spectrum_value = state.get(ident)
            break
        tag_digest = hashlib.md5(
            json.dumps(
                {
                    "masses": tag_masses,
                    "sequence": sequence,
                    "selectedAA": selected_aa,
                },
                sort_keys=True,
            ).encode()
        ).hexdigest()[:8]
        level = "annotated" if valid_open_mass else "deconvolved"
        hash_input = "|".join(
            [
                "tagger",
                str(spectrum_value),
                tag_digest,
                str(tagger_mass if valid_open_mass else None),
                str(len(mono_mass)),
                str(len(df_charges)),
                str(len(df_level1)),
            ]
        )
        data_hash = hashlib.sha256(hash_input.encode()).hexdigest()

        return {
            "plotData": df_level0,
            "plotDataTaggerSegments": df_segments,
            "plotDataTaggerCharges": df_charges,
            "plotDataTaggerLevel1": df_level1,
            "_hash": data_hash,
            "_plotConfig": {
                "mode": "tagger",
                "xColumn": self._x_column,
                "yColumn": self._y_column,
                "highlightColumn": "highlight",
                "selectedColumn": "selected_gold",
                "annotationColumn": "mass_label",
                "interactivityColumns": {
                    col: col
                    for col in (
                        self._interactivity.values() if self._interactivity else []
                    )
                },
                "level": level,
            },
        }

    def _interactivity_first_identifier(self) -> Optional[str]:
        """Return the first interactivity identifier (the drill-down key)."""
        if self._interactivity:
            return next(iter(self._interactivity.keys()))
        return None

    def _attach_peak_annotations(
        self,
        result: Dict[str, Any],
        annotations: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """
        Attach generic render-time per-peak annotation descriptors to the payload.

        Mirrors the dynamic-annotation pattern: descriptors are NOT cached (the
        bridge re-applies them on a cache hit via :meth:`_apply_fresh_annotations`)
        and the hash absorbs them so the frontend re-renders when they change.

        Args:
            result: The vue-data dict to attach onto.
            annotations: Explicit descriptor list (e.g. the selective-highlight z=N
                labels computed at render time). Defaults to ``self._peak_annotations``
                so existing callers (``_apply_fresh_annotations``) are unchanged.
        """
        descriptors = annotations if annotations is not None else self._peak_annotations
        if descriptors is None:
            return
        result["peakAnnotations"] = descriptors
        digest = hashlib.md5(
            json.dumps(descriptors, sort_keys=True, default=str).encode()
        ).hexdigest()[:8]
        result["_hash"] = f"{result.get('_hash', '')}_pa{digest}"

    def _get_component_args(self) -> Dict[str, Any]:
        """
        Get component arguments to send to Vue.

        Returns:
            Dict with all plot configuration for Vue
        """
        if self._mode == "density":
            return self._get_component_args_density()

        # Default styling
        default_styling = {
            "highlightColor": "#E4572E",
            "selectedColor": "#F3A712",
            "unhighlightedColor": "lightblue",
            "highlightHiddenColor": "#1f77b4",
            "annotationColors": {
                "massButton": "#E4572E",
                "selectedMassButton": "#F3A712",
                "sequenceArrow": "#E4572E",
                "selectedSequenceArrow": "#F3A712",
                "background": "#f0f0f0",
                "buttonHover": "#e0e0e0",
            },
        }

        # Merge user styling with defaults
        styling = {**default_styling, **self._styling}
        if "annotationColors" in self._styling:
            styling["annotationColors"] = {
                **default_styling["annotationColors"],
                **self._styling["annotationColors"],
            }

        if self._mode == "tagger":
            return self._get_component_args_tagger(styling)

        # Use dynamic title if set, otherwise static title
        title = self._dynamic_title if self._dynamic_title else (self._title or "")

        args: Dict[str, Any] = {
            "componentType": self._get_vue_component_name(),
            "mode": "default",
            "title": title,
            "xLabel": self._x_label,
            "yLabel": self._y_label,
            "styling": styling,
            "config": self._plot_config,
            # Pass interactivity for click handling (sets selection on peak click)
            "interactivity": self._interactivity,
            # Column mappings for Arrow data parsing in Vue
            "xColumn": self._x_column,
            "yColumn": self._y_column,
            "highlightColumn": self._highlight_column,
            "annotationColumn": self._annotation_column,
        }

        # Selective-highlight (FLASHApp parity): config-time flags so the Vue
        # modebar toggle buttons are constructed even before any mass is selected.
        # ``deconvPeaksToggle`` enables the "Show Deconvolved Peaks" button (the
        # annotated spectrum). The two toggle DEFAULTS (annotations ON, deconv-peaks
        # OFF) match the oracle. Only emitted when the new path is configured so
        # existing default plots are byte-identical.
        if self._highlight_selection:
            args["selectiveHighlightEnabled"] = True
            args["deconvPeaksToggle"] = bool(self._deconv_peaks_toggle)

        # Add any extra pass-through config options, excluding the structured
        # constructor params that are stored in self._config purely for
        # subprocess recreation (they are already surfaced via dedicated args /
        # `config`) and must not leak as top-level component args.
        for key, val in self._config.items():
            if key not in _MANAGED_CONFIG_KEYS and key not in args:
                args[key] = val

        return args

    def _get_component_args_density(self) -> Dict[str, Any]:
        """Component args for the density (target/decoy KDE) plot."""
        styling = {"targetColor": "green", "decoyColor": "red", **self._styling}
        args: Dict[str, Any] = {
            "componentType": "PlotlyDensityPlot",
            "mode": "density",
            "title": self._title or "",
            "xLabel": self._x_label if self._x_label != self._x_column else "QScore",
            "yLabel": self._y_label if self._y_label != self._y_column else "Density",
            "xColumn": self._x_column,
            "yColumn": self._y_column,
            "categoryColumn": self._category_column,
            "targetValue": self._target_value,
            "decoyValue": self._decoy_value,
            "scoreLabel": self._plot_config.get("scoreLabel", "QScore"),
            # Optional explicit trace legend names (oracle FDR uses "Target QScores"
            # / "Decoy QScores"); when unset the Vue falls back to
            # f"{scoreLabel} (Target)" / f"{scoreLabel} (Decoy)".
            "targetLabel": self._plot_config.get("targetLabel"),
            "decoyLabel": self._plot_config.get("decoyLabel"),
            "styling": styling,
            "config": self._plot_config,
        }
        return args

    def _get_component_args_tagger(self, styling: Dict[str, Any]) -> Dict[str, Any]:
        """Component args for the tagger overlay (reuses PlotlyLineplot dispatch)."""
        title_l0 = self._title or self._TAGGER_TITLE_L0
        title_l1 = self._title_level1 or self._TAGGER_TITLE_L1
        xlabel_l0 = (
            self._x_label if self._x_label != self._x_column else self._TAGGER_XLABEL_L0
        )
        xlabel_l1 = self._x_label_level1 or self._TAGGER_XLABEL_L1

        args: Dict[str, Any] = {
            "componentType": "PlotlyLineplot",
            "mode": "tagger",
            "title": title_l0,
            "titleLevel1": title_l1,
            "xLabel": xlabel_l0,
            "xLabelLevel1": xlabel_l1,
            "yLabel": self._y_label if self._y_label != self._y_column else "Intensity",
            "styling": styling,
            "interactivity": self._interactivity,
            "xColumn": self._x_column,
            "yColumn": self._y_column,
            "highlightColumn": "highlight",
            "selectedColumn": "selected_gold",
            "annotationColumn": "mass_label",
            "taggerMassButtons": True,
            "taggerSegmentsKey": "plotDataTaggerSegments",
            "taggerChargesKey": "plotDataTaggerCharges",
            "taggerLevel1Key": "plotDataTaggerLevel1",
            "xPosScalingFactor": self._x_pos_scaling_factor,
            "config": self._plot_config,
        }
        # Mirror the default path: structured constructor params (incl. the tagger
        # tag-resolution keys like tag_data_path, which can be an absolute fs path)
        # are stored in self._config for subprocess recreation and must NOT leak
        # into the Vue args as snake_case top-level keys.
        for key, val in self._config.items():
            if key not in _MANAGED_CONFIG_KEYS and key not in args:
                args[key] = val
        return args

    def with_styling(
        self,
        highlight_color: Optional[str] = None,
        selected_color: Optional[str] = None,
        unhighlighted_color: Optional[str] = None,
    ) -> "LinePlot":
        """
        Update plot styling.

        Args:
            highlight_color: Color for highlighted points
            selected_color: Color for selected points
            unhighlighted_color: Color for unhighlighted points

        Returns:
            Self for method chaining
        """
        if highlight_color:
            self._styling["highlightColor"] = highlight_color
        if selected_color:
            self._styling["selectedColor"] = selected_color
        if unhighlighted_color:
            self._styling["unhighlightedColor"] = unhighlighted_color
        return self

    def with_annotations(
        self,
        background_color: Optional[str] = None,
        button_color: Optional[str] = None,
        selected_button_color: Optional[str] = None,
    ) -> "LinePlot":
        """
        Configure annotation styling.

        Args:
            background_color: Background color for annotation boxes
            button_color: Color for annotation buttons
            selected_button_color: Color for selected annotation buttons

        Returns:
            Self for method chaining
        """
        if "annotationColors" not in self._styling:
            self._styling["annotationColors"] = {}

        if background_color:
            self._styling["annotationColors"]["background"] = background_color
        if button_color:
            self._styling["annotationColors"]["massButton"] = button_color
        if selected_button_color:
            self._styling["annotationColors"]["selectedMassButton"] = (
                selected_button_color
            )

        return self

    def set_dynamic_annotations(
        self,
        annotations: Optional[Dict[int, Dict[str, Any]]] = None,
        title: Optional[str] = None,
    ) -> "LinePlot":
        """
        Set dynamic annotations to be applied at render time.

        This allows updating peak annotations without recreating the component.
        Annotations are keyed by the interactivity column value (e.g., peak_id),
        which provides a stable identifier independent of row order.

        Args:
            annotations: Dict mapping peak IDs to annotation data.
                Keys should match values in the first interactivity column.
                Each entry should have:
                - 'highlight': bool - whether to highlight this peak
                - 'annotation': str - label text (e.g., "b3¹⁺")
                Example: {123: {'highlight': True, 'annotation': 'b2¹⁺'}}
            title: Optional dynamic title override

        Returns:
            Self for method chaining

        Example:
            # Compute annotations for current identification (keyed by peak_id)
            annotations = {
                123: {'highlight': True, 'annotation': 'b2¹⁺'},
                456: {'highlight': True, 'annotation': 'b3¹⁺'},
            }
            spectrum_plot.set_dynamic_annotations(annotations, title="PEPTIDER")
            spectrum_plot(key="plot", state_manager=sm)
        """
        self._dynamic_annotations = annotations
        self._dynamic_title = title
        return self

    def clear_dynamic_annotations(self) -> "LinePlot":
        """
        Clear any dynamic annotations.

        Returns:
            Self for method chaining
        """
        self._dynamic_annotations = None
        self._dynamic_title = None
        return self

    def set_peak_annotations(
        self, annotations: Optional[List[Dict[str, Any]]]
    ) -> "LinePlot":
        """
        Set generic per-peak annotation descriptors (render-time, not cached).

        This is a flat list of self-describing label descriptors in **data
        coordinates**, independent of the per-row ``annotation_column`` model.
        It supports drawing **multiple** labels at arbitrary x positions with
        per-label color — e.g. per-charge ``z={charge}`` labels placed at each
        charge group's intensity-weighted center-of-gravity m/z.

        Each descriptor is a dict:
        - ``x`` (float): data-x of the label.
        - ``text`` (str): label text (e.g. ``"z=12"``).
        - ``color`` (str, optional): badge fill (defaults to the highlight color).
        - ``hover`` (str, optional): hover text for an invisible point at the label.
        - ``group`` (str|int, optional): group id for overlap-suppression scoping.
        - ``y`` (float, optional): explicit label y (defaults to the computed band).

        The COG / charge-group math is performed in Python by the caller (see
        :func:`compute_charge_annotations`), keeping the heavy logic testable and
        the Vue side a dumb renderer. The existing ``annotation_column`` path is
        unaffected (still used for deconvolved-spectrum mass labels).

        Args:
            annotations: List of descriptor dicts, or None to clear.

        Returns:
            Self for method chaining.
        """
        self._peak_annotations = annotations
        return self

    def clear_peak_annotations(self) -> "LinePlot":
        """
        Clear any generic per-peak annotation descriptors.

        Returns:
            Self for method chaining
        """
        self._peak_annotations = None
        return self

    def _preserves_plot_config(self) -> bool:
        """
        Whether a cache hit should keep the cached _plotConfig verbatim.

        Tagger mode emits a fully state-derived _plotConfig (drill-down ``level``,
        selected/highlight column names) that the generic _build_plot_config
        rebuild cannot reproduce. Tagger is fully state-dependent, so a cache hit
        means the cached config is still correct — preserve it.

        The selective-highlight (FLASHApp parity) path also emits a state-derived
        _plotConfig (the ``_dynamic_highlight`` column wiring). Because the highlight
        selection is a state dependency, a cache HIT means the same selection, so the
        cached config — including the dynamic highlight column — is still correct.
        Preserving it stops the generic rebuild from reverting to the static
        ``highlight_column`` (which would drop the selective highlight on a hit).
        """
        return self._mode == "tagger" or bool(self._highlight_selection)

    def _build_plot_config(
        self,
        highlight_col: Optional[str],
        annotation_col: Optional[str],
    ) -> Dict[str, Any]:
        """
        Build _plotConfig dict for Vue component.

        Args:
            highlight_col: Column name for highlight values
            annotation_col: Column name for annotation text

        Returns:
            Config dict with column mappings for Vue
        """
        return {
            "xColumn": self._x_column,
            "yColumn": self._y_column,
            "highlightColumn": highlight_col,
            "annotationColumn": annotation_col,
            "interactivityColumns": {
                col: col
                for col in (self._interactivity.values() if self._interactivity else [])
            },
        }

    def _strip_dynamic_columns(self, vue_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Strip dynamic annotation columns from vue_data for caching.

        Returns a copy with dynamic columns removed so the cached version
        doesn't contain stale annotation data.

        Args:
            vue_data: The vue data dict to strip

        Returns:
            Copy of vue_data without dynamic columns and _plotConfig
        """
        import pandas as pd

        vue_data = dict(vue_data)
        df = vue_data.get("plotData")

        if df is not None and isinstance(df, pd.DataFrame):
            dynamic_cols = ["_dynamic_highlight", "_dynamic_annotation"]
            cols_to_drop = [c for c in dynamic_cols if c in df.columns]
            if cols_to_drop:
                vue_data["plotData"] = df.drop(columns=cols_to_drop)

        # Remove _plotConfig since it may reference dynamic columns
        vue_data.pop("_plotConfig", None)
        # Render-time peak annotations are re-applied by _apply_fresh_annotations.
        vue_data.pop("peakAnnotations", None)
        return vue_data

    def _apply_fresh_annotations(self, vue_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Apply current dynamic annotations to cached base vue_data.

        This is called by bridge.py when there's a cache hit for a component
        with dynamic annotations. Re-applies the current annotation state.

        Args:
            vue_data: Cached base vue_data (without annotation columns)

        Returns:
            vue_data with current annotations applied
        """
        import pandas as pd

        df_pandas = vue_data.get("plotData")
        if df_pandas is None:
            return vue_data

        # Ensure we have a DataFrame
        if not isinstance(df_pandas, pd.DataFrame):
            return vue_data

        # Determine highlight/annotation columns
        highlight_col = self._highlight_column
        annotation_col = self._annotation_column

        if self._dynamic_annotations and len(df_pandas) > 0:
            # Apply dynamic annotations
            df_pandas = df_pandas.copy()
            num_rows = len(df_pandas)
            highlights = [False] * num_rows
            annotations = [""] * num_rows

            # Get the interactivity column for lookup
            id_column = None
            if self._interactivity:
                id_column = list(self._interactivity.values())[0]

            # Apply annotations by peak_id lookup
            if id_column and id_column in df_pandas.columns:
                peak_ids = df_pandas[id_column].tolist()
                for row_idx, peak_id in enumerate(peak_ids):
                    if peak_id in self._dynamic_annotations:
                        ann_data = self._dynamic_annotations[peak_id]
                        highlights[row_idx] = ann_data.get("highlight", False)
                        annotations[row_idx] = ann_data.get("annotation", "")
            else:
                # Fallback: use row index as key
                for idx, ann_data in self._dynamic_annotations.items():
                    if isinstance(idx, int) and 0 <= idx < num_rows:
                        highlights[idx] = ann_data.get("highlight", False)
                        annotations[idx] = ann_data.get("annotation", "")

            df_pandas["_dynamic_highlight"] = highlights
            df_pandas["_dynamic_annotation"] = annotations
            highlight_col = "_dynamic_highlight"
            annotation_col = "_dynamic_annotation"

        # Build result
        vue_data = dict(vue_data)
        vue_data["plotData"] = df_pandas
        vue_data["_plotConfig"] = self._build_plot_config(highlight_col, annotation_col)
        # Re-attach generic per-peak annotations from the live instance.
        self._attach_peak_annotations(vue_data)
        return vue_data

    @classmethod
    def density(
        cls,
        cache_id: str,
        data: Optional[pl.LazyFrame] = None,
        data_path: Optional[str] = None,
        *,
        x_column: str = "x",
        y_column: str = "y",
        category_column: str = "group",
        target_value: str = "target",
        decoy_value: str = "decoy",
        kde_from: Optional[Dict[str, str]] = None,
        kde_points: int = 200,
        title: Optional[str] = None,
        x_label: Optional[str] = None,
        y_label: Optional[str] = None,
        styling: Optional[Dict[str, Any]] = None,
        config: Optional[Dict[str, Any]] = None,
        cache_path: str = ".",
        regenerate_cache: bool = False,
        **kwargs,
    ) -> "LinePlot":
        """
        Build a ``mode="density"`` LinePlot (two-series target/decoy KDE / FDR plot).

        Groups the mode-specific density parameters out of the generic ``LinePlot``
        signature. Behavior is identical to ``LinePlot(mode="density", ...)``.

        Args:
            cache_id: Unique cache identifier (MANDATORY).
            data: Tidy long ``{x, y, category}`` frame. Optional if cache exists.
            data_path: Path to parquet file (preferred for large datasets).
            x_column / y_column: Tidy frame x/y columns.
            category_column: Column holding the ``target``/``decoy`` label
                (the categorical grouping; matches Heatmap/Plot3D ``category_column``).
            target_value: Value in ``category_column`` mapping to the target series.
                Default ``"target"``.
            decoy_value: Value mapping to the decoy series. Default ``"decoy"``.
                The decoy series may be absent (target-only plot).
            kde_from: Optional ``{"score": <col>, "label": <col>}`` to build the
                KDE from raw scores at preprocess time (lazily imports scipy);
                omit to pass a precomputed frame.
            kde_points: Number of ``linspace`` points per series (default 200).
            title / x_label / y_label: Presentation labels.
            styling: Style dict (``targetColor`` / ``decoyColor`` overrides).
            config: Extra Plotly config (e.g. ``{"scoreLabel": ...}``).
            cache_path: Base path for cache storage. Default "." (current dir).
            regenerate_cache: If True, regenerate even if a valid cache exists.
            **kwargs: Additional pass-through config.

        Returns:
            A configured ``LinePlot`` in density mode.
        """
        return cls(
            cache_id=cache_id,
            data=data,
            data_path=data_path,
            cache_path=cache_path,
            regenerate_cache=regenerate_cache,
            mode="density",
            x_column=x_column,
            y_column=y_column,
            title=title,
            x_label=x_label,
            y_label=y_label,
            styling=styling,
            config=config,
            category_column=category_column,
            target_value=target_value,
            decoy_value=decoy_value,
            kde_from=kde_from,
            kde_points=kde_points,
            **kwargs,
        )

    @classmethod
    def tagger(
        cls,
        cache_id: str,
        data: Optional[pl.LazyFrame] = None,
        data_path: Optional[str] = None,
        *,
        filters: Optional[Dict[str, str]] = None,
        filter_defaults: Optional[Dict[str, Any]] = None,
        interactivity: Optional[Dict[str, str]] = None,
        x_column: str = "x",
        y_column: str = "y",
        signal_peaks_column: Optional[str] = None,
        mz_column: Optional[str] = None,
        mz_intensity_column: Optional[str] = None,
        tag_identifier: str = "tag",
        mass_match_tol: float = 1e-5,
        title: Optional[str] = None,
        title_level1: Optional[str] = None,
        x_label: Optional[str] = None,
        x_label_level1: Optional[str] = None,
        y_label: Optional[str] = None,
        x_pos_scaling_factor: float = 27.5,
        styling: Optional[Dict[str, Any]] = None,
        config: Optional[Dict[str, Any]] = None,
        cache_path: str = ".",
        regenerate_cache: bool = False,
        **kwargs,
    ) -> "LinePlot":
        """
        Build a ``mode="tagger"`` LinePlot (sequence-tag overlay + drill-down).

        Groups the mode-specific tagger parameters (including the FLASHApp-flavored
        ``signal_peaks_column`` layout and the oracle ``x_pos_scaling_factor``
        magic number) out of the generic ``LinePlot`` signature. Behavior is
        identical to ``LinePlot(mode="tagger", ...)``.

        Args:
            cache_id: Unique cache identifier (MANDATORY).
            data: Per-scan list-column frame. Optional if cache exists.
            data_path: Path to parquet file (preferred for large datasets).
            filters: Identifier->column filter mapping. The ``tag_identifier`` key
                (default ``"tag"``) carries the opaque ``TagData`` payload and is
                excluded from row filtering.
            filter_defaults: Default filter values (e.g. ``{"tagger_mass": None}``).
            interactivity: Drill-down mapping (e.g. ``{"tagger_mass": "peak_id"}``).
            x_column / y_column: List-columns of deconvolved masses / intensities.
            signal_peaks_column: Column of per-mass raw signal peaks,
                ``list[mass][peak] = [peak_index, mz, intensity, charge]``
                (FLASHApp layout).
            mz_column: Column with the annotated (m/z) spectrum masses.
            mz_intensity_column: Column with the annotated spectrum intensities.
            tag_identifier: Selection identifier carrying the opaque ``TagData``
                payload. Default ``"tag"``.
            mass_match_tol: Mass-match tolerance for highlighting tag fragment
                masses against the deconvolved masses. Default ``1e-5``.
            title / title_level1: Level-0 / level-1 drill-down titles.
            x_label / x_label_level1: Level-0 / level-1 x-axis labels.
            y_label: Y-axis label.
            x_pos_scaling_factor: Oracle level-1 charge-label scaling (27.5).
            styling: Style configuration dict.
            config: Extra Plotly config.
            cache_path: Base path for cache storage. Default "." (current dir).
            regenerate_cache: If True, regenerate even if a valid cache exists.
            **kwargs: Additional pass-through config.

        Returns:
            A configured ``LinePlot`` in tagger mode.
        """
        return cls(
            cache_id=cache_id,
            data=data,
            data_path=data_path,
            cache_path=cache_path,
            regenerate_cache=regenerate_cache,
            mode="tagger",
            filters=filters,
            filter_defaults=filter_defaults,
            interactivity=interactivity,
            x_column=x_column,
            y_column=y_column,
            title=title,
            x_label=x_label,
            y_label=y_label,
            styling=styling,
            config=config,
            signal_peaks_column=signal_peaks_column,
            mz_column=mz_column,
            mz_intensity_column=mz_intensity_column,
            tag_identifier=tag_identifier,
            mass_match_tol=mass_match_tol,
            title_level1=title_level1,
            x_label_level1=x_label_level1,
            x_pos_scaling_factor=x_pos_scaling_factor,
            **kwargs,
        )

    @classmethod
    def from_sequence_view(
        cls,
        sequence_view: "SequenceView",
        cache_id: str,
        cache_path: str = ".",
        title: Optional[str] = None,
        x_label: str = "m/z",
        y_label: str = "Intensity",
        styling: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> "LinePlot":
        """
        Create a LinePlot linked to a SequenceView for annotated spectrum display.

        The created LinePlot will:
        - Use the same peaks data as the SequenceView
        - Use the same filters (spectrum selection)
        - Use the same interactivity (peak selection)
        - Automatically apply annotations from SequenceView when rendered

        Args:
            sequence_view: The SequenceView to link to
            cache_id: Unique identifier for this component's cache
            cache_path: Base path for cache storage
            title: Plot title (optional)
            x_label: X-axis label (default: "m/z")
            y_label: Y-axis label (default: "Intensity")
            styling: Style configuration dict
            **kwargs: Additional LinePlot configuration

        Returns:
            A new LinePlot instance linked to the SequenceView

        Example:
            sequence_view = SequenceView(
                cache_id="seq",
                sequence_data=sequences_df,
                peaks_data=peaks_df,
                filters={"spectrum": "scan_id"},
                interactivity={"peak": "peak_id"},
            )

            # Create linked LinePlot
            spectrum_plot = LinePlot.from_sequence_view(
                sequence_view,
                cache_id="spectrum",
                title="Annotated Spectrum",
            )

            # Render both - annotations flow automatically
            sv_result = sequence_view(key="sv", state_manager=state_manager)
            spectrum_plot(key="plot", state_manager=state_manager, sequence_view_key="sv")
        """
        # Get peaks data from SequenceView (uses cached data)
        peaks_data = sequence_view.peaks_data

        if peaks_data is None:
            raise ValueError(
                "SequenceView has no peaks_data. Cannot create linked LinePlot."
            )

        # Only include filters whose columns exist in peaks_data
        # SequenceView may have filters for both sequence_data and peaks_data,
        # but LinePlot only uses peaks_data
        peaks_columns = peaks_data.collect_schema().names()
        valid_filters = (
            {
                identifier: column
                for identifier, column in sequence_view._filters.items()
                if column in peaks_columns
            }
            if sequence_view._filters
            else None
        )

        # Create the LinePlot with filtered filters and interactivity
        plot = cls(
            cache_id=cache_id,
            data=peaks_data,
            filters=valid_filters,
            interactivity=sequence_view._interactivity.copy()
            if sequence_view._interactivity
            else None,
            cache_path=cache_path,
            x_column="mass",
            y_column="intensity",
            title=title,
            x_label=x_label,
            y_label=y_label,
            styling=styling,
            **kwargs,
        )

        return plot

    def __call__(
        self,
        key: Optional[str] = None,
        state_manager: Optional["StateManager"] = None,
        height: Optional[int] = None,
        sequence_view_key: Optional[str] = None,
    ) -> Any:
        """
        Render the component in Streamlit.

        Args:
            key: Optional unique key for the Streamlit component
            state_manager: Optional StateManager for cross-component state.
                If not provided, uses a default shared StateManager.
            height: Optional height in pixels for the component
            sequence_view_key: Optional key of a SequenceView component to get
                annotations from. When provided, automatically applies fragment
                annotations from that SequenceView.

        Returns:
            The value returned by the Vue component (usually selection state)
        """
        from ..core.state import get_default_state_manager
        from ..rendering.bridge import get_component_annotations, render_component

        if state_manager is None:
            state_manager = get_default_state_manager()

        # Apply annotations from linked SequenceView if specified
        if sequence_view_key:
            annotations_df = get_component_annotations(sequence_view_key)
            if annotations_df is not None and annotations_df.height > 0:
                # Convert annotation DataFrame to dynamic annotations dict
                # keyed by peak_id for stable lookup
                dynamic_annotations = {}
                for row in annotations_df.iter_rows(named=True):
                    peak_id = row.get("peak_id")
                    if peak_id is not None:
                        dynamic_annotations[peak_id] = {
                            "highlight": True,
                            "annotation": row.get("annotation", ""),
                            "color": row.get("highlight_color", "#E4572E"),
                        }
                self.set_dynamic_annotations(dynamic_annotations)
            else:
                self.clear_dynamic_annotations()

        return render_component(
            component=self, state_manager=state_manager, key=key, height=height
        )


# ---------------------------------------------------------------------------
# Pure, testable numeric helpers (tagger + charge-annotation math).
#
# These mirror the oracle (PlotlyLineplotTagger.vue / PlotlyLineplotUnified.vue)
# byte-for-byte: 1e-5 mass tolerance, COG = Σ (I/ΣI)·mz, reversed-index
# `len-1-selectedAA`, gold rule `== i || == i-1` for masses / `== i` for arrows.
# ---------------------------------------------------------------------------


def _as_list(value: Any) -> List[Any]:
    """Coerce a (possibly numpy/None) cell value to a Python list."""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    # numpy arrays / polars-backed sequences
    try:
        return list(value)
    except TypeError:
        return [value]


def _as_float_list(value: Any) -> List[float]:
    """Coerce a cell value to a list of floats."""
    return [float(v) for v in _as_list(value)]


def _parse_tag_payload(tag: Any):
    """
    Extract ``(masses, sequence, selectedAA)`` from a TagData payload.

    The payload is the opaque dict the (oracle) tag table builds:
    ``{sequence, nTerminal, masses, selectedAA, startPos, endPos}``. Non-zero
    masses are kept (oracle ``filter(n => n !== 0)``).
    """
    if not isinstance(tag, dict):
        return [], "", None
    masses = [float(m) for m in _as_list(tag.get("masses")) if float(m) != 0.0]
    sequence = tag.get("sequence") or ""
    selected_aa = tag.get("selectedAA")
    return masses, sequence, selected_aa


def _highlight_mass_positions(
    mono_mass: List[float],
    tag_masses: List[float],
    tol: float,
) -> List[int]:
    """
    Match each tag fragment mass to a MonoMass index within ``tol`` (oracle
    ``highlightedMassPos``). All-or-nothing: if not every tag mass matches a
    deconvolved mass, return ``[]`` (no highlight).
    """
    positions: List[int] = []
    for target in tag_masses:
        for j, mass in enumerate(mono_mass):
            if abs(target - mass) <= tol:
                positions.append(j)
                break
    if len(positions) == len(tag_masses):
        return positions
    return []


def _reversed_selected_aa(sequence: str, selected_aa: Any) -> Optional[int]:
    """
    Reverse the within-tag residue index into the descending-mass space
    (oracle ``reversedSelectedAA = sequence.length - 1 - selectedAA``).
    """
    if not sequence or selected_aa is None:
        return None
    try:
        return (len(sequence) - 1) - int(selected_aa)
    except (TypeError, ValueError):
        return None


def compute_tagger_segments(
    mono_mass: List[float],
    highlighted_pos: List[int],
    sequence: str,
    reversed_selected_aa: Optional[int],
) -> List[Dict[str, Any]]:
    """
    Build the level-0 sequence-arrow segments (one per adjacent highlighted pair).

    Mirrors the oracle arrow loop (PlotlyLineplotTagger.vue 449–540):
    - ``residue = sequence[len-1-i]`` (reversed index),
    - ``delta = |x_start - x_end|``,
    - ``selected`` (gold) iff ``reversed_selected_aa == i``.

    Returns one fewer row than the number of highlighted masses.
    """
    segments: List[Dict[str, Any]] = []
    for i in range(len(highlighted_pos) - 1):
        x_start = mono_mass[highlighted_pos[i]]
        x_end = mono_mass[highlighted_pos[i + 1]]
        residue = ""
        if sequence:
            reverse_index = len(sequence) - 1 - i
            if 0 <= reverse_index < len(sequence):
                residue = sequence[reverse_index]
        segments.append(
            {
                "x_start": x_start,
                "x_end": x_end,
                "residue": residue,
                "delta": abs(x_start - x_end),
                "selected": reversed_selected_aa is not None
                and reversed_selected_aa == i,
            }
        )
    return segments


def compute_charge_cog(peaks_for_charge: List[tuple]) -> float:
    """
    Intensity-weighted center-of-gravity m/z for one charge group.

    ``COG = Σ (I_i / ΣI) · mz_i`` (oracle formula). ``peaks_for_charge`` is a
    list of ``(mz, intensity)`` tuples. A zero total intensity yields the simple
    mean (degenerate guard).
    """
    total = sum(intensity for _mz, intensity in peaks_for_charge)
    if total == 0:
        n = len(peaks_for_charge)
        return sum(mz for mz, _ in peaks_for_charge) / n if n else 0.0
    return sum((intensity / total) * mz for mz, intensity in peaks_for_charge)


def compute_tagger_charges(
    signal_peaks_for_mass: List[Any],
    selected_aa: Any = None,
    selected_mass_index: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    Explode one mass's raw signal peaks into level-1 charge-cluster rows.

    Each ``signal`` is ``[peak_index, mz, intensity, charge]`` (FLASHApp layout).
    Rows carry the per-charge intensity-weighted ``cog`` (precomputed),
    ``charge_label = f"z={charge}"`` and a ``selected`` (gold) flag matching the
    oracle level-1 rule (``selectedAA == selected_mass_index`` or
    ``selectedAA == selected_mass_index - 1``).
    """
    # Group (mz, intensity) by charge while preserving first-seen charge order.
    order: List[int] = []
    groups: Dict[int, List[tuple]] = {}
    rows_raw: List[tuple] = []  # (mz, intensity, charge)
    for signal in signal_peaks_for_mass:
        sig = _as_list(signal)
        if len(sig) < 4:
            continue
        mz = float(sig[1])
        intensity = float(sig[2])
        charge = int(round(float(sig[3])))
        rows_raw.append((mz, intensity, charge))
        if charge not in groups:
            groups[charge] = []
            order.append(charge)
        groups[charge].append((mz, intensity))

    cog_by_charge = {c: compute_charge_cog(groups[c]) for c in order}

    gold = False
    if selected_aa is not None and selected_mass_index is not None:
        try:
            saa = int(selected_aa)
            gold = (saa == selected_mass_index) or (saa == selected_mass_index - 1)
        except (TypeError, ValueError):
            gold = False

    rows: List[Dict[str, Any]] = []
    for peak_id, (mz, intensity, charge) in enumerate(rows_raw):
        rows.append(
            {
                "mz": mz,
                "intensity": intensity,
                "charge": charge,
                "peak_id": peak_id,
                "cog": cog_by_charge[charge],
                "charge_label": f"z={charge}",
                "selected": gold,
            }
        )
    return rows


def compute_tagger_level1_spectrum(
    anno_mz: List[float],
    anno_intensity: List[float],
    open_signal_peaks: List[Any],
    stick_gold: bool,
    tol: float,
) -> List[Dict[str, Any]]:
    """
    Build the level-1 (Augmented Annotated Spectrum) sticks: the FULL annotated
    spectrum with ONLY the open mass's m/z peaks highlighted.

    Mirrors the oracle (PlotlyLineplotTagger.vue): at level 1 the sticks come from
    the whole ``MonoMass_Anno``/``SumIntensity_Anno`` array (``xColumn``/``yColumn``
    lines 115-119, 157-164), and ``highlightedPos`` (lines 760-771) marks a peak as
    highlighted iff it is within ``tol`` of one of the open mass's signal-peak mzs.
    The rest of the spectrum stays unhighlighted (lightblue).

    Gold/orange split (oracle ``plotData`` 253-283): a highlighted peak is GOLD iff
    ``stick_gold`` (``reversedSelectedAA == selectedMass || == selectedMass-1``),
    else ORANGE. ``stick_gold`` is the same for all of the open mass's peaks because
    they all share ``posHighlight == selectedMass``.

    Returns one row per annotated peak: ``{x, y, highlight, selected_gold}``.
    """
    # Collect the open mass's m/z peak positions (highlight anchors).
    open_mzs: List[float] = []
    for signal in open_signal_peaks:
        sig = _as_list(signal)
        if len(sig) < 4:
            continue
        open_mzs.append(float(sig[1]))

    rows: List[Dict[str, Any]] = []
    n = min(len(anno_mz), len(anno_intensity))
    for i in range(n):
        mz = anno_mz[i]
        is_hl = any(abs(mz - omz) <= tol for omz in open_mzs)
        rows.append(
            {
                "x": mz,
                "y": anno_intensity[i],
                "highlight": is_hl,
                "selected_gold": bool(is_hl and stick_gold),
            }
        )
    return rows


def compute_charge_annotations(
    signal_peaks_for_mass: List[Any],
    color: str = "#E4572E",
    template: str = "z={}",
) -> List[Dict[str, Any]]:
    """
    Build generic ``PeakAnnotation`` descriptors for per-charge labels.

    Convenience producer for :meth:`LinePlot.set_peak_annotations`: groups one
    mass's raw signal peaks (``[peak_index, mz, intensity, charge]``) by charge,
    computes the intensity-weighted center-of-gravity m/z per group (oracle
    formula) and emits one ``{x, text, color, group}`` label per charge. No
    ``hover`` is set — the oracle m/z charge branch emits no hover point for
    charge labels (PlotlyLineplotUnified.vue 889-899).

    The label text is ``template.format(charge)`` (default ``"z={}"`` -> ``"z=2"``),
    matching the oracle ``"z=" + charge`` and the configurable
    ``highlight_annotation_template`` LinePlot param.

    This keeps the library generic (it consumes plain descriptors); callers in
    any MS viewer can reuse it for the plain Annotated-Spectrum charge overlay.
    """
    order: List[int] = []
    groups: Dict[int, List[tuple]] = {}
    for signal in signal_peaks_for_mass:
        sig = _as_list(signal)
        if len(sig) < 4:
            continue
        mz = float(sig[1])
        intensity = float(sig[2])
        charge = int(round(float(sig[3])))
        if charge not in groups:
            groups[charge] = []
            order.append(charge)
        groups[charge].append((mz, intensity))

    labels: List[Dict[str, Any]] = []
    for charge in order:
        cog = compute_charge_cog(groups[charge])
        # No hover: the oracle m/z charge branch (PlotlyLineplotUnified.vue
        # 889-899) emits NO invisible hover point for charge labels. Omitting
        # ``hover`` keeps the descriptor hover-free (descriptorHoverTrace then
        # contributes nothing for these labels).
        labels.append(
            {
                "x": cog,
                "text": template.format(charge),
                "color": color,
                "group": "charge",
            }
        )
    return labels


# Type hint import
if TYPE_CHECKING:
    from ..core.state import StateManager
