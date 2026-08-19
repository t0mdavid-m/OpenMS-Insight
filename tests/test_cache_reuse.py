"""A cache_id must identify one (data, config) pair -- constructing it twice reuses it.

Creation mode used to re-run `_preprocess()` and rewrite every Parquet file on every
construction, consulting the cache only in reconstruction mode. Under Streamlit that
means a full rebuild on every rerun: for a 608k-point heatmap, ~4.9 MB rewritten each
time a user clicks anything, which is both the dominant cost of an interaction and the
trigger for concurrent writes to files polars has memory-mapped.

The reuse key is a hash of the configuration *as passed in*, captured before
preprocessing runs. It cannot be the existing `config_hash`, which is computed after
`_preprocess()` and therefore contains values preprocessing derived -- Table's
auto-detected `column_definitions`, Heatmap's auto-computed `x_bins`/`y_bins`.
"""

from __future__ import annotations

import json
from pathlib import Path

import polars as pl
import pytest

from openms_insight import Heatmap, LinePlot, Table


@pytest.fixture
def count_preprocess(monkeypatch):
    """Count `_preprocess()` calls on a component class."""

    def install(cls):
        calls = {"n": 0}
        original = cls._preprocess

        def counting(self):
            calls["n"] += 1
            return original(self)

        monkeypatch.setattr(cls, "_preprocess", counting)
        return calls

    return install


def _manifest(cache_dir: Path, cache_id: str) -> dict:
    return json.loads((cache_dir / cache_id / "manifest.json").read_text())


class TestCreationModeReusesCache:
    def test_second_identical_construction_does_not_preprocess(
        self, mock_streamlit, temp_cache_dir, sample_table_data, count_preprocess
    ):
        calls = count_preprocess(Table)

        def build():
            return Table(
                cache_id="reuse",
                data=sample_table_data,
                cache_path=str(temp_cache_dir),
                index_field="id",
            )

        build()
        assert calls["n"] == 1

        build()
        assert calls["n"] == 1, "identical config must reuse the cache on disk"

    def test_reused_component_serves_the_same_data(
        self, mock_streamlit, temp_cache_dir, sample_table_data
    ):
        first = Table(
            cache_id="reuse_data",
            data=sample_table_data,
            cache_path=str(temp_cache_dir),
            index_field="id",
        )
        expected = first._prepare_vue_data({})

        second = Table(
            cache_id="reuse_data",
            data=sample_table_data,
            cache_path=str(temp_cache_dir),
            index_field="id",
        )
        actual = second._prepare_vue_data({})

        assert actual["tableData"].equals(expected["tableData"])
        assert actual["_hash"] == expected["_hash"]

    def test_cache_files_are_not_rewritten(
        self, mock_streamlit, temp_cache_dir, sample_table_data
    ):
        Table(
            cache_id="untouched",
            data=sample_table_data,
            cache_path=str(temp_cache_dir),
            index_field="id",
        )
        parquet = temp_cache_dir / "untouched" / "preprocessed" / "data.parquet"
        before = parquet.stat().st_mtime_ns

        Table(
            cache_id="untouched",
            data=sample_table_data,
            cache_path=str(temp_cache_dir),
            index_field="id",
        )

        assert parquet.stat().st_mtime_ns == before


class TestCacheIsRebuiltWhenItMust:
    def test_changed_config_rebuilds(
        self, mock_streamlit, temp_cache_dir, sample_lineplot_data, count_preprocess
    ):
        calls = count_preprocess(LinePlot)

        LinePlot(
            cache_id="config_change",
            data=sample_lineplot_data,
            cache_path=str(temp_cache_dir),
            x_column="mass",
            y_column="intensity",
        )
        assert calls["n"] == 1

        LinePlot(
            cache_id="config_change",
            data=sample_lineplot_data,
            cache_path=str(temp_cache_dir),
            x_column="intensity",  # different
            y_column="mass",
        )
        assert calls["n"] == 2

    def test_changed_filters_rebuild(
        self, mock_streamlit, temp_cache_dir, sample_table_data, count_preprocess
    ):
        calls = count_preprocess(Table)

        Table(
            cache_id="filter_change",
            data=sample_table_data,
            cache_path=str(temp_cache_dir),
            index_field="id",
        )
        Table(
            cache_id="filter_change",
            data=sample_table_data,
            cache_path=str(temp_cache_dir),
            index_field="id",
            filters={"spectrum": "id"},
        )

        assert calls["n"] == 2

    def test_regenerate_cache_forces_a_rebuild(
        self, mock_streamlit, temp_cache_dir, sample_table_data, count_preprocess
    ):
        """The documented meaning of the flag, which was previously inert."""
        calls = count_preprocess(Table)

        Table(
            cache_id="forced",
            data=sample_table_data,
            cache_path=str(temp_cache_dir),
            index_field="id",
        )
        Table(
            cache_id="forced",
            data=sample_table_data,
            cache_path=str(temp_cache_dir),
            index_field="id",
            regenerate_cache=True,
        )

        assert calls["n"] == 2

    def test_cache_without_input_hash_is_rebuilt(
        self, mock_streamlit, temp_cache_dir, sample_table_data, count_preprocess
    ):
        """Caches written by older versions carry no reuse key; rebuild rather than
        guess that they match."""
        calls = count_preprocess(Table)

        Table(
            cache_id="legacy",
            data=sample_table_data,
            cache_path=str(temp_cache_dir),
            index_field="id",
        )
        manifest_path = temp_cache_dir / "legacy" / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        del manifest["input_config_hash"]
        manifest_path.write_text(json.dumps(manifest))

        Table(
            cache_id="legacy",
            data=sample_table_data,
            cache_path=str(temp_cache_dir),
            index_field="id",
        )

        assert calls["n"] == 2

    def test_corrupt_manifest_is_rebuilt(
        self, mock_streamlit, temp_cache_dir, sample_table_data, count_preprocess
    ):
        calls = count_preprocess(Table)

        Table(
            cache_id="corrupt",
            data=sample_table_data,
            cache_path=str(temp_cache_dir),
            index_field="id",
        )
        (temp_cache_dir / "corrupt" / "manifest.json").write_text("{ not json")

        Table(
            cache_id="corrupt",
            data=sample_table_data,
            cache_path=str(temp_cache_dir),
            index_field="id",
        )

        assert calls["n"] == 2


class TestPreprocessingDerivedConfig:
    """The reuse key must be computable *before* preprocessing runs.

    Several components overwrite their own config during `_preprocess()`. If the key
    were taken from `_get_cache_config()` after the fact, it could never match on the
    next construction and the cache would rebuild forever.
    """

    def test_heatmap_auto_computed_bins_do_not_defeat_reuse(
        self, mock_streamlit, temp_cache_dir, sample_heatmap_data, count_preprocess
    ):
        calls = count_preprocess(Heatmap)

        def build():
            return Heatmap(
                cache_id="bins",
                data=sample_heatmap_data,
                cache_path=str(temp_cache_dir),
                x_column="retention_time",
                y_column="mz",
                intensity_column="intensity",
            )

        first = build()
        assert first._x_bins is not None and first._x_bins > 0

        second = build()

        assert calls["n"] == 1
        # Derived values come back from the manifest, not from a fresh computation.
        assert second._x_bins == first._x_bins
        assert second._y_bins == first._y_bins

    def test_table_auto_detected_columns_do_not_defeat_reuse(
        self, mock_streamlit, temp_cache_dir, sample_table_data, count_preprocess
    ):
        calls = count_preprocess(Table)

        def build():
            return Table(
                cache_id="autocols",
                data=sample_table_data,
                cache_path=str(temp_cache_dir),
                index_field="id",
            )

        first = build()
        assert first._column_definitions

        second = build()

        assert calls["n"] == 1
        assert second._column_definitions == first._column_definitions

    def test_explicit_bins_still_distinguish_caches(
        self, mock_streamlit, temp_cache_dir, sample_heatmap_data, count_preprocess
    ):
        """Auto-computed bins must not mask a bin size the caller actually asked for."""
        calls = count_preprocess(Heatmap)

        def build(x_bins):
            return Heatmap(
                cache_id="explicit_bins",
                data=sample_heatmap_data,
                cache_path=str(temp_cache_dir),
                x_column="retention_time",
                y_column="mz",
                intensity_column="intensity",
                x_bins=x_bins,
                y_bins=20,
            )

        build(50)
        build(50)
        assert calls["n"] == 1

        build(80)
        assert calls["n"] == 2


class TestManifest:
    def test_manifest_records_the_input_hash(
        self, mock_streamlit, temp_cache_dir, sample_table_data
    ):
        Table(
            cache_id="manifest_field",
            data=sample_table_data,
            cache_path=str(temp_cache_dir),
            index_field="id",
        )

        manifest = _manifest(temp_cache_dir, "manifest_field")

        assert manifest["input_config_hash"]
        # It is deliberately not the post-preprocess hash: that one contains values
        # preprocessing derived and so cannot be recomputed before preprocessing.
        assert manifest["input_config_hash"] != manifest["config_hash"]


class TestReconstructionModeUnchanged:
    def test_reconstruction_still_works(
        self, mock_streamlit, temp_cache_dir, sample_table_data
    ):
        Table(
            cache_id="recon",
            data=sample_table_data,
            cache_path=str(temp_cache_dir),
            index_field="id",
            interactivity={"row": "id"},
        )

        restored = Table(cache_id="recon", cache_path=str(temp_cache_dir))

        assert restored._interactivity == {"row": "id"}
        assert restored._index_field == "id"


class TestDataPathReuse:
    def test_warm_cache_skips_the_subprocess(
        self, mock_streamlit, temp_cache_dir, sample_table_data, monkeypatch
    ):
        """Spawning a process only to discover there is nothing to do costs ~1.3 s."""
        data_path = temp_cache_dir / "src.parquet"
        sample_table_data.collect().write_parquet(data_path)

        Table(
            cache_id="viapath",
            data_path=str(data_path),
            cache_path=str(temp_cache_dir),
            index_field="id",
        )

        spawned = {"n": 0}
        import openms_insight.core.subprocess_preprocess as sp

        original = sp.preprocess_component

        def counting(*args, **kwargs):
            spawned["n"] += 1
            return original(*args, **kwargs)

        monkeypatch.setattr(sp, "preprocess_component", counting)

        Table(
            cache_id="viapath",
            data_path=str(data_path),
            cache_path=str(temp_cache_dir),
            index_field="id",
        )

        assert spawned["n"] == 0

    def test_regenerate_cache_reaches_the_child(
        self, mock_streamlit, temp_cache_dir, sample_table_data, monkeypatch
    ):
        """The parent decides to rebuild; the child must not re-apply the guard and
        decide otherwise, or regenerate_cache would silently do nothing."""
        data_path = temp_cache_dir / "src2.parquet"
        sample_table_data.collect().write_parquet(data_path)

        Table(
            cache_id="viapath_force",
            data_path=str(data_path),
            cache_path=str(temp_cache_dir),
            index_field="id",
        )

        captured = {}
        import openms_insight.core.subprocess_preprocess as sp

        def capture(component_class, **kwargs):
            captured.update(kwargs)

        monkeypatch.setattr(sp, "preprocess_component", capture)

        Table(
            cache_id="viapath_force",
            data_path=str(data_path),
            cache_path=str(temp_cache_dir),
            index_field="id",
            regenerate_cache=True,
        )

        assert captured.get("regenerate_cache") is True


class TestSequenceViewReuse:
    """SequenceView does not inherit BaseComponent and repeats the defect on its own,
    so a fix in base.py does not reach it."""

    @pytest.fixture
    def count_create_cache(self, monkeypatch):
        from openms_insight import SequenceView

        calls = {"n": 0}
        original = SequenceView._create_cache

        def counting(self):
            calls["n"] += 1
            return original(self)

        monkeypatch.setattr(SequenceView, "_create_cache", counting)
        return calls

    def test_second_identical_construction_reuses_cache(
        self, mock_streamlit, temp_cache_dir, count_create_cache
    ):
        from openms_insight import SequenceView

        def build():
            return SequenceView(
                cache_id="sv_reuse",
                sequence_data=("PEPTIDEK", 2),
                cache_path=str(temp_cache_dir),
            )

        build()
        assert count_create_cache["n"] == 1

        build()
        assert count_create_cache["n"] == 1

    def test_changed_peptide_rebuilds(
        self, mock_streamlit, temp_cache_dir, count_create_cache
    ):
        """The sequence is this component's data, and it is cheap enough to hash --
        a changed peptide under an unchanged cache_id is the likeliest mistake here."""
        from openms_insight import SequenceView

        SequenceView(
            cache_id="sv_peptide",
            sequence_data=("PEPTIDEK", 2),
            cache_path=str(temp_cache_dir),
        )
        second = SequenceView(
            cache_id="sv_peptide",
            sequence_data=("ELVISLIVESK", 2),
            cache_path=str(temp_cache_dir),
        )

        assert count_create_cache["n"] == 2
        sequences = second._cached_sequences.collect()
        assert sequences["sequence"].to_list() == ["ELVISLIVESK"]

    def test_changed_charge_rebuilds(
        self, mock_streamlit, temp_cache_dir, count_create_cache
    ):
        from openms_insight import SequenceView

        SequenceView(
            cache_id="sv_charge",
            sequence_data=("PEPTIDEK", 2),
            cache_path=str(temp_cache_dir),
        )
        SequenceView(
            cache_id="sv_charge",
            sequence_data=("PEPTIDEK", 3),
            cache_path=str(temp_cache_dir),
        )

        assert count_create_cache["n"] == 2

    def test_changed_annotation_config_rebuilds(
        self, mock_streamlit, temp_cache_dir, count_create_cache
    ):
        from openms_insight import SequenceView

        SequenceView(
            cache_id="sv_ann",
            sequence_data=("PEPTIDEK", 2),
            cache_path=str(temp_cache_dir),
            annotation_config={"ion_types": ["b", "y"]},
        )
        SequenceView(
            cache_id="sv_ann",
            sequence_data=("PEPTIDEK", 2),
            cache_path=str(temp_cache_dir),
            annotation_config={"ion_types": ["c", "z"]},
        )

        assert count_create_cache["n"] == 2

    def test_regenerate_cache_forces_a_rebuild(
        self, mock_streamlit, temp_cache_dir, count_create_cache
    ):
        from openms_insight import SequenceView

        SequenceView(
            cache_id="sv_force",
            sequence_data=("PEPTIDEK", 2),
            cache_path=str(temp_cache_dir),
        )
        SequenceView(
            cache_id="sv_force",
            sequence_data=("PEPTIDEK", 2),
            cache_path=str(temp_cache_dir),
            regenerate_cache=True,
        )

        assert count_create_cache["n"] == 2

    def test_reconstruction_still_works(self, mock_streamlit, temp_cache_dir):
        from openms_insight import SequenceView

        SequenceView(
            cache_id="sv_recon",
            sequence_data=("PEPTIDEK", 2),
            cache_path=str(temp_cache_dir),
            title="A peptide",
        )

        restored = SequenceView(cache_id="sv_recon", cache_path=str(temp_cache_dir))

        assert restored._title == "A peptide"


class TestDataFreshnessContract:
    def test_changed_data_under_same_id_and_config_is_not_detected(
        self, mock_streamlit, temp_cache_dir, count_preprocess
    ):
        """Pin the contract's cost so it is a decision, not a surprise.

        A cache_id identifies one (data, config) pair. Config is hashed; the data
        behind a LazyFrame cannot be without collecting it, which is the expense the
        cache exists to avoid. New data therefore needs a new cache_id or
        regenerate_cache=True.
        """
        calls = count_preprocess(Table)
        first = pl.LazyFrame({"id": [1, 2], "name": ["a", "b"]})
        second = pl.LazyFrame({"id": [3, 4], "name": ["c", "d"]})

        Table(
            cache_id="stale",
            data=first,
            cache_path=str(temp_cache_dir),
            index_field="id",
        )
        reused = Table(
            cache_id="stale",
            data=second,
            cache_path=str(temp_cache_dir),
            index_field="id",
        )

        assert calls["n"] == 1
        assert reused._prepare_vue_data({})["tableData"]["id"].tolist() == [1, 2]

        refreshed = Table(
            cache_id="stale",
            data=second,
            cache_path=str(temp_cache_dir),
            index_field="id",
            regenerate_cache=True,
        )
        assert refreshed._prepare_vue_data({})["tableData"]["id"].tolist() == [3, 4]
