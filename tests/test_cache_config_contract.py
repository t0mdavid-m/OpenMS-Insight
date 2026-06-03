"""Contract test: cache config must include all configuration parameters.

This test ensures that _get_cache_config() and _restore_cache_config() handle
all component parameters that affect behavior, preventing bugs where parameters
are lost when reconstructing from cache.
"""

import json

import pytest

from openms_insight import Heatmap, Table


class TestHeatmapCacheConfig:
    """Test that Heatmap cache config includes all necessary parameters."""

    def test_cache_config_includes_log_scale(
        self, mock_streamlit, temp_cache_dir, sample_heatmap_data
    ):
        """log_scale must be stored and restored from cache."""
        # Create with non-default value
        heatmap = Heatmap(
            cache_id="test_heatmap_log_scale",
            data=sample_heatmap_data,
            cache_path=str(temp_cache_dir),
            x_column="retention_time",
            y_column="mz",
            intensity_column="intensity",
            log_scale=False,  # Non-default (default is True)
        )

        # Verify it's in cache config
        config = heatmap._get_cache_config()
        assert "log_scale" in config, "log_scale missing from cache config"
        assert config["log_scale"] is False

        # Verify restoration works
        heatmap2 = Heatmap(
            cache_id="test_heatmap_log_scale_restore",
            data=sample_heatmap_data,
            cache_path=str(temp_cache_dir),
            x_column="retention_time",
            y_column="mz",
            intensity_column="intensity",
        )
        heatmap2._restore_cache_config(config)
        assert heatmap2._log_scale is False, "log_scale not restored from cache"

    def test_cache_config_includes_intensity_label(
        self, mock_streamlit, temp_cache_dir, sample_heatmap_data
    ):
        """intensity_label must be stored (render config) and restored from cache.

        intensity_label is a presentation param: it lives in the RENDER config
        (stored in the manifest, excluded from the cache-key hash) rather than the
        hash-affecting cache config.
        """
        # Create with non-default value
        heatmap = Heatmap(
            cache_id="test_heatmap_intensity_label",
            data=sample_heatmap_data,
            cache_path=str(temp_cache_dir),
            x_column="retention_time",
            y_column="mz",
            intensity_column="intensity",
            intensity_label="Score",  # Non-default (default is None)
        )

        # Presentation param: in the render config, NOT the hash-affecting config
        render_config = heatmap._get_render_config()
        assert "intensity_label" in render_config
        assert render_config["intensity_label"] == "Score"
        assert "intensity_label" not in heatmap._get_cache_config()
        # But it IS in the stored (union) config persisted to the manifest
        assert heatmap._get_stored_config()["intensity_label"] == "Score"

        # Verify restoration works via the render-config restore hook
        heatmap2 = Heatmap(
            cache_id="test_heatmap_intensity_label_restore",
            data=sample_heatmap_data,
            cache_path=str(temp_cache_dir),
            x_column="retention_time",
            y_column="mz",
            intensity_column="intensity",
        )
        heatmap2._restore_render_config(render_config)
        assert heatmap2._intensity_label == "Score", (
            "intensity_label not restored from cache"
        )

    def test_cache_config_roundtrip_preserves_all_params(
        self, mock_streamlit, temp_cache_dir, sample_heatmap_data
    ):
        """All config params (data-shaping + presentation) survive save/restore.

        Data-shaping params live in the cache config (hashed); presentation params
        live in the render config (stored, not hashed). The union ``stored``
        config is what is persisted to the manifest; restoring it via BOTH restore
        hooks reproduces every value.
        """
        # Create with various non-default values
        heatmap = Heatmap(
            cache_id="test_heatmap_roundtrip",
            data=sample_heatmap_data,
            cache_path=str(temp_cache_dir),
            x_column="retention_time",
            y_column="mz",
            intensity_column="intensity",
            min_points=5000,
            title="Test Heatmap",
            x_label="RT (min)",
            y_label="m/z",
            colorscale="Viridis",
            reversescale=True,
            log_scale=False,
            intensity_label="Score",
        )

        # The full (union) config persisted to the manifest
        stored = heatmap._get_stored_config()

        # Create new instance and restore via both hooks (as _load_from_cache does)
        heatmap2 = Heatmap(
            cache_id="test_heatmap_roundtrip2",
            data=sample_heatmap_data,
            cache_path=str(temp_cache_dir),
            x_column="retention_time",
            y_column="mz",
            intensity_column="intensity",
        )
        heatmap2._restore_cache_config(stored)
        heatmap2._restore_render_config(stored)

        # Verify data-shaping params restored
        assert heatmap2._min_points == 5000
        assert heatmap2._log_scale is False
        # Verify presentation params restored
        assert heatmap2._title == "Test Heatmap"
        assert heatmap2._x_label == "RT (min)"
        assert heatmap2._y_label == "m/z"
        assert heatmap2._colorscale == "Viridis"
        assert heatmap2._reversescale is True
        assert heatmap2._intensity_label == "Score"

        # Presentation params must NOT be hash-affecting
        cache_config = heatmap._get_cache_config()
        for key in ("title", "x_label", "y_label", "colorscale", "reversescale",
                    "intensity_label"):
            assert key not in cache_config, f"{key} must not be hash-affecting"


class TestCacheConfigCompleteness:
    """Test that _get_cache_config keys match _restore_cache_config handling."""

    @pytest.mark.parametrize(
        "ComponentClass,data_fixture,extra_kwargs",
        [
            (
                Heatmap,
                "sample_heatmap_data",
                {
                    "x_column": "retention_time",
                    "y_column": "mz",
                    "intensity_column": "intensity",
                },
            ),
        ],
    )
    def test_all_cache_config_keys_are_restored(
        self,
        mock_streamlit,
        temp_cache_dir,
        request,
        ComponentClass,
        data_fixture,
        extra_kwargs,
    ):
        """Every key in _get_cache_config should be handled by _restore_cache_config."""
        data = request.getfixturevalue(data_fixture)

        component = ComponentClass(
            cache_id=f"test_{ComponentClass.__name__}_cache_keys",
            data=data,
            cache_path=str(temp_cache_dir),
            **extra_kwargs,
        )

        config = component._get_cache_config()

        # Create fresh instance
        component2 = ComponentClass(
            cache_id=f"test_{ComponentClass.__name__}_cache_keys2",
            data=data,
            cache_path=str(temp_cache_dir),
            **extra_kwargs,
        )

        # Restore config
        component2._restore_cache_config(config)

        # Get config again - should match original
        config2 = component2._get_cache_config()

        # All keys from original config should be in restored config
        for key in config:
            assert key in config2, f"Key '{key}' not restored by _restore_cache_config"
            assert config[key] == config2[key], (
                f"Key '{key}' value mismatch after restore"
            )


class TestHeatmapReversescaleRoundtrip:
    """BUG FIX: reversescale must round-trip through full cache reconstruction.

    Previously reversescale was applied at creation time but never persisted /
    restored, so a heatmap built with reversescale=True silently reverted to
    False when later reconstructed from cache only (cache_id/cache_path) — a
    Phase-1 parity break for the e-value / "bright = best" recipe.
    """

    def test_reversescale_roundtrips_through_reconstruction(
        self, mock_streamlit, temp_cache_dir, sample_heatmap_data
    ):
        cache_id = "test_heatmap_reversescale_roundtrip"

        # Create with reversescale=True (non-default)
        original = Heatmap(
            cache_id=cache_id,
            data=sample_heatmap_data,
            cache_path=str(temp_cache_dir),
            x_column="retention_time",
            y_column="mz",
            intensity_column="intensity",
            min_points=100,
            reversescale=True,
        )
        assert original._reversescale is True
        assert original._get_component_args()["reversescale"] is True

        # The manifest must persist reversescale so reconstruction can restore it
        manifest_path = temp_cache_dir / cache_id / "manifest.json"
        with open(manifest_path) as f:
            manifest = json.load(f)
        assert manifest["config"]["reversescale"] is True

        # Reconstruct from ONLY cache_id + cache_path (no data, no config)
        reconstructed = Heatmap(cache_id=cache_id, cache_path=str(temp_cache_dir))

        # Bug fix: reversescale survives reconstruction
        assert reconstructed._reversescale is True, (
            "reversescale lost on cache reconstruction"
        )
        assert reconstructed._get_component_args()["reversescale"] is True


class TestHeatmapCategoryColorsRoundtrip:
    """BUG FIX: category_colors must round-trip through cache reconstruction.

    category_colors is render-time styling (correctly excluded from the cache
    hash), but it was neither stored in ``_get_render_config()`` nor restored in
    ``_restore_render_config()``, so a heatmap built with a custom categorical
    palette silently reverted to default Plotly colors (``_category_colors={}``)
    when later reconstructed from cache only (cache_id/cache_path) — the same
    parity-break class as the reversescale bug. Mirrors Plot3D, which stores +
    restores category_colors.
    """

    def test_category_colors_roundtrips_through_reconstruction(
        self, mock_streamlit, temp_cache_dir, sample_categorical_heatmap_data
    ):
        cache_id = "test_heatmap_category_colors_roundtrip"
        custom_colors = {
            "Control": "#0000FF",
            "Treatment_A": "#FF0000",
            "Treatment_B": "#00FF00",
        }

        # Create with a custom categorical palette (non-default)
        original = Heatmap(
            cache_id=cache_id,
            data=sample_categorical_heatmap_data,
            cache_path=str(temp_cache_dir),
            x_column="retention_time",
            y_column="mz",
            intensity_column="intensity",
            category_column="sample_group",
            category_colors=custom_colors,
            min_points=100,
        )
        assert original._category_colors == custom_colors
        assert original._get_component_args()["categoryColors"] == custom_colors

        # category_colors lives in render config (persisted), NOT cache config.
        assert "category_colors" not in original._get_cache_config()
        assert original._get_render_config()["category_colors"] == custom_colors

        # The manifest must persist category_colors so reconstruction can restore it
        manifest_path = temp_cache_dir / cache_id / "manifest.json"
        with open(manifest_path) as f:
            manifest = json.load(f)
        assert manifest["config"]["category_colors"] == custom_colors

        # Reconstruct from ONLY cache_id + cache_path (no data, no config)
        reconstructed = Heatmap(cache_id=cache_id, cache_path=str(temp_cache_dir))

        # Bug fix: category_colors survives reconstruction (no revert to {})
        assert reconstructed._category_colors == custom_colors, (
            "category_colors lost on cache reconstruction"
        )
        assert (
            reconstructed._get_component_args()["categoryColors"] == custom_colors
        )


class TestHeatmapDownsampleEnum:
    """The downsample enum collapses the two legacy strategy booleans.

    The legacy ``use_streaming`` / ``use_simple_downsample`` booleans are kept as
    deprecated aliases (honored when explicitly set), and old caches that stored
    the booleans still restore correctly.
    """

    def test_enum_maps_to_internal_booleans(self):
        resolve = Heatmap._resolve_downsample_name
        to_bools = Heatmap._downsample_to_booleans

        # Enum -> internal dispatch booleans (unchanged code paths)
        assert to_bools("streaming") == (True, False)
        assert to_bools("eager") == (False, False)
        assert to_bools("simple") == (False, True)

        # Enum passthrough when no deprecated boolean is set
        assert resolve("streaming", None, None) == "streaming"
        assert resolve("eager", None, None) == "eager"
        assert resolve("simple", None, None) == "simple"

    def test_deprecated_booleans_take_precedence(self):
        resolve = Heatmap._resolve_downsample_name
        # Legacy matrix preserved: simple wins; else streaming toggles streaming/eager
        assert resolve("streaming", None, True) == "simple"
        assert resolve("streaming", True, None) == "streaming"
        assert resolve("streaming", False, None) == "eager"
        # An explicit boolean overrides a conflicting enum value
        assert resolve("eager", True, False) == "streaming"

    def test_invalid_enum_raises(self):
        with pytest.raises(ValueError, match="downsample must be"):
            Heatmap._resolve_downsample_name("nope", None, None)

    def test_old_cache_booleans_restore_to_enum(
        self, mock_streamlit, temp_cache_dir, sample_heatmap_data
    ):
        """A cache written before the rename (booleans, no 'downsample') restores."""
        heatmap = Heatmap(
            cache_id="test_hm_downsample_oldcache",
            data=sample_heatmap_data,
            cache_path=str(temp_cache_dir),
            x_column="retention_time",
            y_column="mz",
            intensity_column="intensity",
            min_points=100,
        )
        # Simulate an old manifest config (no 'downsample' key)
        old_config = {
            "x_column": "retention_time",
            "y_column": "mz",
            "intensity_column": "intensity",
            "use_streaming": False,
            "use_simple_downsample": True,
        }
        heatmap._restore_cache_config(old_config)
        assert heatmap._downsample == "simple"
        assert heatmap._use_streaming is False
        assert heatmap._use_simple_downsample is True


class TestPresentationParamsDoNotInvalidateCache:
    """Changing a presentation-only param must NOT change the cache-key hash.

    Presentation params live in the render config (stored, not hashed); only
    data-shaping params feed _compute_config_hash(). So two heatmaps that differ
    only in title/labels/colorscale/reversescale share the same config hash and
    do not trigger a (potentially million-point) cache rebuild.
    """

    def test_presentation_change_keeps_same_config_hash(
        self, mock_streamlit, temp_cache_dir, sample_heatmap_data
    ):
        base_kwargs = dict(
            data=sample_heatmap_data,
            cache_path=str(temp_cache_dir),
            x_column="retention_time",
            y_column="mz",
            intensity_column="intensity",
            min_points=100,
            # Pin the state-routing zoom_identifier so the two instances differ
            # ONLY in presentation params. (The default is auto-derived from
            # cache_id — a per-instance state key, not a data-shaping param.)
            zoom_identifier="shared_zoom",
        )

        plain = Heatmap(cache_id="test_hm_hash_plain", **base_kwargs)
        # Differ ONLY in presentation params
        styled = Heatmap(
            cache_id="test_hm_hash_styled",
            title="Pretty",
            x_label="RT",
            y_label="m/z",
            colorscale="Viridis",
            reversescale=True,
            intensity_label="Score",
            **base_kwargs,
        )

        assert plain._compute_config_hash() == styled._compute_config_hash(), (
            "presentation-only change must not alter the cache-key hash"
        )

        # Sanity: a data-shaping change DOES alter the hash
        reshaped = Heatmap(
            cache_id="test_hm_hash_reshaped",
            **{**base_kwargs, "min_points": 250},
        )
        assert plain._compute_config_hash() != reshaped._compute_config_hash(), (
            "data-shaping change must alter the cache-key hash"
        )


class TestTableTitleRenderConfig:
    """Table ``title`` is presentation-only — render config, not hash-affecting.

    Previously ``title`` lived in Table's ``_get_cache_config()`` (the lone D1
    holdout among the plot components), so changing it needlessly invalidated the
    potentially large table cache. It now lives in ``_get_render_config()``
    (stored in the manifest, excluded from the cache-key hash) — mirroring
    heatmap/mirrorplot/volcanoplot.
    """

    def test_title_is_render_config_not_cache_config(
        self, mock_streamlit, temp_cache_dir, sample_table_data
    ):
        """title is in the render config, NOT the hash-affecting cache config."""
        table = Table(
            cache_id="test_table_title_render_config",
            data=sample_table_data,
            cache_path=str(temp_cache_dir),
            title="Peaks",  # Non-default (default is None)
        )

        render_config = table._get_render_config()
        assert "title" in render_config
        assert render_config["title"] == "Peaks"
        # Must NOT be hash-affecting
        assert "title" not in table._get_cache_config()
        # But IS in the stored (union) config persisted to the manifest
        assert table._get_stored_config()["title"] == "Peaks"

    def test_title_change_keeps_same_config_hash(
        self, mock_streamlit, temp_cache_dir, sample_table_data
    ):
        """Two tables differing ONLY in title share the same cache-key hash."""
        base_kwargs = dict(
            data=sample_table_data,
            cache_path=str(temp_cache_dir),
            # Pin the state-routing pagination_identifier so the two instances
            # differ ONLY in title. (Its default is auto-derived from cache_id —
            # a per-instance state key, not a data-shaping param.)
            pagination_identifier="shared_page",
        )

        plain = Table(cache_id="test_table_hash_plain", title="A", **base_kwargs)
        retitled = Table(cache_id="test_table_hash_retitled", title="B", **base_kwargs)

        assert plain._compute_config_hash() == retitled._compute_config_hash(), (
            "title-only change must not alter the cache-key hash"
        )

        # Sanity: a data-shaping change DOES alter the hash
        reshaped = Table(
            cache_id="test_table_hash_reshaped",
            title="A",
            page_size=50,
            **base_kwargs,
        )
        assert plain._compute_config_hash() != reshaped._compute_config_hash(), (
            "data-shaping change must alter the cache-key hash"
        )

    def test_title_reaches_vue_via_component_args(
        self, mock_streamlit, temp_cache_dir, sample_table_data
    ):
        """The camelCase 'title' arg still reaches Vue via _get_component_args."""
        table = Table(
            cache_id="test_table_title_args",
            data=sample_table_data,
            cache_path=str(temp_cache_dir),
            title="Peaks",
        )
        assert table._get_component_args()["title"] == "Peaks"

    def test_title_roundtrips_through_reconstruction(
        self, mock_streamlit, temp_cache_dir, sample_table_data
    ):
        """title survives a cache-only (cache_id/cache_path) reconstruction."""
        cache_id = "test_table_title_roundtrip"

        original = Table(
            cache_id=cache_id,
            data=sample_table_data,
            cache_path=str(temp_cache_dir),
            title="Peaks",
        )
        assert original._title == "Peaks"

        # The manifest must persist title so reconstruction can restore it
        manifest_path = temp_cache_dir / cache_id / "manifest.json"
        with open(manifest_path) as f:
            manifest = json.load(f)
        assert manifest["config"]["title"] == "Peaks"

        # Reconstruct from ONLY cache_id + cache_path (no data, no config)
        reconstructed = Table(cache_id=cache_id, cache_path=str(temp_cache_dir))
        assert reconstructed._title == "Peaks", "title lost on cache reconstruction"
        assert reconstructed._get_component_args()["title"] == "Peaks"
