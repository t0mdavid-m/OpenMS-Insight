"""Unit tests for the Scatter3D component (FLASHApp Plotly3Dplot parity).

Covers the Scatter3D.md verification checklist (functionality slice):
- scanIndex value filter selects the row where index == scanIndex
- empty/None scanIndex -> blank payload
- massIndex array subscript into per-mass SignalPeaks/NoisyPeaks (out-of-range -> None)
- get_state_dependencies() == {'scanIndex', 'massIndex'}
- _prepare_vue_data returns dict with string _hash (bridge contract)
- cache reconstruction round-trip
"""

import polars as pl
import pytest

from openms_insight.components.scatter3d import Scatter3D


def _record(peak_index, mz, intensity, charge):
    """A peak record matches masstable.py:252 -> (peak_index, mz, intensity, charge)."""
    return [float(peak_index), float(mz), float(intensity), float(charge)]


@pytest.fixture
def sample_scatter3d_data() -> pl.LazyFrame:
    """One row per scan with nested per-mass SignalPeaks/NoisyPeaks.

    scan index 10:
        mass 0: signal peaks [(0, 500.0, 1000.0, 2), (1, 750.0, 800.0, 2)]
                noisy  peaks [(2, 510.0, 50.0, 2)]
        mass 1: signal peaks [(0, 300.0, 2000.0, 3)]
                noisy  peaks []
    scan index 20:
        mass 0: signal peaks [(0, 400.0, 1500.0, 1)]
                noisy  peaks [(1, 410.0, 30.0, 1)]
    """
    return pl.LazyFrame(
        {
            "index": [10, 20],
            "PrecursorScan": [0, 0],
            "SignalPeaks": [
                # scan 10: two masses
                [
                    [_record(0, 500.0, 1000.0, 2), _record(1, 750.0, 800.0, 2)],
                    [_record(0, 300.0, 2000.0, 3)],
                ],
                # scan 20: one mass
                [
                    [_record(0, 400.0, 1500.0, 1)],
                ],
            ],
            "NoisyPeaks": [
                [
                    [_record(2, 510.0, 50.0, 2)],
                    [],
                ],
                [
                    [_record(1, 410.0, 30.0, 1)],
                ],
            ],
        }
    )


def _make(component_data, temp_cache_dir, cache_id="test_scatter3d"):
    return Scatter3D(
        cache_id=cache_id,
        data=component_data,
        cache_path=str(temp_cache_dir),
    )


def test_state_dependencies(mock_streamlit, temp_cache_dir, sample_scatter3d_data):
    comp = _make(sample_scatter3d_data, temp_cache_dir, "deps")
    assert set(comp.get_state_dependencies()) == {"scanIndex", "massIndex"}


def test_vue_component_name_and_data_key(
    mock_streamlit, temp_cache_dir, sample_scatter3d_data
):
    comp = _make(sample_scatter3d_data, temp_cache_dir, "names")
    assert comp._get_vue_component_name() == "Plotly3DScatter"
    assert comp._get_data_key() == "scatter3dData"


def test_prepare_vue_data_returns_dict_with_hash(
    mock_streamlit, temp_cache_dir, sample_scatter3d_data
):
    comp = _make(sample_scatter3d_data, temp_cache_dir, "hash")
    result = comp._prepare_vue_data({"scanIndex": 10})
    assert isinstance(result, dict)
    assert isinstance(result.get("_hash"), str)
    assert "scatter3dData" in result


def test_empty_scan_index_blank(mock_streamlit, temp_cache_dir, sample_scatter3d_data):
    comp = _make(sample_scatter3d_data, temp_cache_dir, "blank")
    # No scanIndex at all
    result = comp._prepare_vue_data({})
    payload = result["scatter3dData"]
    assert payload["hasSelection"] is False
    assert payload["signalPeaks"] is None
    assert payload["noisyPeaks"] is None

    # Explicit None scanIndex
    result_none = comp._prepare_vue_data({"scanIndex": None})
    assert result_none["scatter3dData"]["hasSelection"] is False


def test_scan_index_selects_correct_row(
    mock_streamlit, temp_cache_dir, sample_scatter3d_data
):
    comp = _make(sample_scatter3d_data, temp_cache_dir, "scan")
    result = comp._prepare_vue_data({"scanIndex": 10})
    payload = result["scatter3dData"]

    assert payload["hasSelection"] is True
    assert payload["massSelected"] is False
    # scan 10 has two masses in SignalPeaks
    assert len(payload["signalPeaks"]) == 2
    # mass 0 first peak record: (0, 500.0, 1000.0, 2)
    rec = payload["signalPeaks"][0][0]
    assert rec[1] == pytest.approx(500.0)
    assert rec[2] == pytest.approx(1000.0)
    assert rec[3] == pytest.approx(2.0)
    # noisy peaks preserved (mass 0 has 1 noisy peak, mass 1 has none)
    assert len(payload["noisyPeaks"]) == 2
    assert len(payload["noisyPeaks"][0]) == 1
    assert len(payload["noisyPeaks"][1]) == 0


def test_scan_index_other_row(mock_streamlit, temp_cache_dir, sample_scatter3d_data):
    comp = _make(sample_scatter3d_data, temp_cache_dir, "scan20")
    result = comp._prepare_vue_data({"scanIndex": 20})
    payload = result["scatter3dData"]
    assert payload["hasSelection"] is True
    assert len(payload["signalPeaks"]) == 1
    assert payload["signalPeaks"][0][0][1] == pytest.approx(400.0)


def test_scan_index_not_found(mock_streamlit, temp_cache_dir, sample_scatter3d_data):
    comp = _make(sample_scatter3d_data, temp_cache_dir, "missing")
    result = comp._prepare_vue_data({"scanIndex": 999})
    payload = result["scatter3dData"]
    # selection present but no matching row -> arrays None
    assert payload["hasSelection"] is True
    assert payload["signalPeaks"] is None
    assert payload["noisyPeaks"] is None


def test_mass_index_subscript(mock_streamlit, temp_cache_dir, sample_scatter3d_data):
    comp = _make(sample_scatter3d_data, temp_cache_dir, "mass")
    # scan 10, mass 0 -> isolate first mass's peak set
    result = comp._prepare_vue_data({"scanIndex": 10, "massIndex": 0})
    payload = result["scatter3dData"]
    assert payload["massSelected"] is True
    # After subscript, signalPeaks is the per-peak list of mass 0 (2 peaks)
    assert len(payload["signalPeaks"]) == 2
    assert payload["signalPeaks"][0][1] == pytest.approx(500.0)
    assert payload["signalPeaks"][1][1] == pytest.approx(750.0)
    # noisy peaks of mass 0 -> 1 peak
    assert len(payload["noisyPeaks"]) == 1
    assert payload["noisyPeaks"][0][1] == pytest.approx(510.0)

    # scan 10, mass 1 -> single signal peak, empty noisy
    result1 = comp._prepare_vue_data({"scanIndex": 10, "massIndex": 1})
    p1 = result1["scatter3dData"]
    assert len(p1["signalPeaks"]) == 1
    assert p1["signalPeaks"][0][1] == pytest.approx(300.0)
    assert p1["noisyPeaks"] == []


def test_mass_index_out_of_range(mock_streamlit, temp_cache_dir, sample_scatter3d_data):
    comp = _make(sample_scatter3d_data, temp_cache_dir, "oor")
    # scan 10 has 2 masses; massIndex 5 is out of range -> None (mirror update.py)
    result = comp._prepare_vue_data({"scanIndex": 10, "massIndex": 5})
    payload = result["scatter3dData"]
    assert payload["massSelected"] is True
    assert payload["signalPeaks"] is None
    assert payload["noisyPeaks"] is None


def test_hash_changes_with_selection(
    mock_streamlit, temp_cache_dir, sample_scatter3d_data
):
    comp = _make(sample_scatter3d_data, temp_cache_dir, "hashchange")
    h_blank = comp._prepare_vue_data({})["_hash"]
    h_scan = comp._prepare_vue_data({"scanIndex": 10})["_hash"]
    h_mass = comp._prepare_vue_data({"scanIndex": 10, "massIndex": 0})["_hash"]
    assert len({h_blank, h_scan, h_mass}) == 3


def test_component_args(mock_streamlit, temp_cache_dir, sample_scatter3d_data):
    comp = _make(sample_scatter3d_data, temp_cache_dir, "args")
    args = comp._get_component_args()
    assert args["componentType"] == "Plotly3DScatter"
    assert args["signalColor"] == "#3366CC"
    assert args["noiseColor"] == "#DC3912"
    assert args["height"] == 800


def test_cache_reconstruction(mock_streamlit, temp_cache_dir, sample_scatter3d_data):
    cache_id = "recon"
    # Build once to populate the on-disk cache, then reconstruct from it.
    _make(sample_scatter3d_data, temp_cache_dir, cache_id)
    # Reconstruct from cache (no data)
    comp2 = Scatter3D(cache_id=cache_id, cache_path=str(temp_cache_dir))
    assert comp2._get_vue_component_name() == "Plotly3DScatter"
    assert set(comp2.get_state_dependencies()) == {"scanIndex", "massIndex"}
    result = comp2._prepare_vue_data({"scanIndex": 20})
    payload = result["scatter3dData"]
    assert payload["hasSelection"] is True
    assert payload["signalPeaks"][0][0][1] == pytest.approx(400.0)


def test_validation_missing_column(mock_streamlit, temp_cache_dir):
    bad = pl.LazyFrame({"index": [1], "SignalPeaks": [[[[0.0, 1.0, 2.0, 1.0]]]]})
    with pytest.raises(ValueError, match="noisy_column"):
        Scatter3D(
            cache_id="badcol",
            data=bad,
            cache_path=str(temp_cache_dir),
        )
