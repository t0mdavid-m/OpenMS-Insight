"""Access to the committed example dataset.

The dataset is derived offline by ``tools/derive_example_dataset.py`` and committed
under ``gallery/data/``. See ``gallery/data/manifest.json`` for the provenance of every
table, and ``docs/adr/0001-example-data-committed-to-repo.md`` for why it lives here.

The helpers here are deliberately tiny. Example pages display their own source, so
every character of setup they need is a character the reader has to skim past.
"""

from __future__ import annotations

import functools
import json
import os
from pathlib import Path
from typing import Any, Dict

import polars as pl

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# Components write their Parquet caches relative to the working directory, which
# use_cache_dir() sets once at startup. That keeps `cache_path=` out of every example.
CACHE_DIR = Path(
    os.environ.get(
        "GALLERY_CACHE_DIR", Path(__file__).resolve().parent.parent / ".cache"
    )
)


def data(name: str) -> str:
    """Absolute path to a table in the example dataset, e.g. ``"scans"``."""
    target = (
        DATA_DIR / name if name.endswith(".parquet") else DATA_DIR / f"{name}.parquet"
    )
    if not target.exists():
        raise FileNotFoundError(
            f"Example dataset table missing: {target}. "
            "Run tools/derive_example_dataset.py to regenerate gallery/data/."
        )
    return str(target)


def scan(name: str) -> pl.LazyFrame:
    """A table from the example dataset as a polars LazyFrame.

    Examples pass this straight to a component's ``data=``. It is exactly
    ``pl.scan_parquet(<path>)`` -- the helper exists only to keep the example code
    short, since readers copy what they see.

    Note that examples deliberately use ``data=`` rather than ``data_path=``. The
    latter re-runs preprocessing in a spawned subprocess to return memory to the OS,
    which is worth it for multi-gigabyte inputs but fails outside ``__main__`` (so
    under headless tests) and buys nothing for a dataset this size.
    """
    return pl.scan_parquet(data(name))


def use_cache_dir() -> None:
    """Point the process at a writable cache directory.

    Called once when the app starts. Components then default to ``cache_path="."``,
    so examples never have to mention caching at all.
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    os.chdir(CACHE_DIR)


@functools.lru_cache(maxsize=1)
def manifest() -> Dict[str, Any]:
    """The provenance manifest shipped with the dataset."""
    with (DATA_DIR / "manifest.json").open(encoding="utf-8") as handle:
        return json.load(handle)


def table_info(name: str) -> Dict[str, Any]:
    """Manifest entry for one table, e.g. ``"flashdeconv/scans.parquet"``."""
    return manifest()["tables"].get(name, {})
