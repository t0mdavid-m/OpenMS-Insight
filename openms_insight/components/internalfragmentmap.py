"""InternalFragmentMap component — internal-fragment map over a peptide/protein sequence.

Re-implements FLASHApp's (previously disabled) internal-fragment computation
(``src/render/sequence.py:204-274``) as a reusable, consumer-only OpenMS-Insight
component. Per ion type ``by`` / ``bz`` / ``cy`` it computes the theoretical
internal-fragment masses (minimum length 5 residues, first/last residue excluded,
terminal-ion 10 ppm exclusion, per-type mass shifts, ``+H2O``, modification handling)
and ships them to the Vue ``InternalFragmentMap`` component for rendering as a matrix
of segments grouped/colored by ion type.

The component is **consumer only**: it filters by ``proteinIndex`` (FLASHTnT) or uses a
configured sequence (FLASHDeconv). It emits no selection. Clearing the filter yields an
empty map.
"""

import hashlib
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple, Union

import polars as pl

from ..core.base import BaseComponent
from ..core.registry import register_component

# Mass constants (identical to FLASHApp src/render/sequence.py:16-17)
H2O = 18.010564683
NH3 = 17.0265491015

# Monoisotopic residue masses (FLASHApp sequence.py:148-172). X / Z have no defined mass.
AA_MASSES: Dict[str, float] = {
    "A": 71.037114,
    "R": 156.101111,
    "N": 114.042927,
    "D": 115.026943,
    "C": 103.009185,
    "E": 129.042593,
    "Q": 128.058578,
    "G": 57.021464,
    "H": 137.058912,
    "I": 113.084064,
    "L": 113.084064,
    "K": 128.094963,
    "M": 131.040485,
    "F": 147.068414,
    "P": 97.052764,
    "S": 87.032028,
    "T": 101.047679,
    "U": 150.953633405,
    "W": 186.079313,
    "Y": 163.063329,
    "V": 99.068414,
    "X": 0.0,
    "Z": 0.0,
}

# Ion types computed (by/cz are equivalent so only by, bz, cy are emitted).
ION_TYPES: Tuple[str, str, str] = ("by", "bz", "cy")

# Default per-type colors and ordering — matched to the real FLASHApp .vue <style>.
DEFAULT_ION_COLORS: Dict[str, str] = {
    "by": "#f0a441",
    "cy": "#12871d",
    "bz": "#7831cc",
}

# Proton mass (for the pure-python fallback terminal-mass computation).
PROTON_MASS = 1.007276

# Cache format version — bump on schema change.
CACHE_VERSION = 1


def _is_match_with_tolerance(sorted_values: List[float], target: float, ppm: float) -> bool:
    """Return True iff some value in ``sorted_values`` matches ``target`` within ``ppm``.

    Binary search over the ascending-sorted list. Faithful port of
    ``isMatchWithTolerance`` (sequence.py:174-201): the tolerance window is
    ``target * ppm / 1e6`` (relative to the target, NOT the candidate).
    """
    tolerance = target * ppm / 1e6
    left, right = 0, len(sorted_values) - 1
    while left <= right:
        mid = (left + right) // 2
        if abs(sorted_values[mid] - target) <= tolerance:
            return True
        elif sorted_values[mid] < target:
            left = mid + 1
        else:
            right = mid - 1
    return False


def _terminal_fragment_masses(sequence: str) -> List[float]:
    """Compute the sorted set of terminal ion masses (by + cz prefix+suffix).

    Mirrors ``getFragmentMassesWithSeq(protein, 'by')`` + ``(protein, 'cz')`` and the
    concatenation/sort at sequence.py:212-216. Uses pyOpenMS for exact parity when
    available, otherwise a pure-python fallback using residue masses + ion offsets.
    """
    try:
        from pyopenms import AASequence, Residue

        def _remove_ambiguous(protein: "AASequence") -> "AASequence":
            return AASequence.fromString(
                protein.toUniModString().replace("X", "").replace("x", "")
            )

        def _masses_with_seq(protein: "AASequence", res_type: str) -> List[float]:
            n = protein.size()
            prefix = [0.0] * n
            suffix = [0.0] * n
            if res_type == "by":
                prefix_ion = Residue.ResidueType.BIon
                suffix_ion = Residue.ResidueType.YIon
            else:  # cz
                prefix_ion = Residue.ResidueType.CIon
                suffix_ion = Residue.ResidueType.ZIon
            for i in range(n):
                prefix[i] = _remove_ambiguous(protein.getPrefix(i + 1)).getMonoWeight(
                    prefix_ion, 0
                )
            for i in reversed(range(n)):
                suffix[i] = _remove_ambiguous(protein.getSuffix(i + 1)).getMonoWeight(
                    suffix_ion, 0
                )
            return prefix + suffix

        protein = AASequence.fromString(sequence)
        terminal = _masses_with_seq(protein, "by") + _masses_with_seq(protein, "cz")
        terminal.sort()
        return terminal
    except Exception:
        return _terminal_fragment_masses_simple(sequence)


def _terminal_fragment_masses_simple(sequence: str) -> List[float]:
    """Pure-python fallback for terminal ion masses (no pyOpenMS).

    Uses prefix/suffix cumulative residue masses + standard b/y/c/z neutral offsets.
    Not bit-identical to pyOpenMS but sufficient for the 10 ppm terminal exclusion in
    environments without pyOpenMS (and for unit tests).
    """
    residues = [c for c in sequence if c in AA_MASSES]
    n = len(residues)
    if n == 0:
        return []

    prefix_cum = []
    running = 0.0
    for aa in residues:
        running += AA_MASSES[aa]
        prefix_cum.append(running)

    suffix_cum = []
    running = 0.0
    for aa in reversed(residues):
        running += AA_MASSES[aa]
        suffix_cum.append(running)
    suffix_cum = list(reversed(suffix_cum))

    # Neutral fragment offsets (relative to summed residue masses).
    B_OFF = 0.0
    Y_OFF = H2O
    C_OFF = NH3
    Z_OFF = H2O - NH3

    terminal: List[float] = []
    for i in range(n):
        terminal.append(prefix_cum[i] + B_OFF)  # b prefix
        terminal.append(prefix_cum[i] + C_OFF)  # c prefix
        terminal.append(suffix_cum[i] + Y_OFF)  # y suffix
        terminal.append(suffix_cum[i] + Z_OFF)  # z suffix
    terminal.sort()
    return terminal


def get_internal_fragment_masses_with_seq(
    sequence: str,
    res_type: str,
    modifications: Optional[List[Tuple[int, int, float]]] = None,
) -> Tuple[List[float], List[int], List[int]]:
    """Faithful port of ``getInternalFragmentMassesWithSeq`` (sequence.py:204-256).

    Args:
        sequence: Plain residue string (single-letter codes).
        res_type: One of ``'by'``, ``'bz'``, ``'cy'`` (``'cz'`` is equivalent to ``'by'``).
        modifications: Optional list of ``(start, end, mass)`` with 1-based inclusive
            ranges (as produced by FLASHApp's modification handling).

    Returns:
        ``(masses, start_indices, end_indices)`` where ``start_indices`` are 0-based
        N-terminal indices ``i`` and ``end_indices`` are the C-terminal bound ``j+1``.
    """
    # Per-type mass shift (sequence.py:205).
    if res_type == "by" or res_type == "cz":
        shift = -H2O
    elif res_type == "bz":
        shift = -H2O - NH3
    else:  # cy
        shift = -H2O + NH3

    masses: List[float] = []
    start_indices: List[int] = []
    end_indices: List[int] = []

    terminal_masses = _terminal_fragment_masses(sequence)

    seq_len = len(sequence)
    # Iterate over N-terminal bound i.
    for i, _ in enumerate(sequence):
        # First position cannot have internal fragments.
        if i == 0:
            continue
        # Last position cannot have internal fragments.
        if i == seq_len - 1:
            break
        mass = 0.0
        # Iterate over C-terminal bound j.
        for j in range(seq_len):
            # Valid internal fragments have C-terminal bound >= N-terminal.
            if j >= i:
                mass = mass + AA_MASSES.get(sequence[j], 0.0)
            # Only consider fragments of at least length 5.
            if j < i + 5 - 1:
                continue

            possible_masses = [mass]

            if modifications is not None:
                for s, e, m in modifications:
                    # Modification fully contained.
                    if (s >= i + 1) and (e <= j + 1):
                        possible_masses[0] += m
                    # Modification partially contained.
                    elif (s >= i + 1) or (e <= j + 1):
                        possible_masses.append(mass + m)

            # NOTE: the loop variable reuse of `mass` here is a faithful port of the
            # original (sequence.py:247). Without mods possible_masses == [mass], so the
            # reuse is a no-op on the common path.
            for mass in possible_masses:
                if _is_match_with_tolerance(terminal_masses, mass, 10.0):
                    continue
                masses.append(mass + H2O + shift)
                start_indices.append(i)
                end_indices.append(j + 1)
    return masses, start_indices, end_indices


def get_internal_fragment_data_from_seq(
    sequence: str,
    modifications: Optional[List[Tuple[int, int, float]]] = None,
) -> Dict[str, List[Any]]:
    """Faithful port of ``getInternalFragmentDataFromSeq`` (sequence.py:260-274).

    Returns a dict with, per ion type in ``('by','bz','cy')``: ``fragment_masses_{t}``,
    ``start_indices_{t}``, ``end_indices_{t}``.
    """
    out: Dict[str, List[Any]] = {}
    for ion_type in ION_TYPES:
        ions, starts, ends = get_internal_fragment_masses_with_seq(
            sequence, ion_type, modifications
        )
        out["fragment_masses_%s" % ion_type] = ions
        out["start_indices_%s" % ion_type] = starts
        out["end_indices_%s" % ion_type] = ends
    return out


def _parse_residues(sequence_str: str) -> List[str]:
    """Extract single-letter residues from a (possibly modified) OpenMS sequence.

    Uses pyOpenMS when available; otherwise a naive parser stripping modification
    parentheses.
    """
    try:
        from pyopenms import AASequence

        aa_seq = AASequence.fromString(sequence_str)
        return [aa_seq.getResidue(i).getOneLetterCode() for i in range(aa_seq.size())]
    except Exception:
        residues: List[str] = []
        i = 0
        while i < len(sequence_str):
            ch = sequence_str[i]
            if ch.isalpha():
                residues.append(ch.upper())
                i += 1
            elif ch == "(":
                end = sequence_str.find(")", i)
                i = end + 1 if end > i else i + 1
            elif ch == "[":
                end = sequence_str.find("]", i)
                i = end + 1 if end > i else i + 1
            else:
                i += 1
        return residues


@register_component("internalfragmentmap")
class InternalFragmentMap(BaseComponent):
    """Internal fragment map over a peptide/protein sequence (consumer-only).

    Computes the FLASHApp internal-fragment masses per ion type (``by`` / ``bz`` /
    ``cy``) and renders them as a per-type matrix over the sequence in Vue. Filters by
    ``proteinIndex`` (FLASHTnT) or uses a single configured sequence (FLASHDeconv).

    Example (FLASHTnT — proteoform-keyed)::

        ifm = InternalFragmentMap(
            cache_id="ifm",
            sequence_data=proteoform_lf,          # cols: proteoform_index, sequence, ...
            filters={"proteinIndex": "proteoform_index"},
            cache_path=cache_dir,
        )
        ifm(key="ifm", state_manager=state_manager)

    Example (FLASHDeconv — single sequence)::

        ifm = InternalFragmentMap(cache_id="ifm", sequence_data="PEPTIDESEQUENCE")
    """

    _component_type: str = "internalfragmentmap"

    def __init__(
        self,
        cache_id: str,
        sequence_data: Optional[Union[pl.LazyFrame, str]] = None,
        sequence_data_path: Optional[str] = None,
        peaks_data: Optional[pl.LazyFrame] = None,
        peaks_data_path: Optional[str] = None,
        filters: Optional[Dict[str, str]] = None,
        modifications: Optional[List[Tuple[int, int, float]]] = None,
        tolerance: float = 10.0,
        tolerance_ppm: bool = True,
        ion_colors: Optional[Dict[str, str]] = None,
        cache_path: str = ".",
        title: Optional[str] = "Internal Fragment Map",
        height: int = 400,
        **kwargs,
    ):
        """Initialize the component.

        Args:
            cache_id: Unique identifier for this component's cache (MANDATORY).
            sequence_data: One of:
                - LazyFrame with a ``sequence`` column (+ optional filter column,
                  optional ``proteoform_start`` / ``proteoform_end`` / ``computed_mass``).
                - Plain sequence string (single configured sequence; FLASHDeconv).
            sequence_data_path: Parquet path with the sequence frame.
            peaks_data: Optional LazyFrame of observed (deconvolved) masses with a
                ``mass`` column (+ optional filter column for the scan). When provided,
                Vue keeps only fragments matching an observed mass within ``tolerance``.
            peaks_data_path: Parquet path with the observed-mass frame.
            filters: Mapping of identifier -> column name for filtering. For FLASHTnT use
                ``{"proteinIndex": "proteoform_index"}``. None / no selection -> empty.
            modifications: Optional static modification list ``[(start, end, mass), ...]``
                (1-based inclusive ranges) applied in the internal-fragment compute.
            tolerance: Observed/theoretical match tolerance shown to Vue (default 10).
            tolerance_ppm: Whether ``tolerance`` is ppm (default True) or Da.
            ion_colors: Optional override of per-type colors (keys ``by``/``cy``/``bz``).
            cache_path: Base path for cache storage.
            title: Title displayed above the map. Default ``"Internal Fragment Map"``.
            height: Component height in pixels.
        """
        # Pop conflicting kwargs that the subprocess path may re-pass explicitly.
        kwargs.pop("filter_defaults", None)
        kwargs.pop("interactivity", None)

        self._title = title
        self._height = height
        self._modifications = modifications
        self._tolerance = tolerance
        self._tolerance_ppm = tolerance_ppm
        self._ion_colors = {**DEFAULT_ION_COLORS, **(ion_colors or {})}

        # Resolve sequence-data source (static string vs frame).
        self._source_static_sequence: Optional[str] = None
        if sequence_data is not None and sequence_data_path is not None:
            raise ValueError(
                "Provide either 'sequence_data' or 'sequence_data_path', not both"
            )
        if isinstance(sequence_data, str):
            self._source_static_sequence = sequence_data
            sequence_lf: Optional[pl.LazyFrame] = pl.LazyFrame(
                {"sequence": [sequence_data]}
            )
        elif isinstance(sequence_data, pl.LazyFrame):
            sequence_lf = sequence_data
        elif sequence_data_path is not None:
            sequence_lf = pl.scan_parquet(sequence_data_path)
        else:
            sequence_lf = None

        if peaks_data is not None and peaks_data_path is not None:
            raise ValueError(
                "Provide either 'peaks_data' or 'peaks_data_path', not both"
            )
        if peaks_data_path is not None:
            peaks_data = pl.scan_parquet(peaks_data_path)
        self._source_peaks_data = peaks_data

        # filter_defaults: every filter defaults to None (clearing selection -> empty).
        # Pass None (not {}) when there are no filters so reconstruction mode (no data,
        # no config) is not misdetected as "config provided" by BaseComponent.
        filter_defaults = (
            {ident: None for ident in filters.keys()} if filters else None
        )

        super().__init__(
            cache_id=cache_id,
            data=sequence_lf,
            filters=filters,
            filter_defaults=filter_defaults,
            interactivity=None,
            cache_path=cache_path,
            # Pass config for subprocess/cache reconstruction.
            modifications=modifications,
            tolerance=tolerance,
            tolerance_ppm=tolerance_ppm,
            ion_colors=self._ion_colors,
            title=title,
            height=height,
            static_sequence=self._source_static_sequence,
            **kwargs,
        )

    # ------------------------------------------------------------------ caching

    def _validate_mappings(self) -> None:
        """Validate the sequence frame has a 'sequence' column and filter columns exist."""
        if self._raw_data is None:
            return
        schema = self._raw_data.collect_schema()
        names = schema.names()
        if "sequence" not in names:
            raise ValueError(
                f"sequence_data must contain a 'sequence' column. Available: {names}"
            )
        for identifier, column in self._filters.items():
            if column not in names:
                raise ValueError(
                    f"Filter column '{column}' for identifier '{identifier}' not found. "
                    f"Available columns: {names}"
                )

    def _preprocess(self) -> None:
        """Cache the sequence frame (sorted by filter columns) and optional peaks frame."""
        data = self._raw_data
        filter_cols = [c for c in self._filters.values()]

        # Keep only useful columns, preserving the filter + sequence + optional metadata.
        schema = data.collect_schema()
        wanted = filter_cols + [
            c
            for c in (
                "sequence",
                "proteoform_start",
                "proteoform_end",
                "computed_mass",
            )
            if c in schema.names()
        ]
        wanted = list(dict.fromkeys(wanted))
        data = data.select(wanted)
        if filter_cols:
            data = data.sort(filter_cols)
        self._preprocessed_data["sequences"] = data

        if self._source_peaks_data is not None:
            peaks = self._source_peaks_data
            pschema = peaks.collect_schema()
            pcols = [c for c in filter_cols if c in pschema.names()]
            if "mass" in pschema.names():
                pcols.append("mass")
            pcols = list(dict.fromkeys(pcols))
            peaks = peaks.select(pcols)
            if [c for c in filter_cols if c in pschema.names()]:
                peaks = peaks.sort([c for c in filter_cols if c in pschema.names()])
            self._preprocessed_data["peaks"] = peaks

    def _get_cache_config(self) -> Dict[str, Any]:
        return {
            "version": CACHE_VERSION,
            "title": self._title,
            "height": self._height,
            "modifications": self._modifications,
            "tolerance": self._tolerance,
            "tolerance_ppm": self._tolerance_ppm,
            "ion_colors": self._ion_colors,
            "static_sequence": self._source_static_sequence,
        }

    def _restore_cache_config(self, config: Dict[str, Any]) -> None:
        self._title = config.get("title", "Internal Fragment Map")
        self._height = config.get("height", 400)
        mods = config.get("modifications")
        # JSON round-trips tuples to lists — normalize back to tuples.
        self._modifications = (
            [tuple(m) for m in mods] if mods is not None else None
        )
        self._tolerance = config.get("tolerance", 10.0)
        self._tolerance_ppm = config.get("tolerance_ppm", True)
        self._ion_colors = config.get("ion_colors", {**DEFAULT_ION_COLORS})
        self._source_static_sequence = config.get("static_sequence")
        self._source_peaks_data = None

    # --------------------------------------------------------------- data access

    def _get_sequence_for_state(self, state: Dict[str, Any]) -> str:
        """Resolve the sequence string for the current selection state.

        Honors None-default filters: when a filter is None and its default is None,
        returns an empty string (empty map). Applies proteoform_start/end slicing when
        present (mirrors the FLASHApp .vue sequence slicing).
        """
        seqs = self._preprocessed_data.get("sequences")
        if seqs is None:
            return ""
        if isinstance(seqs, pl.DataFrame):
            seqs = seqs.lazy()

        schema = seqs.collect_schema()
        names = schema.names()
        filtered = seqs
        for identifier, column in self._filters.items():
            if column in names:
                value = state.get(identifier)
                if value is not None:
                    filtered = filtered.filter(pl.col(column) == value)
                elif self._filter_defaults.get(identifier, "__missing__") is None:
                    return ""

        try:
            df = filtered.head(1).collect()
        except Exception:
            return ""
        if df.height == 0:
            return ""

        sequence = df["sequence"][0] or ""
        start = df["proteoform_start"][0] if "proteoform_start" in names else None
        end = df["proteoform_end"][0] if "proteoform_end" in names else None
        if start is not None and end is not None and sequence:
            return sequence[int(start) : int(end) + 1]
        return sequence

    def _get_observed_masses_for_state(self, state: Dict[str, Any]) -> List[float]:
        """Resolve observed (deconvolved) masses for the current state, if peaks exist."""
        peaks = self._preprocessed_data.get("peaks")
        if peaks is None:
            return []
        if isinstance(peaks, pl.DataFrame):
            peaks = peaks.lazy()
        schema = peaks.collect_schema()
        names = schema.names()
        if "mass" not in names:
            return []
        filtered = peaks
        for identifier, column in self._filters.items():
            if column in names:
                value = state.get(identifier)
                if value is not None:
                    filtered = filtered.filter(pl.col(column) == value)
                elif self._filter_defaults.get(identifier, "__missing__") is None:
                    return []
        try:
            return filtered.select("mass").collect()["mass"].to_list()
        except Exception:
            return []

    def _compute_internal_fragments(self, sequence_str: str) -> Dict[str, List[Any]]:
        """Compute the per-ion-type internal-fragment arrays from a sequence string."""
        residues = _parse_residues(sequence_str)
        plain = "".join(residues)
        if not plain:
            return {
                k: []
                for ion in ION_TYPES
                for k in (
                    f"fragment_masses_{ion}",
                    f"start_indices_{ion}",
                    f"end_indices_{ion}",
                )
            }
        return get_internal_fragment_data_from_seq(plain, self._modifications)

    # --------------------------------------------------------------- vue payload

    def _prepare_vue_data(self, state: Dict[str, Any]) -> Dict[str, Any]:
        sequence_str = self._get_sequence_for_state(state)
        residues = _parse_residues(sequence_str)
        fragment_data = self._compute_internal_fragments(sequence_str)
        observed_masses = self._get_observed_masses_for_state(state)

        internal_fragment_data = {
            "sequence": residues,
            **fragment_data,
        }

        hash_input = json.dumps(
            {
                "seq": "".join(residues),
                "obs": len(observed_masses),
                "tol": self._tolerance,
                "ppm": self._tolerance_ppm,
            },
            sort_keys=True,
        )
        data_hash = hashlib.md5(hash_input.encode()).hexdigest()[:8]

        return {
            "internalFragmentData": internal_fragment_data,
            "observedMasses": observed_masses,
            "settings": {
                "tolerance": self._tolerance,
                "toleranceUnit": "ppm" if self._tolerance_ppm else "Da",
                "ionColors": self._ion_colors,
            },
            "_hash": data_hash,
        }

    def _get_vue_component_name(self) -> str:
        return "InternalFragmentMap"

    def _get_data_key(self) -> str:
        return "internalFragmentData"

    def _get_component_args(self) -> Dict[str, Any]:
        args: Dict[str, Any] = {
            "componentType": self._get_vue_component_name(),
            "height": self._height,
            "title": self._title or "Internal Fragment Map",
            "tolerance": self._tolerance,
            "toleranceUnit": "ppm" if self._tolerance_ppm else "Da",
            "ionColors": self._ion_colors,
        }
        return args

    def get_state_dependencies(self) -> List[str]:
        """Filter identifiers (proteinIndex / scanIndex). Clears recompute the map."""
        return list(self._filters.keys())

    def __repr__(self) -> str:
        return (
            f"InternalFragmentMap(cache_id='{self._cache_id}', "
            f"filters={self._filters})"
        )


if TYPE_CHECKING:
    from ..core.state import StateManager  # noqa: F401
