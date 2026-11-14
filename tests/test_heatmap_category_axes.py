"""A Heatmap whose axes are categories (sample and protein names) can be zoomed."""

import polars as pl

from openms_insight import Heatmap


def _data() -> pl.LazyFrame:
    samples = [f"S{i}" for i in range(6)]
    proteins = [f"P{j}" for j in range(30)]
    rows = [
        {"Sample": s, "Protein": p, "z": float(i - j)}
        for i, s in enumerate(samples)
        for j, p in enumerate(proteins)
    ]
    return pl.DataFrame(rows).lazy()


def test_zoom_on_category_axes(mock_streamlit, temp_cache_dir):
    heatmap = Heatmap(
        cache_id="category_axes",
        data=_data(),
        x_column="Sample",
        y_column="Protein",
        intensity_column="z",
        zoom_identifier="zoom@hm",
        cache_path=str(temp_cache_dir),
    )
    # Plotly reports a category axis zoom as positions (numbers)
    zoom = {"xRange": [-0.5, 2.5], "yRange": [-44.6, 140.7]}
    payload = heatmap._prepare_vue_data({"zoom@hm": zoom})
    frame = payload["heatmapData"]
    assert len(frame) == 6 * 30


def test_help_is_sent_to_vue(mock_streamlit, temp_cache_dir):
    heatmap = Heatmap(
        cache_id="category_axes_help",
        data=_data(),
        x_column="Sample",
        y_column="Protein",
        intensity_column="z",
        cache_path=str(temp_cache_dir),
        help="Each cell is a protein's z-score in a sample.",
    )
    assert heatmap._help == "Each cell is a protein's z-score in a sample."
    assert "help" not in heatmap._get_cache_config()
    assert heatmap.set_help(None)._help is None


def test_toolbar_settings_validated_and_kept_out_of_cache(tmp_path):
    import polars as pl
    import pytest

    from openms_insight import Heatmap
    from openms_insight.core.settings import setting_value, validate_settings

    df = pl.DataFrame({"x": [1.0, 2.0], "y": [1.0, 2.0], "v": [1.0, 2.0]})
    settings = [
        {"identifier": "top_n", "label": "Proteins shown", "kind": "range", "min": 20, "max": 200, "step": 10, "default": 50},
        {"identifier": "scale", "label": "Scale", "options": ["z", "log"]},
    ]
    hm = Heatmap(cache_id="hs", data=df.lazy(), x_column="x", y_column="y", intensity_column="v",
                 cache_path=str(tmp_path), toolbar_settings=settings)
    assert [s["identifier"] for s in hm._toolbar_settings] == ["top_n", "scale"]
    assert hm._toolbar_settings[1]["default"] == "z"
    assert "toolbar_settings" not in hm._get_cache_config()

    class State:
        def __init__(self, v):
            self.v = v

        def get_selection(self, identifier):
            return self.v.get(identifier)

    assert setting_value(State({}), hm._toolbar_settings[0]) == 50
    assert setting_value(State({"top_n": 80}), hm._toolbar_settings[0]) == 80
    with pytest.raises(ValueError):
        validate_settings([{"identifier": "a", "kind": "choice", "options": []}])
    with pytest.raises(ValueError):
        validate_settings([{"identifier": "a", "kind": "range"}])
