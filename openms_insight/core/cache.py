"""Caching utilities for components.

This module provides the infrastructure for automatic component caching:
- CacheMissError: Exception raised when cache not found and data not provided
- get_cache_dir: Utility to compute cache directory path
"""

from pathlib import Path


class CacheMissError(Exception):
    """Raised when cache not found and no data provided.

    This error is raised when:
    1. A component is instantiated without the `data` parameter
    2. No valid cache exists at the specified cache_path/cache_id location

    To resolve, either:
    - Provide the `data` parameter to create the cache
    - Ensure the cache exists from a previous run
    - Set `regenerate_cache=True` and provide `data` to rebuild
    """

    pass


def get_cache_dir(cache_path: str, cache_id: str) -> Path:
    """Get cache directory for a component.

    The cache directory structure is: {cache_path}/{cache_id}/

    Args:
        cache_path: Base path for cache storage (default "." for current dir)
        cache_id: Unique identifier for this component's cache

    Returns:
        Path object pointing to the component's cache directory
    """
    return Path(cache_path) / cache_id
