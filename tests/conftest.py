"""Pytest configuration and shared fixtures for openms-insight tests."""

import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, Generator
from unittest.mock import MagicMock, patch

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

    with patch('streamlit.session_state', mock_session_state):
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
    return pl.LazyFrame({
        "id": [1, 2, 3, 4, 5],
        "scan_id": [100, 100, 200, 200, 300],
        "mass": [500.5, 600.6, 700.7, 800.8, 900.9],
        "name": ["peak_a", "peak_b", "peak_c", "peak_d", "peak_e"],
    })


@pytest.fixture
def sample_lineplot_data() -> pl.LazyFrame:
    """Create sample data for LinePlot component."""
    return pl.LazyFrame({
        "mass": [100.0, 200.0, 300.0, 400.0, 500.0],
        "intensity": [1000.0, 2000.0, 1500.0, 3000.0, 500.0],
        "scan_id": [1, 1, 1, 2, 2],
        "peak_id": [10, 20, 30, 40, 50],
        "annotation": ["b2", "", "y3", "", "b4"],
    })


@pytest.fixture
def sample_heatmap_data() -> pl.LazyFrame:
    """Create sample data for Heatmap component."""
    import random
    random.seed(42)

    n_points = 1000
    return pl.LazyFrame({
        "retention_time": [random.uniform(0, 100) for _ in range(n_points)],
        "mz": [random.uniform(100, 2000) for _ in range(n_points)],
        "intensity": [random.uniform(100, 10000) for _ in range(n_points)],
        "scan_id": [random.randint(1, 10) for _ in range(n_points)],
    })


@pytest.fixture
def sample_sequence_data() -> pl.LazyFrame:
    """Create sample data for SequenceView component."""
    return pl.LazyFrame({
        "scan_id": [1, 2, 3],
        "sequence": ["PEPTIDER", "ACDEFGHK", "MNPQRST"],
        "precursor_charge": [2, 3, 1],
    })


@pytest.fixture
def sample_peaks_data() -> pl.LazyFrame:
    """Create sample peaks data for SequenceView component."""
    return pl.LazyFrame({
        "scan_id": [1, 1, 1, 2, 2, 3],
        "peak_id": [101, 102, 103, 201, 202, 301],
        "mass": [200.5, 300.6, 400.7, 250.3, 350.4, 150.2],
        "intensity": [1000.0, 2000.0, 1500.0, 3000.0, 2500.0, 500.0],
    })
