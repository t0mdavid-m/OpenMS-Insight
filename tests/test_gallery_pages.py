"""Every gallery page must execute end to end without raising.

This runs the real Streamlit script for each page under ``AppTest``, which exercises
the whole Python side: data loading, preprocessing, Parquet cache writes, payload
preparation and the render bridge. It does *not* prove the Vue components draw
anything -- ``AppTest`` has no browser, and a custom component call simply returns its
default there. Rendering is covered by the Playwright job instead.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

GALLERY_DIR = Path(__file__).resolve().parent.parent / "gallery"
CONTENT_DIR = GALLERY_DIR / "content"
PAGES = sorted(CONTENT_DIR.glob("*.py"))

pytest.importorskip("streamlit.testing.v1", reason="requires Streamlit's test harness")


@pytest.fixture(scope="module", autouse=True)
def _gallery_importable():
    """Put the gallery on sys.path so pages can `from src import layout`."""
    added = str(GALLERY_DIR) not in sys.path
    if added:
        sys.path.insert(0, str(GALLERY_DIR))
    yield
    if added:
        sys.path.remove(str(GALLERY_DIR))


@pytest.fixture(autouse=True)
def _preserve_main_module():
    """Restore ``sys.modules["__main__"]`` after each AppTest run.

    ``AppTest`` executes the page script as ``__main__``. On platforms where
    ``multiprocessing`` uses spawn rather than fork, the child re-imports the parent's
    ``__main__`` -- so leaving a Streamlit page there makes the child execute that page
    and die on its imports. Without this, these tests silently break the unrelated
    ``data_path`` subprocess tests later in the same session.
    """
    original = sys.modules.get("__main__")
    yield
    if original is not None:
        sys.modules["__main__"] = original


@pytest.fixture
def _cache_dir(tmp_path, monkeypatch):
    """Run each page in a throwaway working directory.

    Components default to ``cache_path="."``, so this is also what keeps generated
    Parquet caches out of the repository during a test run.
    """
    monkeypatch.chdir(tmp_path)
    yield tmp_path


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.stem)
def test_page_runs_without_exception(page: Path, _cache_dir) -> None:
    from streamlit.testing.v1 import AppTest

    app = AppTest.from_file(str(page), default_timeout=300)
    app.run()

    assert not app.exception, f"{page.name} raised: " + "; ".join(
        str(e.value) for e in app.exception
    )


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.stem)
def test_page_has_a_title(page: Path, _cache_dir) -> None:
    from streamlit.testing.v1 import AppTest

    app = AppTest.from_file(str(page), default_timeout=300)
    app.run()
    assert app.title, f"{page.name} renders no st.title()"


@pytest.mark.parametrize(
    "page", [p for p in PAGES if p.stem != "home"], ids=lambda p: p.stem
)
def test_example_page_shows_its_own_source(page: Path, _cache_dir) -> None:
    """Each example page must display the code that produced it."""
    from streamlit.testing.v1 import AppTest

    app = AppTest.from_file(str(page), default_timeout=300)
    app.run()

    assert app.code, f"{page.name} displays no source code block"
    shown = app.code[0].value
    assert "layout.render" not in shown, (
        f"{page.name} is showing page furniture rather than the example itself"
    )
    assert "state_manager=sm" in shown, (
        f"{page.name}'s displayed source does not look like a rendered component"
    )


def test_pages_were_discovered() -> None:
    assert PAGES, f"No gallery pages found under {CONTENT_DIR}"
