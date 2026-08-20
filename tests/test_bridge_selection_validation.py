"""Tests for `_validate_interactivity_selections`.

This function clears an interactivity selection that no longer exists in the newly
filtered data, which is what lets a table's auto-selection take over after a filter
changes. It had no coverage at all, and shipped a defect that made every MirrorPlot
click impossible to keep: the component flattens its two per-side filters into one
union dict for the base class, and the validator applied every entry conjunctively, so
a two-sided plot validated against ``scan_id == top AND scan_id == bottom`` -- always
empty, so every selection was judged missing and cleared.
"""

from __future__ import annotations

from typing import Any

import polars as pl
import pytest

from openms_insight.core.state import StateManager
from openms_insight.rendering.bridge import _validate_interactivity_selections


class FakeComponent:
    """Minimal stand-in exposing only what the validator reads."""

    def __init__(
        self,
        data: pl.DataFrame,
        interactivity: dict[str, str],
        filters: dict[str, str] | None = None,
        filter_defaults: dict[str, Any] | None = None,
        groups: list[tuple[dict[str, str], dict[str, Any]]] | None = None,
    ):
        self._cache_id = "fake"
        self._interactivity = interactivity
        self._filters = filters or {}
        self._filter_defaults = filter_defaults or {}
        self._preprocessed_data = {"data": data.lazy()}
        self._raw_data = None
        self._groups = groups

    def get_validation_filter_groups(self):
        if self._groups is None:
            return [(self._filters, self._filter_defaults)]
        return self._groups


@pytest.fixture
def peaks() -> pl.DataFrame:
    """Two spectra, disjoint peak ids -- the mirror plot's shape."""
    return pl.DataFrame(
        {
            "scan_id": [3371, 3371, 3371, 3373, 3373, 3373],
            "peak_id": [1, 2, 3, 4, 5, 6],
            "mass": [100.0, 200.0, 300.0, 110.0, 210.0, 310.0],
        }
    )


@pytest.fixture
def state_manager(mock_streamlit) -> StateManager:
    return StateManager(session_key="test_validation")


class TestSingleFilterComponent:
    """The behaviour that already worked must not regress."""

    def test_selection_in_filtered_data_survives(self, peaks, state_manager):
        component = FakeComponent(
            peaks,
            interactivity={"peak": "peak_id"},
            filters={"scan": "scan_id"},
        )
        state_manager.set_selection("peak", 2)
        state = {"scan": 3371, "peak": 2}

        changed = _validate_interactivity_selections(component, state_manager, state)

        assert changed is False
        assert state_manager.get_selection("peak") == 2

    def test_selection_outside_filtered_data_is_cleared(self, peaks, state_manager):
        component = FakeComponent(
            peaks,
            interactivity={"peak": "peak_id"},
            filters={"scan": "scan_id"},
        )
        # Peak 5 belongs to scan 3373, but the filter now selects 3371.
        state_manager.set_selection("peak", 5)
        state = {"scan": 3371, "peak": 5}

        changed = _validate_interactivity_selections(component, state_manager, state)

        assert changed is True
        assert state_manager.get_selection("peak") is None

    def test_float_from_javascript_is_coerced_before_comparison(
        self, peaks, state_manager
    ):
        """JS numbers arrive as floats; a whole float must match an integer column."""
        component = FakeComponent(
            peaks,
            interactivity={"peak": "peak_id"},
            filters={"scan": "scan_id"},
        )
        state_manager.set_selection("peak", 2.0)
        state = {"scan": 3371.0, "peak": 2.0}

        changed = _validate_interactivity_selections(component, state_manager, state)

        assert changed is False
        assert state_manager.get_selection("peak") == 2.0

    def test_awaiting_filter_validates_nothing(self, peaks, state_manager):
        component = FakeComponent(
            peaks,
            interactivity={"peak": "peak_id"},
            filters={"scan": "scan_id"},
        )
        state_manager.set_selection("peak", 5)
        state = {"peak": 5}  # no 'scan' yet, and no default

        changed = _validate_interactivity_selections(component, state_manager, state)

        assert changed is False
        assert state_manager.get_selection("peak") == 5


class TestPerSideFilterGroups:
    """A MirrorPlot filters each half independently; the union is not a conjunction."""

    def _mirror(self, peaks, top=3371, bottom=3373):
        return FakeComponent(
            peaks,
            interactivity={"peak": "peak_id"},
            # What MirrorPlot hands the base class: a lossy union of both sides.
            filters={"scan_top": "scan_id", "scan_bottom": "scan_id"},
            filter_defaults={"scan_top": top, "scan_bottom": bottom},
            groups=[
                ({"scan_top": "scan_id"}, {"scan_top": top}),
                ({"scan_bottom": "scan_id"}, {"scan_bottom": bottom}),
            ],
        )

    def test_peak_on_top_side_survives(self, peaks, state_manager):
        component = self._mirror(peaks)
        state_manager.set_selection("peak", 2)
        state = {"scan_top": 3371, "scan_bottom": 3373, "peak": 2}

        changed = _validate_interactivity_selections(component, state_manager, state)

        assert changed is False
        assert state_manager.get_selection("peak") == 2

    def test_peak_on_bottom_side_survives(self, peaks, state_manager):
        component = self._mirror(peaks)
        state_manager.set_selection("peak", 5)
        state = {"scan_top": 3371, "scan_bottom": 3373, "peak": 5}

        changed = _validate_interactivity_selections(component, state_manager, state)

        assert changed is False
        assert state_manager.get_selection("peak") == 5

    def test_peak_on_neither_side_is_still_cleared(self, peaks, state_manager):
        """The validator must keep doing its job across the union of both sides."""
        extra = pl.concat(
            [
                peaks,
                pl.DataFrame(
                    {"scan_id": [9999], "peak_id": [42], "mass": [999.0]}
                ).cast(peaks.schema),
            ]
        )
        component = self._mirror(extra)
        state_manager.set_selection("peak", 42)
        state = {"scan_top": 3371, "scan_bottom": 3373, "peak": 42}

        changed = _validate_interactivity_selections(component, state_manager, state)

        assert changed is True
        assert state_manager.get_selection("peak") is None

    def test_both_sides_on_same_scan(self, peaks, state_manager):
        component = self._mirror(peaks, top=3371, bottom=3371)
        state_manager.set_selection("peak", 3)
        state = {"scan_top": 3371, "scan_bottom": 3371, "peak": 3}

        changed = _validate_interactivity_selections(component, state_manager, state)

        assert changed is False
        assert state_manager.get_selection("peak") == 3

    def test_unfiltered_side_admits_everything(self, peaks, state_manager):
        """A side with no filters shows the whole table, so nothing can be invalid."""
        component = FakeComponent(
            peaks,
            interactivity={"peak": "peak_id"},
            filters={"scan_bottom": "scan_id"},
            filter_defaults={"scan_bottom": 3373},
            groups=[
                ({}, {}),
                ({"scan_bottom": "scan_id"}, {"scan_bottom": 3373}),
            ],
        )
        state_manager.set_selection("peak", 1)  # only in scan 3371
        state = {"scan_bottom": 3373, "peak": 1}

        changed = _validate_interactivity_selections(component, state_manager, state)

        assert changed is False
        assert state_manager.get_selection("peak") == 1


class TestEmptyFilteredData:
    """An empty frame clears selections, and that is intended.

    A filter matching no rows means the component displays nothing, so nothing in it
    can still be selected. ``TestTableSelectionClearingOnInvalidFilter`` in
    tests/integration/test_tabulator.py depends on this. It is worth pinning here too,
    because treating "empty" as "cannot tell" looks like a tempting safety net and
    would silently disable clearing for every component.
    """

    def test_selection_cleared_when_filter_matches_no_rows(self, peaks, state_manager):
        component = FakeComponent(
            peaks,
            interactivity={"peak": "peak_id"},
            filters={"scan": "scan_id"},
        )
        state_manager.set_selection("peak", 2)
        state = {"scan": 12345, "peak": 2}

        changed = _validate_interactivity_selections(component, state_manager, state)

        assert changed is True
        assert state_manager.get_selection("peak") is None


class TestRealMirrorPlot:
    """The shipped scenario, end to end through a real component.

    Every other MirrorPlot test calls ``_prepare_vue_data`` directly and never reaches
    the bridge, which is how the conjunction defect survived to release.
    """

    def _plot(self, data, cache_dir, cache_id="validation"):
        from openms_insight import MirrorPlot

        return MirrorPlot(
            cache_id=cache_id,
            data=data,
            cache_path=str(cache_dir),
            filters_top={"spectrum_top": "scan_id"},
            filter_defaults_top={"spectrum_top": 1},
            filters_bottom={"spectrum_bottom": "scan_id"},
            filter_defaults_bottom={"spectrum_bottom": 2},
            interactivity={"selected_peak": "peak_id"},
            x_column="mass",
            y_column="intensity",
        )

    def test_union_filters_reach_the_base_class(
        self, mock_streamlit, temp_cache_dir, sample_lineplot_data
    ):
        """Pin the lossy flattening the fix has to work around."""
        plot = self._plot(sample_lineplot_data, temp_cache_dir)

        assert plot._filters == {
            "spectrum_top": "scan_id",
            "spectrum_bottom": "scan_id",
        }
        assert plot.get_validation_filter_groups() == [
            ({"spectrum_top": "scan_id"}, {"spectrum_top": 1}),
            ({"spectrum_bottom": "scan_id"}, {"spectrum_bottom": 2}),
        ]

    def test_peak_from_either_half_survives_validation(
        self, mock_streamlit, temp_cache_dir, sample_lineplot_data, state_manager
    ):
        plot = self._plot(sample_lineplot_data, temp_cache_dir)
        state = {"spectrum_top": 1, "spectrum_bottom": 2}

        for peak in (10, 20, 30, 40, 50):
            state_manager.set_selection("selected_peak", peak)
            changed = _validate_interactivity_selections(
                plot, state_manager, {**state, "selected_peak": peak}
            )

            assert changed is False, f"peak {peak} was wrongly cleared"
            assert state_manager.get_selection("selected_peak") == peak

    def test_peak_absent_from_both_halves_is_cleared(
        self, mock_streamlit, temp_cache_dir, sample_lineplot_data, state_manager
    ):
        plot = self._plot(sample_lineplot_data, temp_cache_dir, cache_id="validation2")
        state_manager.set_selection("selected_peak", 999)

        changed = _validate_interactivity_selections(
            plot,
            state_manager,
            {"spectrum_top": 1, "spectrum_bottom": 2, "selected_peak": 999},
        )

        assert changed is True
        assert state_manager.get_selection("selected_peak") is None


class TestComponentsWithoutValidatableData:
    def test_component_without_data_is_skipped(self, state_manager):
        """Heatmap keeps levels, not a 'data' frame, so it cannot be validated."""

        class NoData:
            _cache_id = "heatmap"
            _interactivity = {"scan": "scan_id"}
            _filters: dict[str, str] = {}
            _filter_defaults: dict[str, Any] = {}
            _preprocessed_data = {"level_0": pl.DataFrame({"x": [1]}).lazy()}
            _raw_data = None

        state_manager.set_selection("scan", 7)

        changed = _validate_interactivity_selections(NoData(), state_manager, {})

        assert changed is False
        assert state_manager.get_selection("scan") == 7

    def test_component_without_interactivity_is_skipped(self, peaks, state_manager):
        component = FakeComponent(peaks, interactivity={}, filters={"scan": "scan_id"})

        changed = _validate_interactivity_selections(
            component, state_manager, {"scan": 3371}
        )

        assert changed is False
