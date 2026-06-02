"""Tests for InternalFragmentMap component and its core algorithm."""

import builtins

import numpy as np
import polars as pl
import pytest

from openms_insight import InternalFragmentMap
from openms_insight.components.internalfragmentmap import (
    _terminal_masses,
    internal_fragment_data,
    internal_fragment_masses,
)

SEQ = "PEPTIDERPEPTIDEK"  # 16 residues


class TestInternalFragmentAlgorithm:
    """The core port of getInternalFragmentMassesWithSeq (sequence.py:204-274)."""

    @pytest.mark.parametrize("ion_type", ["by", "bz", "cy"])
    def test_invariants(self, ion_type):
        masses, starts, ends = internal_fragment_masses(SEQ, ion_type)
        n = len(SEQ)
        # Equal-length parallel arrays
        assert len(masses) == len(starts) == len(ends)
        # >= 5 residues; start is an interior N-bound; end = j+1 in [start+5, n]
        for s, e in zip(starts, ends):
            assert e - s >= 5
            assert 1 <= s <= n - 2
            assert s + 5 <= e <= n

    def test_unknown_ion_type(self):
        with pytest.raises(ValueError, match="Unknown ion_type"):
            internal_fragment_masses(SEQ, "xy")

    def test_short_sequence_no_fragments(self):
        # Length 5 has no interior >=5 internal fragment
        masses, starts, ends = internal_fragment_masses("PEPTK", "by")
        assert masses == [] and starts == [] and ends == []

    @pytest.mark.parametrize("ion_type", ["by", "bz", "cy"])
    def test_terminal_exclusion_reduces_count(self, ion_type):
        with_excl = internal_fragment_masses(SEQ, ion_type, exclude_terminal=True)
        without = internal_fragment_masses(SEQ, ion_type, exclude_terminal=False)
        # Excluding terminal-coinciding fragments never increases the count
        assert len(with_excl[0]) <= len(without[0])

    def test_data_schema(self):
        data = internal_fragment_data(SEQ)
        for t in ("by", "bz", "cy"):
            assert f"fragment_masses_{t}" in data
            assert f"start_indices_{t}" in data
            assert f"end_indices_{t}" in data

    def test_pyopenms_and_fallback_terminal_masses_agree(self):
        """Terminal masses match (well within 10 ppm) with or without pyOpenMS."""
        tm_default = sorted(_terminal_masses(SEQ))

        # Force the static-table fallback by blocking the pyopenms import
        real_import = builtins.__import__

        def blocker(name, *args, **kwargs):
            if name == "pyopenms" or name.startswith("pyopenms."):
                raise ImportError("blocked for test")
            return real_import(name, *args, **kwargs)

        builtins.__import__ = blocker
        try:
            tm_fallback = sorted(_terminal_masses(SEQ))
        finally:
            builtins.__import__ = real_import

        assert len(tm_default) == len(tm_fallback)
        max_diff = np.max(np.abs(np.array(tm_default) - np.array(tm_fallback)))
        # 1e-5 Da << 10 ppm of a ~1000 Da ion (~0.01 Da)
        assert max_diff < 1e-3


class TestInternalFragmentMapComponent:
    @pytest.fixture
    def sequence_df(self):
        return pl.LazyFrame(
            {"proteoform_index": [0, 1], "sequence": [SEQ, "ACDEFGHIKLMN"]}
        )

    @pytest.fixture
    def peaks_df(self):
        return pl.LazyFrame(
            {
                "scan_id": [10, 10, 10, 20],
                "mass": [500.25, 612.30, 729.40, 333.10],
            }
        )

    def test_init_and_names(
        self, mock_streamlit, temp_cache_dir, sequence_df, peaks_df
    ):
        ifm = InternalFragmentMap(
            cache_id="ifm_init",
            sequence_data=sequence_df,
            peaks_data=peaks_df,
            filters={"proteinIndex": "proteoform_index", "scanIndex": "scan_id"},
            cache_path=str(temp_cache_dir),
        )
        assert ifm._get_vue_component_name() == "InternalFragmentMap"
        assert ifm._get_data_key() == "internalFragmentData"
        assert set(ifm.get_state_dependencies()) == {"proteinIndex", "scanIndex"}

    def test_prepare_vue_data_with_selection(
        self, mock_streamlit, temp_cache_dir, sequence_df, peaks_df
    ):
        ifm = InternalFragmentMap(
            cache_id="ifm_sel",
            sequence_data=sequence_df,
            peaks_data=peaks_df,
            filters={"proteinIndex": "proteoform_index", "scanIndex": "scan_id"},
            cache_path=str(temp_cache_dir),
        )
        out = ifm._prepare_vue_data({"proteinIndex": 0, "scanIndex": 10})
        payload = out["internalFragmentData"]
        assert payload["sequence"] == list(SEQ)
        assert len(payload["observedMasses"]) == 3  # scan 10 peaks
        # All three fragment types present and non-empty for a 16-mer
        for t in ("by", "bz", "cy"):
            assert len(payload[f"fragment_masses_{t}"]) > 0
        assert "colors" in payload
        assert "_hash" in out

    def test_empty_without_selection(
        self, mock_streamlit, temp_cache_dir, sequence_df, peaks_df
    ):
        ifm = InternalFragmentMap(
            cache_id="ifm_empty",
            sequence_data=sequence_df,
            peaks_data=peaks_df,
            filters={"proteinIndex": "proteoform_index", "scanIndex": "scan_id"},
            cache_path=str(temp_cache_dir),
        )
        out = ifm._prepare_vue_data({})
        payload = out["internalFragmentData"]
        assert payload["sequence"] == []
        assert payload["observedMasses"] == []
        assert payload["fragment_masses_by"] == []

    def test_static_sequence(self, mock_streamlit, temp_cache_dir):
        ifm = InternalFragmentMap(
            cache_id="ifm_static",
            sequence_data=SEQ,
            cache_path=str(temp_cache_dir),
        )
        out = ifm._prepare_vue_data({})
        assert out["internalFragmentData"]["sequence"] == list(SEQ)

    def test_component_args(self, mock_streamlit, temp_cache_dir, sequence_df):
        ifm = InternalFragmentMap(
            cache_id="ifm_args",
            sequence_data=sequence_df,
            filters={"proteinIndex": "proteoform_index"},
            title="Internal Fragment Map",
            cache_path=str(temp_cache_dir),
        )
        args = ifm._get_component_args()
        assert args["componentType"] == "InternalFragmentMap"
        assert args["title"] == "Internal Fragment Map"
        # Legend colors match the original Vue component
        assert args["colors"]["by"] == "#f0a441"
        assert args["colors"]["cy"] == "#12871d"
        assert args["colors"]["bz"] == "#7831cc"

    def test_cache_reconstruction(
        self, mock_streamlit, temp_cache_dir, sequence_df, peaks_df
    ):
        InternalFragmentMap(
            cache_id="ifm_recon",
            sequence_data=sequence_df,
            peaks_data=peaks_df,
            filters={"proteinIndex": "proteoform_index", "scanIndex": "scan_id"},
            title="Internal Fragment Map",
            cache_path=str(temp_cache_dir),
        )
        ifm2 = InternalFragmentMap(cache_id="ifm_recon", cache_path=str(temp_cache_dir))
        assert ifm2._filters == {
            "proteinIndex": "proteoform_index",
            "scanIndex": "scan_id",
        }
        assert ifm2._title == "Internal Fragment Map"
        out = ifm2._prepare_vue_data({"proteinIndex": 1, "scanIndex": 20})
        assert out["internalFragmentData"]["sequence"] == list("ACDEFGHIKLMN")
