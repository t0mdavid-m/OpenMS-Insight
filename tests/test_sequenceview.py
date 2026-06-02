"""Tests for SequenceView component behavior."""

from pathlib import Path

import polars as pl
import pytest


class TestSequenceViewEmptyState:
    """Tests for SequenceView empty state handling."""

    def test_get_sequence_returns_empty_when_filter_is_none(
        self,
        temp_cache_dir: Path,
        sample_sequence_data: pl.LazyFrame,
        sample_peaks_data: pl.LazyFrame,
    ):
        """When filter value is None and filter_defaults has None, return empty sequence."""
        from openms_insight.components.sequenceview import SequenceView

        cache_id = "test_sv_empty_state"
        sv = SequenceView(
            cache_id=cache_id,
            sequence_data=sample_sequence_data,
            peaks_data=sample_peaks_data,
            cache_path=str(temp_cache_dir),
            filters={"identification": "scan_id"},
        )

        # When identification is None (no selection)
        state = {"identification": None}
        sequence, charge = sv._get_sequence_for_state(state)

        # Should return empty, NOT the first row
        assert sequence == "", "Should return empty sequence when filter is None"

    def test_get_peaks_returns_empty_when_filter_is_none(
        self,
        temp_cache_dir: Path,
        sample_sequence_data: pl.LazyFrame,
        sample_peaks_data: pl.LazyFrame,
    ):
        """When filter value is None and filter_defaults has None, return empty peaks."""
        from openms_insight.components.sequenceview import SequenceView

        cache_id = "test_sv_empty_peaks"
        sv = SequenceView(
            cache_id=cache_id,
            sequence_data=sample_sequence_data,
            peaks_data=sample_peaks_data,
            cache_path=str(temp_cache_dir),
            filters={"spectrum": "scan_id"},
        )

        # When spectrum is None (no selection)
        state = {"spectrum": None}
        peaks_df = sv._get_peaks_for_state(state)

        # Should return empty DataFrame, NOT all peaks
        assert peaks_df.height == 0, "Should return empty DataFrame when filter is None"

    def test_get_sequence_returns_data_when_filter_has_value(
        self,
        temp_cache_dir: Path,
        sample_sequence_data: pl.LazyFrame,
        sample_peaks_data: pl.LazyFrame,
    ):
        """When filter value is set, return matching data."""
        from openms_insight.components.sequenceview import SequenceView

        cache_id = "test_sv_with_value"
        sv = SequenceView(
            cache_id=cache_id,
            sequence_data=sample_sequence_data,
            peaks_data=sample_peaks_data,
            cache_path=str(temp_cache_dir),
            filters={"identification": "scan_id"},
        )

        # Get actual scan_id from data
        df = sample_sequence_data.collect()
        first_scan_id = df["scan_id"][0]

        # When identification is set
        state = {"identification": first_scan_id}
        sequence, charge = sv._get_sequence_for_state(state)

        # Should return the matching sequence
        assert sequence != "", "Should return sequence when filter has value"
        assert sequence == df["sequence"][0]

    def test_get_peaks_returns_data_when_filter_has_value(
        self,
        temp_cache_dir: Path,
        sample_sequence_data: pl.LazyFrame,
        sample_peaks_data: pl.LazyFrame,
    ):
        """When filter value is set, return matching peaks."""
        from openms_insight.components.sequenceview import SequenceView

        cache_id = "test_sv_peaks_value"
        sv = SequenceView(
            cache_id=cache_id,
            sequence_data=sample_sequence_data,
            peaks_data=sample_peaks_data,
            cache_path=str(temp_cache_dir),
            filters={"spectrum": "scan_id"},
        )

        # Get actual scan_id from peaks data
        df = sample_peaks_data.collect()
        first_scan_id = df["scan_id"][0]

        # When spectrum is set
        state = {"spectrum": first_scan_id}
        peaks_df = sv._get_peaks_for_state(state)

        # Should return the matching peaks (scan_id=1 has 3 peaks in fixture)
        assert peaks_df.height > 0, "Should return peaks when filter has value"

    def test_filter_not_in_defaults_returns_all_data_when_none(
        self,
        temp_cache_dir: Path,
        sample_sequence_data: pl.LazyFrame,
        sample_peaks_data: pl.LazyFrame,
    ):
        """When filter has no default (not in filter_defaults), None means show all data."""
        from openms_insight.components.sequenceview import SequenceView

        cache_id = "test_sv_no_default"
        sv = SequenceView(
            cache_id=cache_id,
            sequence_data=sample_sequence_data,
            peaks_data=sample_peaks_data,
            cache_path=str(temp_cache_dir),
            filters={"identification": "scan_id"},
        )

        # Manually remove from filter_defaults to simulate filter without default
        sv._filter_defaults = {}

        # When identification is None and no default
        state = {"identification": None}
        sequence, charge = sv._get_sequence_for_state(state)

        # Should return first row (all data behavior)
        assert sequence != "", "Should return data when filter has no default"

    def test_multiple_filters_one_none(
        self,
        temp_cache_dir: Path,
        sample_sequence_data: pl.LazyFrame,
        sample_peaks_data: pl.LazyFrame,
    ):
        """When one filter is None with None default, return empty even if other filter has value."""
        from openms_insight.components.sequenceview import SequenceView

        # Add sequence_id to data
        seq_data = sample_sequence_data.with_columns(pl.lit(1).alias("sequence_id"))

        cache_id = "test_sv_multi_filter"
        sv = SequenceView(
            cache_id=cache_id,
            sequence_data=seq_data,
            peaks_data=sample_peaks_data,
            cache_path=str(temp_cache_dir),
            filters={"spectrum": "scan_id", "sequence": "sequence_id"},
        )

        # When spectrum is None but sequence has value
        state = {"spectrum": None, "sequence": 1}
        sequence, charge = sv._get_sequence_for_state(state)

        # Should return empty because one filter with None default is None
        assert sequence == "", (
            "Should return empty when any filter with None default is None"
        )


# Flat number[] keys attached to sequenceData when internal_fragments=True.
INTERNAL_KEYS = [
    "fragment_masses_by",
    "start_indices_by",
    "end_indices_by",
    "fragment_masses_bz",
    "start_indices_bz",
    "end_indices_bz",
    "fragment_masses_cy",
    "start_indices_cy",
    "end_indices_cy",
]


class TestSequenceViewInternalFragments:
    """Contract tests for the internal_fragments wiring (payload/args/cache)."""

    def test_internal_flag_adds_keys_to_vue_data(
        self,
        temp_cache_dir: Path,
        sample_sequence_data: pl.LazyFrame,
        sample_peaks_data: pl.LazyFrame,
    ):
        """internal_fragments=True attaches the nine flat lists + flags."""
        from openms_insight.components.sequenceview import SequenceView

        sv = SequenceView(
            cache_id="test_sv_internal_on",
            sequence_data=sample_sequence_data,
            peaks_data=sample_peaks_data,
            cache_path=str(temp_cache_dir),
            filters={"spectrum": "scan_id"},
            internal_fragments=True,
        )

        data = sv._prepare_vue_data({"spectrum": 1})
        seq = data["sequenceData"]

        assert seq["internal_fragments"] is True
        assert seq["internal_fragment_tolerance"] == 10.0
        assert seq["internal_fragment_tolerance_ppm"] is True
        for key in INTERNAL_KEYS:
            assert key in seq, f"missing internal key {key}"
            assert isinstance(seq[key], list), f"{key} must be a flat list"
            # flat list (no nested per-position lists)
            assert all(not isinstance(v, list) for v in seq[key])

    def test_internal_flag_off_no_keys(
        self,
        temp_cache_dir: Path,
        sample_sequence_data: pl.LazyFrame,
        sample_peaks_data: pl.LazyFrame,
    ):
        """Default internal_fragments=False adds none of the internal keys."""
        from openms_insight.components.sequenceview import SequenceView

        sv = SequenceView(
            cache_id="test_sv_internal_off",
            sequence_data=sample_sequence_data,
            peaks_data=sample_peaks_data,
            cache_path=str(temp_cache_dir),
            filters={"spectrum": "scan_id"},
        )

        data = sv._prepare_vue_data({"spectrum": 1})
        seq = data["sequenceData"]

        assert "internal_fragments" not in seq
        for key in INTERNAL_KEYS:
            assert key not in seq, f"unexpected internal key {key} when off"

    def test_internal_hash_changes_with_flag(
        self,
        temp_cache_dir: Path,
        sample_sequence_data: pl.LazyFrame,
        sample_peaks_data: pl.LazyFrame,
    ):
        """The change-detection hash differs when internal_fragments flips."""
        from openms_insight.components.sequenceview import SequenceView

        sv_off = SequenceView(
            cache_id="test_sv_hash_off",
            sequence_data=sample_sequence_data,
            peaks_data=sample_peaks_data,
            cache_path=str(temp_cache_dir),
            filters={"spectrum": "scan_id"},
        )
        sv_on = SequenceView(
            cache_id="test_sv_hash_on",
            sequence_data=sample_sequence_data,
            peaks_data=sample_peaks_data,
            cache_path=str(temp_cache_dir),
            filters={"spectrum": "scan_id"},
            internal_fragments=True,
        )

        h_off = sv_off._prepare_vue_data({"spectrum": 1})["_hash"]
        h_on = sv_on._prepare_vue_data({"spectrum": 1})["_hash"]
        assert h_off != h_on

    def test_internal_component_args(
        self,
        temp_cache_dir: Path,
        sample_sequence_data: pl.LazyFrame,
        sample_peaks_data: pl.LazyFrame,
    ):
        """_get_component_args exposes internalFragments/config only when on."""
        from openms_insight.components.sequenceview import SequenceView

        sv_on = SequenceView(
            cache_id="test_sv_args_on",
            sequence_data=sample_sequence_data,
            peaks_data=sample_peaks_data,
            cache_path=str(temp_cache_dir),
            filters={"spectrum": "scan_id"},
            internal_fragments=True,
        )
        args_on = sv_on._get_component_args()
        assert args_on["componentType"] == "SequenceView"
        assert args_on["internalFragments"] is True
        assert args_on["internalFragmentConfig"]["tolerance"] == 10.0
        assert args_on["internalFragmentConfig"]["tolerancePpm"] is True

        sv_off = SequenceView(
            cache_id="test_sv_args_off",
            sequence_data=sample_sequence_data,
            peaks_data=sample_peaks_data,
            cache_path=str(temp_cache_dir),
            filters={"spectrum": "scan_id"},
        )
        args_off = sv_off._get_component_args()
        assert "internalFragments" not in args_off
        assert "internalFragmentConfig" not in args_off

    def test_internal_custom_config_in_args(
        self,
        temp_cache_dir: Path,
        sample_sequence_data: pl.LazyFrame,
        sample_peaks_data: pl.LazyFrame,
    ):
        """internal_fragment_config overrides flow through to args + payload."""
        from openms_insight.components.sequenceview import SequenceView

        sv = SequenceView(
            cache_id="test_sv_custom_cfg",
            sequence_data=sample_sequence_data,
            peaks_data=sample_peaks_data,
            cache_path=str(temp_cache_dir),
            filters={"spectrum": "scan_id"},
            internal_fragments=True,
            internal_fragment_config={"tolerance": 25.0, "tolerance_ppm": False},
        )
        args = sv._get_component_args()
        assert args["internalFragmentConfig"]["tolerance"] == 25.0
        assert args["internalFragmentConfig"]["tolerancePpm"] is False

        seq = sv._prepare_vue_data({"spectrum": 1})["sequenceData"]
        assert seq["internal_fragment_tolerance"] == 25.0
        assert seq["internal_fragment_tolerance_ppm"] is False

    def test_internal_cache_roundtrip(
        self,
        temp_cache_dir: Path,
        sample_sequence_data: pl.LazyFrame,
        sample_peaks_data: pl.LazyFrame,
    ):
        """Reconstruction from cache restores internal flag + config."""
        from openms_insight.components.sequenceview import SequenceView

        cache_id = "test_sv_internal_cache"
        SequenceView(
            cache_id=cache_id,
            sequence_data=sample_sequence_data,
            peaks_data=sample_peaks_data,
            cache_path=str(temp_cache_dir),
            filters={"spectrum": "scan_id"},
            internal_fragments=True,
            internal_fragment_config={"tolerance": 15.0},
        )

        # Reconstruct from cache (no data args).
        restored = SequenceView(cache_id=cache_id, cache_path=str(temp_cache_dir))
        assert restored._internal_fragments is True
        assert restored._internal_fragment_config["tolerance"] == 15.0
        # Untouched keys keep parity defaults.
        assert restored._internal_fragment_config["min_length"] == 5
        assert restored._internal_fragment_config["remove_terminal_collisions"] is True

    def test_internal_config_requires_data(
        self,
        temp_cache_dir: Path,
    ):
        """internal_fragments=True without sequence_data raises (has_config gate)."""
        from openms_insight.components.sequenceview import SequenceView

        with pytest.raises(ValueError):
            SequenceView(
                cache_id="test_sv_internal_no_data",
                cache_path=str(temp_cache_dir),
                internal_fragments=True,
            )

    def test_internal_config_arg_requires_data(
        self,
        temp_cache_dir: Path,
    ):
        """internal_fragment_config without sequence_data also raises."""
        from openms_insight.components.sequenceview import SequenceView

        with pytest.raises(ValueError):
            SequenceView(
                cache_id="test_sv_internal_cfg_no_data",
                cache_path=str(temp_cache_dir),
                internal_fragment_config={"tolerance": 5.0},
            )

    def test_internal_empty_sequence_safe(
        self,
        temp_cache_dir: Path,
        sample_sequence_data: pl.LazyFrame,
        sample_peaks_data: pl.LazyFrame,
    ):
        """Empty sequence (filter None) -> internal arrays all empty, no error."""
        from openms_insight.components.sequenceview import SequenceView

        sv = SequenceView(
            cache_id="test_sv_internal_empty",
            sequence_data=sample_sequence_data,
            peaks_data=sample_peaks_data,
            cache_path=str(temp_cache_dir),
            filters={"spectrum": "scan_id"},
            internal_fragments=True,
        )

        # spectrum None with None default -> empty sequence.
        data = sv._prepare_vue_data({"spectrum": None})
        seq = data["sequenceData"]
        assert seq["sequence"] == []
        assert seq["internal_fragments"] is True
        for key in INTERNAL_KEYS:
            assert seq[key] == []
