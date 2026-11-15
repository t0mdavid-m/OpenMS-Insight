"""relative_intensity on LinePlot: a render-time option passed to Vue, not part of the cache."""

import json

import polars as pl
import pytest

from openms_insight import LinePlot


@pytest.fixture
def spectra() -> pl.LazyFrame:
    return pl.LazyFrame(
        {
            "scan": [1, 1, 2, 2],
            "mz": [100.0, 200.0, 150.0, 250.0],
            "intensity": [10.0, 20.0, 30.0, 40.0],
        }
    )


def _lineplot(spectra, cache_dir, cache_id, **kwargs):
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
    args = _lineplot(spectra, temp_cache_dir, "ri")._get_component_args()
    assert args["relativeIntensity"] is False


def test_true_is_passed_to_vue(mock_streamlit, temp_cache_dir, spectra):
    plot = _lineplot(spectra, temp_cache_dir, "ri", relative_intensity=True)
    assert plot._get_component_args()["relativeIntensity"] is True


@pytest.mark.parametrize("value", [1, "yes", None])
def test_rejects_non_bool(mock_streamlit, temp_cache_dir, spectra, value):
    with pytest.raises(ValueError, match="relative_intensity"):
        _lineplot(spectra, temp_cache_dir, "ri", relative_intensity=value)


def test_not_part_of_the_cache(mock_streamlit, temp_cache_dir, spectra):
    off = _lineplot(spectra, temp_cache_dir, "same")
    with open(off._get_manifest_path()) as f:
        before = json.load(f)
    on = _lineplot(spectra, temp_cache_dir, "same", relative_intensity=True)
    with open(on._get_manifest_path()) as f:
        after = json.load(f)
    assert before == after
    assert "relative_intensity" not in json.dumps(after)


def test_reconstructed_plot_starts_absolute(mock_streamlit, temp_cache_dir, spectra):
    _lineplot(spectra, temp_cache_dir, "rebuilt", relative_intensity=True)
    rebuilt = LinePlot(cache_id="rebuilt", cache_path=str(temp_cache_dir))
    assert rebuilt._get_component_args()["relativeIntensity"] is False
