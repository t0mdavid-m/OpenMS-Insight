"""The USI button of LinePlot and MirrorPlot: a render-time option, not part of the cache."""

import json

import polars as pl
import pytest

from openms_insight import LinePlot, MirrorPlot
from openms_insight.core.usi import usi_placeholders, validate_usi

USI = "mzspec:PXD000561:Adult_Frontalcortex_bRP_Elite_85_f09:scan:{spectrum}"


@pytest.fixture
def spectra() -> pl.LazyFrame:
    return pl.LazyFrame(
        {"scan": [1, 1], "mz": [100.0, 200.0], "intensity": [10.0, 20.0]}
    )


def _plot(spectra, cache_dir, cache_id="usi", **kwargs) -> LinePlot:
    return LinePlot(
        cache_id=cache_id,
        data=spectra,
        filters={"spectrum": "scan"},
        x_column="mz",
        y_column="intensity",
        cache_path=str(cache_dir),
        **kwargs,
    )


def _mirror(spectra, cache_dir, cache_id="mirror_usi", **kwargs) -> MirrorPlot:
    return MirrorPlot(
        cache_id=cache_id,
        data=spectra,
        filters_top={"spectrum": "scan"},
        filters_bottom={"spectrum": "scan"},
        x_column="mz",
        y_column="intensity",
        cache_path=str(cache_dir),
        **kwargs,
    )


@pytest.mark.parametrize(
    "usi",
    [
        USI,
        "mzspec:PXD000561:run:scan:17555",
        "mzspec:PXD000561:run:index:{spectrum}:{peptide}/{charge}",
        "mzspec:{collection}:{run}:nativeId:{native_id}",
        "MZSPEC:PXD000561:run:{index_type}:{spectrum}",
        "  mzspec:PXD000561:run:scan:{spectrum}  ",
    ],
)
def test_valid(usi):
    assert validate_usi(usi) == usi.strip()


@pytest.mark.parametrize(
    "usi",
    [
        "",
        "PXD000561:run:scan:1",
        "mzspec:PXD000561:run:scan",
        "mzspec:PXD000561::scan:1",
        "mzspec:PXD000561:run:spectrum:1",
        "mzspec:PXD000561:run:scan:{}",
        "mzspec:PXD000561:run:scan:{ spectrum}",
        "mzspec:PXD000561:run:scan:{spectrum",
        "mzspec:PXD000561:run:scan:spectrum}",
        42,
    ],
)
def test_invalid(usi):
    with pytest.raises(ValueError):
        validate_usi(usi)


def test_placeholders():
    assert usi_placeholders("mzspec:{c}:run:scan:{spectrum}:{p}/{z}") == [
        "c",
        "spectrum",
        "p",
        "z",
    ]


def test_lineplot_args(mock_streamlit, temp_cache_dir, spectra):
    assert "usi" not in _plot(spectra, temp_cache_dir)._get_component_args()
    args = _plot(spectra, temp_cache_dir, cache_id="on", usi=USI)._get_component_args()
    assert args["usi"] == USI
    with pytest.raises(ValueError):
        _plot(spectra, temp_cache_dir, cache_id="bad", usi="scan 5")


def test_mirrorplot_args(mock_streamlit, temp_cache_dir, spectra):
    assert "usi" not in _mirror(spectra, temp_cache_dir)._get_component_args()
    args = _mirror(
        spectra, temp_cache_dir, cache_id="mirror_on", usi=USI
    )._get_component_args()
    assert args["usi"] == USI


@pytest.mark.parametrize("build", [_plot, _mirror])
def test_not_part_of_the_cache(mock_streamlit, temp_cache_dir, spectra, build):
    off = build(spectra, temp_cache_dir, cache_id="same")
    with open(off._get_manifest_path()) as f:
        before = json.load(f)
    on = build(spectra, temp_cache_dir, cache_id="same", usi=USI)
    with open(on._get_manifest_path()) as f:
        after = json.load(f)
    assert before == after
    assert "mzspec" not in json.dumps(after)
