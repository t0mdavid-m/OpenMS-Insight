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


# ---------------------------------------------------------------------------
# Mass-info header (3-seqview-004) + inbound mass->fragment-row highlight
# (3-seqview-003).
# ---------------------------------------------------------------------------


@pytest.fixture
def observed_mass_sequence_data() -> pl.LazyFrame:
    """Sequence frame carrying a per-row observed (proteoform) mass.

    scan 1: PEPTIDER with an observed mass; scan 2: a non-positive observed mass
    (-1) -> the header shows observed/delta as "-"; scan 3: no observed mass
    column issue tested separately.
    """
    return pl.DataFrame(
        {
            "scan_id": [1, 2, 3],
            "sequence": ["PEPTIDER", "ACDEFGHK", "MNPQRST"],
            "precursor_charge": [2, 3, 1],
            "obs_mass": [955.45, -1.0, 800.0],
        }
    ).lazy()


class TestSequenceViewMassHeader:
    """Contract tests for the mass-info header payload + args wiring."""

    def test_observed_mass_in_vue_data(
        self,
        temp_cache_dir: Path,
        observed_mass_sequence_data: pl.LazyFrame,
        sample_peaks_data: pl.LazyFrame,
    ):
        """observed_mass_column attaches `observed_mass` + `mass_header_title`."""
        from openms_insight.components.sequenceview import SequenceView

        sv = SequenceView(
            cache_id="test_sv_obsmass_on",
            sequence_data=observed_mass_sequence_data,
            peaks_data=sample_peaks_data,
            cache_path=str(temp_cache_dir),
            filters={"spectrum": "scan_id"},
            observed_mass_column="obs_mass",
        )
        seq = sv._prepare_vue_data({"spectrum": 1})["sequenceData"]
        assert seq["observed_mass"] == pytest.approx(955.45)
        # theoretical_mass is always present; the Vue side derives the delta.
        assert "theoretical_mass" in seq
        assert seq["mass_header_title"] == "Proteoform"

    def test_custom_mass_header_title(
        self,
        temp_cache_dir: Path,
        observed_mass_sequence_data: pl.LazyFrame,
        sample_peaks_data: pl.LazyFrame,
    ):
        """mass_header_title overrides the oracle default massTitle."""
        from openms_insight.components.sequenceview import SequenceView

        sv = SequenceView(
            cache_id="test_sv_obsmass_title",
            sequence_data=observed_mass_sequence_data,
            peaks_data=sample_peaks_data,
            cache_path=str(temp_cache_dir),
            filters={"spectrum": "scan_id"},
            observed_mass_column="obs_mass",
            mass_header_title="Precursor",
        )
        seq = sv._prepare_vue_data({"spectrum": 1})["sequenceData"]
        assert seq["mass_header_title"] == "Precursor"

    def test_negative_observed_mass_still_emitted(
        self,
        temp_cache_dir: Path,
        observed_mass_sequence_data: pl.LazyFrame,
        sample_peaks_data: pl.LazyFrame,
    ):
        """A non-positive observed mass is still emitted (Vue renders '-')."""
        from openms_insight.components.sequenceview import SequenceView

        sv = SequenceView(
            cache_id="test_sv_obsmass_neg",
            sequence_data=observed_mass_sequence_data,
            peaks_data=sample_peaks_data,
            cache_path=str(temp_cache_dir),
            filters={"spectrum": "scan_id"},
            observed_mass_column="obs_mass",
        )
        seq = sv._prepare_vue_data({"spectrum": 2})["sequenceData"]
        assert seq["observed_mass"] == pytest.approx(-1.0)

    def test_no_observed_mass_when_unconfigured(
        self,
        temp_cache_dir: Path,
        sample_sequence_data: pl.LazyFrame,
        sample_peaks_data: pl.LazyFrame,
    ):
        """Back-compat: no observed_mass_column -> no header keys in payload."""
        from openms_insight.components.sequenceview import SequenceView

        sv = SequenceView(
            cache_id="test_sv_obsmass_off",
            sequence_data=sample_sequence_data,
            peaks_data=sample_peaks_data,
            cache_path=str(temp_cache_dir),
            filters={"spectrum": "scan_id"},
        )
        seq = sv._prepare_vue_data({"spectrum": 1})["sequenceData"]
        assert "observed_mass" not in seq
        assert "mass_header_title" not in seq

    def test_observed_mass_changes_hash(
        self,
        temp_cache_dir: Path,
        observed_mass_sequence_data: pl.LazyFrame,
        sample_peaks_data: pl.LazyFrame,
    ):
        """Different observed mass per state -> different data hash (re-render)."""
        from openms_insight.components.sequenceview import SequenceView

        sv = SequenceView(
            cache_id="test_sv_obsmass_hash",
            sequence_data=observed_mass_sequence_data,
            peaks_data=sample_peaks_data,
            cache_path=str(temp_cache_dir),
            filters={"spectrum": "scan_id"},
            observed_mass_column="obs_mass",
        )
        h1 = sv._prepare_vue_data({"spectrum": 1})["_hash"]
        h3 = sv._prepare_vue_data({"spectrum": 3})["_hash"]
        assert h1 != h3

    def test_get_observed_mass_for_state_unmatched(
        self,
        temp_cache_dir: Path,
        observed_mass_sequence_data: pl.LazyFrame,
        sample_peaks_data: pl.LazyFrame,
    ):
        """None-default filter with no selection -> None observed mass."""
        from openms_insight.components.sequenceview import SequenceView

        sv = SequenceView(
            cache_id="test_sv_obsmass_unmatched",
            sequence_data=observed_mass_sequence_data,
            peaks_data=sample_peaks_data,
            cache_path=str(temp_cache_dir),
            filters={"spectrum": "scan_id"},
            observed_mass_column="obs_mass",
        )
        assert sv._get_observed_mass_for_state({"spectrum": None}) is None

    def test_observed_mass_cache_roundtrip(
        self,
        temp_cache_dir: Path,
        observed_mass_sequence_data: pl.LazyFrame,
        sample_peaks_data: pl.LazyFrame,
    ):
        """Reconstruction restores observed_mass_column + mass_header_title."""
        from openms_insight.components.sequenceview import SequenceView

        cache_id = "test_sv_obsmass_cache"
        SequenceView(
            cache_id=cache_id,
            sequence_data=observed_mass_sequence_data,
            peaks_data=sample_peaks_data,
            cache_path=str(temp_cache_dir),
            filters={"spectrum": "scan_id"},
            observed_mass_column="obs_mass",
            mass_header_title="Precursor",
        )
        restored = SequenceView(cache_id=cache_id, cache_path=str(temp_cache_dir))
        assert restored._observed_mass_column == "obs_mass"
        assert restored._mass_header_title == "Precursor"
        seq = restored._prepare_vue_data({"spectrum": 1})["sequenceData"]
        assert seq["observed_mass"] == pytest.approx(955.45)
        assert seq["mass_header_title"] == "Precursor"

    def test_observed_mass_column_requires_sequence_data(
        self,
        temp_cache_dir: Path,
    ):
        """observed_mass_column is a config arg -> guarded in reconstruction mode."""
        from openms_insight.components.sequenceview import SequenceView

        with pytest.raises(CacheMissError):
            SequenceView(
                cache_id="test_sv_obsmass_guard",
                cache_path=str(temp_cache_dir),
                observed_mass_column="obs_mass",
            )


class TestSequenceViewInboundMassHighlight:
    """Args/contract tests for the inbound mass->fragment-row highlight identifier.

    The Vue store-listening behavior (resolve selection -> highlight row, default-
    OFF, no re-publish) is covered by the vitest spec
    ``SequenceView.massHeader.spec.ts``; here we cover the Python arg surface.
    """

    def test_mass_selection_identifier_in_args_when_set(
        self,
        temp_cache_dir: Path,
        sample_sequence_data: pl.LazyFrame,
        sample_peaks_data: pl.LazyFrame,
    ):
        """mass_selection_identifier flows into Vue args as massSelectionIdentifier."""
        from openms_insight.components.sequenceview import SequenceView

        sv = SequenceView(
            cache_id="test_sv_inbound_on",
            sequence_data=sample_sequence_data,
            peaks_data=sample_peaks_data,
            cache_path=str(temp_cache_dir),
            filters={"spectrum": "scan_id"},
            interactivity={"mass": "peak_id"},
            mass_selection_identifier="mass",
        )
        args = sv._get_component_args()
        assert args["massSelectionIdentifier"] == "mass"

    def test_mass_selection_identifier_absent_by_default(
        self,
        temp_cache_dir: Path,
        sample_sequence_data: pl.LazyFrame,
        sample_peaks_data: pl.LazyFrame,
    ):
        """Default-OFF: no mass_selection_identifier -> arg not emitted (back-compat)."""
        from openms_insight.components.sequenceview import SequenceView

        sv = SequenceView(
            cache_id="test_sv_inbound_off",
            sequence_data=sample_sequence_data,
            peaks_data=sample_peaks_data,
            cache_path=str(temp_cache_dir),
            filters={"spectrum": "scan_id"},
        )
        args = sv._get_component_args()
        assert "massSelectionIdentifier" not in args

    def test_mass_selection_identifier_cache_roundtrip(
        self,
        temp_cache_dir: Path,
        sample_sequence_data: pl.LazyFrame,
        sample_peaks_data: pl.LazyFrame,
    ):
        """Reconstruction from cache restores the inbound identifier."""
        from openms_insight.components.sequenceview import SequenceView

        cache_id = "test_sv_inbound_cache"
        SequenceView(
            cache_id=cache_id,
            sequence_data=sample_sequence_data,
            peaks_data=sample_peaks_data,
            cache_path=str(temp_cache_dir),
            filters={"spectrum": "scan_id"},
            mass_selection_identifier="mass",
        )
        restored = SequenceView(cache_id=cache_id, cache_path=str(temp_cache_dir))
        assert restored._mass_selection_identifier == "mass"
        assert restored._get_component_args()["massSelectionIdentifier"] == "mass"

    def test_mass_selection_identifier_requires_sequence_data(
        self,
        temp_cache_dir: Path,
    ):
        """mass_selection_identifier is a config arg -> guarded in reconstruction."""
        from openms_insight.components.sequenceview import SequenceView

        with pytest.raises(CacheMissError):
            SequenceView(
                cache_id="test_sv_inbound_guard",
                cache_path=str(temp_cache_dir),
                mass_selection_identifier="mass",
            )


# ---------------------------------------------------------------------------
# AMBIGUOUS residue (X) handling in the theoretical-mass + terminal-fragment
# computation (round-15 finding 3-seqview-007).
#
# The oracle FLASHApp strips X/x (`remove_ambigious`) before EVERY pyOpenMS mass
# call: once for the whole-sequence theoretical mass, and once PER prefix/suffix
# fragment (`getFragmentMassesWithSeq`). These tests reproduce the oracle
# numerically (independent verbatim port below) and assert the Insight
# theoretical mass + terminal fragments now MATCH the oracle exactly for an
# X-containing proteoform — while a clean control stays byte-unchanged.
# ---------------------------------------------------------------------------

pyopenms = pytest.importorskip("pyopenms")


def _oracle_remove_ambigious(protein):
    """Verbatim port of FLASHApp/src/render/sequence.py:remove_ambigious."""
    from pyopenms import AASequence

    return AASequence.fromString(
        protein.toUniModString().replace("X", "").replace("x", "")
    )


def _oracle_fragment_masses_with_seq(protein, res_type):
    """Verbatim port of FLASHApp getFragmentMassesWithSeq (one ion family)."""
    from pyopenms import Residue

    protein_length = protein.size()
    prefix_mass_list = [0.0] * protein_length
    suffix_mass_list = [0.0] * protein_length
    prefix_ion_type, suffix_ion_type = {
        "ax": (Residue.ResidueType.AIon, Residue.ResidueType.XIon),
        "by": (Residue.ResidueType.BIon, Residue.ResidueType.YIon),
        "cz": (Residue.ResidueType.CIon, Residue.ResidueType.ZIon),
    }[res_type]
    for aa_index in range(protein_length):
        prefix_mass_list[aa_index] = _oracle_remove_ambigious(
            protein.getPrefix(aa_index + 1)
        ).getMonoWeight(prefix_ion_type, 0)
    for aa_index in reversed(range(protein_length)):
        suffix_mass_list[aa_index] = _oracle_remove_ambigious(
            protein.getSuffix(aa_index + 1)
        ).getMonoWeight(suffix_ion_type, 0)
    return prefix_mass_list, suffix_mass_list


def _oracle_theoretical_mass(seq):
    """Oracle whole-sequence theoretical mass (remove_ambigious -> monoweight)."""
    from pyopenms import AASequence

    return _oracle_remove_ambigious(AASequence.fromString(seq)).getMonoWeight()


def _oracle_fragment_grid(seq):
    """Build the oracle per-position a/b/c/x/y/z grid for a sequence.

    Mirrors the Insight ``calculate_fragment_masses_pyopenms`` output shape
    (per-position ``number[][]``) so the two can be compared directly.
    """
    from pyopenms import AASequence

    p = AASequence.fromString(seq)
    grid = {}
    for it in ("ax", "by", "cz"):
        pre, suf = _oracle_fragment_masses_with_seq(p, it)
        grid[f"fragment_masses_{it[0]}"] = [[v] for v in pre]
        grid[f"fragment_masses_{it[1]}"] = [[v] for v in suf]
    return grid


class TestSequenceViewAmbiguousX:
    """X-residue handling: Insight must match the oracle's X-stripped masses."""

    def test_theoretical_mass_x_matches_oracle(self):
        """PEPTXIDEK theoretical mass == oracle (X-stripped PEPTIDEK), not 0.0."""
        from openms_insight.components.sequenceview import get_theoretical_mass

        got = get_theoretical_mass("PEPTXIDEK")
        oracle = _oracle_theoretical_mass("PEPTXIDEK")
        # Bug repro guard: the old code returned 0.0 here.
        assert got != 0.0
        assert got == oracle
        # X-stripped PEPTXIDEK is mass-equivalent to PEPTIDEK.
        assert got == get_theoretical_mass("PEPTIDEK")

    def test_fragment_masses_x_match_oracle_exact(self):
        """PEPTXIDEK terminal fragments == oracle getFragmentMassesWithSeq, exact."""
        from openms_insight.components.sequenceview import (
            calculate_fragment_masses_pyopenms,
        )

        got = calculate_fragment_masses_pyopenms("PEPTXIDEK")
        oracle = _oracle_fragment_grid("PEPTXIDEK")
        for ion in ("a", "b", "c", "x", "y", "z"):
            key = f"fragment_masses_{ion}"
            assert got[key] == oracle[key], f"{key} diverges from oracle"

    def test_fragment_grid_is_full_length(self):
        """The X grid keeps one entry per residue (full-length, X positions kept)."""
        from openms_insight.components.sequenceview import (
            calculate_fragment_masses_pyopenms,
        )

        got = calculate_fragment_masses_pyopenms("PEPTXIDEK")
        for ion in ("a", "b", "c", "x", "y", "z"):
            # 9 residues -> 9 positions, each a single-mass list.
            assert len(got[f"fragment_masses_{ion}"]) == 9
            assert all(len(p) == 1 for p in got[f"fragment_masses_{ion}"])

    def test_x_position_duplicates_neighbor_mass(self):
        """At the X position, the X-stripped prefix == its neighbour's prefix.

        For PEPTXIDEK the b-ion at the T (index 3) and at the X (index 4) are
        equal because removing X from 'PEPTX' yields 'PEPT' (oracle behaviour).
        """
        from openms_insight.components.sequenceview import (
            calculate_fragment_masses_pyopenms,
        )

        b = calculate_fragment_masses_pyopenms("PEPTXIDEK")["fragment_masses_b"]
        assert b[3] == b[4]

    def test_modified_x_sequence_matches_oracle(self):
        """A modification before X is preserved through the X-strip (oracle parity)."""
        from openms_insight.components.sequenceview import (
            calculate_fragment_masses_pyopenms,
            get_theoretical_mass,
        )

        seq = "PEPT(Phospho)XIDEK"
        assert get_theoretical_mass(seq) == _oracle_theoretical_mass(seq)
        got = calculate_fragment_masses_pyopenms(seq)
        oracle = _oracle_fragment_grid(seq)
        for ion in ("a", "b", "c", "x", "y", "z"):
            assert got[f"fragment_masses_{ion}"] == oracle[f"fragment_masses_{ion}"]

    @pytest.mark.parametrize(
        "seq",
        ["XPEPTIDEK", "PEPTIDEKX", "PXEPTXIDEXK", "XXPEPTIDEK", "PEPTXBIDEK"],
    )
    def test_x_variants_match_oracle(self, seq):
        """Leading/trailing/multi-X (and X+B) all match the oracle exactly.

        Leading/trailing X strips to an empty terminal sub-sequence whose
        getMonoWeight returns 0.0 (same as the oracle) — no exception, no
        all-empty degradation.
        """
        from openms_insight.components.sequenceview import (
            calculate_fragment_masses_pyopenms,
            get_theoretical_mass,
        )

        assert get_theoretical_mass(seq) == _oracle_theoretical_mass(seq)
        got = calculate_fragment_masses_pyopenms(seq)
        oracle = _oracle_fragment_grid(seq)
        for ion in ("a", "b", "c", "x", "y", "z"):
            assert got[f"fragment_masses_{ion}"] == oracle[f"fragment_masses_{ion}"]

    def test_clean_control_matches_full_oracle_grid(self):
        """Clean PEPTIDEK: the FULL grid (incl. the terminal ion) equals the oracle.

        Round-16 finding 3-seqview-008: the unified oracle path now populates the
        full-length terminal fragment ion (``b_L`` / ``y_L`` etc.) for clean
        sequences too, so EVERY grid position — not just ``1..L-1`` — equals the
        oracle's ``getFragmentMassesWithSeq`` value. (The former TSG path left the
        last position empty.)
        """
        from openms_insight.components.sequenceview import (
            calculate_fragment_masses_pyopenms,
        )

        got = calculate_fragment_masses_pyopenms("PEPTIDEK")
        oracle = _oracle_fragment_grid("PEPTIDEK")
        for ion in ("a", "b", "c", "x", "y", "z"):
            ins = got[f"fragment_masses_{ion}"]
            orc = oracle[f"fragment_masses_{ion}"]
            assert len(ins) == len(orc)
            # Every position is populated (no empty terminal cell) and matches.
            for pos_ins, pos_orc in zip(ins, orc):
                assert len(pos_ins) == len(pos_orc) == 1
                assert pos_ins[0] == pytest.approx(pos_orc[0], abs=1e-5)

    def test_clean_full_length_terminal_ion_present(self):
        """Clean PEPTIDEK now carries the full-length b_L / y_L terminal ion.

        Pins the 3-seqview-008 fix: the intact-proteoform prefix ion (``b_8`` at
        grid index 7 = C-terminal residue) and suffix ion (``y_8`` at grid index 7
        = ion number 8, which the Vue grid maps to residue 0) are populated and
        equal the oracle's full-length masses. (Previously both were ``[]``.)
        """
        from openms_insight.components.sequenceview import (
            calculate_fragment_masses_pyopenms,
        )

        got = calculate_fragment_masses_pyopenms("PEPTIDEK")
        oracle = _oracle_fragment_grid("PEPTIDEK")
        last = 7  # ion number 8 -> grid index 7
        for ion in ("a", "b", "c", "x", "y", "z"):
            assert got[f"fragment_masses_{ion}"][last] != []
            assert got[f"fragment_masses_{ion}"][last][0] == pytest.approx(
                oracle[f"fragment_masses_{ion}"][last][0], abs=1e-5
            )

    def test_clean_positions_1_to_Lminus1_unchanged_vs_tsg(self):
        """Clean sequences: grid positions 1..L-1 are byte-equal to the old TSG path.

        Back-compat proof for 3-seqview-008. We recompute the former
        ``TheoreticalSpectrumGenerator`` masses inline and assert the unified
        oracle path reproduces them EXACTLY for every populated non-terminal
        position (a/b/c/x/y/z) on several clean sequences (incl. a modified one).
        The ONLY new value is the full-length terminal ion at index ``L-1``.
        """
        from openms_insight.components.sequenceview import (
            calculate_fragment_masses_pyopenms,
        )
        from pyopenms import AASequence, MSSpectrum, TheoreticalSpectrumGenerator

        def _tsg_grid(seq):
            aa_seq = AASequence.fromString(seq)
            n = aa_seq.size()
            tsg = TheoreticalSpectrumGenerator()
            params = tsg.getParameters()
            for ion in ("a", "b", "c", "x", "y", "z"):
                params.setValue(f"add_{ion}_ions", "true")
            params.setValue("add_first_prefix_ion", "true")
            params.setValue("add_metainfo", "true")
            tsg.setParameters(params)
            spec = MSSpectrum()
            tsg.getSpectrum(spec, aa_seq, 1, 1)
            ion_types = ["a", "b", "c", "x", "y", "z"]
            grid = {f"fragment_masses_{i}": [[] for _ in range(n)] for i in ion_types}
            names = []
            for sda in spec.getStringDataArrays():
                if sda.getName() == "IonNames":
                    for i in range(sda.size()):
                        nm = sda[i]
                        names.append(nm.decode() if isinstance(nm, bytes) else nm)
                    break
            for i in range(spec.size()):
                nm = names[i] if i < len(names) else ""
                if not nm:
                    continue
                it = nm[0].lower()
                if it not in ion_types:
                    continue
                num = ""
                for ch in nm[1:]:
                    if ch.isdigit():
                        num += ch
                    else:
                        break
                if not num:
                    continue
                idx = int(num) - 1
                if 0 <= idx < n:
                    grid[f"fragment_masses_{it}"][idx].append(
                        spec[i].getMZ() - 1.007276
                    )
            return grid

        for seq in ("PEPTIDEK", "ACDEFGHK", "SHC(Carbamidomethyl)IAEVEK"):
            new = calculate_fragment_masses_pyopenms(seq)
            old = _tsg_grid(seq)
            n = AASequence.fromString(seq).size()
            for ion in ("a", "b", "c", "x", "y", "z"):
                for i in range(n - 1):  # 1..L-1 (grid indices 0..n-2)
                    o = old[f"fragment_masses_{ion}"][i]
                    g = new[f"fragment_masses_{ion}"][i]
                    if o:  # TSG populated this non-terminal position
                        assert len(g) == 1
                        assert g[0] == pytest.approx(o[0], abs=1e-6), (
                            f"{seq} {ion} pos {i} changed vs TSG"
                        )


class TestSequenceViewNonAmbiguousResidues:
    """Edge sweep: the oracle strips ONLY X/x; B/Z/J/U/O must pass through.

    The oracle's ``remove_ambigious`` deletes nothing but X/x, so B (Asx), Z
    (Glx), J (Leu/Ile), U (Sec) and O (Pyl) are left for pyOpenMS to weigh. They
    contain no X, so the Insight code takes the byte-unchanged pyOpenMS path; the
    theoretical mass must match the oracle's (no over-stripping).
    """

    @pytest.mark.parametrize(
        "seq",
        ["PEPTBIDEK", "PEPTZIDEK", "PEPTJIDEK", "PEPTUIDEK", "PEPTOIDEK"],
    )
    def test_non_x_residue_theoretical_matches_oracle(self, seq):
        from openms_insight.components.sequenceview import get_theoretical_mass

        got = get_theoretical_mass(seq)
        oracle = _oracle_theoretical_mass(seq)
        # pyOpenMS accepts these residues -> a real (non-zero) mass, == oracle.
        assert got != 0.0
        assert got == oracle

    @pytest.mark.parametrize(
        "seq",
        ["PEPTBIDEK", "PEPTJIDEK", "PEPTUIDEK", "PEPTOIDEK"],
    )
    def test_non_x_residue_fragments_match_oracle_populated(self, seq):
        """Populated terminal positions equal the oracle for B/J/U/O too."""
        from openms_insight.components.sequenceview import (
            calculate_fragment_masses_pyopenms,
        )

        got = calculate_fragment_masses_pyopenms(seq)
        oracle = _oracle_fragment_grid(seq)
        for ion in ("a", "b", "c", "x", "y", "z"):
            ins = got[f"fragment_masses_{ion}"]
            orc = oracle[f"fragment_masses_{ion}"]
            for pos_ins, pos_orc in zip(ins, orc):
                if pos_ins:
                    assert pos_ins[0] == pytest.approx(pos_orc[0], abs=1e-5)

    def test_empty_sequence_safe(self):
        """Empty sequence -> 0.0 theoretical + all-empty fragments (no error)."""
        from openms_insight.components.sequenceview import (
            calculate_fragment_masses_pyopenms,
            get_theoretical_mass,
        )

        assert get_theoretical_mass("") == 0.0
        frags = calculate_fragment_masses_pyopenms("")
        for ion in ("a", "b", "c", "x", "y", "z"):
            assert frags[f"fragment_masses_{ion}"] == []
