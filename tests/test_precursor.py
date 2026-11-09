"""The precursor mark on the spectrum views: argument plumbing and caches.

The mark itself is drawn in the browser (utils/precursorMark.ts); Python only
passes the precursor's m/z and charge.
"""

import json
import math

import pytest
from component_cases import COMPONENT_CASES, build_kwargs

from openms_insight import LinePlot, MirrorPlot
from openms_insight.core.precursor import precursor_args, validate_precursor

# MirrorPlot is not in COMPONENT_CASES; it is tested on its own below
MARK_CASES = [case for case in COMPONENT_CASES if case[0] is LinePlot]
OTHER_CASES = [case for case in COMPONENT_CASES if case[0] is not LinePlot]
OTHER_IDS = [case[0].__name__ for case in OTHER_CASES]


@pytest.fixture
def make(mock_streamlit, temp_cache_dir, request):
    def _make(case, cache_id="precursor", **overrides):
        ComponentClass, data_fixture, extra_kwargs, fixture_kwargs = case
        kwargs = build_kwargs(request, extra_kwargs, fixture_kwargs)
        kwargs.update(overrides)
        return ComponentClass(
            cache_id=f"{ComponentClass.__name__}_{cache_id}",
            data=request.getfixturevalue(data_fixture),
            cache_path=str(temp_cache_dir),
            **kwargs,
        )

    return _make


def test_line_plot_is_covered():
    assert len(MARK_CASES) == 1


def test_no_precursor_by_default(make):
    assert make(MARK_CASES[0])._get_component_args()["precursor"] is None


def test_precursor_is_passed(make):
    plot = make(MARK_CASES[0], precursor_mz=912.4567, precursor_charge=2)
    assert plot._get_component_args()["precursor"] == {"mz": 912.4567, "charge": 2}


def test_unknown_charge_is_zero(make):
    plot = make(MARK_CASES[0], precursor_mz=500)
    assert plot._get_component_args()["precursor"] == {"mz": 500.0, "charge": 0}


@pytest.mark.parametrize("mz", ["500", True, 0, -1.0, math.nan, math.inf])
def test_invalid_mz_raises(mz):
    with pytest.raises(ValueError, match="precursor_mz"):
        validate_precursor(mz, 2)


@pytest.mark.parametrize("charge", ["2", True, -1, 2.0])
def test_invalid_charge_raises(charge):
    with pytest.raises(ValueError, match="precursor_charge"):
        validate_precursor(500.0, charge)


def test_charge_without_mz_marks_nothing():
    assert precursor_args(*validate_precursor(None, 3)) == {"precursor": None}


def test_precursor_does_not_touch_the_cache(make):
    plain = make(MARK_CASES[0], cache_id="reuse")
    with open(plain._get_manifest_path()) as f:
        manifest = json.load(f)
    marked = make(
        MARK_CASES[0], cache_id="reuse", precursor_mz=700.0, precursor_charge=3
    )
    with open(marked._get_manifest_path()) as f:
        assert json.load(f)["cache_generation"] == manifest["cache_generation"]
    config = plain._get_cache_config()
    assert not any("precursor" in key for key in config)
    assert plain._compute_config_hash() == marked._compute_config_hash()


@pytest.mark.parametrize("case", OTHER_CASES, ids=OTHER_IDS)
def test_other_components_send_nothing(make, case):
    assert "precursor" not in make(case)._get_component_args()


def _mirror(temp_cache_dir, data, **overrides):
    options = {
        "cache_id": "precursor",
        "data": data,
        "cache_path": str(temp_cache_dir),
        "filters_top": {"spectrum_top": "scan_id"},
        "filters_bottom": {"spectrum_bottom": "scan_id"},
        "interactivity": {"selected_peak": "peak_id"},
        "x_column": "mass",
        "y_column": "intensity",
    }
    options.update(overrides)
    return MirrorPlot(**options)


def test_mirror_plot_precursor(mock_streamlit, temp_cache_dir, sample_lineplot_data):
    plain = _mirror(temp_cache_dir, sample_lineplot_data, cache_id="plain")
    assert plain._get_component_args()["precursor"] is None
    marked = _mirror(
        temp_cache_dir,
        sample_lineplot_data,
        cache_id="marked",
        precursor_mz=650.25,
        precursor_charge=2,
    )
    assert marked._get_component_args()["precursor"] == {"mz": 650.25, "charge": 2}
    assert plain._compute_config_hash() == marked._compute_config_hash()
    with pytest.raises(ValueError, match="precursor_mz"):
        _mirror(temp_cache_dir, sample_lineplot_data, cache_id="bad", precursor_mz=-5)


def test_mirror_plot_precursor_when_loading_by_cache_id(
    mock_streamlit, temp_cache_dir, sample_lineplot_data
):
    _mirror(temp_cache_dir, sample_lineplot_data, cache_id="load")
    loaded = MirrorPlot(
        cache_id="load", cache_path=str(temp_cache_dir), precursor_mz=800.5
    )
    assert loaded._get_component_args()["precursor"] == {"mz": 800.5, "charge": 0}
