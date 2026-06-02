"""Tests for the LinePlot FLASHTnT "tagger overlay" (opt-in, default off).

The overlay is gated behind ``tag_overlay``. These tests assert that:
- with ``tag_overlay`` off the component is byte-identical to before (regression),
- with ``signal_peaks_column`` + a ``tagData`` state the SignalPeaks list-column
  is projected/emitted, and ``tagData`` / ``AApos`` reach the component args and
  ``get_state_dependencies``,
- the config survives cache reconstruction,
- a bad ``signal_peaks_column`` is rejected by validation.
"""

import polars as pl
import pytest

from openms_insight import LinePlot


@pytest.fixture
def primary_df() -> pl.LazyFrame:
    return pl.LazyFrame(
        {
            "scan_id": [1, 1, 1, 2, 2],
            "mass": [100.0, 200.0, 300.0, 400.0, 500.0],
            "intensity": [10.0, 20.0, 30.0, 40.0, 50.0],
        }
    )


@pytest.fixture
def primary_with_signal_peaks() -> pl.LazyFrame:
    # Each peak row's value is a list of [mz, intensity, charge] triplets,
    # aligned 1:1 with the primary peaks.
    return pl.LazyFrame(
        {
            "scan_id": [1, 1, 1],
            "mass": [100.0, 200.0, 300.0],
            "intensity": [10.0, 20.0, 30.0],
            "signal_peaks": [
                [[50.0, 6.0, 2], [100.5, 4.0, 1]],
                [[100.0, 12.0, 2], [200.5, 8.0, 1]],
                [[150.0, 18.0, 2], [300.5, 12.0, 1]],
            ],
        }
    )


class TestTaggerOverlayOff:
    """tag_overlay defaulting off must leave existing behavior unchanged."""

    def test_default_off_args_unchanged(
        self, mock_streamlit, temp_cache_dir, primary_df
    ):
        lp = LinePlot(
            cache_id="lp_tag_off",
            data=primary_df,
            filters={"scanIndex": "scan_id"},
            x_column="mass",
            y_column="intensity",
            cache_path=str(temp_cache_dir),
        )
        args = lp._get_component_args()
        # No tagger keys leak into args when the flag is off.
        assert "tagOverlay" not in args
        assert "signalPeaksColumn" not in args
        assert "tagData" not in args
        assert "aaPos" not in args

    def test_default_off_state_dependencies_unchanged(
        self, mock_streamlit, temp_cache_dir, primary_df
    ):
        lp = LinePlot(
            cache_id="lp_tag_off_deps",
            data=primary_df,
            filters={"scanIndex": "scan_id"},
            x_column="mass",
            y_column="intensity",
            cache_path=str(temp_cache_dir),
        )
        # Identical to the base behavior: filter identifiers only.
        assert lp.get_state_dependencies() == ["scanIndex"]

    def test_default_off_no_signal_peaks_projected(
        self, mock_streamlit, temp_cache_dir, primary_with_signal_peaks
    ):
        """Without tag_overlay/signal_peaks_column, the list-column is not emitted."""
        lp = LinePlot(
            cache_id="lp_tag_off_proj",
            data=primary_with_signal_peaks,
            filters={"scanIndex": "scan_id"},
            x_column="mass",
            y_column="intensity",
            cache_path=str(temp_cache_dir),
        )
        out = lp._prepare_vue_data({"scanIndex": 1})
        assert "signal_peaks" not in out["plotData"].columns
        # _plotConfig still advertises a None signal-peaks column.
        assert out["_plotConfig"]["signalPeaksColumn"] is None


class TestTaggerOverlayOn:
    def test_signal_peaks_projected_and_emitted(
        self, mock_streamlit, temp_cache_dir, primary_with_signal_peaks
    ):
        lp = LinePlot(
            cache_id="lp_tag_on_proj",
            data=primary_with_signal_peaks,
            filters={"scanIndex": "scan_id"},
            x_column="mass",
            y_column="intensity",
            tag_overlay=True,
            signal_peaks_column="signal_peaks",
            cache_path=str(temp_cache_dir),
        )
        out = lp._prepare_vue_data({"scanIndex": 1})
        df = out["plotData"]
        # The SignalPeaks list-column rides along inside plotData, 1:1 aligned.
        assert "signal_peaks" in df.columns
        assert len(df) == 3
        first = df["signal_peaks"].tolist()[0]
        assert list(first[0]) == [50.0, 6.0, 2]
        # _plotConfig tells Vue the column name.
        assert out["_plotConfig"]["signalPeaksColumn"] == "signal_peaks"

    def test_tag_data_and_aa_pos_reach_args(
        self, mock_streamlit, temp_cache_dir, primary_with_signal_peaks
    ):
        lp = LinePlot(
            cache_id="lp_tag_on_args",
            data=primary_with_signal_peaks,
            filters={"scanIndex": "scan_id"},
            x_column="mass",
            y_column="intensity",
            tag_overlay=True,
            signal_peaks_column="signal_peaks",
            cache_path=str(temp_cache_dir),
        )
        tag_data = {
            "masses": [300.0, 200.0, 100.0],
            "sequence": "PEP",
            "nTerminal": True,
            "startPos": 0,
            "endPos": 2,
            "selectedAA": 1,
        }
        state = {"scanIndex": 1, "tagData": tag_data, "AApos": 2}
        # _prepare_vue_data captures the render state for _get_component_args.
        lp._prepare_vue_data(state)
        args = lp._get_component_args()
        assert args["tagOverlay"] is True
        assert args["signalPeaksColumn"] == "signal_peaks"
        assert args["tagData"] == tag_data
        assert args["aaPos"] == 2

    def test_tag_data_absent_renders_as_today(
        self, mock_streamlit, temp_cache_dir, primary_with_signal_peaks
    ):
        """tag_overlay on but no tagData state → no tagData/aaPos in args."""
        lp = LinePlot(
            cache_id="lp_tag_on_notag",
            data=primary_with_signal_peaks,
            filters={"scanIndex": "scan_id"},
            x_column="mass",
            y_column="intensity",
            tag_overlay=True,
            signal_peaks_column="signal_peaks",
            cache_path=str(temp_cache_dir),
        )
        lp._prepare_vue_data({"scanIndex": 1})
        args = lp._get_component_args()
        # Flag + column advertised, but no selection forwarded.
        assert args["tagOverlay"] is True
        assert args["signalPeaksColumn"] == "signal_peaks"
        assert "tagData" not in args
        assert "aaPos" not in args

    def test_state_dependencies_include_tag_keys(
        self, mock_streamlit, temp_cache_dir, primary_with_signal_peaks
    ):
        lp = LinePlot(
            cache_id="lp_tag_on_deps",
            data=primary_with_signal_peaks,
            filters={"scanIndex": "scan_id"},
            x_column="mass",
            y_column="intensity",
            tag_overlay=True,
            signal_peaks_column="signal_peaks",
            cache_path=str(temp_cache_dir),
        )
        deps = lp.get_state_dependencies()
        assert "scanIndex" in deps
        assert "tagData" in deps
        assert "AApos" in deps

    def test_config_survives_cache_reconstruction(
        self, mock_streamlit, temp_cache_dir, primary_with_signal_peaks
    ):
        LinePlot(
            cache_id="lp_tag_recon",
            data=primary_with_signal_peaks,
            filters={"scanIndex": "scan_id"},
            x_column="mass",
            y_column="intensity",
            tag_overlay=True,
            signal_peaks_column="signal_peaks",
            cache_path=str(temp_cache_dir),
        )
        lp2 = LinePlot(cache_id="lp_tag_recon", cache_path=str(temp_cache_dir))
        assert lp2._tag_overlay is True
        assert lp2._signal_peaks_column == "signal_peaks"
        # Rebuilt component still projects the list-column and exposes deps.
        out = lp2._prepare_vue_data({"scanIndex": 1})
        assert "signal_peaks" in out["plotData"].columns
        assert "tagData" in lp2.get_state_dependencies()

    def test_invalid_signal_peaks_column_rejected(
        self, mock_streamlit, temp_cache_dir, primary_df
    ):
        with pytest.raises(ValueError, match="signal_peaks_column"):
            LinePlot(
                cache_id="lp_tag_badcol",
                data=primary_df,
                filters={"scanIndex": "scan_id"},
                x_column="mass",
                y_column="intensity",
                tag_overlay=True,
                signal_peaks_column="does_not_exist",
                cache_path=str(temp_cache_dir),
            )
