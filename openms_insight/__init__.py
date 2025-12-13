"""
Streamlit Vue Components - Interactive visualization components for Streamlit.

This package provides reusable, interactive Streamlit components backed by Vue.js
visualizations with cross-component selection state management.
"""

from .core.base import BaseComponent
from .core.state import StateManager
from .core.registry import register_component, get_component_class
from .core.cache import CacheMissError
from .core.subprocess_preprocess import preprocess_component

from .components.table import Table
from .components.lineplot import LinePlot
from .components.heatmap import Heatmap
from .components.sequenceview import SequenceView

__version__ = "0.1.0"

__all__ = [
    # Core
    "BaseComponent",
    "StateManager",
    "register_component",
    "get_component_class",
    "CacheMissError",
    "preprocess_component",
    # Components
    "Table",
    "LinePlot",
    "Heatmap",
    "SequenceView",
]
