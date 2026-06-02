"""Line plot component using Plotly.js."""

from typing import TYPE_CHECKING, Any, Dict, Optional

import polars as pl

from ..core.base import BaseComponent
from ..core.registry import register_component
from ..preprocessing.filtering import filter_and_collect_cached

if TYPE_CHECKING:
    from .sequenceview import SequenceView


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
        overlay_data: Optional[pl.LazyFrame] = None,
        overlay_x_column: Optional[str] = None,
        overlay_y_column: Optional[str] = None,
        overlay_color: str = "#9467bd",
        overlay_name: str = "Overlay",
        tag_overlay: bool = False,
        signal_peaks_column: Optional[str] = None,
        **kwargs,
    ):
        """
        Initialize the LinePlot component.

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
            overlay_data: Optional second-series LazyFrame drawn over the primary
                spectrum as sticks in a distinct color (e.g. raw/annotated peaks
                over deconvolved sticks). Shares the same ``filters`` as the
                primary data, so it is filtered to the same scan selection.
            overlay_x_column: x column in ``overlay_data`` (defaults to x_column).
            overlay_y_column: y column in ``overlay_data`` (defaults to y_column).
            overlay_color: Color for the overlay series. Default "#9467bd".
            overlay_name: Legend/series name for the overlay. Default "Overlay".
            tag_overlay: Opt-in flag enabling the FLASHTnT "tagger overlay"
                geometry (matched tag-mass highlighting, inter-residue amino-acid
                arrows, and per-mass charge ``z=N`` buttons). Default False, in
                which case the plot renders exactly as without this feature. The
                overlay geometry is only drawn in Vue when both ``tag_overlay`` is
                True AND a ``tagData`` selection is present in the StateManager.
            signal_peaks_column: Optional list-column on the PRIMARY data. Each
                peak row's value is a list of ``[mz, intensity, charge]`` triplets
                (the deconvolved-mass SignalPeaks constituents), aligned 1:1 with
                the primary peaks. Used by the tagger overlay to build per-mass
                charge ``z=N`` buttons at each charge's intensity-weighted
                center-of-gravity m/z. Carried through preprocessing/projection
                and persisted in the cache config.
            **kwargs: Additional configuration options
        """
        self._x_column = x_column
        self._y_column = y_column
        self._title = title
        self._x_label = x_label or x_column
        self._y_label = y_label or y_column
        self._highlight_column = highlight_column
        self._annotation_column = annotation_column
        self._styling = styling or {}
        self._plot_config = config or {}
        # Optional overlay (second) series
        self._overlay_x_column = overlay_x_column or x_column
        self._overlay_y_column = overlay_y_column or y_column
        self._overlay_color = overlay_color
        self._overlay_name = overlay_name
        # Source overlay frame (cached separately at preprocess time)
        self._source_overlay_data = overlay_data
        self._has_overlay = overlay_data is not None
        # Tagger overlay (opt-in; default off → behavior unchanged)
        self._tag_overlay = tag_overlay
        self._signal_peaks_column = signal_peaks_column

        # Dynamic annotations set at render time (not cached)
        self._dynamic_annotations: Optional[Dict[str, Any]] = None
        self._dynamic_title: Optional[str] = None
        # Latest render state, captured in _prepare_vue_data so _get_component_args
        # can forward tag selection (tagData / AApos) to Vue. Not cached.
        self._render_state: Dict[str, Any] = {}

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
            overlay_x_column=overlay_x_column,
            overlay_y_column=overlay_y_column,
            overlay_color=overlay_color,
            overlay_name=overlay_name,
            tag_overlay=tag_overlay,
            signal_peaks_column=signal_peaks_column,
            **kwargs,
        )

    def _get_cache_config(self) -> Dict[str, Any]:
        """
        Get configuration that affects cache validity.

        Returns:
            Dict of config values that affect preprocessing
        """
        return {
            "x_column": self._x_column,
            "y_column": self._y_column,
            "highlight_column": self._highlight_column,
            "annotation_column": self._annotation_column,
            "title": self._title,
            "x_label": self._x_label,
            "y_label": self._y_label,
            "styling": self._styling,
            "plot_config": self._plot_config,
            "has_overlay": self._has_overlay,
            "overlay_x_column": self._overlay_x_column,
            "overlay_y_column": self._overlay_y_column,
            "overlay_color": self._overlay_color,
            "overlay_name": self._overlay_name,
            "tag_overlay": self._tag_overlay,
            "signal_peaks_column": self._signal_peaks_column,
        }

    def _restore_cache_config(self, config: Dict[str, Any]) -> None:
        """Restore component-specific configuration from cached config."""
        self._x_column = config.get("x_column", "x")
        self._y_column = config.get("y_column", "y")
        self._highlight_column = config.get("highlight_column")
        self._annotation_column = config.get("annotation_column")
        self._title = config.get("title")
        self._x_label = config.get("x_label", self._x_column)
        self._y_label = config.get("y_label", self._y_column)
        self._styling = config.get("styling", {})
        self._plot_config = config.get("plot_config", {})
        # Overlay (second) series config
        self._has_overlay = config.get("has_overlay", False)
        self._overlay_x_column = config.get("overlay_x_column", self._x_column)
        self._overlay_y_column = config.get("overlay_y_column", self._y_column)
        self._overlay_color = config.get("overlay_color", "#9467bd")
        self._overlay_name = config.get("overlay_name", "Overlay")
        self._source_overlay_data = None
        # Tagger overlay config
        self._tag_overlay = config.get("tag_overlay", False)
        self._signal_peaks_column = config.get("signal_peaks_column")
        # Initialize dynamic annotations (not cached)
        self._dynamic_annotations = None
        self._dynamic_title = None
        self._render_state = {}

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
        super()._validate_mappings()

        schema = self._raw_data.collect_schema()
        column_names = schema.names()

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

        if self._signal_peaks_column and self._signal_peaks_column not in column_names:
            raise ValueError(
                f"signal_peaks_column '{self._signal_peaks_column}' not found in "
                f"data. Available columns: {column_names}"
            )

    def _preprocess(self) -> None:
        """
        Preprocess plot data.

        Sorts by filter columns for efficient predicate pushdown, then
        collects the LazyFrame for caching by base class.
        """
        data = self._raw_data

        # Sort by filter columns for efficient predicate pushdown.
        # This clusters identical filter values together, enabling Polars
        # to skip row groups that don't contain the target value when
        # filtering by selection state.
        if self._filters:
            sort_columns = list(self._filters.values())
            data = data.sort(sort_columns)

        # Store configuration in preprocessed data for serialization
        self._preprocessed_data["plot_config"] = {
            "x_column": self._x_column,
            "y_column": self._y_column,
            "highlight_column": self._highlight_column,
            "annotation_column": self._annotation_column,
        }

        # Store LazyFrame for streaming to disk (filter happens at render time)
        # Base class will use sink_parquet() to stream without full materialization
        self._preprocessed_data["data"] = data  # Keep lazy

        # Optional overlay (second) series: sort by filter columns too so the
        # same predicate pushdown applies, and let the base class cache it as
        # overlay_data.parquet (auto-reloaded as a LazyFrame on read).
        if self._source_overlay_data is not None:
            overlay = self._source_overlay_data
            if self._filters:
                overlay_sort = [
                    c
                    for c in self._filters.values()
                    if c in overlay.collect_schema().names()
                ]
                if overlay_sort:
                    overlay = overlay.sort(overlay_sort)
            self._preprocessed_data["overlay_data"] = overlay

    def get_state_dependencies(self) -> list:
        """
        State keys that affect this plot's rendered output.

        Includes the filter identifiers (default) plus, when the tagger overlay
        is enabled, the tag-selection keys (``tagData`` and ``AApos``) so the
        bridge re-renders the component whenever the selected tag / amino-acid
        position changes. When ``tag_overlay`` is off this matches the base
        behavior exactly (filters only).
        """
        deps = list(self._filters.keys())
        if self._tag_overlay:
            for key in ("tagData", "AApos"):
                if key not in deps:
                    deps.append(key)
        return deps

    def _get_vue_component_name(self) -> str:
        """Return the Vue component name."""
        return "PlotlyLineplotUnified"

    def _get_data_key(self) -> str:
        """Return the key used to send primary data to Vue."""
        return "plotData"

    def _prepare_vue_data(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Prepare plot data for Vue component.

        LinePlots filter based on filters mapping if provided.

        Sends data as a pandas DataFrame for efficient Arrow serialization.
        Vue parses the Arrow table and extracts column arrays for rendering.

        Args:
            state: Current selection state from StateManager

        Returns:
            Dict with plotData (pandas DataFrame) and _hash for change detection
        """
        # Capture the latest render state so _get_component_args can forward the
        # tag selection (tagData / AApos) to Vue alongside the static config.
        self._render_state = dict(state) if state else {}

        # Build list of columns to select (projection pushdown for efficiency)
        columns_to_select = [self._x_column, self._y_column]
        if self._highlight_column:
            columns_to_select.append(self._highlight_column)
        if self._annotation_column:
            columns_to_select.append(self._annotation_column)
        # Carry the SignalPeaks list-column (tagger overlay) through projection so
        # it arrives 1:1-aligned inside plotData. Vue reads it as a list-per-row.
        if self._signal_peaks_column and self._signal_peaks_column not in (
            columns_to_select
        ):
            columns_to_select.append(self._signal_peaks_column)
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

        # Apply dynamic annotations if set
        # Annotations are keyed by peak_id (stable identifier from interactivity column)
        if self._dynamic_annotations and len(df_pandas) > 0:
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
                    if peak_id in self._dynamic_annotations:
                        ann_data = self._dynamic_annotations[peak_id]
                        highlights[row_idx] = ann_data.get("highlight", False)
                        annotations[row_idx] = ann_data.get("annotation", "")
            else:
                # Fallback: use row index as key (legacy behavior)
                for idx, ann_data in self._dynamic_annotations.items():
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
            import hashlib

            ann_hash = hashlib.md5(
                str(sorted(self._dynamic_annotations.keys())).encode()
            ).hexdigest()[:8]
            data_hash = f"{data_hash}_{ann_hash}"

        # Optional overlay (second) series, filtered to the same selection.
        result: Dict[str, Any] = {
            "plotData": df_pandas,
            "_hash": data_hash,
            "_plotConfig": self._build_plot_config(highlight_col, annotation_col),
        }

        overlay = self._preprocessed_data.get("overlay_data")
        if overlay is not None:
            if isinstance(overlay, pl.DataFrame):
                overlay = overlay.lazy()
            overlay_cols = [self._overlay_x_column, self._overlay_y_column]
            if self._filters:
                for col in self._filters.values():
                    if col not in overlay_cols:
                        overlay_cols.append(col)
            overlay_pandas, overlay_hash = filter_and_collect_cached(
                overlay,
                self._filters,
                state,
                columns=overlay_cols,
                filter_defaults=self._filter_defaults,
            )
            result["plotDataOverlay"] = overlay_pandas
            result["_hash"] = f"{data_hash}_{overlay_hash}"

        # Send as DataFrame for Arrow serialization (efficient binary transfer)
        # Vue will parse and extract columns using the config
        return result

    def _get_component_args(self) -> Dict[str, Any]:
        """
        Get component arguments to send to Vue.

        Returns:
            Dict with all plot configuration for Vue
        """
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

        # Use dynamic title if set, otherwise static title
        title = self._dynamic_title if self._dynamic_title else (self._title or "")

        args: Dict[str, Any] = {
            "componentType": self._get_vue_component_name(),
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

        # Overlay (second) series presentation for Vue
        if self._has_overlay:
            args["hasOverlay"] = True
            args["overlayXColumn"] = self._overlay_x_column
            args["overlayYColumn"] = self._overlay_y_column
            args["overlayColor"] = self._overlay_color
            args["overlayName"] = self._overlay_name

        # Tagger overlay (opt-in). Always advertise the flag + the SignalPeaks
        # column name so Vue can gate the new geometry; forward the current tag
        # selection (read from StateManager state, not a data column) so Vue can
        # render matched-mass highlights / arrows / z=N buttons. Vue also reads
        # these straight from the selection store, so they stay live between the
        # render that captures them here and the next.
        if self._tag_overlay:
            args["tagOverlay"] = True
            if self._signal_peaks_column:
                args["signalPeaksColumn"] = self._signal_peaks_column
            tag_data = self._render_state.get("tagData")
            if tag_data is not None:
                args["tagData"] = tag_data
            aa_pos = self._render_state.get("AApos")
            if aa_pos is not None:
                args["aaPos"] = aa_pos

        # Add any extra config options
        args.update(self._config)

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
            "signalPeaksColumn": self._signal_peaks_column,
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
        return vue_data

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

        # Store reference to sequence view key for annotation lookup
        plot._linked_sequence_view_key: Optional[str] = None

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


# Type hint import
if TYPE_CHECKING:
    from ..core.state import StateManager
