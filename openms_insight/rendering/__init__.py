"""Rendering utilities for Python-to-Vue communication."""

from .bridge import get_vue_component_function, render_component

__all__ = [
    "render_component",
    "get_vue_component_function",
]
