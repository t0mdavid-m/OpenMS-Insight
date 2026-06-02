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


class TestSequenceViewPositionInteractivity:
    """Residue-position interactivity (``interactivity={"AApos": "<position>"}``).

    The 0-based residue index is emitted by the Vue on a residue click; the
    Python side advertises the identifier->sentinel mapping (so the bridge
    forwards the emitted value) and must round-trip it through the cache. With
    the sentinel mapping set, an emitted index round-trips via the StateManager;
    without it, the component args/mapping are unchanged.
    """

    def test_position_sentinel_value(self):
        from openms_insight.components.sequenceview import POSITION_SENTINEL

        # The exact sentinel the caller uses and the Vue matches against.
        assert POSITION_SENTINEL == "<position>"

    def test_position_interactivity_in_component_args(
        self, temp_cache_dir, sample_sequence_data, sample_peaks_data
    ):
        from openms_insight.components.sequenceview import (
            POSITION_SENTINEL,
            SequenceView,
        )

        sv = SequenceView(
            cache_id="sv_aapos_args",
            sequence_data=sample_sequence_data,
            peaks_data=sample_peaks_data,
            filters={"spectrum": "scan_id"},
            interactivity={"AApos": POSITION_SENTINEL},
            cache_path=str(temp_cache_dir),
        )
        args = sv._get_component_args()
        # Interactivity (incl. the position sentinel) reaches the Vue args.
        assert args["interactivity"] == {"AApos": POSITION_SENTINEL}
        assert sv.get_interactivity_mapping() == {"AApos": POSITION_SENTINEL}

    def test_position_index_round_trips_via_state(
        self, temp_cache_dir, sample_sequence_data, sample_peaks_data
    ):
        from openms_insight.components.sequenceview import (
            POSITION_SENTINEL,
            SequenceView,
        )
        from openms_insight.core.state import StateManager

        sv = SequenceView(
            cache_id="sv_aapos_roundtrip",
            sequence_data=sample_sequence_data,
            peaks_data=sample_peaks_data,
            filters={"spectrum": "scan_id"},
            interactivity={"AApos": POSITION_SENTINEL},
            cache_path=str(temp_cache_dir),
        )
        # AApos is an emitted (not a filter) identifier, so it must not appear in
        # the data-affecting state dependencies (it does not refilter the view).
        assert "AApos" not in sv.get_state_dependencies()

        # Simulate the Vue emitting the clicked residue's 0-based index for the
        # mapped identifier; it must round-trip unchanged through the state.
        sm = StateManager()
        for clicked_index in (0, 3, 7):
            sm.set_selection("AApos", clicked_index)
            assert sm.get_selection("AApos") == clicked_index

    def test_position_interactivity_survives_cache_reconstruction(
        self, temp_cache_dir, sample_sequence_data, sample_peaks_data
    ):
        from openms_insight.components.sequenceview import (
            POSITION_SENTINEL,
            SequenceView,
        )

        SequenceView(
            cache_id="sv_aapos_recon",
            sequence_data=sample_sequence_data,
            peaks_data=sample_peaks_data,
            filters={"spectrum": "scan_id"},
            interactivity={"AApos": POSITION_SENTINEL},
            cache_path=str(temp_cache_dir),
        )
        sv2 = SequenceView(cache_id="sv_aapos_recon", cache_path=str(temp_cache_dir))
        assert sv2.get_interactivity_mapping() == {"AApos": POSITION_SENTINEL}
        assert sv2._get_component_args()["interactivity"] == {
            "AApos": POSITION_SENTINEL
        }

    def test_without_position_interactivity_unchanged(
        self, temp_cache_dir, sample_sequence_data, sample_peaks_data
    ):
        from openms_insight.components.sequenceview import SequenceView

        # No interactivity configured -> args carry no interactivity key and the
        # mapping stays empty (byte-identical to pre-feature behavior).
        sv = SequenceView(
            cache_id="sv_aapos_off",
            sequence_data=sample_sequence_data,
            peaks_data=sample_peaks_data,
            filters={"spectrum": "scan_id"},
            cache_path=str(temp_cache_dir),
        )
        args = sv._get_component_args()
        assert "interactivity" not in args
        assert sv.get_interactivity_mapping() == {}

    def test_peak_interactivity_still_works(
        self, temp_cache_dir, sample_sequence_data, sample_peaks_data
    ):
        from openms_insight.components.sequenceview import SequenceView

        # Legacy peak-id interactivity is unaffected by the new feature: a
        # non-sentinel column keeps mapping through to the Vue args as before.
        sv = SequenceView(
            cache_id="sv_peak_only",
            sequence_data=sample_sequence_data,
            peaks_data=sample_peaks_data,
            filters={"spectrum": "scan_id"},
            interactivity={"peak": "peak_id"},
            cache_path=str(temp_cache_dir),
        )
        assert sv._get_component_args()["interactivity"] == {"peak": "peak_id"}


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


class TestSequenceViewMassHeaderAndFragments:
    """Mass header + precomputed fragment masses (FLASHTnT visual parity)."""

    def _proteoform_df(self):
        """Two proteoforms with header masses and per-residue fragment masses.

        Fragment mass columns use the legacy ``list[list[float]]`` shape
        (outer = residue, inner = modification-ambiguity variants, length 1).
        """
        return pl.LazyFrame(
            {
                "proteoform_index": [0, 1],
                "sequence": ["PEPTIDER", "ACDEFGHK"],
                "precursor_charge": [2, 3],
                "theo_mass": [955.46, 879.36],
                "obs_mass": [955.50, 879.40],
                # 8 residues each; one variant per residue.
                "frag_b": [
                    [
                        [97.05],
                        [226.09],
                        [323.14],
                        [424.19],
                        [537.27],
                        [652.30],
                        [781.34],
                        [896.37],
                    ],
                    [
                        [71.04],
                        [174.05],
                        [289.07],
                        [418.12],
                        [565.18],
                        [622.20],
                        [759.26],
                        [887.36],
                    ],
                ],
                "frag_y": [
                    [
                        [175.12],
                        [290.14],
                        [403.23],
                        [504.27],
                        [605.32],
                        [702.37],
                        [831.41],
                        [928.47],
                    ],
                    [
                        [147.11],
                        [275.17],
                        [332.19],
                        [469.25],
                        [598.29],
                        [713.32],
                        [816.33],
                        [919.34],
                    ],
                ],
            }
        )

    def test_header_masses_emitted_when_configured(self, temp_cache_dir):
        from openms_insight.components.sequenceview import SequenceView

        sv = SequenceView(
            cache_id="sv_header",
            sequence_data=self._proteoform_df(),
            filters={"proteinIndex": "proteoform_index"},
            theoretical_mass_column="theo_mass",
            observed_mass_column="obs_mass",
            cache_path=str(temp_cache_dir),
        )
        out = sv._prepare_vue_data({"proteinIndex": 0})
        sd = out["sequenceData"]
        # Scalar mass columns are downcast to Float32 by optimize_for_transfer
        # (display rounds to 2 decimals), so compare with tolerance.
        assert sd["theoretical_mass"] == pytest.approx(955.46, abs=1e-2)
        assert sd["observed_mass"] == pytest.approx(955.50, abs=1e-2)
        # Precursor mass is now populated from the observed proteoform mass.
        assert out["precursorMass"] == pytest.approx(955.50, abs=1e-2)

    def test_header_masses_absent_when_not_configured(
        self, temp_cache_dir, sample_sequence_data
    ):
        from openms_insight.components.sequenceview import SequenceView

        sv = SequenceView(
            cache_id="sv_noheader",
            sequence_data=sample_sequence_data,
            filters={"spectrum": "scan_id"},
            cache_path=str(temp_cache_dir),
        )
        df = sample_sequence_data.collect()
        out = sv._prepare_vue_data({"spectrum": df["scan_id"][0]})
        sd = out["sequenceData"]
        # No observed_mass key, and precursor mass keeps legacy 0.0 default.
        assert "observed_mass" not in sd
        assert out["precursorMass"] == 0.0

    def test_precomputed_fragment_masses_emitted(self, temp_cache_dir):
        from openms_insight.components.sequenceview import SequenceView

        sv = SequenceView(
            cache_id="sv_precomp",
            sequence_data=self._proteoform_df(),
            filters={"proteinIndex": "proteoform_index"},
            fragment_mass_columns={"b": "frag_b", "y": "frag_y"},
            cache_path=str(temp_cache_dir),
        )
        out = sv._prepare_vue_data({"proteinIndex": 0})
        sd = out["sequenceData"]
        assert "precomputed_fragment_masses" in sd
        pf = sd["precomputed_fragment_masses"]
        assert set(pf.keys()) == {"b", "y"}
        # Normalized to list[list[float]] (outer=residue, inner=variants).
        assert pf["b"][0] == [97.05]
        assert pf["y"][2] == [403.23]
        assert len(pf["b"]) == 8

    def test_precomputed_fragments_absent_when_not_configured(
        self, temp_cache_dir, sample_sequence_data
    ):
        from openms_insight.components.sequenceview import SequenceView

        sv = SequenceView(
            cache_id="sv_noprecomp",
            sequence_data=sample_sequence_data,
            filters={"spectrum": "scan_id"},
            cache_path=str(temp_cache_dir),
        )
        df = sample_sequence_data.collect()
        out = sv._prepare_vue_data({"spectrum": df["scan_id"][0]})
        assert "precomputed_fragment_masses" not in out["sequenceData"]

    def test_flat_fragment_masses_are_wrapped(self, temp_cache_dir):
        from openms_insight.components.sequenceview import SequenceView

        # Flat list[float] (one mass per residue) must be wrapped per residue.
        flat_df = pl.LazyFrame(
            {
                "proteoform_index": [0],
                "sequence": ["PEP"],
                "precursor_charge": [1],
                "frag_b": [[97.05, 226.09, 323.14]],
            }
        )
        sv = SequenceView(
            cache_id="sv_flatfrag",
            sequence_data=flat_df,
            filters={"proteinIndex": "proteoform_index"},
            fragment_mass_columns={"b": "frag_b"},
            cache_path=str(temp_cache_dir),
        )
        out = sv._prepare_vue_data({"proteinIndex": 0})
        pf = out["sequenceData"]["precomputed_fragment_masses"]
        assert pf["b"] == [[97.05], [226.09], [323.14]]

    def test_existing_recompute_unchanged_when_params_none(
        self, temp_cache_dir, sample_sequence_data
    ):
        from openms_insight.components.sequenceview import SequenceView

        sv = SequenceView(
            cache_id="sv_recompute",
            sequence_data=sample_sequence_data,
            filters={"spectrum": "scan_id"},
            cache_path=str(temp_cache_dir),
        )
        df = sample_sequence_data.collect()
        out = sv._prepare_vue_data({"spectrum": df["scan_id"][0]})
        sd = out["sequenceData"]
        # Recompute path still populates the pyOpenMS-derived fragment arrays.
        assert "fragment_masses_b" in sd
        assert "fragment_masses_y" in sd
        assert "precomputed_fragment_masses" not in sd

    def test_header_and_fragments_survive_cache_reconstruction(self, temp_cache_dir):
        from openms_insight.components.sequenceview import SequenceView

        SequenceView(
            cache_id="sv_header_recon",
            sequence_data=self._proteoform_df(),
            filters={"proteinIndex": "proteoform_index"},
            theoretical_mass_column="theo_mass",
            observed_mass_column="obs_mass",
            fragment_mass_columns={"b": "frag_b", "y": "frag_y"},
            cache_path=str(temp_cache_dir),
        )
        sv2 = SequenceView(cache_id="sv_header_recon", cache_path=str(temp_cache_dir))
        assert sv2._theoretical_mass_column == "theo_mass"
        assert sv2._observed_mass_column == "obs_mass"
        assert sv2._fragment_mass_columns == {"b": "frag_b", "y": "frag_y"}
        out = sv2._prepare_vue_data({"proteinIndex": 1})
        sd = out["sequenceData"]
        assert sd["theoretical_mass"] == pytest.approx(879.36, abs=1e-2)
        assert sd["observed_mass"] == pytest.approx(879.40, abs=1e-2)
        # Nested-list fragment masses keep full Float64 precision (not downcast).
        assert sd["precomputed_fragment_masses"]["y"][0] == [147.11]


class TestSequenceViewProteoformWindow:
    """Proteoform truncation window + per-residue modification override (FLASHTnT)."""

    def _data(self) -> pl.LazyFrame:
        # PEPTIDER (length 8); proteoform window = residues 1..5 inclusive; a
        # +79.97 mod at residue index 2. The modifications array is FULL length.
        return pl.LazyFrame(
            {
                "scan_id": [1],
                "sequence": ["PEPTIDER"],
                "precursor_charge": [2],
                "pf_start": [1],
                "pf_end": [5],
                "mods": [[None, None, 79.97, None, None, None, None, None]],
            }
        )

    def test_proteoform_window_and_mods_in_vue_data(self, temp_cache_dir: Path):
        from openms_insight.components.sequenceview import SequenceView

        sv = SequenceView(
            cache_id="test_sv_pf",
            sequence_data=self._data(),
            cache_path=str(temp_cache_dir),
            filters={"identification": "scan_id"},
            proteoform_start_column="pf_start",
            proteoform_end_column="pf_end",
            modifications_column="mods",
        )
        sd = sv._prepare_vue_data({"identification": 1})["sequenceData"]
        assert sd["proteoform_start"] == 1
        assert sd["proteoform_end"] == 5
        # The per-residue modification array overrides the parsed (all-null) one.
        assert sd["modifications"][2] == pytest.approx(79.97)
        assert sd["modifications"][0] is None
        assert len(sd["modifications"]) == len("PEPTIDER")

    def test_window_and_mods_survive_cache_reconstruction(self, temp_cache_dir: Path):
        from openms_insight.components.sequenceview import SequenceView

        SequenceView(
            cache_id="test_sv_pf_recon",
            sequence_data=self._data(),
            cache_path=str(temp_cache_dir),
            filters={"identification": "scan_id"},
            proteoform_start_column="pf_start",
            proteoform_end_column="pf_end",
            modifications_column="mods",
        )
        sv2 = SequenceView(cache_id="test_sv_pf_recon", cache_path=str(temp_cache_dir))
        sd = sv2._prepare_vue_data({"identification": 1})["sequenceData"]
        assert sd["proteoform_start"] == 1 and sd["proteoform_end"] == 5
        assert sd["modifications"][2] == pytest.approx(79.97)
