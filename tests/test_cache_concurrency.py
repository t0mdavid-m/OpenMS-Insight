"""Concurrent construction of one cache_id must not corrupt the cache.

Streamlit runs two script threads at once by default (`runner.fastReruns`): a rerun
calls `request_stop()` on the previous run and starts the next one without joining it,
and `request_stop` only takes effect at an interrupt point, which is an `st.*` call.
Preprocessing contains none, so the outgoing thread keeps writing Parquet while the
incoming one starts rewriting the same paths -- files polars has memory-mapped for
reading. On Linux that is a fatal SIGBUS; on Windows the write is refused with
ERROR_USER_MAPPED_FILE and readers see torn files and Rust panics.

Reusing a warm cache removes the trigger for the steady state, but the cold start,
`regenerate_cache=True`, and two sessions arriving at once still collide.
"""

from __future__ import annotations

import threading
from typing import Any

import polars as pl
import pytest

from openms_insight import Heatmap, Table


def _run_concurrently(target, n: int = 4) -> list[BaseException]:
    """Run `target` on n threads started as simultaneously as possible."""
    barrier = threading.Barrier(n)
    errors: list[BaseException] = []
    lock = threading.Lock()

    def worker(index: int) -> None:
        try:
            barrier.wait(timeout=30)
            target(index)
        except BaseException as exc:  # noqa: BLE001 - reported, not swallowed
            with lock:
                errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=120)

    assert not any(t.is_alive() for t in threads), "a worker thread deadlocked"
    return errors


class TestConcurrentConstruction:
    def test_cold_start_from_several_threads_does_not_fail(
        self, mock_streamlit, temp_cache_dir, sample_table_data
    ):
        def build(_index: int) -> None:
            Table(
                cache_id="race",
                data=sample_table_data,
                cache_path=str(temp_cache_dir),
                index_field="id",
            )

        errors = _run_concurrently(build)

        assert not errors, f"concurrent construction raised: {errors!r}"

    def test_only_one_thread_preprocesses(
        self, mock_streamlit, temp_cache_dir, sample_table_data, monkeypatch
    ):
        """Threads that lose the race should find a warm cache, not rebuild it.

        This is what keeps two of them from writing the same Parquet file at once.
        """
        calls: dict[str, int] = {"n": 0}
        counter_lock = threading.Lock()
        original = Table._preprocess

        def counting(self):
            with counter_lock:
                calls["n"] += 1
            return original(self)

        monkeypatch.setattr(Table, "_preprocess", counting)

        def build(_index: int) -> None:
            Table(
                cache_id="dedupe",
                data=sample_table_data,
                cache_path=str(temp_cache_dir),
                index_field="id",
            )

        errors = _run_concurrently(build)

        assert not errors, f"concurrent construction raised: {errors!r}"
        assert calls["n"] == 1, (
            f"{calls['n']} threads preprocessed the same cache_id concurrently"
        )

    def test_heatmap_cascade_survives_concurrent_construction(
        self, mock_streamlit, temp_cache_dir, sample_heatmap_data
    ):
        """The heatmap writes its levels itself and reads each one back to build the
        next, so a concurrent rebuild has more windows to tear than a single write."""

        def build(_index: int) -> None:
            Heatmap(
                cache_id="race_heatmap",
                data=sample_heatmap_data,
                cache_path=str(temp_cache_dir),
                x_column="retention_time",
                y_column="mz",
                intensity_column="intensity",
            )

        errors = _run_concurrently(build)

        assert not errors, f"concurrent heatmap construction raised: {errors!r}"

    def test_forced_rebuilds_do_not_collide(
        self, mock_streamlit, temp_cache_dir, sample_table_data
    ):
        """regenerate_cache=True bypasses the reuse guard, so every thread writes."""
        Table(
            cache_id="forced_race",
            data=sample_table_data,
            cache_path=str(temp_cache_dir),
            index_field="id",
        )

        def rebuild(_index: int) -> None:
            Table(
                cache_id="forced_race",
                data=sample_table_data,
                cache_path=str(temp_cache_dir),
                index_field="id",
                regenerate_cache=True,
            )

        errors = _run_concurrently(rebuild)

        assert not errors, f"concurrent rebuild raised: {errors!r}"


class TestCacheIsUsableAfterConcurrentWrites:
    def test_cache_reads_back_correctly(
        self, mock_streamlit, temp_cache_dir, sample_table_data
    ):
        def build(_index: int) -> None:
            Table(
                cache_id="readback",
                data=sample_table_data,
                cache_path=str(temp_cache_dir),
                index_field="id",
                regenerate_cache=True,
            )

        _run_concurrently(build)

        restored = Table(cache_id="readback", cache_path=str(temp_cache_dir))
        rows = restored._prepare_vue_data({})["tableData"]

        expected = sample_table_data.collect().height
        assert len(rows) == expected

    def test_no_temporary_files_are_left_behind(
        self, mock_streamlit, temp_cache_dir, sample_table_data
    ):
        Table(
            cache_id="tmpfiles",
            data=sample_table_data,
            cache_path=str(temp_cache_dir),
            index_field="id",
        )

        leftovers = [
            p
            for p in (temp_cache_dir / "tmpfiles").rglob("*")
            if ".tmp-" in p.name or p.name.endswith(".tmp")
        ]

        assert not leftovers, f"temporary files left in cache: {leftovers}"


class TestAtomicReplacement:
    """A reader must never observe a half-written file."""

    def test_reader_sees_old_or_new_never_partial(self, temp_cache_dir):
        from openms_insight.core.cache import atomic_write

        target = temp_cache_dir / "atomic.parquet"
        pl.DataFrame({"n": list(range(100))}).write_parquet(target)

        observed: list[Any] = []
        stop = threading.Event()

        def reader() -> None:
            while not stop.is_set():
                try:
                    observed.append(pl.read_parquet(target).height)
                except Exception as exc:  # noqa: BLE001 - a torn read is the failure
                    observed.append(exc)
                    return
                # A real reader is not permanently inside a read. On Windows the
                # destination cannot be replaced while a handle is open, so a reader
                # at 100% duty cycle would block the writer indefinitely -- that is a
                # platform constraint, not the property under test here.
                stop.wait(0.005)

        thread = threading.Thread(target=reader)
        thread.start()
        try:
            for size in (5000, 20, 8000, 30):
                frame = pl.DataFrame({"n": list(range(size))})
                with atomic_write(target) as tmp:
                    frame.write_parquet(tmp)
        finally:
            stop.set()
            thread.join(timeout=30)

        failures = [o for o in observed if isinstance(o, Exception)]
        assert not failures, f"reader observed a torn file: {failures[:3]}"
        assert observed, "reader never managed a read"

    def test_failed_write_leaves_the_original_intact(self, temp_cache_dir):
        from openms_insight.core.cache import atomic_write

        target = temp_cache_dir / "keep.parquet"
        pl.DataFrame({"n": [1, 2, 3]}).write_parquet(target)

        with pytest.raises(RuntimeError):
            with atomic_write(target) as tmp:
                pl.DataFrame({"n": [9]}).write_parquet(tmp)
                raise RuntimeError("preprocessing blew up")

        assert pl.read_parquet(target)["n"].to_list() == [1, 2, 3]
        assert not list(target.parent.glob("*.tmp-*")), "temp file was not cleaned up"
