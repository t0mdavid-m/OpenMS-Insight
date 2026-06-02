"""Tests for Table custom column formatter wiring (Item A parity).

Verifies that named registry formatters (`fixed`, `placeholder`) are carried
through the Table API as JSON-serializable column-definition dicts:

- `column_definitions` with `formatter` (string name) + `formatterParams`
  survive `_get_component_args()` unchanged.
- They round-trip through the on-disk cache (manifest.json is JSON, so the
  formatter MUST stay a string, never an inline JS function) and are restored
  identically when a Table is reconstructed from cache only.
- The chainable ergonomic helpers `with_fixed_format` / `with_placeholder`
  set the expected `formatter` / `formatterParams` on the matching column.

The JS side (formatters.ts `customFormatters` registry + TabulatorTable.vue
name->function resolution) is covered by the strict vue-tsc build; these tests
lock the Python contract that feeds it.
"""

import json
from pathlib import Path

import polars as pl
import pytest

from openms_insight import Table


# Column definitions exercising both new named formatters. The `fixed` formatter
# reproduces the oracle toFixedFormatter (guarded toFixed); `placeholder`
# reproduces the inline `-1 -> '-'` sentinel substitution.
FORMATTER_COLUMN_DEFS = [
    {"field": "id", "title": "ID", "sorter": "number"},
    {
        "field": "mass",
        "title": "Monoisotopic mass",
        "sorter": "number",
        "formatter": "fixed",
        "formatterParams": {"precision": 4, "minLength": 4},
    },
    {
        "field": "qvalue",
        "title": "Q-Value",
        "sorter": "number",
        "formatter": "placeholder",
        "formatterParams": {"sentinels": [-1], "text": "-", "loose": True},
    },
]


@pytest.fixture
def formatter_table_data() -> pl.LazyFrame:
    """Small frame with the columns referenced by FORMATTER_COLUMN_DEFS."""
    return pl.LazyFrame(
        {
            "id": [1, 2, 3, 4],
            "mass": [12.0, 1234.56789, 1.5, -1.0],
            "qvalue": [0.01, -1.0, 0.5, -1.0],
        }
    )


def _find_col(column_defs, field):
    """Return the column-definition dict for `field` (or None)."""
    for col in column_defs:
        if col.get("field") == field:
            return col
    return None


class TestNamedFormatterArgs:
    """Named formatters survive serialization to Vue component args."""

    def test_component_args_carry_named_formatters(
        self, mock_streamlit, temp_cache_dir, formatter_table_data
    ):
        """columnDefinitions in _get_component_args carry formatter name + params."""
        table = Table(
            cache_id="test_fmt_args",
            data=formatter_table_data,
            cache_path=str(temp_cache_dir),
            column_definitions=[dict(c) for c in FORMATTER_COLUMN_DEFS],
        )

        column_defs = table._get_component_args()["columnDefinitions"]

        mass_col = _find_col(column_defs, "mass")
        assert mass_col is not None
        # Formatter MUST remain a string (registry name), not a function/object.
        assert mass_col["formatter"] == "fixed"
        assert isinstance(mass_col["formatter"], str)
        assert mass_col["formatterParams"] == {"precision": 4, "minLength": 4}

        q_col = _find_col(column_defs, "qvalue")
        assert q_col is not None
        assert q_col["formatter"] == "placeholder"
        assert q_col["formatterParams"] == {
            "sentinels": [-1],
            "text": "-",
            "loose": True,
        }

    def test_column_definitions_are_json_serializable(
        self, mock_streamlit, temp_cache_dir, formatter_table_data
    ):
        """The full columnDefinitions payload is JSON-serializable end-to-end.

        This is the load-bearing constraint: the cache layer json.dump()s the
        config, so an inline JS-function formatter would break. A string name +
        plain-dict params must serialize cleanly.
        """
        table = Table(
            cache_id="test_fmt_json",
            data=formatter_table_data,
            cache_path=str(temp_cache_dir),
            column_definitions=[dict(c) for c in FORMATTER_COLUMN_DEFS],
        )

        column_defs = table._get_component_args()["columnDefinitions"]

        # Round-trips through JSON with identical content.
        reencoded = json.loads(json.dumps(column_defs))
        assert _find_col(reencoded, "mass")["formatter"] == "fixed"
        assert _find_col(reencoded, "qvalue")["formatter"] == "placeholder"


class TestNamedFormatterCacheRoundTrip:
    """Named formatters survive a full write/reload through the disk cache."""

    def test_manifest_persists_formatter_strings(
        self, mock_streamlit, temp_cache_dir, formatter_table_data
    ):
        """manifest.json stores the formatter names verbatim (proves JSON-safe)."""
        cache_id = "test_fmt_manifest"
        Table(
            cache_id=cache_id,
            data=formatter_table_data,
            cache_path=str(temp_cache_dir),
            column_definitions=[dict(c) for c in FORMATTER_COLUMN_DEFS],
        )

        manifest_path = Path(temp_cache_dir) / cache_id / "manifest.json"
        with open(manifest_path) as f:
            manifest = json.load(f)

        cached_defs = manifest["config"]["column_definitions"]
        assert _find_col(cached_defs, "mass")["formatter"] == "fixed"
        assert _find_col(cached_defs, "mass")["formatterParams"] == {
            "precision": 4,
            "minLength": 4,
        }
        assert _find_col(cached_defs, "qvalue")["formatter"] == "placeholder"

    def test_reconstructed_table_preserves_named_formatters(
        self, mock_streamlit, temp_cache_dir, formatter_table_data
    ):
        """Reconstruct from cache only; named formatters + params are unchanged."""
        cache_id = "test_fmt_reconstruct"

        original = Table(
            cache_id=cache_id,
            data=formatter_table_data,
            cache_path=str(temp_cache_dir),
            column_definitions=[dict(c) for c in FORMATTER_COLUMN_DEFS],
        )
        original_defs = original._get_component_args()["columnDefinitions"]

        # Reconstruct from ONLY cache_id + cache_path (canonical reconstruction).
        reconstructed = Table(
            cache_id=cache_id,
            cache_path=str(temp_cache_dir),
        )
        reconstructed_defs = reconstructed._get_component_args()["columnDefinitions"]

        # Formatter wiring is identical across the cache boundary.
        assert _find_col(reconstructed_defs, "mass")["formatter"] == "fixed"
        assert (
            _find_col(reconstructed_defs, "mass")["formatterParams"]
            == _find_col(original_defs, "mass")["formatterParams"]
        )
        assert _find_col(reconstructed_defs, "qvalue")["formatter"] == "placeholder"
        assert (
            _find_col(reconstructed_defs, "qvalue")["formatterParams"]
            == _find_col(original_defs, "qvalue")["formatterParams"]
        )


class TestFormatterHelpers:
    """The chainable ergonomic helpers set the expected formatter + params."""

    def test_with_fixed_format_defaults(
        self, mock_streamlit, temp_cache_dir, formatter_table_data
    ):
        """with_fixed_format() defaults reproduce toFixedFormatter() (4 dp, len>4)."""
        table = Table(
            cache_id="test_fmt_helper_fixed",
            data=formatter_table_data,
            cache_path=str(temp_cache_dir),
            # No formatter set initially; helper applies it.
            column_definitions=[
                {"field": "id", "title": "ID"},
                {"field": "mass", "title": "Mass"},
                {"field": "qvalue", "title": "Q"},
            ],
        )

        returned = table.with_fixed_format("mass")
        # Chainable: returns self.
        assert returned is table

        mass_col = _find_col(table._column_definitions, "mass")
        assert mass_col["formatter"] == "fixed"
        assert mass_col["formatterParams"] == {"precision": 4, "minLength": 4}

    def test_with_fixed_format_custom_params(
        self, mock_streamlit, temp_cache_dir, formatter_table_data
    ):
        """with_fixed_format honors precision and min_length overrides."""
        table = Table(
            cache_id="test_fmt_helper_fixed_custom",
            data=formatter_table_data,
            cache_path=str(temp_cache_dir),
            column_definitions=[{"field": "mass", "title": "Mass"}],
        )

        table.with_fixed_format("mass", precision=2, min_length=0)

        mass_col = _find_col(table._column_definitions, "mass")
        assert mass_col["formatterParams"] == {"precision": 2, "minLength": 0}

    def test_with_placeholder_defaults(
        self, mock_streamlit, temp_cache_dir, formatter_table_data
    ):
        """with_placeholder() defaults reproduce the inline -1 -> '-' formatter."""
        table = Table(
            cache_id="test_fmt_helper_placeholder",
            data=formatter_table_data,
            cache_path=str(temp_cache_dir),
            column_definitions=[{"field": "qvalue", "title": "Q"}],
        )

        returned = table.with_placeholder("qvalue")
        assert returned is table

        q_col = _find_col(table._column_definitions, "qvalue")
        assert q_col["formatter"] == "placeholder"
        # sentinels normalized from tuple default to a (JSON-serializable) list.
        assert q_col["formatterParams"] == {
            "sentinels": [-1],
            "text": "-",
            "loose": True,
        }

    def test_with_placeholder_custom_params(
        self, mock_streamlit, temp_cache_dir, formatter_table_data
    ):
        """with_placeholder honors custom sentinels/text/loose."""
        table = Table(
            cache_id="test_fmt_helper_placeholder_custom",
            data=formatter_table_data,
            cache_path=str(temp_cache_dir),
            column_definitions=[{"field": "qvalue", "title": "Q"}],
        )

        table.with_placeholder("qvalue", sentinels=(0, -1), text="n/a", loose=False)

        q_col = _find_col(table._column_definitions, "qvalue")
        assert q_col["formatterParams"] == {
            "sentinels": [0, -1],
            "text": "n/a",
            "loose": False,
        }

    def test_helper_params_are_json_serializable(
        self, mock_streamlit, temp_cache_dir, formatter_table_data
    ):
        """Params set by helpers stay JSON-serializable (cache-safe)."""
        table = Table(
            cache_id="test_fmt_helper_json",
            data=formatter_table_data,
            cache_path=str(temp_cache_dir),
            column_definitions=[
                {"field": "mass", "title": "Mass"},
                {"field": "qvalue", "title": "Q"},
            ],
        )

        table.with_fixed_format("mass").with_placeholder("qvalue")

        # Must not raise.
        encoded = json.dumps(table._column_definitions)
        decoded = json.loads(encoded)
        assert _find_col(decoded, "mass")["formatter"] == "fixed"
        assert _find_col(decoded, "qvalue")["formatter"] == "placeholder"
