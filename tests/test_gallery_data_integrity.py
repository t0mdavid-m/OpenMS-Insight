"""What each gallery page draws must be what its source table actually holds.

``test_gallery_pages.py`` proves the pages run and ``test_gallery_render.py`` proves
they paint. Neither looks at the numbers, so a page could render a beautiful plot of
the wrong rows -- a filter that silently matches nothing, a downsampler that invents
coordinates, a matrix reordered by clustering into the wrong cells -- and every test
would still pass.

This module captures the payload each page actually hands to Vue (by standing in for
the Streamlit custom component and recording its arguments) and compares it against
the Parquet in ``gallery/data``, recomputed here rather than taken on trust.

Floats arrive as Float32: the cache downcasts Float64 on write. The comparison casts
the source the same way and then demands exact equality, so a real discrepancy cannot
hide behind a tolerance.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest.mock import patch

import numpy as np
import pandas as pd
import polars as pl
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
GALLERY_DIR = REPO_ROOT / "gallery"
CONTENT_DIR = GALLERY_DIR / "content"
DATA_DIR = GALLERY_DIR / "data"

pytest.importorskip("streamlit.testing.v1", reason="requires Streamlit's test harness")

PAGES = sorted(p.stem for p in CONTENT_DIR.glob("*.py") if p.stem != "home")


def source(name: str) -> pl.DataFrame:
    """A table from the committed example dataset."""
    return pl.read_parquet(DATA_DIR / f"{name}.parquet")


def as_cached(frame: pl.DataFrame) -> pl.DataFrame:
    """The frame as the cache stores it: Float64 downcast to Float32."""
    return frame.with_columns(
        pl.col(name).cast(pl.Float32)
        for name, dtype in frame.schema.items()
        if dtype == pl.Float64
    )


def assert_equals_source(
    shown: pd.DataFrame,
    expected: pl.DataFrame,
    *,
    key: str | None = None,
    ordered: bool = True,
) -> None:
    """Every value drawn is the value stored, for every column the two share.

    ``ordered`` is on by default because payload order is display order -- a table's
    page or a spectrum's peaks appear as sent. VolcanoPlot is the exception: it groups
    its rows into significance traces, so there ``key`` carries the identity instead.
    """
    expected = as_cached(expected)
    shared = [column for column in shown.columns if column in expected.columns]
    assert shown.shape[0] == expected.height, (
        f"payload has {shown.shape[0]} rows, source has {expected.height}"
    )
    assert shared, "payload and source share no columns"

    drawn = pl.from_pandas(shown[shared])
    if key is not None:
        merged = drawn.join(expected.select(shared), on=key, how="inner", suffix="_src")
        assert merged.height == drawn.height, f"{key} values missing from the source"
        for column in shared:
            if column == key:
                continue
            assert (merged[column] == merged[f"{column}_src"]).all(), (
                f"{column} differs from the source"
            )
        if ordered:
            assert drawn[key].to_list() == expected[key].to_list(), (
                f"rows are drawn in a different order than {key} in the source"
            )
    else:
        assert ordered, "an unordered comparison needs a key column"
        for column in shared:
            assert (drawn[column] == expected[column]).all(), (
                f"{column} differs from the source"
            )


@pytest.fixture(scope="module", autouse=True)
def _gallery_importable():
    """Put the gallery on sys.path so `from src import dataset` resolves."""
    added = str(GALLERY_DIR) not in sys.path
    if added:
        sys.path.insert(0, str(GALLERY_DIR))
    yield
    if added:
        sys.path.remove(str(GALLERY_DIR))


def _recording_into(sink: list[dict[str, Any]]) -> Callable[[], Callable[..., None]]:
    """Stand in for the Streamlit custom component and keep what it was handed.

    Returning ``None`` is what a real component returns before the browser has
    answered, so the bridge takes its usual first-render path.
    """

    def recorder(**kwargs: Any) -> None:
        sink.append(kwargs)

    return lambda: recorder


@pytest.fixture(scope="module")
def payloads(tmp_path_factory) -> dict[str, list[dict[str, Any]]]:
    """Run every page and record what it sends to Vue.

    One module-scoped run: preprocessing the 608k-point MS1 map is the expensive part
    and every page after the first reuses the cache it builds.
    """
    from streamlit.testing.v1 import AppTest

    cache_dir = tmp_path_factory.mktemp("gallery_cache")
    original_cwd = Path.cwd()
    os.chdir(cache_dir)

    captured: dict[str, list[dict[str, Any]]] = {}
    try:
        for page in PAGES:
            calls: list[dict[str, Any]] = []

            # AppTest runs the page as __main__; restore it so the spawn-based
            # subprocess tests do not re-import a Streamlit page as their entry point.
            original_main = sys.modules.get("__main__")
            with patch(
                "openms_insight.rendering.bridge.get_vue_component_function",
                _recording_into(calls),
            ):
                app = AppTest.from_file(
                    str(CONTENT_DIR / f"{page}.py"), default_timeout=600
                )
                app.run()
            if original_main is not None:
                sys.modules["__main__"] = original_main

            assert not app.exception, f"{page} raised: " + "; ".join(
                str(e.value) for e in app.exception
            )
            captured[page] = calls
    finally:
        os.chdir(original_cwd)
    return captured


def payload_of(
    payloads: dict[str, list[dict[str, Any]]],
    page: str,
    component_type: str,
    data_key: str,
) -> dict[str, Any]:
    """The last payload one page sent for one component, once it carried data.

    The bridge renders in two phases -- the first pass has nothing cached to send --
    so the payload worth checking is the last one.
    """
    for call in reversed(payloads[page]):
        args = call["components"][0][0]["componentArgs"]
        if args.get("componentType") == component_type and data_key in call:
            return call
    raise AssertionError(f"{page} never sent {data_key} for {component_type}")


class TestSourceTables:
    """The dataset the pages document is the dataset on disk."""

    def test_manifest_lists_exactly_the_committed_tables(self) -> None:
        from src import dataset  # noqa: PLC0415 - needs the gallery on sys.path

        listed = set(dataset.manifest()["tables"])
        on_disk = {
            str(path.relative_to(DATA_DIR)).replace("\\", "/")
            for path in DATA_DIR.rglob("*.parquet")
        }
        assert listed == on_disk

    @pytest.mark.parametrize(
        "name",
        sorted(
            str(p.relative_to(DATA_DIR)).replace("\\", "/")
            for p in DATA_DIR.rglob("*.parquet")
        ),
    )
    def test_manifest_row_and_column_counts_are_real(self, name: str) -> None:
        from src import dataset  # noqa: PLC0415

        info = dataset.table_info(name)
        frame = pl.read_parquet(DATA_DIR / name)
        assert info["rows"] == frame.height
        assert list(info["columns"]) == frame.columns

    @pytest.mark.parametrize("page", PAGES)
    def test_every_previewed_table_resolves(self, page: str) -> None:
        """A page's ``tables=`` entries must name real manifest keys.

        A name that misses the manifest still renders, silently, with an empty
        description and an unknown provenance line.
        """
        import ast

        from src import dataset  # noqa: PLC0415

        tree = ast.parse((CONTENT_DIR / f"{page}.py").read_text(encoding="utf-8"))
        declared: list[str] = []
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and getattr(node.func, "attr", "") == "render"
            ):
                for keyword in node.keywords:
                    if keyword.arg == "tables":
                        declared = [element.value for element in keyword.value.elts]
        for name in declared:
            assert dataset.table_info(name), f"{page} previews unknown table {name}"
            assert Path(dataset.data(name)).exists()


class TestTable:
    def test_page_shows_the_first_page_of_scans(self, payloads) -> None:
        call = payload_of(payloads, "table", "TabulatorTable", "tableData")
        scans = source("flashdeconv/scans")
        pagination = call["_pagination"]

        assert pagination["total_rows"] == scans.height
        assert pagination["total_pages"] == -(-scans.height // pagination["page_size"])
        assert_equals_source(
            call["tableData"], scans.slice(0, pagination["page_size"]), key="scan_id"
        )

    def test_column_filter_ranges_come_from_the_data(self, payloads) -> None:
        """Tabulator's filter controls advertise these bounds to the user."""
        call = payload_of(payloads, "table", "TabulatorTable", "tableData")
        scans = source("flashdeconv/scans")

        for column, info in call["components"][0][0]["componentArgs"][
            "columnMetadata"
        ].items():
            if info["type"] == "numeric":
                assert info["min"] == pytest.approx(
                    float(scans[column].min()), abs=0.01
                )
                assert info["max"] == pytest.approx(
                    float(scans[column].max()), abs=0.01
                )
            else:
                assert sorted(info["unique_values"]) == sorted(
                    scans[column].unique().to_list()
                )


class TestLinePlot:
    def test_plot_holds_exactly_the_filtered_scan(self, payloads) -> None:
        call = payload_of(payloads, "lineplot", "PlotlyLineplotUnified", "plotData")
        shown = call["plotData"]

        assert set(shown["scan_id"]) == {3371}
        assert_equals_source(
            shown,
            source("flashdeconv/deconv_peaks").filter(pl.col("scan_id") == 3371),
            key="peak_id",
        )


class TestMirrorPlot:
    @pytest.mark.parametrize(("side", "scan"), [("Top", 3371), ("Bottom", 3373)])
    def test_each_half_holds_its_own_scan(self, payloads, side: str, scan: int) -> None:
        call = payload_of(payloads, "mirrorplot", "PlotlyMirrorPlot", "plotDataTop")
        shown = call[f"plotData{side}"]

        assert set(shown["scan_id"]) == {scan}
        assert_equals_source(
            shown,
            source("flashdeconv/deconv_peaks").filter(pl.col("scan_id") == scan),
            key="peak_id",
        )

    def test_the_flip_is_a_rendering_detail(self, payloads) -> None:
        """Both halves are cached positive; the y-axis flip happens in the browser."""
        call = payload_of(payloads, "mirrorplot", "PlotlyMirrorPlot", "plotDataTop")

        assert (call["plotDataTop"]["intensity"] > 0).all()
        assert (call["plotDataBottom"]["intensity"] > 0).all()


class TestVolcanoPlot:
    def test_every_protein_keeps_its_own_numbers(self, payloads) -> None:
        call = payload_of(payloads, "volcano", "PlotlyVolcano", "volcanoData")

        assert_equals_source(
            call["volcanoData"],
            source("pxd044981/proteins"),
            key="protein_id",
            ordered=False,
        )

    def test_the_y_axis_is_the_adjusted_p_value(self, payloads) -> None:
        """The page labels the axis -log10 adjusted p, so it must not plot raw p."""
        call = payload_of(payloads, "volcano", "PlotlyVolcano", "volcanoData")
        shown = call["volcanoData"].sort_values("protein_id")
        proteins = source("pxd044981/proteins").sort("protein_id")

        expected = -np.log10(np.asarray(proteins["padj"].to_list()))
        assert shown["_neglog10_pvalue"].to_numpy() == pytest.approx(expected, abs=1e-5)


class TestHeatmap:
    @pytest.mark.parametrize("page", ["heatmap", "scale"])
    def test_every_drawn_point_is_a_real_measurement(self, payloads, page: str) -> None:
        """Downsampling selects rows; it must never synthesise a coordinate."""
        call = payload_of(payloads, page, "PlotlyHeatmap", "heatmapData")
        columns = ["rt", "mass", "intensity", "scan_id"]
        drawn = pl.from_pandas(call["heatmapData"][columns])
        ms1 = source("flashdeconv/ms1_map")

        assert drawn.join(ms1, on=columns, how="semi").height == drawn.height
        assert drawn.unique().height == drawn.height
        assert drawn.height <= ms1.height

    @pytest.mark.parametrize("page", ["heatmap", "scale"])
    def test_a_clicked_point_reports_the_scan_it_came_from(
        self, payloads, page: str
    ) -> None:
        """The identifier a click writes is only useful if it is the right one."""
        call = payload_of(payloads, page, "PlotlyHeatmap", "heatmapData")
        drawn = pl.from_pandas(call["heatmapData"][["rt", "scan_id"]])
        by_rt = source("flashdeconv/ms1_map").select(["rt", "scan_id"]).unique()

        mismatched = drawn.join(by_rt, on="rt", how="left", suffix="_src").filter(
            pl.col("scan_id") != pl.col("scan_id_src")
        )
        assert mismatched.height == 0


class TestSequenceView:
    def test_the_browser_receives_the_scan_it_was_given(self, payloads) -> None:
        call = payload_of(payloads, "sequence_view", "SequenceView", "sequenceData")
        peaks = as_cached(
            source("pxd044981/psm_peaks").filter(pl.col("scan_id") == 44672)
        )

        assert "".join(call["sequenceData"]["sequence"]) == "ILNNGHAFNVEFDDSQDK"
        assert call["precursorCharge"] == 2
        assert list(call["peakIds"]) == peaks["peak_id"].to_list()
        assert np.asarray(call["observedMasses"]) == pytest.approx(
            np.asarray(peaks["mass"].to_list()), abs=0.0
        )

    def test_theoretical_masses_are_the_peptides_own(self, payloads) -> None:
        """Fragment matching happens in the browser, on the numbers Python sends."""
        residues = {
            "G": 57.02146,
            "A": 71.03711,
            "S": 87.03203,
            "P": 97.05276,
            "V": 99.06841,
            "T": 101.04768,
            "C": 103.00919,
            "L": 113.08406,
            "I": 113.08406,
            "N": 114.04293,
            "D": 115.02694,
            "Q": 128.05858,
            "K": 128.09496,
            "E": 129.04259,
            "M": 131.04049,
            "H": 137.05891,
            "F": 147.06841,
            "R": 156.10111,
            "Y": 163.06333,
            "W": 186.07931,
        }
        water = 18.010565
        sequence = "ILNNGHAFNVEFDDSQDK"
        call = payload_of(payloads, "sequence_view", "SequenceView", "sequenceData")
        sent = call["sequenceData"]

        assert sent["theoretical_mass"] == pytest.approx(
            sum(residues[a] for a in sequence) + water, abs=0.01
        )
        # Neutral fragment masses: the browser adds protons per charge state.
        b_ions = np.cumsum([residues[a] for a in sequence])
        y_ions = np.cumsum([residues[a] for a in reversed(sequence)]) + water
        assert np.asarray([m[0] for m in sent["fragment_masses_b"]]) == pytest.approx(
            b_ions, abs=0.01
        )
        assert np.asarray([m[0] for m in sent["fragment_masses_y"]]) == pytest.approx(
            y_ions, abs=0.01
        )


class TestPCA:
    def test_points_are_the_runs_named_in_the_metadata(self, payloads) -> None:
        call = payload_of(payloads, "pca", "PlotlyPca", "pcaData")
        shown = call["pcaData"]
        matrix = source("pxd044981/quant_matrix")
        samples = source("pxd044981/samples")
        groups = dict(
            zip(samples["sample_id"].to_list(), samples["group"].to_list(), strict=True)
        )

        assert list(shown["sample_id"]) == [
            c for c in matrix.columns if c != "protein_id"
        ]
        assert [groups[s] for s in shown["sample_id"]] == list(shown["group"])

    def test_coordinates_reproduce_an_independent_pca(self, payloads) -> None:
        """Z-score each protein, then decompose -- the same thing, computed here.

        Only the magnitudes are compared: the sign of a principal component is
        arbitrary, and the component does not pin sklearn's randomised solver, so the
        scores are reproducible to about a part in a thousand rather than exactly.
        """
        call = payload_of(payloads, "pca", "PlotlyPca", "pcaData")
        shown = call["pcaData"]
        matrix = source("pxd044981/quant_matrix")
        runs = [c for c in matrix.columns if c != "protein_id"]

        values = matrix.select(runs).to_numpy().T.astype(np.float64)
        standardised = (values - values.mean(axis=0)) / values.std(axis=0, ddof=0)
        left, singular, _ = np.linalg.svd(
            standardised - standardised.mean(axis=0), full_matrices=False
        )
        scores = left * singular
        variance = singular**2 / (singular**2).sum() * 100

        for index, component in enumerate(("PC1", "PC2")):
            drawn = np.asarray(shown[component], dtype=np.float64)
            assert abs(np.corrcoef(scores[:, index], drawn)[0, 1]) > 0.999
            assert np.abs(drawn) == pytest.approx(
                np.abs(scores[:, index]), rel=0.02, abs=0.5
            )

        args = call["components"][0][0]["componentArgs"]
        for index, label in enumerate((args["xLabel"], args["yLabel"])):
            stated = float(label.split("(")[1].rstrip("%)"))
            assert stated == pytest.approx(variance[index], abs=0.1)


class TestClusteredHeatmap:
    def test_clustering_reorders_cells_without_moving_their_values(
        self, payloads
    ) -> None:
        call = payload_of(
            payloads, "clustered_heatmap", "PlotlyClusteredHeatmap", "heatmapMatrix"
        )
        args = call["components"][0][0]["componentArgs"]
        matrix = as_cached(source("pxd044981/spike_in_matrix"))
        by_protein = {row["protein_id"]: row for row in matrix.to_dicts()}
        shown = call["heatmapMatrix"].set_index("protein_id")

        assert sorted(args["rowLabels"]) == sorted(matrix["protein_id"].to_list())
        assert sorted(args["colLabels"]) == sorted(
            c for c in matrix.columns if c != "protein_id"
        )
        for protein in args["rowLabels"]:
            for run in args["colLabels"]:
                assert float(shown.loc[protein, run]) == float(by_protein[protein][run])

    def test_replicates_of_a_level_end_up_adjacent(self, payloads) -> None:
        """The page's claim: five contiguous blocks of three, from the numbers alone."""
        call = payload_of(
            payloads, "clustered_heatmap", "PlotlyClusteredHeatmap", "heatmapMatrix"
        )
        samples = source("pxd044981/samples")
        groups = dict(
            zip(samples["sample_id"].to_list(), samples["group"].to_list(), strict=True)
        )

        order = [
            groups[c] for c in call["components"][0][0]["componentArgs"]["colLabels"]
        ]
        blocks = [g for i, g in enumerate(order) if i == 0 or g != order[i - 1]]
        assert len(blocks) == len(set(order)) == 5


class TestLinkedPages:
    def test_the_spectrum_follows_the_table_selection(self, payloads) -> None:
        table = payload_of(
            payloads, "link_scan_spectrum", "TabulatorTable", "tableData"
        )
        plot = payload_of(
            payloads, "link_scan_spectrum", "PlotlyLineplotUnified", "plotData"
        )
        scans = source("flashdeconv/scans")
        selected = table["selection_store"]["scan"]

        assert_equals_source(
            table["tableData"],
            scans.slice(0, table["_pagination"]["page_size"]),
            key="scan_id",
        )
        assert selected == int(table["tableData"]["scan_id"].iloc[0])
        assert set(plot["plotData"]["scan_id"]) == {selected}
        assert_equals_source(
            plot["plotData"],
            source("flashdeconv/deconv_peaks")
            .filter(pl.col("scan_id") == selected)
            .drop("peak_id"),
        )

    @pytest.mark.parametrize(("side", "scan"), [("Top", 44672), ("Bottom", 47417)])
    def test_each_mirror_half_is_a_real_psm(
        self, payloads, side: str, scan: int
    ) -> None:
        call = payload_of(
            payloads, "link_sequence_mirror", "PlotlyMirrorPlot", "plotDataTop"
        )

        assert set(call[f"plotData{side}"]["scan_id"]) == {scan}
        assert_equals_source(
            call[f"plotData{side}"],
            source("pxd044981/psm_peaks").filter(pl.col("scan_id") == scan),
            key="peak_id",
        )

    def test_the_annotated_half_is_the_spectrum_the_sequence_view_read(
        self, payloads
    ) -> None:
        """Annotations land by peak id, so both components must see the same peaks."""
        mirror = payload_of(
            payloads, "link_sequence_mirror", "PlotlyMirrorPlot", "plotDataTop"
        )
        sequence_view = payload_of(
            payloads, "link_sequence_mirror", "SequenceView", "sequenceData"
        )

        assert list(sequence_view["peakIds"]) == list(mirror["plotDataTop"]["peak_id"])
        assert np.asarray(sequence_view["observedMasses"]) == pytest.approx(
            mirror["plotDataTop"]["mass"].to_numpy(), abs=0.0
        )
