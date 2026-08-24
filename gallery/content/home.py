"""Gallery overview."""

from importlib.metadata import PackageNotFoundError, version

import streamlit as st
from src import dataset

try:
    # Read the installed distribution, not openms_insight.__version__, which is not
    # kept in sync with pyproject.toml.
    INSTALLED_VERSION = version("openms-insight")
except PackageNotFoundError:  # pragma: no cover - only when running from a source tree
    INSTALLED_VERSION = "unknown"

st.title("OpenMS-Insight")
st.markdown(
    "Interactive visualization components for mass-spectrometry data in Streamlit, "
    "backed by Vue. Every page in this gallery is a live component running on real "
    "published data, shown next to the exact code that produced it."
)

st.code("pip install openms-insight", language="bash")

left, right = st.columns(2)
with left:
    st.subheader("Components")
    st.markdown(
        "- **Table** — server-side pagination, filtering, sorting, CSV export\n"
        "- **Line plot** — spectra with annotations and highlighting\n"
        "- **Mirror plot** — two spectra face to face\n"
        "- **Heatmap** — multi-resolution maps that stay responsive\n"
        "- **Volcano plot** — differential abundance with thresholds\n"
        "- **Sequence view** — peptides with fragment-ion matching"
    )
with right:
    st.subheader("What makes it different")
    st.markdown(
        "Components link to each other through shared **identifiers** rather than "
        "callbacks. One component writes a value on click, another reads it as a "
        "filter, and neither knows the other exists.\n\n"
        "The **Linking components** pages are the ones worth your time — a single "
        "plot is not news, but a table driving a spectrum with no event wiring might be."
    )

st.divider()
st.subheader("About the data")

manifest = dataset.manifest()
sources = manifest["sources"]
st.markdown(
    f"Nothing here is synthetic. Two published sources back the whole gallery, derived "
    f"once into {len(manifest['tables'])} small tables "
    f"(`tools/derive_example_dataset.py`):\n\n"
    f"- **Top-down FLASHDeconv results** from "
    f"[FLASHApp]({sources['flashapp']['repository']}) — the scan table, MS1 map and "
    f"deconvolved spectra.\n"
    f"- **[{sources['pxd044981']['accession']}]({sources['pxd044981']['url']})**, "
    f"*{sources['pxd044981']['title']}* — a UPS2 protein standard spiked into a "
    f"constant yeast background, which gives the volcano plot a real ground truth. "
    f"Search results are the authors' own MaxQuant output."
)

with st.expander("Full provenance"):
    st.caption(
        "Every table records where it came from and what was done to it. This is the "
        "manifest shipped with the dataset."
    )
    st.json(manifest)

st.caption(f"openms-insight {INSTALLED_VERSION} · dataset {manifest['version']}")
