"""Hashing a render payload must not convert pandas to polars.

`_hash_data` used to call `pl.from_pandas()` on every pandas payload, on every render
of every component. That conversion parallelises Series construction across polars'
own ThreadPoolExecutor, and a faulthandler dump caught two Streamlit script threads
inside it at the moment the interpreter died -- `Windows fatal exception: access
violation` in `numpy_to_pyseries`, both threads in `pl.from_pandas` under `_hash_data`.

Streamlit reaches that state easily: `runner.fastReruns` starts a new script thread
without joining the previous one, so any two overlapping renders collide.

The conversion was never needed. The hash uses shape, column names, the first and last
row, and per-column sums -- all of which pandas provides directly, so removing it is
also one less full-frame conversion per render.

**This does not fix the gallery crash.** With this change the server still dies under
sustained use, next faulting inside `pl.scan_parquet` with only one script thread
live -- so the faulting site is wherever memory is next touched, and something else
corrupts the heap first. Treat this as closing one confirmed fault site, not as the
root cause.
"""

from __future__ import annotations

import threading

import pandas as pd
import polars as pl
import pytest

from openms_insight.preprocessing.filtering import compute_pandas_dataframe_hash
from openms_insight.rendering.bridge import _hash_data


@pytest.fixture
def frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "rt": [1.0, 2.0, 3.0, 4.0],
            "mass": [100.5, 200.5, 300.5, 400.5],
            "scan_id": [10, 11, 12, 13],
            "flag": [True, False, True, False],
            "label": ["a", "b", "c", "d"],
        }
    )


class TestNoPolarsConversion:
    def test_hash_data_never_calls_from_pandas(self, frame, monkeypatch):
        """The regression guard. If this fails, the crash is back."""

        def explode(*args, **kwargs):  # pragma: no cover - only runs on regression
            raise AssertionError(
                "_hash_data called pl.from_pandas: this is the concurrency crash"
            )

        monkeypatch.setattr(pl, "from_pandas", explode)

        assert _hash_data({"plotData": frame, "_hash": "x"})

    def test_pandas_hash_needs_no_conversion(self, frame, monkeypatch):
        monkeypatch.setattr(pl, "from_pandas", lambda *a, **k: pytest.fail("converted"))

        assert compute_pandas_dataframe_hash(frame)


class TestHashBehaviour:
    def test_stable_across_calls(self, frame):
        assert compute_pandas_dataframe_hash(frame) == compute_pandas_dataframe_hash(
            frame.copy()
        )

    def test_changes_when_a_value_changes(self, frame):
        before = compute_pandas_dataframe_hash(frame)
        changed = frame.copy()
        changed.loc[2, "mass"] = 999.0

        assert compute_pandas_dataframe_hash(changed) != before

    def test_changes_when_rows_are_added(self, frame):
        before = compute_pandas_dataframe_hash(frame)
        grown = pd.concat([frame, frame.tail(1)], ignore_index=True)

        assert compute_pandas_dataframe_hash(grown) != before

    def test_changes_when_columns_change(self, frame):
        before = compute_pandas_dataframe_hash(frame)

        assert compute_pandas_dataframe_hash(frame.drop(columns=["label"])) != before

    def test_changes_when_a_boolean_column_changes(self, frame):
        """Annotation highlighting rides on boolean columns."""
        before = compute_pandas_dataframe_hash(frame)
        changed = frame.copy()
        changed["flag"] = [True, True, True, True]

        assert compute_pandas_dataframe_hash(changed) != before

    def test_detects_a_dynamic_annotation_text_change(self):
        """`_dynamic*` string columns carry fragment labels; a relabel must invalidate."""
        base = pd.DataFrame({"peak_id": [1, 2], "_dynamic_annotation": ["y1", "y2"]})
        relabelled = pd.DataFrame(
            {"peak_id": [1, 2], "_dynamic_annotation": ["b1", "b2"]}
        )

        assert compute_pandas_dataframe_hash(base) != compute_pandas_dataframe_hash(
            relabelled
        )

    def test_empty_frame_is_hashable(self):
        assert compute_pandas_dataframe_hash(pd.DataFrame({"a": []}))


class TestConcurrency:
    def test_many_threads_hash_consistently(self, frame):
        """The shape that crashed: several renders hashing at the same moment."""
        expected = _hash_data({"plotData": frame})
        results: list[str] = []
        errors: list[BaseException] = []
        lock = threading.Lock()
        barrier = threading.Barrier(8)

        def worker() -> None:
            try:
                barrier.wait(timeout=30)
                for _ in range(25):
                    value = _hash_data({"plotData": frame.copy()})
                    with lock:
                        results.append(value)
            except BaseException as exc:  # noqa: BLE001
                with lock:
                    errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=120)

        assert not errors, f"concurrent hashing raised: {errors[:3]!r}"
        assert not any(t.is_alive() for t in threads)
        assert len(set(results)) == 1, "concurrent hashing produced differing hashes"
        assert results[0] == expected, (
            "concurrent hashing disagreed with serial hashing"
        )


class TestPolarsFramesStillWork:
    def test_polars_payload_is_still_hashed(self):
        df = pl.DataFrame({"a": [1, 2, 3], "b": [1.5, 2.5, 3.5]})

        assert _hash_data({"tableData": df})

    def test_polars_hash_detects_change(self):
        first = pl.DataFrame({"a": [1, 2, 3]})
        second = pl.DataFrame({"a": [1, 2, 4]})

        assert _hash_data({"tableData": first}) != _hash_data({"tableData": second})
