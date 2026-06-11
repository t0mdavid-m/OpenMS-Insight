"""Pytest configuration and shared fixtures for openms-insight tests."""

import shutil
import tempfile
from pathlib import Path
from typing import Generator
from unittest.mock import patch

import polars as pl
import pytest


class MockSessionState(dict):
    """Mock Streamlit session_state that behaves like a dict."""

    pass


@pytest.fixture
def mock_streamlit():
    """
    Mock Streamlit's session_state for testing components.

    This fixture patches st.session_state to allow testing components
    without running a full Streamlit server.
    """
    mock_session_state = MockSessionState()

    with patch("streamlit.session_state", mock_session_state):
        yield mock_session_state


@pytest.fixture
def temp_cache_dir() -> Generator[Path, None, None]:
    """Create a temporary directory for cache storage."""
    tmpdir = tempfile.mkdtemp(prefix="openms_insight_test_")
    yield Path(tmpdir)
    shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture
def sample_table_data() -> pl.LazyFrame:
    """Create sample data for Table component."""
    return pl.LazyFrame(
        {
            "id": [1, 2, 3, 4, 5],
            "scan_id": [100, 100, 200, 200, 300],
            "mass": [500.5, 600.6, 700.7, 800.8, 900.9],
            "name": ["peak_a", "peak_b", "peak_c", "peak_d", "peak_e"],
        }
    )


@pytest.fixture
def sample_lineplot_data() -> pl.LazyFrame:
    """Create sample data for LinePlot component."""
    return pl.LazyFrame(
        {
            "mass": [100.0, 200.0, 300.0, 400.0, 500.0],
            "intensity": [1000.0, 2000.0, 1500.0, 3000.0, 500.0],
            "scan_id": [1, 1, 1, 2, 2],
            "peak_id": [10, 20, 30, 40, 50],
            "annotation": ["b2", "", "y3", "", "b4"],
        }
    )


@pytest.fixture
def sample_density_data() -> pl.LazyFrame:
    """Tidy long {x, y, group} density frame (target + decoy series)."""
    return pl.LazyFrame(
        {
            "x": [0.1, 0.5, 0.9, 0.2, 0.6, 1.0],
            "y": [0.2, 1.0, 0.3, 0.1, 0.4, 0.05],
            "group": [
                "target",
                "target",
                "target",
                "decoy",
                "decoy",
                "decoy",
            ],
        }
    )


@pytest.fixture
def sample_density_data_target_only() -> pl.LazyFrame:
    """Tidy long {x, y, group} density frame with no decoy rows."""
    return pl.LazyFrame(
        {
            "x": [0.1, 0.5, 0.9],
            "y": [0.2, 1.0, 0.3],
            "group": ["target", "target", "target"],
        }
    )


@pytest.fixture
def sample_density_scores() -> pl.LazyFrame:
    """Raw scores + target/decoy label column for the kde_from path.

    Label 0 => target, label > 0 => decoy (FLASHApp TargetDecoyType convention,
    mapped to 'target'/'decoy' via target_value/decoy_value in the test).
    """
    import random

    random.seed(7)
    n = 300
    return pl.LazyFrame(
        {
            "Qscore": [random.uniform(0.0, 1.0) for _ in range(n)]
            + [random.uniform(0.0, 0.5) for _ in range(n)],
            "label": ["target"] * n + ["decoy"] * n,
        }
    )


@pytest.fixture
def TAG_PAYLOAD() -> dict:
    """A TagData payload (opaque dict carried by the 'tag' selection).

    masses are descending fragment masses matching the deconvolved MonoMass of
    scan 1 in `sample_tagger_data` (350.0, 250.0, 150.0). sequence length 3 with
    selectedAA=1 => reversedSelectedAA = (3-1) - 1 = 1.
    """
    return {
        "sequence": "ABC",
        "nTerminal": True,
        "masses": [350.0, 250.0, 150.0],
        "selectedAA": 1,
        "startPos": 0,
        "endPos": 2,
    }


@pytest.fixture
def sample_tagger_data() -> pl.LazyFrame:
    """Per-scan frame with list columns for the tagger mode.

    Scan 1 (scan_id=1) deconvolved masses [150, 250, 350], one with a multi-peak
    charge envelope for COG testing. SignalPeaks[i] is a list of
    [peak_index, mz, intensity, charge] for MonoMass[i].
    """
    return pl.LazyFrame(
        {
            "scan_id": [1, 2],
            "tag_id": [10, 20],
            "MonoMass": [
                [150.0, 250.0, 350.0],
                [100.0, 200.0],
            ],
            "SumIntensity": [
                [1000.0, 2000.0, 1500.0],
                [500.0, 800.0],
            ],
            # SignalPeaks: per-mass list of [idx, mz, intensity, charge].
            # Stored all-float (masstable schema: list_(list_(list_(float64())))).
            "SignalPeaks": [
                [
                    # mass 150.0 -> charge 12 (two peaks for COG) + charge 13
                    [
                        [0.0, 75.0, 3.0, 12.0],
                        [1.0, 75.1, 1.0, 12.0],
                        [2.0, 50.0, 2.0, 13.0],
                    ],
                    # mass 250.0 -> charge 5 single peak
                    [[3.0, 125.0, 4.0, 5.0]],
                    # mass 350.0 -> charge 7 single peak
                    [[4.0, 175.0, 6.0, 7.0]],
                ],
                [
                    [[5.0, 100.0, 1.0, 1.0]],
                    [[6.0, 200.0, 1.0, 1.0]],
                ],
            ],
            "MonoMass_Anno": [
                [75.0, 75.1, 50.0, 125.0, 175.0],
                [100.0, 200.0],
            ],
            "SumIntensity_Anno": [
                [3.0, 1.0, 2.0, 4.0, 6.0],
                [1.0, 1.0],
            ],
        }
    )


@pytest.fixture
def sample_heatmap_data() -> pl.LazyFrame:
    """Create sample data for Heatmap component."""
    import random

    random.seed(42)

    n_points = 1000
    return pl.LazyFrame(
        {
            "retention_time": [random.uniform(0, 100) for _ in range(n_points)],
            "mz": [random.uniform(100, 2000) for _ in range(n_points)],
            "intensity": [random.uniform(100, 10000) for _ in range(n_points)],
            "scan_id": [random.randint(1, 10) for _ in range(n_points)],
        }
    )


@pytest.fixture
def sample_sequence_data() -> pl.LazyFrame:
    """Create sample data for SequenceView component."""
    return pl.LazyFrame(
        {
            "scan_id": [1, 2, 3],
            "sequence": ["PEPTIDER", "ACDEFGHK", "MNPQRST"],
            "precursor_charge": [2, 3, 1],
        }
    )


@pytest.fixture
def sample_peaks_data() -> pl.LazyFrame:
    """Create sample peaks data for SequenceView component."""
    return pl.LazyFrame(
        {
            "scan_id": [1, 1, 1, 2, 2, 3],
            "peak_id": [101, 102, 103, 201, 202, 301],
            "mass": [200.5, 300.6, 400.7, 250.3, 350.4, 150.2],
            "intensity": [1000.0, 2000.0, 1500.0, 3000.0, 2500.0, 500.0],
        }
    )


@pytest.fixture
def sample_volcanoplot_data() -> pl.LazyFrame:
    """Create sample data for VolcanoPlot component."""
    import random

    random.seed(42)

    n_proteins = 100
    return pl.LazyFrame(
        {
            "protein_id": [f"PROT{i:04d}" for i in range(n_proteins)],
            "protein_name": [f"Protein_{i}" for i in range(n_proteins)],
            "log2FC": [random.uniform(-4, 4) for _ in range(n_proteins)],
            "pvalue": [random.uniform(0.0001, 1) for _ in range(n_proteins)],
            "comparison_id": [
                random.choice(["A_vs_B", "C_vs_D"]) for _ in range(n_proteins)
            ],
        }
    )


@pytest.fixture
def sample_plot3d_data() -> pl.LazyFrame:
    """Create sample tidy long-format data for the Plot3D component.

    One row per plotted point. Includes:
    - a non-positive intensity row (to exercise drop_nonpositive_z),
    - two series values ("Signal"/"Noise"),
    - two scan values (to exercise filtering).
    """
    return pl.LazyFrame(
        {
            "mass": [1000.0, 1500.0, 2000.0, 2500.0, 3000.0, 3500.0],
            "charge": [2, 3, 2, 4, 3, 2],
            "intensity": [500.0, 1200.0, 0.0, 800.0, 1500.0, 300.0],
            "series": [
                "Signal",
                "Signal",
                "Noise",
                "Signal",
                "Noise",
                "Noise",
            ],
            "scan": [100, 100, 100, 200, 200, 200],
            "mass_index": [0, 1, 0, 0, 1, 1],
        }
    )


@pytest.fixture
def sample_categorical_heatmap_data() -> pl.LazyFrame:
    """Create sample data for categorical Heatmap component."""
    import random

    random.seed(42)

    n_points = 500
    categories = ["Control", "Treatment_A", "Treatment_B"]
    return pl.LazyFrame(
        {
            "retention_time": [random.uniform(0, 100) for _ in range(n_points)],
            "mz": [random.uniform(100, 2000) for _ in range(n_points)],
            "intensity": [random.uniform(100, 10000) for _ in range(n_points)],
            "sample_group": [random.choice(categories) for _ in range(n_points)],
            "scan_id": [random.randint(1, 10) for _ in range(n_points)],
        }
    )


@pytest.fixture
def pagination_test_data() -> pl.LazyFrame:
    """
    Create 500-row synthetic dataset for pagination and filtering tests.

    Schema:
        - id: Row identifier (0-499)
        - value: String values (item_0, item_1, ...)
        - score: Float values (0.0, 1.5, 3.0, ...)
        - category: Categorical column (A/B/C/D/E cycling)
        - description: Text column for regex testing
        - priority: Numeric column with few unique values (1-5, becomes categorical)
    """
    return pl.LazyFrame(
        {
            "id": list(range(500)),
            "value": [f"item_{i}" for i in range(500)],
            "score": [i * 1.5 for i in range(500)],
            "category": ["A", "B", "C", "D", "E"] * 100,
            "description": [
                f"Description for row {i} with {'even' if i % 2 == 0 else 'odd'} index"
                for i in range(500)
            ],
            "priority": [i % 5 + 1 for i in range(500)],
        }
    )
