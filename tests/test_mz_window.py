"""LinePlot's shaded m/z window: render-time options passed to Vue, not part of the cache."""

import json

import polars as pl
import pytest

from openms_insight import LinePlot


@pytest.fixture
def spectra() -> pl.LazyFrame:
    return pl.LazyFrame(
        {
            "scan": [1, 1],
            "mz": [100.0, 200.0],
            "intensity": [10.0, 20.0],
        }
    )


def _plot(spectra, cache_dir, cache_id="win", **kwargs) -> LinePlot:
    return LinePlot(
        cache_id=cache_id,
        data=spectra,
        filters={"spectrum": "scan"},
        x_column="mz",
        y_column="intensity",
        cache_path=str(cache_dir),
        **kwargs,
    )


def test_off_by_default(mock_streamlit, temp_cache_dir, spectra):
    args = _plot(spectra, temp_cache_dir)._get_component_args()
    assert "windowIdentifier" not in args


@pytest.mark.parametrize(
    ("tolerance", "value", "unit"),
    [
        (0.01, 0.01, "Da"),
        (1, 1.0, "Da"),
        ("10 ppm", 10.0, "ppm"),
        ("5ppm", 5.0, "ppm"),
        ("0.02 Da", 0.02, "Da"),
        (" 0.5 th ", 0.5, "Da"),
        ("1e-3", 0.001, "Da"),
    ],
)
def test_tolerance(mock_streamlit, temp_cache_dir, spectra, tolerance, value, unit):
    args = _plot(
        spectra, temp_cache_dir, window_identifier="xic", window_tolerance=tolerance
    )._get_component_args()
    assert args["windowIdentifier"] == "xic"
    assert args["windowTolerance"] == pytest.approx(value)
    assert args["windowToleranceUnit"] == unit


@pytest.mark.parametrize("value", ["", 5, ["xic"]])
def test_rejects_bad_identifier(mock_streamlit, temp_cache_dir, spectra, value):
    with pytest.raises(ValueError, match="window_identifier"):
        _plot(spectra, temp_cache_dir, window_identifier=value)


@pytest.mark.parametrize(
    "value", [0, -1, 101, "20000 ppm", "ten ppm", "10 mmu", None, True, float("nan")]
)
def test_rejects_bad_tolerance(mock_streamlit, temp_cache_dir, spectra, value):
    with pytest.raises(ValueError, match="window_tolerance"):
        _plot(spectra, temp_cache_dir, window_identifier="xic", window_tolerance=value)


def test_not_part_of_the_cache(mock_streamlit, temp_cache_dir, spectra):
    off = _plot(spectra, temp_cache_dir, cache_id="same")
    with open(off._get_manifest_path()) as f:
        before = json.load(f)
    on = _plot(
        spectra,
        temp_cache_dir,
        cache_id="same",
        window_identifier="xic",
        window_tolerance="10 ppm",
    )
    with open(on._get_manifest_path()) as f:
        after = json.load(f)
    assert before == after
    assert "window" not in json.dumps(after)
