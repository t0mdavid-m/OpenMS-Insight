"""Protein structure view: fragment evidence of a sequence on its 3D structure."""

import hashlib
import json
from typing import Any

import polars as pl

from ..core.registry import register_component
from .protein_sequence_view import ProteinSequenceView

STRUCTURE_STATUSES = ("ok", "missing", "unavailable")


@register_component("protein_structure_view")
class ProteinStructureView(ProteinSequenceView):
    """
    3D structure of a protein, coloured by the fragment evidence of a sequence entry.

    Takes the same data as ``ProteinSequenceView`` (one row per sequence entry
    with its spectrum) and draws the entry's fragmentation sites on a structure
    (PDB or mmCIF) with 3Dmol.js: one residue per terminal ion, in the sequence
    view's colours (a/x green, b/y blue, c/z red), and both cleavage sites of
    each annotated internal fragment. Modified residues carry the sequence
    view's dotted pattern and a label, residues outside
    ``start_position``..``end_position`` are greyed out (or hidden). The
    sequence is aligned to the structure's chains, so structures with their
    own residue numbering work too. Clicking a residue sets ``aa_identifier``,
    so residue selection is shared with a sequence view.

    The structure itself is given per render with ``set_structure()``, since
    where it comes from (a database download, an upload) is up to the app.

    Example:
        view = ProteinStructureView(
            cache_id="structure_view",
            data=identifications,
            filters={"protein": "hit_index"},
            aa_identifier="aa",
        )
        view.set_structure({"status": "ok", "format": "pdb", "data": pdb_text,
                            "accession": "P60844", "label": "AlphaFold DB model"})
        view(key="structure_view", state_manager=state_manager)
    """

    _component_type: str = "protein_structure_view"

    def __init__(
        self,
        cache_id: str,
        data: pl.LazyFrame | None = None,
        data_path: str | None = None,
        filters: dict[str, str] | None = None,
        filter_defaults: dict[str, Any] | None = None,
        interactivity: dict[str, str] | None = None,
        cache_path: str = ".",
        regenerate_cache: bool = False,
        mass_column: str | None = "masses",
        aa_identifier: str | None = None,
        fragment_identifier: str | None = None,
        settings: dict[str, Any] | None = None,
        title: str | None = "Structure View",
        empty_message: str = "Select an entry to show its structure.",
        viewer_height: int = 480,
        float_precision: str = "float64",
        **kwargs,
    ):
        """
        Initialize the ProteinStructureView component.

        Args:
            cache_id: Unique identifier for this component's cache (MANDATORY).
            data: Polars LazyFrame, one row per sequence entry (see
                ``ProteinSequenceView``).
            data_path: Path to a parquet file with the data.
            filters: Mapping of identifier names to column names selecting the
                entry to show, e.g. {'protein': 'hit_index'}.
            filter_defaults: Default values for filters when state is None.
            interactivity: Not used; clicks set ``aa_identifier``.
            cache_path: Base path for cache storage.
            regenerate_cache: Rebuild the cache even if a matching one exists.
            mass_column: List column with the spectrum's deconvolved masses,
                matched against the theoretical fragment masses when the entry
                has no ``annotated_fragments``.
            aa_identifier: Identifier holding the selected residue (0-based).
            fragment_identifier: Identifier holding a fragment selected in a
                ``ProteinSequenceView`` (its ``fragment_identifier``): its
                cleavage sites are marked, the rest of the protein faded and
                the view centred on it.
            settings: Fragment settings: {'tolerance': ppm, 'ion_types': [...]}.
            title: Title above the view (None: no title).
            empty_message: Shown while no entry is selected.
            viewer_height: Height of the 3D viewer in pixels.
            float_precision: Masses are compared at ppm level, so they are kept
                as Float64 by default.
            **kwargs: Additional configuration options.
        """
        self._empty_message = empty_message
        self._viewer_height = viewer_height
        # Structure shown with the next render (set per render, not cached)
        self._structure: dict[str, Any] | None = None
        super().__init__(
            cache_id=cache_id,
            data=data,
            data_path=data_path,
            filters=filters,
            filter_defaults=filter_defaults,
            interactivity=interactivity,
            cache_path=cache_path,
            regenerate_cache=regenerate_cache,
            mass_column=mass_column,
            precursor_mass_column=None,
            aa_identifier=aa_identifier,
            fragment_identifier=fragment_identifier,
            settings=settings,
            title=title,
            float_precision=float_precision,
            empty_message=empty_message,
            viewer_height=viewer_height,
            **kwargs,
        )

    def _get_cache_config(self) -> dict[str, Any]:
        config = super()._get_cache_config()
        config["empty_message"] = self._empty_message
        config["viewer_height"] = self._viewer_height
        return config

    def _restore_cache_config(self, config: dict[str, Any]) -> None:
        super()._restore_cache_config(config)
        self._empty_message = config.get(
            "empty_message", "Select an entry to show its structure."
        )
        self._viewer_height = config.get("viewer_height", 480)
        self._structure = None

    def _get_vue_component_name(self) -> str:
        return "ProteinStructureView"

    def set_structure(self, structure: dict[str, Any] | None) -> "ProteinStructureView":
        """
        Structure to show with the next render.

        Args:
            structure: None (nothing to show yet) or a dict with ``status``:
                'ok' with ``format`` ('pdb' or 'cif') and ``data`` (the file's
                text), or 'missing' / 'unavailable' with a ``message`` shown in
                its place. Optional: ``accession`` (names the PNG download),
                ``label`` (source line below the viewer) and ``url`` (links the
                label).

        Returns:
            Self for method chaining.
        """
        if structure is not None:
            status = structure.get("status")
            if status not in STRUCTURE_STATUSES:
                raise ValueError(
                    f"structure status must be one of {STRUCTURE_STATUSES}, got {status!r}"
                )
            if status == "ok" and structure.get("format") not in ("pdb", "cif"):
                raise ValueError(
                    "a structure with status 'ok' needs format 'pdb' or 'cif'"
                )
        self._structure = structure
        return self

    def _get_render_key(self) -> str | None:
        # The structure's text can be large: hash its identity, not the text
        structure = self._structure
        if structure is None:
            return None
        text = structure.get("data") or ""
        key = {
            **{k: v for k, v in structure.items() if k != "data"},
            "data": hashlib.md5(text.encode()).hexdigest(),
        }
        return hashlib.md5(
            json.dumps(key, sort_keys=True, default=str).encode()
        ).hexdigest()

    def _prepare_vue_data(self, state: dict[str, Any]) -> dict[str, Any]:
        data = super()._prepare_vue_data(state)
        data["structure"] = self._structure
        data["_hash"] = hashlib.md5(
            json.dumps([data["_hash"], self._get_render_key()]).encode()
        ).hexdigest()
        return data

    def _get_component_args(self) -> dict[str, Any]:
        args = super()._get_component_args()
        args.update(
            {
                "emptyMessage": self._empty_message,
                "viewerHeight": self._viewer_height,
            }
        )
        return args
