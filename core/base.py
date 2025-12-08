"""Base component class for all visualization components."""

from abc import ABC, abstractmethod
from datetime import datetime
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING
import polars as pl

from .cache import CacheMissError, get_cache_dir

if TYPE_CHECKING:
    from .state import StateManager

# Cache format version - increment when cache structure changes
# Version 2: Added sorting by filter columns + smaller row groups for predicate pushdown
CACHE_VERSION = 2


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
        filters: Optional[Dict[str, str]] = None,
        interactivity: Optional[Dict[str, str]] = None,
        cache_path: str = ".",
        regenerate_cache: bool = False,
        **kwargs
    ):
        """
        Initialize the component.

        Args:
            cache_id: Unique identifier for this component's cache (MANDATORY).
                Creates a folder {cache_path}/{cache_id}/ for cached data.
            data: Polars LazyFrame with source data. Optional if cache exists.
            filters: Mapping of identifier names to column names for filtering.
                Example: {'spectrum': 'scan_id'}
                When 'spectrum' selection exists, component filters data where
                scan_id equals the selected value.
            interactivity: Mapping of identifier names to column names for clicks.
                Example: {'my_selection': 'mass'}
                When user clicks/selects, sets 'my_selection' to the clicked
                row's mass value.
            cache_path: Base path for cache storage. Default "." (current dir).
            regenerate_cache: If True, regenerate cache even if valid cache exists.
            **kwargs: Component-specific configuration options
        """
        self._cache_id = cache_id
        self._cache_dir = get_cache_dir(cache_path, cache_id)
        self._filters = filters or {}
        self._interactivity = interactivity or {}
        self._preprocessed_data: Dict[str, Any] = {}
        self._config = kwargs

        # Check if we should load from cache or preprocess
        if regenerate_cache or not self._is_cache_valid():
            if data is None:
                raise CacheMissError(
                    f"Cache not found at '{self._cache_dir}' and no data provided. "
                    f"Either provide data= or ensure cache exists from a previous run."
                )
            self._raw_data = data
            # Validate columns exist in data
            self._validate_mappings()
            # Run component-specific preprocessing
            self._preprocess()
            # Save to cache for next time
            self._save_to_cache()
        else:
            # Load from valid cache
            self._raw_data = None
            self._load_from_cache()

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
            **self._get_cache_config()
        }
        config_str = json.dumps(config_dict, sort_keys=True, default=str)
        return hashlib.sha256(config_str.encode()).hexdigest()

    def _get_manifest_path(self) -> Path:
        """Get path to cache manifest file."""
        return self._cache_dir / "manifest.json"

    def _get_preprocessed_dir(self) -> Path:
        """Get path to preprocessed data directory."""
        return self._cache_dir / "preprocessed"

    def _is_cache_valid(self) -> bool:
        """
        Check if cache is valid and can be loaded.

        Cache is valid when:
        1. manifest.json exists
        2. version matches current CACHE_VERSION
        3. component_type matches
        4. config_hash matches current config
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

        # Check config hash
        current_hash = self._compute_config_hash()
        if manifest.get("config_hash") != current_hash:
            return False

        return True

    def _load_from_cache(self) -> None:
        """Load preprocessed data from cache."""
        manifest_path = self._get_manifest_path()
        preprocessed_dir = self._get_preprocessed_dir()

        with open(manifest_path) as f:
            manifest = json.load(f)

        # Load filters and interactivity from manifest
        self._filters = manifest.get("filters", {})
        self._interactivity = manifest.get("interactivity", {})

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

    def _save_to_cache(self) -> None:
        """Save preprocessed data to cache."""
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
            "interactivity": self._interactivity,
            "data_files": {},
            "data_values": {},
        }

        # Save preprocessed data
        row_group_size = self._get_row_group_size()
        for key, value in self._preprocessed_data.items():
            if isinstance(value, pl.LazyFrame):
                filename = f"{key}.parquet"
                filepath = preprocessed_dir / filename
                value.collect().write_parquet(
                    filepath,
                    compression='zstd',
                    statistics=True,
                    row_group_size=row_group_size,
                )
                manifest["data_files"][key] = filename
            elif isinstance(value, pl.DataFrame):
                filename = f"{key}.parquet"
                filepath = preprocessed_dir / filename
                value.write_parquet(
                    filepath,
                    compression='zstd',
                    statistics=True,
                    row_group_size=row_group_size,
                )
                manifest["data_files"][key] = filename
            elif self._is_json_serializable(value):
                manifest["data_values"][key] = value

        # Write manifest
        with open(self._get_manifest_path(), "w") as f:
            json.dump(manifest, f, indent=2)

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
    def _prepare_vue_data(
        self,
        state: Dict[str, Any]
    ) -> Dict[str, Any]:
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

    def get_interactivity_mapping(self) -> Dict[str, str]:
        """Return the interactivity identifier-to-column mapping."""
        return self._interactivity.copy()

    def get_filter_identifiers(self) -> List[str]:
        """Return list of filter identifiers this component uses."""
        return list(self._filters.keys())

    def get_interactivity_identifiers(self) -> List[str]:
        """Return list of interactivity identifiers this component sets."""
        return list(self._interactivity.keys())

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
        state_manager: Optional['StateManager'] = None,
        height: Optional[int] = None
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
        from .state import get_default_state_manager
        from ..rendering.bridge import render_component

        if state_manager is None:
            state_manager = get_default_state_manager()

        return render_component(
            component=self,
            state_manager=state_manager,
            key=key,
            height=height
        )

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"cache_id='{self._cache_id}', "
            f"filters={self._filters}, "
            f"interactivity={self._interactivity}, "
            f"config={self._config})"
        )
