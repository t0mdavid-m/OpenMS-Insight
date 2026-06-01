"""Tests for SequenceView component behavior."""

from pathlib import Path

import polars as pl


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


class TestSequenceViewExtensions:
    """Tests for coverage coloring, fixed mods, and ion_types (FLASHApp parity)."""

    def _seq_df_with_coverage(self):
        import polars as pl

        return pl.LazyFrame(
            {
                "proteoform_index": [0, 1],
                "sequence": ["PEPTIDER", "ACDEFGHK"],
                "precursor_charge": [2, 3],
                "coverage": [[0.0, 1.0, 2.0, 2.0, 1.0, 0.0, 0.0, 0.0], [0.0] * 8],
                "max_coverage": [2.0, 0.0],
            }
        )

    def test_fixed_modifications_emitted(self, temp_cache_dir, sample_sequence_data):
        from openms_insight.components.sequenceview import SequenceView

        sv = SequenceView(
            cache_id="sv_fixedmod",
            sequence_data=sample_sequence_data,
            filters={"spectrum": "scan_id"},
            fixed_modifications=["C", "M"],
            cache_path=str(temp_cache_dir),
        )
        df = sample_sequence_data.collect()
        state = {"spectrum": df["scan_id"][0]}
        out = sv._prepare_vue_data(state)
        assert out["sequenceData"]["fixed_modifications"] == ["C", "M"]

    def test_ion_types_emitted(self, temp_cache_dir, sample_sequence_data):
        from openms_insight.components.sequenceview import SequenceView

        sv = SequenceView(
            cache_id="sv_iontypes",
            sequence_data=sample_sequence_data,
            filters={"spectrum": "scan_id"},
            annotation_config={"ion_types": ["c", "z"]},
            cache_path=str(temp_cache_dir),
        )
        df = sample_sequence_data.collect()
        out = sv._prepare_vue_data({"spectrum": df["scan_id"][0]})
        assert out["sequenceData"]["ion_types"] == ["c", "z"]

    def test_coverage_emitted_when_selected(self, temp_cache_dir):
        from openms_insight.components.sequenceview import SequenceView

        sv = SequenceView(
            cache_id="sv_cov",
            sequence_data=self._seq_df_with_coverage(),
            filters={"proteinIndex": "proteoform_index"},
            coverage_column="coverage",
            max_coverage_column="max_coverage",
            cache_path=str(temp_cache_dir),
        )
        out = sv._prepare_vue_data({"proteinIndex": 0})
        sd = out["sequenceData"]
        assert "coverage" in sd
        assert len(sd["coverage"]) == 8
        assert sd["maxCoverage"] == 2.0

    def test_coverage_absent_when_not_configured(
        self, temp_cache_dir, sample_sequence_data
    ):
        from openms_insight.components.sequenceview import SequenceView

        sv = SequenceView(
            cache_id="sv_nocov",
            sequence_data=sample_sequence_data,
            filters={"spectrum": "scan_id"},
            cache_path=str(temp_cache_dir),
        )
        df = sample_sequence_data.collect()
        out = sv._prepare_vue_data({"spectrum": df["scan_id"][0]})
        assert "coverage" not in out["sequenceData"]

    def test_coverage_survives_cache_reconstruction(self, temp_cache_dir):
        from openms_insight.components.sequenceview import SequenceView

        SequenceView(
            cache_id="sv_cov_recon",
            sequence_data=self._seq_df_with_coverage(),
            filters={"proteinIndex": "proteoform_index"},
            coverage_column="coverage",
            max_coverage_column="max_coverage",
            fixed_modifications=["C"],
            cache_path=str(temp_cache_dir),
        )
        sv2 = SequenceView(cache_id="sv_cov_recon", cache_path=str(temp_cache_dir))
        assert sv2._coverage_column == "coverage"
        assert sv2._fixed_modifications == ["C"]
        out = sv2._prepare_vue_data({"proteinIndex": 0})
        assert out["sequenceData"]["coverage"][2] == 2.0
        assert out["sequenceData"]["fixed_modifications"] == ["C"]
