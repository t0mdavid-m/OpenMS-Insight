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


# --------------------------------------------------------------------------- #
# Precursor cross-scan lookup (FLASHApp getPrecursorSignal parity)
# --------------------------------------------------------------------------- #


@pytest.fixture
def sample_precursor_data() -> pl.LazyFrame:
    """MS1 precursor scan + MS2 product scan with the four precursor columns.

    Real (file) scan numbers live in ``Scan``; the deconv row index lives in
    ``index``. Scan 100 is the MS1 precursor (PrecursorScan=0). Scan 101 is the
    MS2 product whose PrecursorScan points at 100 and whose PrecursorMass (999.0)
    matches MonoMass index 1 of scan 100.

    Scan 100 (MS1, index 0):
        MonoMass = [500.0, 999.0]
        mass 0 signal: [(0, 250.0, 1000.0, 2)]   noisy: [(1, 251.0, 40.0, 2)]
        mass 1 signal: [(0, 333.0, 2000.0, 3),    noisy: [(2, 334.0, 60.0, 3)]
                        (1, 499.5, 1800.0, 2)]
    Scan 101 (MS2, index 1):
        MonoMass = [123.0]
        PrecursorScan = 100, PrecursorMass = 999.0
        (its own peaks should NOT be drawn for the precursor-signal view)
    """
    return pl.LazyFrame(
        {
            "index": [0, 1],
            "Scan": [100, 101],
            "PrecursorScan": [0, 100],
            "PrecursorMass": [0.0, 999.0],
            "MonoMass": [[500.0, 999.0], [123.0]],
            "SignalPeaks": [
                [
                    [_record(0, 250.0, 1000.0, 2)],
                    [_record(0, 333.0, 2000.0, 3), _record(1, 499.5, 1800.0, 2)],
                ],
                [
                    [_record(0, 61.5, 500.0, 2)],
                ],
            ],
            "NoisyPeaks": [
                [
                    [_record(1, 251.0, 40.0, 2)],
                    [_record(2, 334.0, 60.0, 3)],
                ],
                [
                    [_record(1, 62.0, 10.0, 2)],
                ],
            ],
        }
    )


def _make_precursor(data, temp_cache_dir, cache_id):
    return Scatter3D(
        cache_id=cache_id,
        data=data,
        cache_path=str(temp_cache_dir),
        scan_filter="index",
        scan_column="Scan",
        precursor_scan_column="PrecursorScan",
        precursor_mass_column="PrecursorMass",
        mono_mass_column="MonoMass",
    )


def test_precursor_lookup_ms2_resolves_precursor_mass(
    mock_streamlit, temp_cache_dir, sample_precursor_data
):
    comp = _make_precursor(sample_precursor_data, temp_cache_dir, "prec_ms2")
    # Select the MS2 scan (index 1), no mass -> resolve precursor scan 100's mass 1.
    result = comp._prepare_vue_data({"scanIndex": 1})
    payload = result["scatter3dData"]
    assert payload["hasSelection"] is True
    # Title stays "Precursor signals"
    assert payload["massSelected"] is False
    # Should be scan 100 mass-1's peaks (flat per-peak list -> number[][]), NOT the
    # MS2 scan's own peaks.
    assert payload["signalPeaks"] is not None
    assert len(payload["signalPeaks"]) == 2
    assert payload["signalPeaks"][0][1] == pytest.approx(333.0)
    assert payload["signalPeaks"][1][1] == pytest.approx(499.5)
    assert len(payload["noisyPeaks"]) == 1
    assert payload["noisyPeaks"][0][1] == pytest.approx(334.0)


def test_precursor_lookup_ms1_blank(
    mock_streamlit, temp_cache_dir, sample_precursor_data
):
    comp = _make_precursor(sample_precursor_data, temp_cache_dir, "prec_ms1")
    # Selecting the MS1 scan (index 0, PrecursorScan == 0) -> blank scene.
    result = comp._prepare_vue_data({"scanIndex": 0})
    payload = result["scatter3dData"]
    assert payload["hasSelection"] is True
    assert payload["massSelected"] is False
    assert payload["signalPeaks"] is None
    assert payload["noisyPeaks"] is None


def test_precursor_lookup_no_mass_match_blank(mock_streamlit, temp_cache_dir):
    # MS2 PrecursorMass has no MonoMass match in the precursor scan -> blank.
    data = pl.LazyFrame(
        {
            "index": [0, 1],
            "Scan": [100, 101],
            "PrecursorScan": [0, 100],
            "PrecursorMass": [0.0, 888.0],  # no match in [500.0, 999.0]
            "MonoMass": [[500.0, 999.0], [123.0]],
            "SignalPeaks": [
                [[_record(0, 250.0, 1000.0, 2)], [_record(0, 333.0, 2000.0, 3)]],
                [[_record(0, 61.5, 500.0, 2)]],
            ],
            "NoisyPeaks": [
                [[], []],
                [[]],
            ],
        }
    )
    comp = _make_precursor(data, temp_cache_dir, "prec_nomatch")
    payload = comp._prepare_vue_data({"scanIndex": 1})["scatter3dData"]
    assert payload["signalPeaks"] is None
    assert payload["noisyPeaks"] is None


def test_precursor_lookup_missing_precursor_row_blank(mock_streamlit, temp_cache_dir):
    # MS2 points to a PrecursorScan that doesn't exist -> blank.
    data = pl.LazyFrame(
        {
            "index": [0],
            "Scan": [101],
            "PrecursorScan": [100],  # no row with Scan == 100
            "PrecursorMass": [999.0],
            "MonoMass": [[123.0]],
            "SignalPeaks": [[[_record(0, 61.5, 500.0, 2)]]],
            "NoisyPeaks": [[[]]],
        }
    )
    comp = _make_precursor(data, temp_cache_dir, "prec_missingrow")
    payload = comp._prepare_vue_data({"scanIndex": 0})["scatter3dData"]
    assert payload["signalPeaks"] is None


def test_precursor_lookup_mass_selected_uses_own_scan(
    mock_streamlit, temp_cache_dir, sample_precursor_data
):
    # When a mass IS selected, precursor lookup is bypassed: subscript the
    # SELECTED scan's own per-mass arrays (legacy mass-signal behavior).
    comp = _make_precursor(sample_precursor_data, temp_cache_dir, "prec_mass")
    payload = comp._prepare_vue_data({"scanIndex": 0, "massIndex": 1})["scatter3dData"]
    assert payload["massSelected"] is True
    # scan 100 (index 0) mass 1 own peaks
    assert len(payload["signalPeaks"]) == 2
    assert payload["signalPeaks"][0][1] == pytest.approx(333.0)


def test_precursor_lookup_disabled_without_columns(
    mock_streamlit, temp_cache_dir, sample_precursor_data
):
    # Without the precursor columns wired, behavior falls back to own-scan peaks.
    comp = Scatter3D(
        cache_id="prec_disabled",
        data=sample_precursor_data,
        cache_path=str(temp_cache_dir),
        scan_filter="index",
    )
    assert comp._precursor_lookup_enabled() is False
    payload = comp._prepare_vue_data({"scanIndex": 1})["scatter3dData"]
    # MS2 scan's OWN nested per-mass peaks (number[][][]) returned, not precursor.
    assert payload["signalPeaks"] is not None
    assert payload["signalPeaks"][0][0][1] == pytest.approx(61.5)


def test_precursor_partial_columns_raises(mock_streamlit, temp_cache_dir):
    # Configuring only some of the four precursor columns is a wiring error.
    data = pl.LazyFrame(
        {
            "index": [0],
            "Scan": [100],
            "SignalPeaks": [[[_record(0, 1.0, 2.0, 1.0)]]],
            "NoisyPeaks": [[[]]],
        }
    )
    with pytest.raises(ValueError, match="all four columns"):
        Scatter3D(
            cache_id="prec_partial",
            data=data,
            cache_path=str(temp_cache_dir),
            scan_column="Scan",  # only one of four
        )


def test_precursor_lookup_cache_reconstruction(
    mock_streamlit, temp_cache_dir, sample_precursor_data
):
    cache_id = "prec_recon"
    _make_precursor(sample_precursor_data, temp_cache_dir, cache_id)
    comp2 = Scatter3D(cache_id=cache_id, cache_path=str(temp_cache_dir))
    # Config restored from cache -> precursor lookup still active.
    assert comp2._scan_column == "Scan"
    assert comp2._precursor_scan_column == "PrecursorScan"
    payload = comp2._prepare_vue_data({"scanIndex": 1})["scatter3dData"]
    assert payload["signalPeaks"][0][1] == pytest.approx(333.0)
