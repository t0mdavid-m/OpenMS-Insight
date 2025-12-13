"""Subprocess-based preprocessing to ensure memory is released after cache creation.

When preprocessing large datasets (especially heatmaps with millions of points),
memory allocators like mimalloc retain freed memory. Running preprocessing in a
subprocess ensures all memory is returned to the OS when the subprocess exits.
"""

import multiprocessing
import os
from typing import Any, Dict, Optional, Type


def _preprocess_worker(
    component_class: Type,
    data_path: str,
    kwargs: Dict[str, Any],
) -> None:
    """Worker function that runs in subprocess to do preprocessing."""
    import polars as pl

    # Set mimalloc to release memory aggressively (in case not inherited)
    os.environ.setdefault("MIMALLOC_PURGE_DELAY", "0")

    # Create component with data - this triggers preprocessing and cache save
    data = pl.scan_parquet(data_path)
    component_class(data=data, **kwargs)
    # Subprocess exits here, releasing all memory


def preprocess_component(
    component_class: Type,
    data_path: str,
    cache_id: str,
    cache_path: str,
    **kwargs,
) -> None:
    """
    Run component preprocessing in a subprocess to guarantee memory release.

    After this function returns, the component cache is ready and the main
    process can create the component without data (loading from cache).

    Args:
        component_class: The component class (e.g., Heatmap, Table)
        data_path: Path to the parquet file containing the data
        cache_id: Unique identifier for the cache
        cache_path: Directory for cache storage
        **kwargs: Additional arguments passed to component constructor

    Example:
        from openms_insight import Heatmap
        from openms_insight.core.subprocess_preprocess import preprocess_component

        # Run preprocessing in subprocess (memory released when done)
        preprocess_component(
            Heatmap,
            data_path="/path/to/data.parquet",
            cache_id="my_heatmap",
            cache_path="/path/to/cache",
            x_column="rt",
            y_column="mz",
            intensity_column="intensity",
        )

        # Now create component from cache (no data needed, no memory spike)
        heatmap = Heatmap(cache_id="my_heatmap", cache_path="/path/to/cache")
    """
    # Prepare kwargs for subprocess
    worker_kwargs = {
        "cache_id": cache_id,
        "cache_path": cache_path,
        **kwargs,
    }

    # Use spawn to get a fresh process (fork might copy memory)
    ctx = multiprocessing.get_context("spawn")
    process = ctx.Process(
        target=_preprocess_worker,
        args=(component_class, data_path, worker_kwargs),
    )
    process.start()
    process.join()

    if process.exitcode != 0:
        raise RuntimeError(
            f"Preprocessing failed with exit code {process.exitcode}"
        )
