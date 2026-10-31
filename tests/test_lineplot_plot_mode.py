"""LinePlot plot_mode: sticks (spectra) or a filled line (chromatograms)."""

import polars as pl
import pytest

from openms_insight import LinePlot


@pytest.fixture
def tic_data():
    return pl.LazyFrame(
        {
            "scan_id": [3, 1, 2],
            "rt": [30.0, 10.0, 20.0],
            "tic": [5.0, 1.0, 3.0],
        }
    )


def test_default_mode_is_sticks(mock_streamlit, temp_cache_dir, tic_data):
    plot = LinePlot(
        cache_id="tic_default",
        data=tic_data,
        cache_path=str(temp_cache_dir),
        x_column="rt",
        y_column="tic",
    )
    assert plot._get_component_args()["plotMode"] == "sticks"


def test_line_mode_reaches_vue_and_survives_reconstruction(
    mock_streamlit, temp_cache_dir, tic_data
):
    LinePlot(
        cache_id="tic_line",
        data=tic_data,
        cache_path=str(temp_cache_dir),
        x_column="rt",
        y_column="tic",
        interactivity={"spectrum": "scan_id"},
        plot_mode="line",
    )
    restored = LinePlot(cache_id="tic_line", cache_path=str(temp_cache_dir))
    args = restored._get_component_args()
    assert args["plotMode"] == "line"
    assert args["interactivity"] == {"spectrum": "scan_id"}


def test_line_mode_is_part_of_the_cache_config(
    mock_streamlit, temp_cache_dir, tic_data
):
    kwargs = {
        "data": tic_data,
        "cache_path": str(temp_cache_dir),
        "x_column": "rt",
        "y_column": "tic",
    }
    sticks = LinePlot(cache_id="tic_sticks", **kwargs)
    line = LinePlot(cache_id="tic_line2", plot_mode="line", **kwargs)
    assert sticks._get_cache_config()["plot_mode"] == "sticks"
    assert line._get_cache_config()["plot_mode"] == "line"


def test_unknown_mode_is_rejected(mock_streamlit, temp_cache_dir, tic_data):
    with pytest.raises(ValueError, match="plot_mode"):
        LinePlot(
            cache_id="tic_bad",
            data=tic_data,
            cache_path=str(temp_cache_dir),
            x_column="rt",
            y_column="tic",
            plot_mode="bars",
        )
