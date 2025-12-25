"""Base component class for all visualization components."""

import hashlib
import json
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

import polars as pl

from .cache import CacheMissError, get_cache_dir

if TYPE_CHECKING:
    from .state import StateManager

# Cache format version - increment when cache structure changes
# Version 2: Added sorting by filter columns + smaller row groups for predicate pushdown
# Version 3: Downcast numeric types (Int64→Int32, Float64→Float32) for efficient transfer
CACHE_VERSION = 3


class BaseComponent(ABC):
    """
    Abstract base class for all visualization components.

    Components are created with a mandatory cache_id and optional data,
    filters, and interactivity mappings. Preprocessed data is automatically
    cached to disk for fast subsequent loads.

    Attributes:
        _cache_id: Unique identifier for this component's cache
        _cache_dir: Path to cache directory
        _raw_data: Original polars LazyFrame (None if loaded from cache)
        _filters: Dict mapping identifiers to column names for filtering
        _interactivity: Dict mapping identifiers to column names for click actions
        _preprocessed_data: Dict of preprocessed data structures
        _config: Component configuration options
        _component_type: Class-level component type identifier
    """

    _component_type: str = ""

    def __init__(
        self,
        cache_id: str,
        data: Optional[pl.LazyFrame] = None,
        data_path: Optional[str] = None,
        filters: Optional[Dict[str, str]] = None,
        filter_defaults: Optional[Dict[str, Any]] = None,
        interactivity: Optional[Dict[str, str]] = None,
        cache_path: str = ".",
        regenerate_cache: bool = False,
        **kwargs,
    ):
        """
        Initialize the component.

        Components can be created in two modes:

        1. **Creation mode** (data provided): Creates cache with specified config.
           All configuration (filters, interactivity, component-specific) is stored.

        2. **Reconstruction mode** (no data): Loads everything from cache.
           Only cache_id and cache_path are needed. All configuration is restored
           from the cached manifest. Any other parameters passed are ignored.

        Args:
            cache_id: Unique identifier for this component's cache (MANDATORY).
                Creates a folder {cache_path}/{cache_id}/ for cached data.
            data: Polars LazyFrame with source data. Required for creation mode.
            data_path: Path to parquet file with source data. Preferred over
                data= for large datasets as preprocessing runs in a subprocess
                to ensure memory is released after cache creation.
            filters: Mapping of identifier names to column names for filtering.
                Example: {'spectrum': 'scan_id'}
                When 'spectrum' selection exists, component filters data where
                scan_id equals the selected value.
            filter_defaults: Default values for filters when state is None.
                Example: {'identification': -1}
                When 'identification' selection is None, filter uses -1 instead.
                This enables showing default/unannotated data when no selection.
            interactivity: Mapping of identifier names to column names for clicks.
                Example: {'my_selection': 'mass'}
                When user clicks/selects, sets 'my_selection' to the clicked
                row's mass value.
            cache_path: Base path for cache storage. Default "." (current dir).
            regenerate_cache: If True, regenerate cache even if valid cache exists.
            **kwargs: Component-specific configuration options
        """
        # Validate inputs
        if data is not None and data_path is not None:
            raise ValueError("Provide either 'data' or 'data_path', not both")

        self._cache_id = cache_id
        self._cache_dir = get_cache_dir(cache_path, cache_id)
        self._preprocessed_data: Dict[str, Any] = {}

        # Determine mode: reconstruction (no data) or creation (data provided)
        has_data = data is not None or data_path is not None

        # Check if any configuration arguments were explicitly provided
        # Note: We only check filters/interactivity/filter_defaults because component-
        # specific kwargs always have default values passed by subclasses
        has_config = (
            filters is not None
            or filter_defaults is not None
            or interactivity is not None
        )

        if not has_data and not regenerate_cache:
            # Reconstruction mode - only cache_id and cache_path allowed
            if has_config:
                raise CacheMissError(
                    "Configuration arguments (filters, interactivity, filter_defaults) "
                    "require data= or data_path= to be provided. "
                    "For reconstruction from cache, use only cache_id and cache_path."
                )
            if not self._cache_exists():
                raise CacheMissError(
                    f"Cache not found at '{self._cache_dir}'. "
                    f"Provide data= or data_path= to create the cache."
                )
            self._raw_data = None
            self._load_from_cache()
        else:
            # Creation mode - use provided config
            if not has_data:
                raise CacheMissError(
                    "regenerate_cache=True requires data= or data_path= to be provided."
                )

            self._filters = filters or {}
            self._filter_defaults = filter_defaults or {}
            self._interactivity = interactivity or {}
            self._config = kwargs

            if data_path is not None:
                # Subprocess preprocessing - memory released after cache creation
                from .subprocess_preprocess import preprocess_component

                preprocess_component(
                    type(self),
                    data_path=data_path,
                    cache_id=cache_id,
                    cache_path=cache_path,
                    filters=filters,
                    filter_defaults=filter_defaults,
                    interactivity=interactivity,
                    **kwargs,
                )
                self._raw_data = None
                self._load_from_cache()
            else:
                # In-process preprocessing
                self._raw_data = data
                self._validate_mappings()
                self._preprocess()
                self._save_to_cache()

    def _validate_mappings(self) -> None:
        """Validate that filter and interactivity columns exist in the data schema."""
        if self._raw_data is None:
            return  # Skip validation when loaded from cache

        schema = self._raw_data.collect_schema()
        column_names = schema.names()

        for identifier, column in self._filters.items():
            if column not in column_names:
                raise ValueError(
                    f"Filter column '{column}' for identifier '{identifier}' not found in data. "
                    f"Available columns: {column_names}"
                )

        for identifier, column in self._interactivity.items():
            if column not in column_names:
                raise ValueError(
                    f"Interactivity column '{column}' for identifier '{identifier}' not found in data. "
                    f"Available columns: {column_names}"
                )

    def _get_cache_config(self) -> Dict[str, Any]:
        """
        Get configuration that affects cache validity.

        Override in subclasses to include component-specific config.
        Config changes will invalidate the cache.

        Returns:
            Dict of config values that affect preprocessing
        """
        return {}

    def _compute_config_hash(self) -> str:
        """Compute hash of configuration for cache validation."""
        config_dict = {
            "filters": self._filters,
            "interactivity": self._interactivity,
            **self._get_cache_config(),
        }
        config_str = json.dumps(config_dict, sort_keys=True, default=str)
        return hashlib.sha256(config_str.encode()).hexdigest()

    def _get_manifest_path(self) -> Path:
        """Get path to cache manifest file."""
        return self._cache_dir / "manifest.json"

    def _get_preprocessed_dir(self) -> Path:
        """Get path to preprocessed data directory."""
        return self._cache_dir / "preprocessed"

    def _cache_exists(self) -> bool:
        """
        Check if a valid cache exists that can be loaded.

        Cache exists when:
        1. manifest.json exists and is readable
        2. version matches current CACHE_VERSION
        3. component_type matches

        Note: This does NOT check config hash. In reconstruction mode,
        all configuration is restored from the cache manifest.
        """
        manifest_path = self._get_manifest_path()
        if not manifest_path.exists():
            return False

        try:
            with open(manifest_path) as f:
                manifest = json.load(f)
        except (json.JSONDecodeError, IOError):
            return False

        # Check version
        if manifest.get("version") != CACHE_VERSION:
            return False

        # Check component type
        if manifest.get("component_type") != self._component_type:
            return False

        return True

    def _load_from_cache(self) -> None:
        """Load all configuration and preprocessed data from cache.

        Restores:
        - filters mapping
        - filter_defaults mapping
        - interactivity mapping
        - Component-specific configuration via _restore_cache_config()
        - All preprocessed data files
        """
        manifest_path = self._get_manifest_path()
        preprocessed_dir = self._get_preprocessed_dir()

        with open(manifest_path) as f:
            manifest = json.load(f)

        # Restore filters, filter_defaults, and interactivity from manifest
        self._filters = manifest.get("filters", {})
        self._filter_defaults = manifest.get("filter_defaults", {})
        self._interactivity = manifest.get("interactivity", {})
        self._config = manifest.get("config", {})

        # Restore component-specific configuration
        self._restore_cache_config(manifest.get("config", {}))

        # Load preprocessed data files
        data_files = manifest.get("data_files", {})
        for key, filename in data_files.items():
            filepath = preprocessed_dir / filename
            if filepath.exists():
                self._preprocessed_data[key] = pl.scan_parquet(filepath)

        # Load simple values
        data_values = manifest.get("data_values", {})
        for key, value in data_values.items():
            self._preprocessed_data[key] = value

    @abstractmethod
    def _restore_cache_config(self, config: Dict[str, Any]) -> None:
        """
        Restore component-specific configuration from cached config dict.

        Called during reconstruction mode to restore all component attributes
        that were stored in the manifest's config section.

        Args:
            config: The config dict from manifest (result of _get_cache_config())
        """
        pass

    def _save_to_cache(self) -> None:
        """Save preprocessed data to cache."""
        from ..preprocessing.filtering import (
            optimize_for_transfer,
            optimize_for_transfer_lazy,
        )

        # Create directories
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        preprocessed_dir = self._get_preprocessed_dir()
        preprocessed_dir.mkdir(parents=True, exist_ok=True)

        # Prepare manifest
        manifest = {
            "version": CACHE_VERSION,
            "component_type": self._component_type,
            "created_at": datetime.now().isoformat(),
            "config_hash": self._compute_config_hash(),
            "config": self._get_cache_config(),
            "filters": self._filters,
            "filter_defaults": self._filter_defaults,
            "interactivity": self._interactivity,
            "data_files": {},
            "data_values": {},
        }

        # Check if files were already saved during preprocessing (e.g., cascading)
        files_already_saved = self._preprocessed_data.pop("_files_already_saved", False)

        # Save preprocessed data with type optimization for efficient transfer
        # Float64→Float32 reduces Arrow payload size
        # Int64→Int32 (when safe) avoids BigInt overhead in JavaScript
        for key, value in self._preprocessed_data.items():
            if isinstance(value, pl.LazyFrame):
                filename = f"{key}.parquet"
                filepath = preprocessed_dir / filename

                if files_already_saved and filepath.exists():
                    # File was saved during preprocessing (cascading) - just register it
                    manifest["data_files"][key] = filename
                else:
                    # Apply streaming-safe optimization (Float64→Float32 only)
                    # Int64 bounds checking would require collect(), breaking streaming
                    value = optimize_for_transfer_lazy(value)
                    value.sink_parquet(filepath, compression="zstd")
                    manifest["data_files"][key] = filename
            elif isinstance(value, pl.DataFrame):
                filename = f"{key}.parquet"
                filepath = preprocessed_dir / filename

                if files_already_saved and filepath.exists():
                    # File was saved during preprocessing - just register it
                    manifest["data_files"][key] = filename
                else:
                    # Full optimization including Int64→Int32 with bounds checking
                    value = optimize_for_transfer(value)
                    value.write_parquet(filepath, compression="zstd")
                    manifest["data_files"][key] = filename
            elif self._is_json_serializable(value):
                manifest["data_values"][key] = value

        # Write manifest
        with open(self._get_manifest_path(), "w") as f:
            json.dump(manifest, f, indent=2)

        # Release memory - data is now safely on disk
        self._preprocessed_data = {}
        self._raw_data = None

        # Reload as lazy scan_parquet() references
        self._load_from_cache()

    def _is_json_serializable(self, value: Any) -> bool:
        """Check if value can be JSON serialized."""
        try:
            json.dumps(value)
            return True
        except (TypeError, ValueError):
            return False

    def _get_row_group_size(self) -> int:
        """
        Get optimal row group size for parquet writing.

        Smaller row groups enable better predicate pushdown when filtering,
        but increase metadata overhead. Override in subclasses for
        component-specific tuning.

        Returns:
            Number of rows per row group (default: 50,000)
        """
        return 50_000

    @abstractmethod
    def _preprocess(self) -> None:
        """
        Run component-specific preprocessing.

        This method should populate self._preprocessed_data with any
        preprocessed data structures needed for rendering.
        """
        pass

    @abstractmethod
    def _get_vue_component_name(self) -> str:
        """Return the Vue component name to render (e.g., 'TabulatorTable')."""
        pass

    @abstractmethod
    def _get_data_key(self) -> str:
        """Return the key used to send primary data to Vue."""
        pass

    @abstractmethod
    def _prepare_vue_data(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Prepare data payload for Vue component.

        Args:
            state: Current selection state from StateManager

        Returns:
            Dict with data to send to Vue component
        """
        pass

    @abstractmethod
    def _get_component_args(self) -> Dict[str, Any]:
        """
        Get component arguments to send to Vue.

        Returns:
            Dict with component configuration for Vue
        """
        pass

    def get_filters_mapping(self) -> Dict[str, str]:
        """Return the filters identifier-to-column mapping."""
        return self._filters.copy()

    def get_filter_defaults(self) -> Dict[str, Any]:
        """Return the filter defaults mapping."""
        return self._filter_defaults.copy()

    def get_interactivity_mapping(self) -> Dict[str, str]:
        """Return the interactivity identifier-to-column mapping."""
        return self._interactivity.copy()

    def get_filter_identifiers(self) -> List[str]:
        """Return list of filter identifiers this component uses."""
        return list(self._filters.keys())

    def get_interactivity_identifiers(self) -> List[str]:
        """Return list of interactivity identifiers this component sets."""
        return list(self._interactivity.keys())

    def get_state_dependencies(self) -> List[str]:
        """
        Return list of state keys that affect this component's data.

        By default, returns filter identifiers. Override in subclasses
        to include additional state keys (e.g., zoom state for heatmaps).

        The returned keys are used in the cache key calculation, so
        changes to any of these state values will trigger data recomputation.

        Returns:
            List of state identifier keys
        """
        return list(self._filters.keys())

    def _get_primary_data(self) -> Optional[pl.LazyFrame]:
        """
        Get the primary data for operations.

        Override in subclasses for complex data structures.
        Returns None if component was loaded from cache without raw data.
        """
        return self._raw_data

    def __call__(
        self,
        key: Optional[str] = None,
        state_manager: Optional["StateManager"] = None,
        height: Optional[int] = None,
    ) -> Any:
        """
        Render the component in Streamlit.

        Args:
            key: Optional unique key for the Streamlit component
            state_manager: Optional StateManager for cross-component state.
                If not provided, uses a default shared StateManager.
            height: Optional height in pixels for the component

        Returns:
            The value returned by the Vue component (usually selection state)
        """
        from ..rendering.bridge import render_component
        from .state import get_default_state_manager

        if state_manager is None:
            state_manager = get_default_state_manager()

        return render_component(
            component=self, state_manager=state_manager, key=key, height=height
        )

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"cache_id='{self._cache_id}', "
            f"filters={self._filters}, "
            f"interactivity={self._interactivity}, "
            f"config={self._config})"
        )
