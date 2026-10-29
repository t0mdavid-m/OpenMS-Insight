"""Tests for the top-down proteomics components and the Table options they need.

Covers SeriesPlot, Plot3D, DeconvolvedSpectrum, ProteoformSequenceView, the
Table options toggle_filters / range_filters / on_select and float_precision.
"""

import json
import math
from pathlib import Path

import polars as pl
import pytest

from openms_insight import (
    DeconvolvedSpectrum,
    Plot3D,
    ProteoformSequenceView,
    SeriesPlot,
    Table,
)


@pytest.fixture
def protein_table_data() -> pl.LazyFrame:
    """Proteoforms, two per scan, the best one flagged."""
    return pl.LazyFrame(
        {
            "index": [0, 1, 2, 3],
            "scan_idx": [10, 10, 20, 20],
            "is_best": [True, False, False, True],
            "Score": [9.0, 5.0, 3.0, 8.0],
        }
    )


@pytest.fixture
def tag_table_data() -> pl.LazyFrame:
    """Sequence tags with their residue ranges."""
    return pl.LazyFrame(
        {
            "tag_idx": [0, 1, 2],
            "scan_idx": [10, 10, 10],
            "StartPos": [0, 5, 8],
            "EndPos": [4, 9, 12],
        }
    )


class TestTableOptions:
    """toggle_filters, range_filters and on_select."""

    def test_defaults_leave_args_and_config_unchanged(
        self, mock_streamlit, temp_cache_dir: Path, sample_table_data
    ):
        table = Table(
            cache_id="plain",
            data=sample_table_data,
            cache_path=str(temp_cache_dir),
        )
        args = table._get_component_args()
        for key in ("toggleFilters", "onSelect", "toggle_filters", "range_filters"):
            assert key not in args
        config = table._get_cache_config()
        for key in ("toggle_filters", "range_filters", "on_select"):
            assert key not in config

    def test_toggle_filter_args_and_filtering(
        self, mock_streamlit, temp_cache_dir: Path, protein_table_data
    ):
        table = Table(
            cache_id="proteins",
            data=protein_table_data,
            index_field="index",
            interactivity={"protein": "index"},
            toggle_filters=[
                {
                    "label": "Best per spectrum",
                    "column": "is_best",
                    "group_column": "scan_idx",
                }
            ],
            on_select={"tag": None},
            cache_path=str(temp_cache_dir),
        )
        args = table._get_component_args()
        assert args["toggleFilters"] == [
            {
                "label": "Best per spectrum",
                "column": "is_best",
                "default": True,
                "group_column": "scan_idx",
            }
        ]
        assert args["onSelect"] == {"tag": None}
        assert "toggle_filters" not in args and "on_select" not in args

        # Default on: only the best rows
        rows = table._prepare_vue_data({})["tableData"]
        assert sorted(rows["index"]) == [0, 3]
        # Switched off through the pagination state: every row
        state = {"proteins_page": {"page": 1, "toggles": {"is_best": False}}}
        rows = table._prepare_vue_data(state)["tableData"]
        assert sorted(rows["index"]) == [0, 1, 2, 3]

    def test_toggle_filter_needs_column(self, mock_streamlit, temp_cache_dir: Path):
        with pytest.raises(ValueError, match="column"):
            Table(
                cache_id="bad",
                data=pl.LazyFrame({"a": [1]}),
                toggle_filters=[{"label": "x"}],
                cache_path=str(temp_cache_dir),
            )

    def test_toggle_options_survive_reconstruction(
        self, mock_streamlit, temp_cache_dir: Path, protein_table_data
    ):
        kwargs = {
            "toggle_filters": [{"label": "Best", "column": "is_best"}],
            "range_filters": {"aa": ["Score", "Score"]},
            "on_select": {"tag": None},
        }
        Table(
            cache_id="rebuild",
            data=protein_table_data,
            cache_path=str(temp_cache_dir),
            **kwargs,
        )
        restored = Table(cache_id="rebuild", cache_path=str(temp_cache_dir))
        args = restored._get_component_args()
        assert args["toggleFilters"][0]["column"] == "is_best"
        assert args["onSelect"] == {"tag": None}
        assert "aa" in restored.get_state_dependencies()

    def test_range_filter(self, mock_streamlit, temp_cache_dir: Path, tag_table_data):
        table = Table(
            cache_id="tags",
            data=tag_table_data,
            index_field="tag_idx",
            filters={"scan": "scan_idx"},
            range_filters={"aa": ["StartPos", "EndPos"]},
            cache_path=str(temp_cache_dir),
        )
        assert "aa" in table.get_state_dependencies()
        rows = table._prepare_vue_data({"scan": 10})["tableData"]
        assert list(rows["tag_idx"]) == [0, 1, 2]
        rows = table._prepare_vue_data({"scan": 10, "aa": 6})["tableData"]
        assert list(rows["tag_idx"]) == [1]
        rows = table._prepare_vue_data({"scan": 10, "aa": 9.0})["tableData"]
        assert list(rows["tag_idx"]) == [1, 2]

        # The bridge drops a selection the range filter hides
        lf = table._preprocessed_data["data"]
        kept = table._apply_validation_filters(lf, {"aa": 2}).collect()
        assert kept["tag_idx"].to_list() == [0]

        exported = table.export_data({"scan": 10, "aa": 12})
        assert exported["tag_idx"].to_list() == [2]


class TestFloatPrecision:
    def test_default_downcasts(self, mock_streamlit, temp_cache_dir: Path):
        table = Table(
            cache_id="f32",
            data=pl.LazyFrame({"mass": [12345.6789012]}),
            cache_path=str(temp_cache_dir),
        )
        schema = table._preprocessed_data["data"].collect_schema()
        assert schema["mass"] == pl.Float32

    def test_float64_keeps_precision(self, mock_streamlit, temp_cache_dir: Path):
        table = Table(
            cache_id="f64",
            data=pl.LazyFrame({"mass": [12345.6789012]}),
            cache_path=str(temp_cache_dir),
            float_precision="float64",
        )
        df = table._preprocessed_data["data"].collect()
        assert df.schema["mass"] == pl.Float64
        assert df["mass"][0] == pytest.approx(12345.6789012, abs=1e-9)

    def test_default_keeps_config_hash(self, mock_streamlit, temp_cache_dir: Path):
        data = pl.LazyFrame({"mass": [1.0]})

        def table(subdir, **kwargs):
            return Table(
                cache_id="h",
                data=data,
                cache_path=str(temp_cache_dir / subdir),
                **kwargs,
            )

        a = table("a")
        b = table("b", float_precision="float32")
        c = table("c", float_precision="float64")
        assert a._compute_config_hash() == b._compute_config_hash()
        assert a._compute_config_hash() != c._compute_config_hash()

    def test_invalid_precision(self, mock_streamlit, temp_cache_dir: Path):
        with pytest.raises(ValueError, match="float_precision"):
            Table(
                cache_id="bad",
                data=pl.LazyFrame({"a": [1.0]}),
                cache_path=str(temp_cache_dir),
                float_precision="float16",
            )


class TestSeriesPlot:
    def test_args_and_data(self, mock_streamlit, temp_cache_dir, sample_series_data):
        plot = SeriesPlot(
            cache_id="fdr",
            data=sample_series_data,
            x_column="QScore",
            y_column="Density",
            series_column="kind",
            series_names={"target": "Target QScores", "decoy": "Decoy QScores"},
            series_colors={"target": "green", "decoy": "red"},
            title="FDR Plot",
            cache_path=str(temp_cache_dir),
        )
        args = plot._get_component_args()
        assert args["componentType"] == "PlotlySeries"
        # Pairs keep the legend order through JSON
        assert args["seriesNames"] == [
            ["target", "Target QScores"],
            ["decoy", "Decoy QScores"],
        ]
        data = plot._prepare_vue_data({})
        assert len(data["plotData"]) == 6


class TestPlot3D:
    def _plot(self, data, cache_dir):
        return Plot3D(
            cache_id="signals",
            data=data,
            filters={"scan": "scan_idx", "mass": "mass_idx"},
            filter_defaults={"mass": -1},
            x_column="mass",
            y_column="charge",
            z_column="intensity",
            series_column="kind",
            title="",
            selection_titles={"mass": "Mass signals", "scan": "Precursor signals"},
            cache_path=str(cache_dir),
        )

    def test_list_columns_are_spread(
        self, mock_streamlit, temp_cache_dir, sample_plot3d_data
    ):
        plot = self._plot(sample_plot3d_data, temp_cache_dir)
        df = plot._prepare_vue_data({"scan": 0, "mass": 0})["plotData"]
        assert len(df) == 3
        assert sorted(df["mass"]) == [1000.0, 1000.5, 1002.0]
        assert df["intensity"].dtype == "float64"

    def test_default_rows_without_mass(
        self, mock_streamlit, temp_cache_dir, sample_plot3d_data
    ):
        plot = self._plot(sample_plot3d_data, temp_cache_dir)
        df = plot._prepare_vue_data({"scan": 0})["plotData"]
        assert sorted(df["mass"]) == [1000.0, 1001.0]

    def test_no_scan_no_points(
        self, mock_streamlit, temp_cache_dir, sample_plot3d_data
    ):
        plot = self._plot(sample_plot3d_data, temp_cache_dir)
        df = plot._prepare_vue_data({})["plotData"]
        assert len(df) == 0

    def test_args(self, mock_streamlit, temp_cache_dir, sample_plot3d_data):
        args = self._plot(sample_plot3d_data, temp_cache_dir)._get_component_args()
        assert args["componentType"] == "Plotly3D"
        assert args["selectionTitles"] == [
            ["mass", "Mass signals"],
            ["scan", "Precursor signals"],
        ]

    def test_invalid_mode(self, mock_streamlit, temp_cache_dir, sample_plot3d_data):
        with pytest.raises(ValueError, match="mode"):
            Plot3D(
                cache_id="bad",
                data=sample_plot3d_data,
                x_column="mass",
                y_column="charge",
                z_column="intensity",
                mode="bars",
                cache_path=str(temp_cache_dir),
            )


class TestDeconvolvedSpectrum:
    def test_one_spectrum_per_scan(
        self, mock_streamlit, temp_cache_dir, sample_deconvolved_spectra
    ):
        spectrum = DeconvolvedSpectrum(
            cache_id="anno",
            data=sample_deconvolved_spectra,
            filters={"scan": "scan_idx"},
            mass_identifier="mass",
            view="annotated",
            float_precision="float64",
            cache_path=str(temp_cache_dir),
        )
        # Selecting a mass must not invalidate the cached spectrum
        assert spectrum.get_state_dependencies() == ["scan"]
        df = spectrum._prepare_vue_data({"scan": 0, "mass": 1})["plotData"]
        assert len(df) == 1
        assert list(df["MonoMass"][0]) == [1000.0, 2000.123456]
        assert len(spectrum._prepare_vue_data({})["plotData"]) == 0

        args = spectrum._get_component_args()
        assert args["title"] == "Annotated Spectrum"
        assert args["massIdentifier"] == "mass"
        assert args["ladder"] is None

    def test_ladder(self, mock_streamlit, temp_cache_dir, sample_deconvolved_spectra):
        spectrum = DeconvolvedSpectrum(
            cache_id="augmented",
            data=sample_deconvolved_spectra,
            filters={"scan": "scan_idx"},
            view="augmented",
            cache_path=str(temp_cache_dir),
        )
        spectrum.set_ladder([1000, 1057.02], "G", selected_index=0, key=7)
        assert spectrum._get_component_args()["ladder"] == {
            "masses": [1000.0, 1057.02],
            "sequence": "G",
            "selectedIndex": 0,
            "key": 7,
        }
        spectrum.set_ladder(None)
        assert spectrum._get_component_args()["ladder"] is None

    def test_deconvolved_view_needs_no_peaks(self, mock_streamlit, temp_cache_dir):
        data = pl.LazyFrame(
            {"scan_idx": [0], "MonoMass": [[1.0]], "SumIntensity": [[2.0]]}
        )
        DeconvolvedSpectrum(
            cache_id="deconv",
            data=data,
            filters={"scan": "scan_idx"},
            cache_path=str(temp_cache_dir),
        )
        with pytest.raises(ValueError, match="not found"):
            DeconvolvedSpectrum(
                cache_id="anno_missing",
                data=data,
                filters={"scan": "scan_idx"},
                view="annotated",
                cache_path=str(temp_cache_dir),
            )

    def test_invalid_view(self, mock_streamlit, temp_cache_dir):
        with pytest.raises(ValueError, match="view"):
            DeconvolvedSpectrum(
                cache_id="bad",
                data=pl.LazyFrame({"MonoMass": [[1.0]], "SumIntensity": [[1.0]]}),
                view="raw",
                cache_path=str(temp_cache_dir),
            )


class TestProteoformSequenceView:
    def test_selected_proteoform(
        self, mock_streamlit, temp_cache_dir, sample_proteoform_data
    ):
        view = ProteoformSequenceView(
            cache_id="seq",
            data=sample_proteoform_data,
            filters={"protein": "proteoform_index"},
            mass_identifier="mass",
            aa_identifier="aa",
            cache_path=str(temp_cache_dir),
        )
        assert view.get_state_dependencies() == ["protein"]

        data = view._prepare_vue_data({"protein": 1})
        assert data["sequenceData"]["sequence"] == list("ACDK")
        assert data["sequenceData"]["proteoform_end"] == -1
        assert data["spectrumData"] == {"masses": [72.04], "precursorMass": 435.2}
        # Spectrum columns are not part of the proteoform
        assert "MonoMass" not in data["sequenceData"]
        # The payload is valid JSON (NaN replaced)
        json.dumps(data, allow_nan=False)

        nan_row = view._prepare_vue_data({"protein": 0})["sequenceData"]
        assert nan_row["computed_mass"] is None

        empty = view._prepare_vue_data({})
        assert empty["sequenceData"] is None and empty["spectrumData"] is None
        assert empty["_hash"] != data["_hash"]

    def test_fixed_sequence(self, mock_streamlit, temp_cache_dir):
        spectra = pl.LazyFrame(
            {
                "scan_idx": [0, 1],
                "MonoMass": [[1.0, 2.0], [3.0]],
                "PrecursorMass": [500.0, 0.0],
            }
        )
        sequence = {
            "sequence": list("PEP"),
            "theoretical_mass": 311.15,
            "fragment_masses_b": [[98.06], [227.1], [float("nan")]],
        }
        view = ProteoformSequenceView(
            cache_id="seq_fixed",
            data=spectra,
            filters={"scan": "scan_idx"},
            sequence=sequence,
            sequence_identifier="sequence",
            cache_path=str(temp_cache_dir),
        )
        data = view._prepare_vue_data({"scan": 1})
        assert data["sequenceData"]["sequence"] == list("PEP")
        assert data["sequenceData"]["fragment_masses_b"][2] == [None]
        assert data["spectrumData"]["masses"] == [3.0]

        # The sequence is part of the configuration: a new one rebuilds the cache
        other = ProteoformSequenceView(
            cache_id="seq_fixed",
            data=spectra,
            filters={"scan": "scan_idx"},
            sequence={"sequence": list("AAA")},
            cache_path=str(temp_cache_dir),
        )
        assert other._prepare_vue_data({"scan": 1})["sequenceData"]["sequence"] == [
            "A",
            "A",
            "A",
        ]
        restored = ProteoformSequenceView(
            cache_id="seq_fixed", cache_path=str(temp_cache_dir)
        )
        assert restored._prepare_vue_data({"scan": 0})["sequenceData"]["sequence"] == [
            "A",
            "A",
            "A",
        ]

    def test_args_and_tag(self, mock_streamlit, temp_cache_dir, sample_proteoform_data):
        view = ProteoformSequenceView(
            cache_id="seq_args",
            data=sample_proteoform_data,
            filters={"protein": "proteoform_index"},
            aa_identifier="aa",
            settings={"tolerance": 10, "ion_types": ["b", "y"]},
            cache_path=str(temp_cache_dir),
        )
        args = view._get_component_args()
        assert args["componentType"] == "ProteoformSequenceView"
        assert args["sequenceIdentifier"] is None
        assert args["settings"] == {"tolerance": 10, "ion_types": ["b", "y"]}
        assert args["tag"] is None
        view.set_tag(2, 5)
        assert view._get_component_args()["tag"] == {"startPos": 2, "endPos": 5}
        view.set_tag(None)
        assert view._get_component_args()["tag"] is None

    def test_requires_sequence(self, mock_streamlit, temp_cache_dir):
        with pytest.raises(ValueError, match="sequence"):
            ProteoformSequenceView(
                cache_id="noseq",
                data=pl.LazyFrame({"MonoMass": [[1.0]], "PrecursorMass": [1.0]}),
                cache_path=str(temp_cache_dir),
            )

    def test_masses_keep_full_precision(self, mock_streamlit, temp_cache_dir):
        data = pl.LazyFrame(
            {
                "proteoform_index": [0],
                "sequence": [["A"]],
                "MonoMass": [[12345.678901]],
                "PrecursorMass": [12345.678901],
            }
        )
        view = ProteoformSequenceView(
            cache_id="seq_precision",
            data=data,
            filters={"protein": "proteoform_index"},
            cache_path=str(temp_cache_dir),
        )
        masses = view._prepare_vue_data({"protein": 0})["spectrumData"]["masses"]
        assert math.isclose(masses[0], 12345.678901, abs_tol=1e-9)


def test_table_navigation_uses_render_state_manager():
    """Navigation state goes to the manager the table is rendered with, and
    only for the duration of that render."""
    from openms_insight.core.state import (
        _render_state_manager,
        get_default_state_manager,
        get_render_state_manager,
    )

    own = object()
    assert get_render_state_manager() is get_default_state_manager()
    token = _render_state_manager.set(own)
    try:
        assert get_render_state_manager() is own
    finally:
        _render_state_manager.reset(token)
    assert get_render_state_manager() is get_default_state_manager()


def test_table_default_row_minus_one_selects_nothing(
    mock_streamlit, temp_cache_dir: Path, sample_table_data
):
    """default_row=-1 means no automatic selection, also when filters change."""
    from openms_insight import Table

    kwargs = {
        "data": sample_table_data,
        "cache_path": str(temp_cache_dir),
        "filters": {"spectrum": "scan_id"},
        "interactivity": {"peak": "id"},
        "index_field": "id",
    }
    none = Table(cache_id="none", default_row=-1, **kwargs)
    assert none._prepare_vue_data({"spectrum": 200})["_auto_selection"] == {}
    first = Table(cache_id="first", **kwargs)
    assert first._prepare_vue_data({"spectrum": 200})["_auto_selection"] == {"peak": 3}
