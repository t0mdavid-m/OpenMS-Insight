"""OpenMS-Insight example gallery.

Navigation is written out explicitly rather than globbed, so page order, grouping and
icons stay under editorial control. Two tests keep that list honest:
``tests/test_gallery_nav.py`` fails if a page exists but is not listed here, and
``tests/test_gallery_coverage.py`` fails if a registered component has no example.
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

GALLERY_DIR = Path(__file__).resolve().parent
if str(GALLERY_DIR) not in sys.path:
    sys.path.insert(0, str(GALLERY_DIR))

from src import dataset  # noqa: E402  (needs sys.path above)

st.set_page_config(
    page_title="OpenMS-Insight gallery",
    page_icon="🔬",
    layout="wide",
)

# Components cache Parquet relative to the working directory; setting it once here is
# what keeps `cache_path=` out of every example.
dataset.use_cache_dir()

PAGES = {
    "": [
        st.Page(Path("content", "home.py"), title="Overview", icon="🏠", default=True),
    ],
    "Components": [
        st.Page(Path("content", "table.py"), title="Table", icon="📋"),
        st.Page(Path("content", "lineplot.py"), title="Line plot", icon="📈"),
        st.Page(Path("content", "mirrorplot.py"), title="Mirror plot", icon="🪞"),
        st.Page(Path("content", "heatmap.py"), title="Heatmap", icon="🔥"),
        st.Page(Path("content", "volcano.py"), title="Volcano plot", icon="🌋"),
        st.Page(Path("content", "sequence_view.py"), title="Sequence view", icon="🧬"),
    ],
    "Linking components": [
        st.Page(
            Path("content", "link_scan_spectrum.py"),
            title="Scan table → spectrum",
            icon="🔗",
        ),
        st.Page(
            Path("content", "link_sequence_mirror.py"),
            title="Sequence → mirror plot",
            icon="🔗",
        ),
    ],
    "Scale": [
        st.Page(Path("content", "scale.py"), title="Large heatmaps", icon="⚡"),
    ],
}

st.navigation(PAGES).run()
