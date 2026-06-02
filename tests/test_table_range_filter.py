"""Tests for the Table ``range_filters`` (range-containment) feature.

Replicates the legacy FLASHApp Tag-Table client-side filter where clicking a
sequence residue narrows the tags to those whose [StartPos, EndPos] span contains
the clicked residue position (``StartPos <= selectedAApos <= EndPos``). The OI
Table implements this server-side, reactive on the selected scalar in state.
"""

import polars as pl

from openms_insight import Table


def _tag_frame() -> pl.LazyFrame:
    """Tag-like frame with protein-absolute StartPos/EndPos (0-based)."""
    return pl.LazyFrame(
        {
            "TagIndex": [0, 1, 2, 3, 4],
            "StartPos": [7, 110, 117, 135, 137],
            "EndPos": [12, 114, 121, 140, 142],
            "TagSequence": ["AAAAAA", "WGQGT", "TVSSA", "STSGGT", "STSGGT"],
        }
    )


class TestRangeFilter:
    def test_no_selection_returns_all_rows(self, mock_streamlit, temp_cache_dir):
        """A None selection is a no-op (all rows pass), mirroring the legacy
        unfiltered Tag Table when no residue is selected."""
        table = Table(
            cache_id="rf_none",
            data=_tag_frame(),
            cache_path=str(temp_cache_dir),
            index_field="TagIndex",
            range_filters={"selectedAApos": ("StartPos", "EndPos")},
            pagination=False,
        )
        result = table._prepare_vue_data({})
        assert len(result["tableData"]) == 5
        result_explicit_none = table._prepare_vue_data({"selectedAApos": None})
        assert len(result_explicit_none) and len(result_explicit_none["tableData"]) == 5

    def test_containment_filters_to_spanning_rows(self, mock_streamlit, temp_cache_dir):
        """For a chosen residue P, only tags with StartPos<=P<=EndPos pass."""
        table = Table(
            cache_id="rf_contain",
            data=_tag_frame(),
            cache_path=str(temp_cache_dir),
            index_field="TagIndex",
            range_filters={"selectedAApos": ("StartPos", "EndPos")},
            pagination=False,
        )

        # P=138 is inside [135,140] (TagIndex 3) and [137,142] (TagIndex 4) only.
        df = table._prepare_vue_data({"selectedAApos": 138})["tableData"]
        assert sorted(df["TagIndex"].tolist()) == [3, 4]

        # P=111 is inside [110,114] only.
        df = table._prepare_vue_data({"selectedAApos": 111})["tableData"]
        assert df["TagIndex"].tolist() == [1]

        # Inclusive endpoints: P == StartPos and P == EndPos both match.
        assert table._prepare_vue_data({"selectedAApos": 7})["tableData"][
            "TagIndex"
        ].tolist() == [0]
        assert table._prepare_vue_data({"selectedAApos": 12})["tableData"][
            "TagIndex"
        ].tolist() == [0]

        # P=200 covered by no tag -> empty.
        assert len(table._prepare_vue_data({"selectedAApos": 200})["tableData"]) == 0

    def test_float_selection_value_matches_int_columns(
        self, mock_streamlit, temp_cache_dir
    ):
        """JS numbers arrive as floats; a float position still matches int cols."""
        table = Table(
            cache_id="rf_float",
            data=_tag_frame(),
            cache_path=str(temp_cache_dir),
            index_field="TagIndex",
            range_filters={"selectedAApos": ("StartPos", "EndPos")},
            pagination=False,
        )
        df = table._prepare_vue_data({"selectedAApos": 138.0})["tableData"]
        assert sorted(df["TagIndex"].tolist()) == [3, 4]

    def test_range_filter_state_dependency(self, mock_streamlit, temp_cache_dir):
        """The range-filter identifier is a state dependency so a residue click
        re-renders the table."""
        table = Table(
            cache_id="rf_deps",
            data=_tag_frame(),
            cache_path=str(temp_cache_dir),
            index_field="TagIndex",
            range_filters={"selectedAApos": ("StartPos", "EndPos")},
        )
        assert "selectedAApos" in table.get_state_dependencies()

    def test_range_filter_survives_cache_reconstruction(
        self, mock_streamlit, temp_cache_dir
    ):
        """range_filters round-trips through the cache manifest (reconstruction
        mode) so a subprocess-recreated Table still filters by containment."""
        Table(
            cache_id="rf_reload",
            data=_tag_frame(),
            cache_path=str(temp_cache_dir),
            index_field="TagIndex",
            range_filters={"selectedAApos": ("StartPos", "EndPos")},
            pagination=False,
        )
        reloaded = Table(cache_id="rf_reload", cache_path=str(temp_cache_dir))
        assert "selectedAApos" in reloaded.get_state_dependencies()
        df = reloaded._prepare_vue_data({"selectedAApos": 138})["tableData"]
        assert sorted(df["TagIndex"].tolist()) == [3, 4]

    def test_range_filter_combines_with_value_filter(
        self, mock_streamlit, temp_cache_dir
    ):
        """A value filter and a range filter compose (legacy: proteoform filter
        AND residue-span filter both apply to the Tag Table)."""
        data = pl.LazyFrame(
            {
                "TagIndex": [0, 1, 2, 3],
                "proteoform_index": [0, 0, 1, 1],
                "StartPos": [135, 137, 135, 137],
                "EndPos": [140, 142, 140, 142],
            }
        )
        table = Table(
            cache_id="rf_combo",
            data=data,
            cache_path=str(temp_cache_dir),
            index_field="TagIndex",
            filters={"proteinIndex": "proteoform_index"},
            range_filters={"selectedAApos": ("StartPos", "EndPos")},
            pagination=False,
        )
        # proteoform 1 AND residue 138 (inside both rows of proteoform 1).
        df = table._prepare_vue_data({"proteinIndex": 1, "selectedAApos": 138})[
            "tableData"
        ]
        assert sorted(df["TagIndex"].tolist()) == [2, 3]
        # residue 136 only inside StartPos<=136 rows (135..140) -> TagIndex 2.
        df = table._prepare_vue_data({"proteinIndex": 1, "selectedAApos": 136})[
            "tableData"
        ]
        assert df["TagIndex"].tolist() == [2]
