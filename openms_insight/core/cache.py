"""Caching utilities for components.

This module provides the infrastructure for automatic component caching:
- CacheMissError: Exception raised when cache not found and data not provided
- get_cache_dir: Utility to compute cache directory path
- atomic_write: Write a cache file without ever exposing a partial one
- cache_lock: Serialize writers to one cache directory within this process
"""

import os
import threading
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
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


@contextmanager
def atomic_write(path: Path) -> Iterator[Path]:
    """Write a cache file without ever exposing a partially written one.

    Yields a temporary path in the same directory; on clean exit it is moved into
    place with ``os.replace``, which is atomic on POSIX and on Windows. A reader
    therefore always sees either the previous complete file or the new complete one,
    never a truncated one -- and, importantly, keeps reading the old inode if it has
    the file memory-mapped, rather than having the bytes pulled out from under it.

    If the body raises, the temporary file is removed and the original is untouched.

    Args:
        path: Final destination path.

    Yields:
        Temporary path to write to.
    """
    tmp = path.with_name(f"{path.name}.tmp-{os.getpid()}-{uuid.uuid4().hex[:8]}")
    try:
        yield tmp
        _replace_with_retry(tmp, path)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                # Best effort: a leftover temp file is untidy but harmless, and it
                # must never mask the real exception from the body.
                pass


def _replace_with_retry(
    tmp: Path, path: Path, attempts: int = 25, delay: float = 0.02
) -> None:
    """Move `tmp` onto `path`, retrying while a reader holds the destination.

    On POSIX this always succeeds first time: rename over an open file just detaches
    the old inode, and readers keep it until they close. Windows refuses instead --
    PermissionError (ERROR_ACCESS_DENIED) or ERROR_USER_MAPPED_FILE while another
    handle or memory mapping is live -- so retry briefly to let transient readers
    finish. Note this is the same limitation that made the previous in-place write
    fail; the difference is that failing here leaves a complete previous file rather
    than a truncated one.
    """
    last: OSError
    for attempt in range(attempts):
        try:
            os.replace(tmp, path)
            return
        except OSError as exc:
            last = exc
            if attempt < attempts - 1:
                time.sleep(delay)

    raise OSError(
        f"Could not replace cache file '{path}' after {attempts} attempts: {last}. "
        "On Windows a file cannot be replaced while another thread or process holds "
        "it open or memory-mapped. The previous cache file is intact and unmodified."
    ) from last


# One lock per cache directory, so unrelated caches never serialize on each other.
_cache_locks: dict[str, threading.RLock] = {}
_cache_locks_guard = threading.Lock()


@contextmanager
def cache_lock(cache_dir: Path) -> Iterator[None]:
    """Serialize writers to one cache directory within this process.

    Streamlit runs script threads concurrently: a rerun stops the previous run and
    starts the next without joining it, and the stop only takes effect at an ``st.*``
    call, of which preprocessing has none. Two threads therefore reach the same
    ``cache_id`` at once and rewrite the same Parquet files while polars has them
    mapped for reading.

    Holding this across the check-and-build also means the thread that loses the race
    finds a warm cache and skips preprocessing entirely, instead of duplicating it.

    This is a threading lock, not a file lock: the collisions that matter come from
    threads inside one Streamlit server process. Separate processes writing one cache
    directory are still protected by :func:`atomic_write`, but not serialized.

    Args:
        cache_dir: The component's cache directory.
    """
    key = str(cache_dir.resolve() if cache_dir.is_absolute() else cache_dir.absolute())
    with _cache_locks_guard:
        lock = _cache_locks.setdefault(key, threading.RLock())
    with lock:
        yield
