"""LinePlot's keep_zoom: a render-time option passed to Vue, not part of the cache."""

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


def _plot(spectra, cache_dir, cache_id="keep_zoom", **kwargs) -> LinePlot:
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
    assert args["keepZoom"] is False


def test_true_is_passed_to_vue(mock_streamlit, temp_cache_dir, spectra):
    args = _plot(spectra, temp_cache_dir, keep_zoom=True)._get_component_args()
    assert args["keepZoom"] is True


@pytest.mark.parametrize("value", [1, "yes", None])
def test_rejects_non_bool(mock_streamlit, temp_cache_dir, spectra, value):
    with pytest.raises(ValueError, match="keep_zoom"):
        _plot(spectra, temp_cache_dir, keep_zoom=value)


def test_not_part_of_the_cache(mock_streamlit, temp_cache_dir, spectra):
    off = _plot(spectra, temp_cache_dir, cache_id="same")
    with open(off._get_manifest_path()) as f:
        before = json.load(f)
    on = _plot(spectra, temp_cache_dir, cache_id="same", keep_zoom=True)
    with open(on._get_manifest_path()) as f:
        after = json.load(f)
    assert before == after
    assert "keep_zoom" not in json.dumps(after)
