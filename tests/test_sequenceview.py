"""Tests for SequenceView component behavior."""

from pathlib import Path

import polars as pl
import pytest

from openms_insight.core.cache import CacheMissError


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

        with pytest.raises(CacheMissError):
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

        with pytest.raises(CacheMissError):
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


# ---------------------------------------------------------------------------
# Per-residue coverage (P1-SV-COV-001) + truncated/undetermined terminals
# (P1-SV-COV-002).
# ---------------------------------------------------------------------------


@pytest.fixture
def coverage_sequence_data() -> pl.LazyFrame:
    """Sequence frame with per-residue coverage lists + proteoform terminals.

    scan 1: PEPTIDER (len 8), coverage peaks at the last residue (max 4),
            truncated N (start=2) + truncated C (end=6).
    scan 2: ACDEFGHK (len 8), all-zero coverage (max 0 -> legend hidden),
            UNDETERMINED N (start=-1) + full C.
    scan 3: MNPQRST  (len 7), flat coverage (max 1), full N + UNDETERMINED C
            (end=-1).
    """
    return pl.DataFrame(
        {
            "scan_id": [1, 2, 3],
            "sequence": ["PEPTIDER", "ACDEFGHK", "MNPQRST"],
            "precursor_charge": [2, 3, 1],
            "cov": [
                [0.0, 1.0, 2.0, 2.0, 1.0, 0.0, 0.0, 4.0],
                [0.0] * 8,
                [1.0] * 7,
            ],
            "pstart": [2, -1, 0],
            "pend": [6, 7, -1],
        }
    ).lazy()


class TestNormalizeCoverage:
    """Pure-function tests for the oracle-parity coverage normalisation."""

    def test_normalize_divides_by_max(self):
        from openms_insight.components.sequenceview import normalize_coverage

        normalized, max_cov = normalize_coverage([0.0, 1.0, 2.0, 4.0])
        # value / max(value) (oracle p_cov), max returned raw.
        assert normalized == [0.0, 0.25, 0.5, 1.0]
        assert max_cov == 4.0

    def test_normalize_all_zero(self):
        from openms_insight.components.sequenceview import normalize_coverage

        normalized, max_cov = normalize_coverage([0.0, 0.0, 0.0])
        assert normalized == [0.0, 0.0, 0.0]
        assert max_cov == 0.0

    def test_normalize_empty(self):
        from openms_insight.components.sequenceview import normalize_coverage

        assert normalize_coverage([]) == ([], 0.0)

    def test_normalize_in_unit_range(self):
        from openms_insight.components.sequenceview import normalize_coverage

        normalized, _ = normalize_coverage([3.0, 7.0, 1.0, 7.0])
        assert all(0.0 <= v <= 1.0 for v in normalized)
        # The maximum residue(s) normalise to exactly 1.0 (drives full alpha).
        assert max(normalized) == 1.0


class TestSequenceViewCoverage:
    """Contract tests for per-residue coverage payload + cache/args wiring."""

    def test_coverage_in_vue_data(
        self,
        temp_cache_dir: Path,
        coverage_sequence_data: pl.LazyFrame,
        sample_peaks_data: pl.LazyFrame,
    ):
        """coverage_column attaches normalised `coverage` + raw `maxCoverage`."""
        from openms_insight.components.sequenceview import SequenceView

        sv = SequenceView(
            cache_id="test_sv_cov_on",
            sequence_data=coverage_sequence_data,
            peaks_data=sample_peaks_data,
            cache_path=str(temp_cache_dir),
            filters={"spectrum": "scan_id"},
            coverage_column="cov",
        )
        seq = sv._prepare_vue_data({"spectrum": 1})["sequenceData"]

        # Per-residue coverage lands, one entry per residue, all in [0, 1].
        assert "coverage" in seq
        assert len(seq["coverage"]) == len(seq["sequence"])
        assert all(0.0 <= v <= 1.0 for v in seq["coverage"])
        # The residue with the raw max (last residue, count 4) -> alpha-driving 1.0.
        assert seq["coverage"][7] == 1.0
        assert seq["coverage"][0] == 0.0
        # maxCoverage is the RAW max (legend label "4x"), not the normalised 1.0.
        assert seq["maxCoverage"] == 4.0

    def test_coverage_drives_alpha_values(
        self,
        temp_cache_dir: Path,
        coverage_sequence_data: pl.LazyFrame,
        sample_peaks_data: pl.LazyFrame,
    ):
        """Normalised coverage equals raw/max exactly (the value Vue maps to alpha)."""
        from openms_insight.components.sequenceview import SequenceView

        sv = SequenceView(
            cache_id="test_sv_cov_alpha",
            sequence_data=coverage_sequence_data,
            peaks_data=sample_peaks_data,
            cache_path=str(temp_cache_dir),
            filters={"spectrum": "scan_id"},
            coverage_column="cov",
        )
        seq = sv._prepare_vue_data({"spectrum": 1})["sequenceData"]
        # raw [0,1,2,2,1,0,0,4] / max 4 -> exact alpha inputs.
        assert seq["coverage"] == [0.0, 0.25, 0.5, 0.5, 0.25, 0.0, 0.0, 1.0]

    def test_coverage_all_zero_max_zero(
        self,
        temp_cache_dir: Path,
        coverage_sequence_data: pl.LazyFrame,
        sample_peaks_data: pl.LazyFrame,
    ):
        """All-zero coverage -> maxCoverage 0 (Vue hides the scale legend)."""
        from openms_insight.components.sequenceview import SequenceView

        sv = SequenceView(
            cache_id="test_sv_cov_zero",
            sequence_data=coverage_sequence_data,
            peaks_data=sample_peaks_data,
            cache_path=str(temp_cache_dir),
            filters={"spectrum": "scan_id"},
            coverage_column="cov",
        )
        # scan 2 has all-zero coverage.
        seq = sv._prepare_vue_data({"spectrum": 2})["sequenceData"]
        assert seq["coverage"] == [0.0] * 8
        assert seq["maxCoverage"] == 0.0

    def test_coverage_off_no_keys(
        self,
        temp_cache_dir: Path,
        coverage_sequence_data: pl.LazyFrame,
        sample_peaks_data: pl.LazyFrame,
    ):
        """No coverage_column -> neither coverage key is emitted (back-compat)."""
        from openms_insight.components.sequenceview import SequenceView

        sv = SequenceView(
            cache_id="test_sv_cov_off",
            sequence_data=coverage_sequence_data,
            peaks_data=sample_peaks_data,
            cache_path=str(temp_cache_dir),
            filters={"spectrum": "scan_id"},
        )
        seq = sv._prepare_vue_data({"spectrum": 1})["sequenceData"]
        assert "coverage" not in seq
        assert "maxCoverage" not in seq

    def test_coverage_hash_changes_with_flag(
        self,
        temp_cache_dir: Path,
        coverage_sequence_data: pl.LazyFrame,
        sample_peaks_data: pl.LazyFrame,
    ):
        """The change-detection hash differs when coverage is supplied."""
        from openms_insight.components.sequenceview import SequenceView

        sv_off = SequenceView(
            cache_id="test_sv_cov_hash_off",
            sequence_data=coverage_sequence_data,
            peaks_data=sample_peaks_data,
            cache_path=str(temp_cache_dir),
            filters={"spectrum": "scan_id"},
        )
        sv_on = SequenceView(
            cache_id="test_sv_cov_hash_on",
            sequence_data=coverage_sequence_data,
            peaks_data=sample_peaks_data,
            cache_path=str(temp_cache_dir),
            filters={"spectrum": "scan_id"},
            coverage_column="cov",
        )
        h_off = sv_off._prepare_vue_data({"spectrum": 1})["_hash"]
        h_on = sv_on._prepare_vue_data({"spectrum": 1})["_hash"]
        assert h_off != h_on

    def test_coverage_cache_roundtrip(
        self,
        temp_cache_dir: Path,
        coverage_sequence_data: pl.LazyFrame,
        sample_peaks_data: pl.LazyFrame,
    ):
        """Reconstruction from cache restores the coverage column + payload."""
        from openms_insight.components.sequenceview import SequenceView

        cache_id = "test_sv_cov_cache"
        SequenceView(
            cache_id=cache_id,
            sequence_data=coverage_sequence_data,
            peaks_data=sample_peaks_data,
            cache_path=str(temp_cache_dir),
            filters={"spectrum": "scan_id"},
            coverage_column="cov",
        )
        restored = SequenceView(cache_id=cache_id, cache_path=str(temp_cache_dir))
        assert restored._coverage_column == "cov"
        seq = restored._prepare_vue_data({"spectrum": 1})["sequenceData"]
        assert seq["maxCoverage"] == 4.0
        assert seq["coverage"][7] == 1.0

    def test_coverage_config_requires_data(
        self,
        temp_cache_dir: Path,
    ):
        """coverage_column without sequence_data raises (has_config gate)."""
        from openms_insight.components.sequenceview import SequenceView

        with pytest.raises(CacheMissError):
            SequenceView(
                cache_id="test_sv_cov_no_data",
                cache_path=str(temp_cache_dir),
                coverage_column="cov",
            )

    def test_coverage_empty_sequence_safe(
        self,
        temp_cache_dir: Path,
        coverage_sequence_data: pl.LazyFrame,
        sample_peaks_data: pl.LazyFrame,
    ):
        """Empty sequence (filter None) -> no coverage keys, no error."""
        from openms_insight.components.sequenceview import SequenceView

        sv = SequenceView(
            cache_id="test_sv_cov_empty",
            sequence_data=coverage_sequence_data,
            peaks_data=sample_peaks_data,
            cache_path=str(temp_cache_dir),
            filters={"spectrum": "scan_id"},
            coverage_column="cov",
        )
        seq = sv._prepare_vue_data({"spectrum": None})["sequenceData"]
        assert seq["sequence"] == []
        assert "coverage" not in seq
        assert "maxCoverage" not in seq


class TestSequenceViewTerminals:
    """Contract tests for truncated / undetermined proteoform terminals."""

    def test_terminals_in_vue_data(
        self,
        temp_cache_dir: Path,
        coverage_sequence_data: pl.LazyFrame,
        sample_peaks_data: pl.LazyFrame,
    ):
        """proteoform_start/end columns attach the terminal indices to payload."""
        from openms_insight.components.sequenceview import SequenceView

        sv = SequenceView(
            cache_id="test_sv_term_on",
            sequence_data=coverage_sequence_data,
            peaks_data=sample_peaks_data,
            cache_path=str(temp_cache_dir),
            filters={"spectrum": "scan_id"},
            proteoform_start_column="pstart",
            proteoform_end_column="pend",
        )
        # scan 1: truncated N (start 2 > 0) + truncated C (end 6 < len-1=7).
        seq = sv._prepare_vue_data({"spectrum": 1})["sequenceData"]
        assert seq["proteoform_start"] == 2
        assert seq["proteoform_end"] == 6

    def test_terminals_undetermined_negative(
        self,
        temp_cache_dir: Path,
        coverage_sequence_data: pl.LazyFrame,
        sample_peaks_data: pl.LazyFrame,
    ):
        """Negative terminal indices propagate (Vue renders the '??' marker)."""
        from openms_insight.components.sequenceview import SequenceView

        sv = SequenceView(
            cache_id="test_sv_term_undet",
            sequence_data=coverage_sequence_data,
            peaks_data=sample_peaks_data,
            cache_path=str(temp_cache_dir),
            filters={"spectrum": "scan_id"},
            proteoform_start_column="pstart",
            proteoform_end_column="pend",
        )
        # scan 2: UNDETERMINED N (start -1). scan 3: UNDETERMINED C (end -1).
        seq2 = sv._prepare_vue_data({"spectrum": 2})["sequenceData"]
        assert seq2["proteoform_start"] == -1  # < 0 -> n_determined False in Vue
        seq3 = sv._prepare_vue_data({"spectrum": 3})["sequenceData"]
        assert seq3["proteoform_end"] == -1  # < 0 -> c_determined False in Vue

    def test_terminals_start_only(
        self,
        temp_cache_dir: Path,
        coverage_sequence_data: pl.LazyFrame,
        sample_peaks_data: pl.LazyFrame,
    ):
        """Only proteoform_start_column -> only proteoform_start emitted."""
        from openms_insight.components.sequenceview import SequenceView

        sv = SequenceView(
            cache_id="test_sv_term_start_only",
            sequence_data=coverage_sequence_data,
            peaks_data=sample_peaks_data,
            cache_path=str(temp_cache_dir),
            filters={"spectrum": "scan_id"},
            proteoform_start_column="pstart",
        )
        seq = sv._prepare_vue_data({"spectrum": 1})["sequenceData"]
        assert seq["proteoform_start"] == 2
        assert "proteoform_end" not in seq

    def test_terminals_off_no_keys(
        self,
        temp_cache_dir: Path,
        coverage_sequence_data: pl.LazyFrame,
        sample_peaks_data: pl.LazyFrame,
    ):
        """No terminal columns -> no terminal keys (back-compat, determined)."""
        from openms_insight.components.sequenceview import SequenceView

        sv = SequenceView(
            cache_id="test_sv_term_off",
            sequence_data=coverage_sequence_data,
            peaks_data=sample_peaks_data,
            cache_path=str(temp_cache_dir),
            filters={"spectrum": "scan_id"},
        )
        seq = sv._prepare_vue_data({"spectrum": 1})["sequenceData"]
        assert "proteoform_start" not in seq
        assert "proteoform_end" not in seq

    def test_terminals_cache_roundtrip(
        self,
        temp_cache_dir: Path,
        coverage_sequence_data: pl.LazyFrame,
        sample_peaks_data: pl.LazyFrame,
    ):
        """Reconstruction restores the terminal columns + payload."""
        from openms_insight.components.sequenceview import SequenceView

        cache_id = "test_sv_term_cache"
        SequenceView(
            cache_id=cache_id,
            sequence_data=coverage_sequence_data,
            peaks_data=sample_peaks_data,
            cache_path=str(temp_cache_dir),
            filters={"spectrum": "scan_id"},
            proteoform_start_column="pstart",
            proteoform_end_column="pend",
        )
        restored = SequenceView(cache_id=cache_id, cache_path=str(temp_cache_dir))
        assert restored._proteoform_start_column == "pstart"
        assert restored._proteoform_end_column == "pend"
        seq = restored._prepare_vue_data({"spectrum": 1})["sequenceData"]
        assert seq["proteoform_start"] == 2
        assert seq["proteoform_end"] == 6

    def test_terminals_config_requires_data(
        self,
        temp_cache_dir: Path,
    ):
        """Terminal columns without sequence_data raise (has_config gate)."""
        from openms_insight.components.sequenceview import SequenceView

        with pytest.raises(CacheMissError):
            SequenceView(
                cache_id="test_sv_term_no_data",
                cache_path=str(temp_cache_dir),
                proteoform_start_column="pstart",
            )

    def test_terminals_empty_sequence_safe(
        self,
        temp_cache_dir: Path,
        coverage_sequence_data: pl.LazyFrame,
        sample_peaks_data: pl.LazyFrame,
    ):
        """Empty sequence (filter None) -> no terminal keys, no error."""
        from openms_insight.components.sequenceview import SequenceView

        sv = SequenceView(
            cache_id="test_sv_term_empty",
            sequence_data=coverage_sequence_data,
            peaks_data=sample_peaks_data,
            cache_path=str(temp_cache_dir),
            filters={"spectrum": "scan_id"},
            proteoform_start_column="pstart",
            proteoform_end_column="pend",
        )
        seq = sv._prepare_vue_data({"spectrum": None})["sequenceData"]
        assert seq["sequence"] == []
        assert "proteoform_start" not in seq
        assert "proteoform_end" not in seq


class TestSequenceViewResidueClick:
    """Config/contract tests for the two-path residue-click model.

    PATH 1 is the ``residue_identifier`` publication (coverage-gated toggle on the
    Vue side); PATH 2 is the new ``fragment_mass_identifier`` mass publication.
    These tests cover the Python surface: arg emission (default-OFF/ON), cache
    roundtrip, and the reconstruction guard. The Vue store-write behavior (toggle,
    mass mapping, back-compat) is covered by the vitest spec
    ``SequenceView.residueClick.spec.ts``.
    """

    def test_identifiers_in_args_when_set(
        self,
        temp_cache_dir: Path,
        coverage_sequence_data: pl.LazyFrame,
        sample_peaks_data: pl.LazyFrame,
    ):
        """residue_identifier + fragment_mass_identifier flow into Vue args."""
        from openms_insight.components.sequenceview import SequenceView

        sv = SequenceView(
            cache_id="test_sv_resclick_on",
            sequence_data=coverage_sequence_data,
            peaks_data=sample_peaks_data,
            cache_path=str(temp_cache_dir),
            filters={"protein": "scan_id"},
            interactivity={"mass": "peak_id"},
            residue_identifier="aa",
            fragment_mass_identifier="mass",
            coverage_column="cov",
        )
        args = sv._get_component_args()
        assert args["residueIdentifier"] == "aa"
        assert args["fragmentMassIdentifier"] == "mass"

    def test_fragment_mass_identifier_absent_by_default(
        self,
        temp_cache_dir: Path,
        sample_sequence_data: pl.LazyFrame,
        sample_peaks_data: pl.LazyFrame,
    ):
        """Default-OFF: no fragment_mass_identifier -> arg not emitted (back-compat)."""
        from openms_insight.components.sequenceview import SequenceView

        sv = SequenceView(
            cache_id="test_sv_resclick_off",
            sequence_data=sample_sequence_data,
            peaks_data=sample_peaks_data,
            cache_path=str(temp_cache_dir),
            filters={"spectrum": "scan_id"},
            residue_identifier="aa",
        )
        args = sv._get_component_args()
        # PATH-1 residue identifier still emitted (existing behavior)...
        assert args["residueIdentifier"] == "aa"
        # ...but PATH-2 mass identifier is OFF by default.
        assert "fragmentMassIdentifier" not in args

    def test_identifiers_cache_roundtrip(
        self,
        temp_cache_dir: Path,
        coverage_sequence_data: pl.LazyFrame,
        sample_peaks_data: pl.LazyFrame,
    ):
        """Reconstruction from cache restores both residue-click identifiers."""
        from openms_insight.components.sequenceview import SequenceView

        cache_id = "test_sv_resclick_cache"
        SequenceView(
            cache_id=cache_id,
            sequence_data=coverage_sequence_data,
            peaks_data=sample_peaks_data,
            cache_path=str(temp_cache_dir),
            filters={"protein": "scan_id"},
            interactivity={"mass": "peak_id"},
            residue_identifier="aa",
            fragment_mass_identifier="mass",
            coverage_column="cov",
        )

        restored = SequenceView(cache_id=cache_id, cache_path=str(temp_cache_dir))
        assert restored._residue_identifier == "aa"
        assert restored._fragment_mass_identifier == "mass"
        args = restored._get_component_args()
        assert args["residueIdentifier"] == "aa"
        assert args["fragmentMassIdentifier"] == "mass"

    def test_fragment_mass_identifier_requires_sequence_data(
        self,
        temp_cache_dir: Path,
    ):
        """fragment_mass_identifier is a config arg -> guarded in reconstruction mode."""
        from openms_insight.components.sequenceview import SequenceView
        from openms_insight.core.cache import CacheMissError

        with pytest.raises(CacheMissError):
            SequenceView(
                cache_id="test_sv_resclick_guard",
                cache_path=str(temp_cache_dir),
                fragment_mass_identifier="mass",
            )
