"""Every registered component must be demonstrated by at least one gallery example.

Coverage is derived by parsing the example pages, not from a hand-written list, so it
cannot drift: adding a seventh component without writing an example for it fails this
test, and no one has to remember to update anything.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Dict, Set

import pytest

from openms_insight.core.registry import list_registered_components

CONTENT_DIR = Path(__file__).resolve().parent.parent / "gallery" / "content"


def _class_to_registry_name() -> Dict[str, str]:
    """Map component class name -> registered name, e.g. ``Table`` -> ``table``."""
    return {cls.__name__: name for name, cls in list_registered_components().items()}


def _components_used(page: Path, class_names: Set[str]) -> Set[str]:
    """Component classes constructed anywhere in a page, found statically."""
    tree = ast.parse(page.read_text(encoding="utf-8"))
    used = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            name = (
                func.id
                if isinstance(func, ast.Name)
                else func.attr
                if isinstance(func, ast.Attribute)
                else None
            )
            if name in class_names:
                used.add(name)
    return used


def test_content_directory_exists() -> None:
    assert CONTENT_DIR.is_dir(), f"Gallery content directory missing: {CONTENT_DIR}"


def test_every_registered_component_has_an_example() -> None:
    class_to_name = _class_to_registry_name()
    demonstrated: Set[str] = set()
    for page in CONTENT_DIR.glob("*.py"):
        for class_name in _components_used(page, set(class_to_name)):
            demonstrated.add(class_to_name[class_name])

    registered = set(list_registered_components())
    missing = registered - demonstrated
    assert not missing, (
        f"These components are registered but have no gallery example: "
        f"{sorted(missing)}. Add a page under gallery/content/ that constructs the "
        f"component, and list it in gallery/app.py."
    )


@pytest.mark.parametrize("page", sorted(CONTENT_DIR.glob("*.py")), ids=lambda p: p.name)
def test_example_pages_are_parseable(page: Path) -> None:
    ast.parse(page.read_text(encoding="utf-8"))
