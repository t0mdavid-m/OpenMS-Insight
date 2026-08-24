"""The gallery's navigation list must name every example page, and only real pages.

Navigation is written out by hand in ``gallery/app.py`` so that ordering, grouping and
icons stay under editorial control. This test removes the cost of that choice: a page
that is added but not listed, or listed but deleted, fails the build instead of
quietly disappearing from the site.
"""

from __future__ import annotations

import ast
from pathlib import Path

GALLERY_DIR = Path(__file__).resolve().parent.parent / "gallery"
APP = GALLERY_DIR / "app.py"
CONTENT_DIR = GALLERY_DIR / "content"


def _pages_listed_in_app() -> set[str]:
    """Filenames passed to ``st.Page(Path("content", ...))`` in app.py."""
    tree = ast.parse(APP.read_text(encoding="utf-8"))
    listed = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = (
            func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
        )
        if name != "Page":
            continue
        for argument in node.args:
            if isinstance(argument, ast.Call):  # Path("content", "table.py")
                parts = [a.value for a in argument.args if isinstance(a, ast.Constant)]
                if parts:
                    listed.add(parts[-1])
            elif isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                listed.add(Path(argument.value).name)
    return listed


def test_every_page_file_is_listed_in_navigation() -> None:
    on_disk = {p.name for p in CONTENT_DIR.glob("*.py")}
    unlisted = on_disk - _pages_listed_in_app()
    assert not unlisted, (
        f"These pages exist but are not in gallery/app.py, so nobody can reach them: "
        f"{sorted(unlisted)}"
    )


def test_navigation_lists_only_existing_pages() -> None:
    on_disk = {p.name for p in CONTENT_DIR.glob("*.py")}
    missing = _pages_listed_in_app() - on_disk
    assert not missing, (
        f"gallery/app.py lists pages that do not exist: {sorted(missing)}"
    )


def test_navigation_is_not_empty() -> None:
    assert _pages_listed_in_app(), "No st.Page entries found in gallery/app.py"
