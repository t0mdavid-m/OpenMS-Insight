"""Top peak labels of the stick spectra: render-time options passed to Vue, not part of the cache."""

import json

import polars as pl
import pytest

from openms_insight import DeconvolvedSpectrum, LinePlot, MirrorPlot


@pytest.fixture
def spectra() -> pl.LazyFrame:
    return pl.LazyFrame(
        {
            "scan": [1, 1, 2, 2],
            "mz": [100.0, 200.0, 150.0, 250.0],
            "intensity": [10.0, 20.0, 30.0, 40.0],
        }
    )


def _lineplot(request, cache_dir, cache_id, **kwargs):
    return LinePlot(
        cache_id=cache_id,
        data=request.getfixturevalue("spectra"),
        filters={"spectrum": "scan"},
        x_column="mz",
        y_column="intensity",
        cache_path=str(cache_dir),
        **kwargs,
    )


def _mirror(request, cache_dir, cache_id, **kwargs):
    return MirrorPlot(
        cache_id=cache_id,
        data=request.getfixturevalue("spectra"),
        filters_top={"spectrum": "scan"},
        filters_bottom={"spectrum": "scan"},
        x_column="mz",
        y_column="intensity",
        cache_path=str(cache_dir),
        **kwargs,
    )


def _deconvolved(request, cache_dir, cache_id, **kwargs):
    return DeconvolvedSpectrum(
        cache_id=cache_id,
        data=request.getfixturevalue("sample_deconvolved_spectra"),
        filters={"scan": "scan_idx"},
        view="deconvolved",
        cache_path=str(cache_dir),
        **kwargs,
    )


BUILDERS = pytest.mark.parametrize(
    "build",
    [_lineplot, _mirror, _deconvolved],
    ids=["LinePlot", "MirrorPlot", "DeconvolvedSpectrum"],
)


@BUILDERS
def test_defaults(mock_streamlit, temp_cache_dir, request, build):
    args = build(request, temp_cache_dir, "top")._get_component_args()
    assert args["topPeakLabels"] == 10
    assert args["showTopPeakLabels"] is False


@BUILDERS
def test_values_are_passed_to_vue(mock_streamlit, temp_cache_dir, request, build):
    args = build(
        request, temp_cache_dir, "top", top_peak_labels=25, show_top_peak_labels=True
    )._get_component_args()
    assert args["topPeakLabels"] == 25
    assert args["showTopPeakLabels"] is True


@BUILDERS
def test_zero_removes_the_button(mock_streamlit, temp_cache_dir, request, build):
    args = build(
        request, temp_cache_dir, "top", top_peak_labels=0
    )._get_component_args()
    assert args["topPeakLabels"] == 0


@BUILDERS
@pytest.mark.parametrize("value", [-1, 201, 2.5, "10", None, True])
def test_rejects_bad_counts(mock_streamlit, temp_cache_dir, request, build, value):
    with pytest.raises(ValueError, match="top_peak_labels"):
        build(request, temp_cache_dir, "top", top_peak_labels=value)


@BUILDERS
@pytest.mark.parametrize("value", [1, "yes", None])
def test_rejects_non_bool_show(mock_streamlit, temp_cache_dir, request, build, value):
    with pytest.raises(ValueError, match="show_top_peak_labels"):
        build(request, temp_cache_dir, "top", show_top_peak_labels=value)


@BUILDERS
def test_not_part_of_the_cache(mock_streamlit, temp_cache_dir, request, build):
    off = build(request, temp_cache_dir, "same")
    with open(off._get_manifest_path()) as f:
        before = json.load(f)
    on = build(
        request,
        temp_cache_dir,
        "same",
        top_peak_labels=50,
        show_top_peak_labels=True,
    )
    with open(on._get_manifest_path()) as f:
        after = json.load(f)
    assert before == after
    assert "top_peak" not in json.dumps(after)
