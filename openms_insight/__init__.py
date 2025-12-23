"""
Streamlit Vue Components - Interactive visualization components for Streamlit.

This package provides reusable, interactive Streamlit components backed by Vue.js
visualizations with cross-component selection state management.
"""

from .components.heatmap import Heatmap
from .components.lineplot import LinePlot
from .components.sequenceview import SequenceView, SequenceViewResult
from .components.table import Table
from .core.base import BaseComponent
from .core.cache import CacheMissError
from .core.registry import get_component_class, register_component
from .core.state import StateManager
from .rendering.bridge import clear_component_annotations, get_component_annotations

__version__ = "0.1.0"

__all__ = [
    # Core
    "BaseComponent",
    "StateManager",
    "register_component",
    "get_component_class",
    "CacheMissError",
    # Components
    "Table",
    "LinePlot",
    "Heatmap",
    "SequenceView",
    "SequenceViewResult",
    # Utilities
    "get_component_annotations",
    "clear_component_annotations",
]
