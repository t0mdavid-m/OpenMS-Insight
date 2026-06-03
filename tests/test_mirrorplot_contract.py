"""Contract tests for MirrorPlot."""

import pandas as pd

from openms_insight import MirrorPlot


class TestMirrorPlotContract:
    def test_cache_config_roundtrip(
        self, mock_streamlit, temp_cache_dir, sample_lineplot_data
    ):
        """_get_cache_config / _restore_cache_config preserves every field."""
        original = MirrorPlot(
            cache_id="test_roundtrip",
            data=sample_lineplot_data,
            cache_path=str(temp_cache_dir),
            filters_top={"spectrum_top": "scan_id"},
            filter_defaults_top={"spectrum_top": 1},
            filters_bottom={"spectrum_bottom": "scan_id"},
            filter_defaults_bottom={"spectrum_bottom": 2},
            interactivity={"selected_peak": "peak_id"},
            x_column="mass",
            y_column="intensity",
            highlight_column="annotation",
            annotation_column="annotation",
            title="Compare",
            title_top="PSM A",
            title_bottom="PSM B",
            x_label="m/z",
            y_label="Intensity",
            styling={"unhighlightedColor": "#1f77b4"},
            config={"displayModeBar": True},
        )
        # The full (union) config persisted to the manifest holds both the
        # hash-affecting (data-shaping) config and the presentation config.
        config = original._get_stored_config()

        # Every constructor field that affects rendering must round-trip
        assert config["filters_top"] == {"spectrum_top": "scan_id"}
        assert config["filters_bottom"] == {"spectrum_bottom": "scan_id"}
        assert config["filter_defaults_top"] == {"spectrum_top": 1}
        assert config["filter_defaults_bottom"] == {"spectrum_bottom": 2}
        assert config["x_column"] == "mass"
        assert config["y_column"] == "intensity"
        assert config["highlight_column"] == "annotation"
        assert config["annotation_column"] == "annotation"
        assert config["title"] == "Compare"
        assert config["title_top"] == "PSM A"
        assert config["title_bottom"] == "PSM B"
        assert config["x_label"] == "m/z"
        assert config["y_label"] == "Intensity"
        assert config["styling"] == {"unhighlightedColor": "#1f77b4"}
        assert config["plot_config"] == {"displayModeBar": True}

        # Titles/labels are presentation params: render-time, NOT hash-affecting
        cache_config = original._get_cache_config()
        for key in ("title", "title_top", "title_bottom", "x_label", "y_label"):
            assert key not in cache_config, f"{key} must not be hash-affecting"

        # Restore on a fresh instance (both hooks, as _load_from_cache does)
        restored = MirrorPlot(
            cache_id="test_roundtrip_target",
            data=sample_lineplot_data,
            cache_path=str(temp_cache_dir),
            filters_top={"spectrum_top": "scan_id"},
            filters_bottom={"spectrum_bottom": "scan_id"},
            x_column="mass",
            y_column="intensity",
        )
        restored._restore_cache_config(config)
        restored._restore_render_config(config)

        assert restored._filters_top == {"spectrum_top": "scan_id"}
        assert restored._filters_bottom == {"spectrum_bottom": "scan_id"}
        assert restored._filter_defaults_top == {"spectrum_top": 1}
        assert restored._filter_defaults_bottom == {"spectrum_bottom": 2}
        assert restored._title_top == "PSM A"
        assert restored._title_bottom == "PSM B"
        assert restored._top_dynamic_annotations is None
        assert restored._bottom_dynamic_annotations is None
        assert restored._top_dynamic_title is None
        assert restored._bottom_dynamic_title is None
        assert restored._x_column == "mass"
        assert restored._y_column == "intensity"
        assert restored._highlight_column == "annotation"
        assert restored._annotation_column == "annotation"
        assert restored._title == "Compare"
        assert restored._x_label == "m/z"
        assert restored._y_label == "Intensity"
        assert restored._styling == {"unhighlightedColor": "#1f77b4"}
        assert restored._plot_config == {"displayModeBar": True}


class TestMirrorPlotPrepareVueData:
    def _make(self, temp_cache_dir, data, **overrides):
        defaults = {
            "cache_id": "test_prepare",
            "data": data,
            "cache_path": str(temp_cache_dir),
            "filters_top": {"spectrum_top": "scan_id"},
            "filters_bottom": {"spectrum_bottom": "scan_id"},
            "interactivity": {"selected_peak": "peak_id"},
            "x_column": "mass",
            "y_column": "intensity",
        }
        defaults.update(overrides)
        return MirrorPlot(**defaults)

    def test_returns_dict_with_hash(
        self, mock_streamlit, temp_cache_dir, sample_lineplot_data
    ):
        comp = self._make(temp_cache_dir, sample_lineplot_data)
        result = comp._prepare_vue_data({"spectrum_top": 1, "spectrum_bottom": 2})
        assert isinstance(result, dict)
        assert "_hash" in result
        assert isinstance(result["_hash"], str)

    def test_returns_both_dataframes(
        self, mock_streamlit, temp_cache_dir, sample_lineplot_data
    ):
        comp = self._make(temp_cache_dir, sample_lineplot_data)
        result = comp._prepare_vue_data({"spectrum_top": 1, "spectrum_bottom": 2})
        assert "plotDataTop" in result
        assert "plotDataBottom" in result
        assert isinstance(result["plotDataTop"], pd.DataFrame)
        assert isinstance(result["plotDataBottom"], pd.DataFrame)

    def test_filters_independently(
        self, mock_streamlit, temp_cache_dir, sample_lineplot_data
    ):
        """Top selection (scan 1) and bottom selection (scan 2) produce disjoint rows."""
        comp = self._make(temp_cache_dir, sample_lineplot_data)
        result = comp._prepare_vue_data({"spectrum_top": 1, "spectrum_bottom": 2})
        df_top = result["plotDataTop"]
        df_bot = result["plotDataBottom"]
        # sample_lineplot_data has scan_id [1,1,1,2,2]: scan 1 has 3 rows, scan 2 has 2
        assert len(df_top) == 3
        assert len(df_bot) == 2
        assert set(df_top["scan_id"]) == {1}
        assert set(df_bot["scan_id"]) == {2}

    def test_keeps_y_positive_on_bottom(
        self, mock_streamlit, temp_cache_dir, sample_lineplot_data
    ):
        """Vue does the y-flip; Python emits positive intensities for both halves."""
        comp = self._make(temp_cache_dir, sample_lineplot_data)
        result = comp._prepare_vue_data({"spectrum_top": 1, "spectrum_bottom": 2})
        assert (result["plotDataTop"]["intensity"] >= 0).all()
        assert (result["plotDataBottom"]["intensity"] >= 0).all()

    def test_get_data_key_returns_plotDataTop(
        self, mock_streamlit, temp_cache_dir, sample_lineplot_data
    ):
        comp = self._make(temp_cache_dir, sample_lineplot_data)
        assert comp._get_data_key() == "plotDataTop"

    def test_state_dependencies_includes_both_sides(
        self, mock_streamlit, temp_cache_dir, sample_lineplot_data
    ):
        comp = self._make(temp_cache_dir, sample_lineplot_data)
        deps = comp.get_state_dependencies()
        assert "spectrum_top" in deps
        assert "spectrum_bottom" in deps

    def test_state_dependencies_excludes_interactivity(
        self, mock_streamlit, temp_cache_dir, sample_lineplot_data
    ):
        comp = self._make(temp_cache_dir, sample_lineplot_data)
        assert "selected_peak" not in comp.get_state_dependencies()

    def test_build_plot_config_accepts_two_args(
        self, mock_streamlit, temp_cache_dir, sample_lineplot_data
    ):
        """Bridge calls _build_plot_config with 2 args; both halves get the same columns."""
        comp = self._make(temp_cache_dir, sample_lineplot_data)
        result = comp._build_plot_config("highlight_col_name", "annotation_col_name")
        assert result["topHighlightColumn"] == "highlight_col_name"
        assert result["bottomHighlightColumn"] == "highlight_col_name"
        assert result["topAnnotationColumn"] == "annotation_col_name"
        assert result["bottomAnnotationColumn"] == "annotation_col_name"


class TestMirrorPlotComponentArgs:
    def _make(self, temp_cache_dir, data, **overrides):
        defaults = {
            "cache_id": "test_args",
            "data": data,
            "cache_path": str(temp_cache_dir),
            "filters_top": {"spectrum_top": "scan_id"},
            "filters_bottom": {"spectrum_bottom": "scan_id"},
            "interactivity": {"selected_peak": "peak_id"},
            "x_column": "mass",
            "y_column": "intensity",
        }
        defaults.update(overrides)
        return MirrorPlot(**defaults)

    def test_includes_componentType(
        self, mock_streamlit, temp_cache_dir, sample_lineplot_data
    ):
        comp = self._make(temp_cache_dir, sample_lineplot_data)
        args = comp._get_component_args()
        assert args["componentType"] == "PlotlyMirrorPlot"

    def test_carries_per_side_titles_and_columns(
        self, mock_streamlit, temp_cache_dir, sample_lineplot_data
    ):
        comp = self._make(
            temp_cache_dir,
            sample_lineplot_data,
            title="Compare",
            title_top="A",
            title_bottom="B",
            x_label="m/z",
            y_label="Intensity",
        )
        args = comp._get_component_args()
        assert args["title"] == "Compare"
        assert args["titleTop"] == "A"
        assert args["titleBottom"] == "B"
        assert args["xLabel"] == "m/z"
        assert args["yLabel"] == "Intensity"
        assert args["xColumn"] == "mass"
        assert args["yColumn"] == "intensity"
        assert args["interactivity"] == {"selected_peak": "peak_id"}

    def test_styling_merged_with_defaults(
        self, mock_streamlit, temp_cache_dir, sample_lineplot_data
    ):
        comp = self._make(
            temp_cache_dir,
            sample_lineplot_data,
            styling={"unhighlightedColor": "#1f77b4"},
        )
        args = comp._get_component_args()
        # Override applied
        assert args["styling"]["unhighlightedColor"] == "#1f77b4"
        # Defaults preserved for unspecified keys
        assert "highlightColor" in args["styling"]
        assert "selectedColor" in args["styling"]


class TestMirrorPlotDynamicAnnotations:
    def _make(self, temp_cache_dir, data, **overrides):
        defaults = {
            "cache_id": "test_dyn",
            "data": data,
            "cache_path": str(temp_cache_dir),
            "filters_top": {"spectrum_top": "scan_id"},
            "filters_bottom": {"spectrum_bottom": "scan_id"},
            "interactivity": {"selected_peak": "peak_id"},
            "x_column": "mass",
            "y_column": "intensity",
        }
        defaults.update(overrides)
        return MirrorPlot(**defaults)

    def test_set_top_only_affects_top(
        self, mock_streamlit, temp_cache_dir, sample_lineplot_data
    ):
        comp = self._make(temp_cache_dir, sample_lineplot_data)
        comp.set_top_dynamic_annotations(
            {10: {"highlight": True, "annotation": "b1"}},
            title="Top!",
        )
        assert comp._top_dynamic_annotations == {
            10: {"highlight": True, "annotation": "b1"}
        }
        assert comp._top_dynamic_title == "Top!"
        assert comp._bottom_dynamic_annotations is None
        assert comp._bottom_dynamic_title is None

    def test_set_bottom_only_affects_bottom(
        self, mock_streamlit, temp_cache_dir, sample_lineplot_data
    ):
        comp = self._make(temp_cache_dir, sample_lineplot_data)
        comp.set_bottom_dynamic_annotations(
            {40: {"highlight": True, "annotation": "y3"}}, title="Bot"
        )
        assert comp._bottom_dynamic_annotations == {
            40: {"highlight": True, "annotation": "y3"}
        }
        assert comp._bottom_dynamic_title == "Bot"
        assert comp._top_dynamic_annotations is None

    def test_clear_top_only(self, mock_streamlit, temp_cache_dir, sample_lineplot_data):
        comp = self._make(temp_cache_dir, sample_lineplot_data)
        comp.set_top_dynamic_annotations({10: {"highlight": True, "annotation": "b1"}})
        comp.set_bottom_dynamic_annotations(
            {40: {"highlight": True, "annotation": "y3"}}
        )
        comp.clear_dynamic_annotations(side="top")
        assert comp._top_dynamic_annotations is None
        assert comp._top_dynamic_title is None
        # Bottom untouched
        assert comp._bottom_dynamic_annotations == {
            40: {"highlight": True, "annotation": "y3"}
        }

    def test_clear_bottom_only(
        self, mock_streamlit, temp_cache_dir, sample_lineplot_data
    ):
        comp = self._make(temp_cache_dir, sample_lineplot_data)
        comp.set_top_dynamic_annotations({10: {"highlight": True, "annotation": "b1"}})
        comp.set_bottom_dynamic_annotations(
            {40: {"highlight": True, "annotation": "y3"}}
        )
        comp.clear_dynamic_annotations(side="bottom")
        assert comp._bottom_dynamic_annotations is None
        assert comp._bottom_dynamic_title is None
        # Top untouched
        assert comp._top_dynamic_annotations == {
            10: {"highlight": True, "annotation": "b1"}
        }

    def test_clear_both(self, mock_streamlit, temp_cache_dir, sample_lineplot_data):
        comp = self._make(temp_cache_dir, sample_lineplot_data)
        comp.set_top_dynamic_annotations({10: {"highlight": True, "annotation": "b1"}})
        comp.set_bottom_dynamic_annotations(
            {40: {"highlight": True, "annotation": "y3"}}
        )
        comp.clear_dynamic_annotations()  # side=None default
        assert comp._top_dynamic_annotations is None
        assert comp._bottom_dynamic_annotations is None
        assert comp._top_dynamic_title is None
        assert comp._bottom_dynamic_title is None

    def test_setters_return_self_for_chaining(
        self, mock_streamlit, temp_cache_dir, sample_lineplot_data
    ):
        comp = self._make(temp_cache_dir, sample_lineplot_data)
        assert comp.set_top_dynamic_annotations({}) is comp
        assert comp.set_bottom_dynamic_annotations({}) is comp
        assert comp.clear_dynamic_annotations() is comp


class TestMirrorPlotBridgeIntegration:
    def _make(self, temp_cache_dir, data, **overrides):
        defaults = {
            "cache_id": "test_bridge",
            "data": data,
            "cache_path": str(temp_cache_dir),
            "filters_top": {"spectrum_top": "scan_id"},
            "filters_bottom": {"spectrum_bottom": "scan_id"},
            "interactivity": {"selected_peak": "peak_id"},
            "x_column": "mass",
            "y_column": "intensity",
        }
        defaults.update(overrides)
        return MirrorPlot(**defaults)

    def test_strip_drops_dynamic_columns_from_both(
        self, mock_streamlit, temp_cache_dir, sample_lineplot_data
    ):
        comp = self._make(temp_cache_dir, sample_lineplot_data)
        # Build vue_data containing dynamic cols on both sides
        comp.set_top_dynamic_annotations({10: {"highlight": True, "annotation": "b1"}})
        comp.set_bottom_dynamic_annotations(
            {40: {"highlight": True, "annotation": "y3"}}
        )
        vue_data = comp._prepare_vue_data({"spectrum_top": 1, "spectrum_bottom": 2})
        assert "_dynamic_highlight" in vue_data["plotDataTop"].columns
        assert "_dynamic_highlight" in vue_data["plotDataBottom"].columns

        stripped = comp._strip_dynamic_columns(vue_data)
        assert "_dynamic_highlight" not in stripped["plotDataTop"].columns
        assert "_dynamic_annotation" not in stripped["plotDataTop"].columns
        assert "_dynamic_highlight" not in stripped["plotDataBottom"].columns
        assert "_dynamic_annotation" not in stripped["plotDataBottom"].columns
        # _plotConfig also removed (may reference dynamic column names)
        assert "_plotConfig" not in stripped

    def test_apply_fresh_annotations_top_only(
        self, mock_streamlit, temp_cache_dir, sample_lineplot_data
    ):
        comp = self._make(temp_cache_dir, sample_lineplot_data)
        # Build cached vue_data with no annotations
        cached = comp._prepare_vue_data({"spectrum_top": 1, "spectrum_bottom": 2})
        cached_clean = comp._strip_dynamic_columns(cached)

        # Set top annotations only
        comp.set_top_dynamic_annotations({10: {"highlight": True, "annotation": "b1"}})
        refreshed = comp._apply_fresh_annotations(cached_clean)

        assert "_dynamic_highlight" in refreshed["plotDataTop"].columns
        # Bottom must NOT have dynamic columns since no bottom annotations set
        assert "_dynamic_highlight" not in refreshed["plotDataBottom"].columns
        # _plotConfig rebuilt
        assert "_plotConfig" in refreshed

    def test_per_side_annotations_apply_on_cache_hit(
        self, mock_streamlit, temp_cache_dir, sample_lineplot_data
    ):
        """BUG FIX: per-side annotations must render through the bridge cache HIT.

        The bridge gated _apply_fresh_annotations on _has_render_time_annotations,
        which only detected the singular _dynamic_annotations / _peak_annotations.
        MirrorPlot stores per-side state in _top_dynamic_annotations /
        _bottom_dynamic_annotations and never sets the singular attr, so on a cache
        HIT the gate returned False and SequenceView-pushed annotations silently
        didn't render. The 46 cache-MISS tests masked this because they hit
        _prepare_vue_data / _apply_fresh_annotations directly.

        Here we go through the real bridge path: warm the cache (MISS, no
        annotations), then set a top annotation and assert the next cached call is
        a HIT that still carries the annotation (_dynamic_highlight column +
        annotation label).
        """
        from openms_insight.rendering import bridge

        # mock_streamlit patches streamlit.session_state, which bridge reads as
        # st.session_state for its per-component runtime cache.
        comp = self._make(temp_cache_dir, sample_lineplot_data)
        component_id = "PlotlyMirrorPlot:test_cache_hit"
        # peak_id 10 belongs to scan_id 1 -> lands on the top side (spectrum_top=1)
        state = {"spectrum_top": 1, "spectrum_bottom": 2}
        filter_state_hashable = (("spectrum_bottom", 2), ("spectrum_top", 1))

        # Warm cache: cache MISS, no annotations -> stores stripped base data
        warm_data, _ = bridge._prepare_vue_data_cached(
            comp, component_id, filter_state_hashable, state
        )
        assert "_dynamic_highlight" not in warm_data["plotDataTop"].columns

        # Now an annotation arrives (e.g. from a linked SequenceView)
        comp.set_top_dynamic_annotations({10: {"highlight": True, "annotation": "b1"}})

        # Next call is a cache HIT (same filter state). With the fix, the gate
        # now detects the per-side annotation and re-applies it to cached data.
        hit_data, _ = bridge._prepare_vue_data_cached(
            comp, component_id, filter_state_hashable, state
        )

        df_top = hit_data["plotDataTop"]
        assert "_dynamic_highlight" in df_top.columns, (
            "per-side annotation did not render on cache HIT"
        )
        assert "_dynamic_annotation" in df_top.columns
        assert df_top["_dynamic_annotation"].tolist().count("b1") == 1
        assert bool(df_top["_dynamic_highlight"].any())
        # _plotConfig must point the top side at the dynamic columns
        assert hit_data["_plotConfig"]["topHighlightColumn"] == "_dynamic_highlight"
        assert hit_data["_plotConfig"]["topAnnotationColumn"] == "_dynamic_annotation"

    def test_per_side_annotation_change_alters_cache_hit_hash(
        self, mock_streamlit, temp_cache_dir, sample_lineplot_data
    ):
        """A changed per-side annotation must change the bridge annotation hash.

        _compute_annotation_hash feeds the cache-validity check in render_component;
        if it ignored per-side annotations, a changed annotation would not force a
        re-render on a HIT. The hash must differ between no-annotation, an
        annotated top side, and a different top annotation.
        """
        from openms_insight.rendering import bridge

        comp = self._make(temp_cache_dir, sample_lineplot_data)

        none_hash = bridge._compute_annotation_hash(comp)
        assert none_hash is None

        comp.set_top_dynamic_annotations({10: {"highlight": True, "annotation": "b1"}})
        top_hash = bridge._compute_annotation_hash(comp)
        assert top_hash is not None
        assert top_hash != none_hash

        comp.set_top_dynamic_annotations(
            {10: {"highlight": True, "annotation": "b1"}, 20: {"highlight": True}}
        )
        changed_hash = bridge._compute_annotation_hash(comp)
        assert changed_hash != top_hash
