"""Internal fragment map component.

Ports FLASHApp's computed-but-disabled InternalFragmentMap into a reusable
OpenMS-Insight component. For a given proteoform sequence it enumerates
*internal* fragment ions — fragments bounded on both sides inside the
sequence — of three ion-pair types (by, bz, cy), each with its start/end
residue indices. Internal fragments must be at least 5 residues long and must
not coincide (within tolerance) with a terminal b/y/c/z ion; both rules match
the original ``getInternalFragmentMassesWithSeq`` (``sequence.py:204-274``).

The Vue side matches these theoretical internal-fragment masses against the
observed masses of the selected scan and renders colored blocks spanning each
matched fragment's residue range over the sequence.

The mass arithmetic uses pyOpenMS when available (for exact residue/terminal
masses) and falls back to a static monoisotopic amino-acid table otherwise, so
the component and its core algorithm are importable and testable without
pyOpenMS — the same strategy ``sequenceview.py`` uses.
"""

import hashlib
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple, Union

import polars as pl

from ..core.registry import register_component

# Monoisotopic constants (match src/render/sequence.py)
H2O = 18.010564683
NH3 = 17.0265491015

# Monoisotopic residue masses (match src/render/sequence.py aa_masses)
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

# Internal-fragment shift per ion-pair type (match sequence.py getInternal...):
#   by, cz -> -H2O ; bz -> -H2O - NH3 ; cy -> -H2O + NH3
_TYPE_SHIFT = {
    "by": -H2O,
    "cz": -H2O,
    "bz": -H2O - NH3,
    "cy": -H2O + NH3,
}

# Minimum internal-fragment length (residues)
_MIN_INTERNAL_LENGTH = 5

# ppm tolerance used to exclude internal fragments coinciding with terminal ions
_TERMINAL_EXCLUSION_PPM = 10.0


def _terminal_masses(sequence: str) -> List[float]:
    """Sorted b/y + c/z terminal-ion neutral masses for every cleavage site.

    Used to exclude internal fragments whose mass coincides with a terminal
    ion. Uses pyOpenMS for exact ion masses when available, else a static
    table. The two paths agree to well under the 10 ppm exclusion tolerance.
    """
    try:
        from pyopenms import AASequence, Residue

        protein = AASequence.fromString(
            AASequence.fromString(sequence)
            .toUniModString()
            .replace("X", "")
            .replace("x", "")
        )
        n = protein.size()
        masses: List[float] = []
        for k in range(1, n + 1):
            prefix = protein.getPrefix(k)
            suffix = protein.getSuffix(k)
            masses.append(prefix.getMonoWeight(Residue.ResidueType.BIon, 0))
            masses.append(prefix.getMonoWeight(Residue.ResidueType.CIon, 0))
            masses.append(suffix.getMonoWeight(Residue.ResidueType.YIon, 0))
            masses.append(suffix.getMonoWeight(Residue.ResidueType.ZIon, 0))
        masses.sort()
        return masses
    except Exception:
        # Static-table fallback: b = prefix sum; y = suffix sum + H2O;
        # c = b + NH3; z = y - NH3.
        n = len(sequence)
        prefix = [0.0] * n
        suffix = [0.0] * n
        running = 0.0
        for i, aa in enumerate(sequence):
            running += AA_MASSES.get(aa, 0.0)
            prefix[i] = running
        running = 0.0
        for i in range(n - 1, -1, -1):
            running += AA_MASSES.get(sequence[i], 0.0)
            suffix[i] = running
        masses = []
        for i in range(n):
            b = prefix[i]
            y = suffix[i] + H2O
            masses.extend([b, b + NH3, y, y - NH3])
        masses.sort()
        return masses


def _matches_within_ppm(sorted_masses: List[float], target: float, ppm: float) -> bool:
    """Binary search: is any value in sorted_masses within ``ppm`` of target?"""
    if not sorted_masses:
        return False
    tolerance = target * ppm / 1e6
    lo, hi = 0, len(sorted_masses) - 1
    while lo <= hi:
        mid = (lo + hi) // 2
        if abs(sorted_masses[mid] - target) <= tolerance:
            return True
        elif sorted_masses[mid] < target:
            lo = mid + 1
        else:
            hi = mid - 1
    return False


def internal_fragment_masses(
    sequence: str, ion_type: str, exclude_terminal: bool = True
) -> Tuple[List[float], List[int], List[int]]:
    """Enumerate internal fragments of one ion-pair type for a sequence.

    Faithful port of ``getInternalFragmentMassesWithSeq`` (sequence.py:204-274,
    modifications omitted). Internal fragments span residues [i, j] strictly
    inside the sequence (the first and last residues are excluded as bounds),
    must be at least 5 residues long, and — when ``exclude_terminal`` — must not
    coincide within 10 ppm with a terminal b/y/c/z ion.

    Args:
        sequence: plain residue string (no modifications).
        ion_type: one of "by", "bz", "cy" (also accepts "cz" as alias of "by"
            shift).
        exclude_terminal: drop fragments matching a terminal ion (default True).

    Returns:
        (masses, start_indices, end_indices) — parallel lists. ``start`` is the
        N-terminal bound index i; ``end`` is j+1 (matching the original).
    """
    if ion_type not in _TYPE_SHIFT:
        raise ValueError(
            f"Unknown ion_type '{ion_type}'. Expected one of {sorted(_TYPE_SHIFT)}."
        )
    shift = _TYPE_SHIFT[ion_type]
    terminal = _terminal_masses(sequence) if exclude_terminal else []

    masses: List[float] = []
    start_indices: List[int] = []
    end_indices: List[int] = []

    seq_len = len(sequence)
    for i in range(seq_len):
        # First residue cannot start an internal fragment; last cannot end one.
        if i == 0:
            continue
        if i == seq_len - 1:
            break
        mass = 0.0
        for j in range(seq_len):
            if j >= i:
                mass += AA_MASSES.get(sequence[j], 0.0)
            # Only fragments of length >= 5
            if j < i + _MIN_INTERNAL_LENGTH - 1:
                continue
            candidate = mass
            if exclude_terminal and _matches_within_ppm(
                terminal, candidate, _TERMINAL_EXCLUSION_PPM
            ):
                continue
            masses.append(candidate + H2O + shift)
            start_indices.append(i)
            end_indices.append(j + 1)

    return masses, start_indices, end_indices


def internal_fragment_data(
    sequence: str, exclude_terminal: bool = True
) -> Dict[str, List]:
    """Compute internal-fragment data for all three ion-pair types.

    Faithful port of ``getInternalFragmentDataFromSeq``. Returns a dict with
    ``fragment_masses_<t>`` / ``start_indices_<t>`` / ``end_indices_<t>`` for
    each t in {by, bz, cy} — the exact schema the Vue component consumes.
    """
    out: Dict[str, List] = {}
    for ion_type in ("by", "bz", "cy"):
        masses, starts, ends = internal_fragment_masses(
            sequence, ion_type, exclude_terminal=exclude_terminal
        )
        out[f"fragment_masses_{ion_type}"] = masses
        out[f"start_indices_{ion_type}"] = starts
        out[f"end_indices_{ion_type}"] = ends
    return out


@register_component("internal_fragment_map")
class InternalFragmentMap:
    """
    Internal fragment map for a proteoform sequence.

    Computes per-type (by/bz/cy) internal-fragment masses and residue ranges
    for a sequence, and ships them alongside the sequence and the selected
    scan's observed masses to the Vue frontend, which matches and renders
    colored fragment blocks over the sequence.

    Follows the SequenceView component shape: ``sequence_data`` (a LazyFrame
    filtered by an identifier, or a static string) plus ``peaks_data`` (the
    observed masses, filtered by a scan identifier). Cross-link via ``filters``,
    typically ``{"proteinIndex": "proteoform_index", "scanIndex": "scan_id"}``.

    Example:
        ifm = InternalFragmentMap(
            cache_id="ifm",
            sequence_data=sequences_df,          # columns: proteoform_index, sequence
            peaks_data=peaks_df,                 # columns: scan_id, mass
            filters={"proteinIndex": "proteoform_index", "scanIndex": "scan_id"},
        )
        ifm(key="ifm", state_manager=state_manager)
    """

    _component_type: str = "internal_fragment_map"

    # ---- Color defaults (match InternalFragmentMap.vue legend) ----
    DEFAULT_COLORS = {
        "by": "#f0a441",  # by/cz
        "cy": "#12871d",
        "bz": "#7831cc",
    }

    def __init__(
        self,
        cache_id: str,
        sequence_data: Optional[Union[pl.LazyFrame, str]] = None,
        sequence_data_path: Optional[str] = None,
        peaks_data: Optional[pl.LazyFrame] = None,
        peaks_data_path: Optional[str] = None,
        filters: Optional[Dict[str, str]] = None,
        cache_path: str = ".",
        sequence_column: str = "sequence",
        mass_column: str = "mass",
        tolerance_ppm: float = 10.0,
        exclude_terminal: bool = True,
        colors: Optional[Dict[str, str]] = None,
        title: Optional[str] = None,
        height: int = 400,
        **kwargs,
    ):
        """
        Initialize the InternalFragmentMap component.

        Args:
            cache_id: Unique identifier for this component's cache (MANDATORY).
            sequence_data: A LazyFrame with a ``sequence_column`` (and any filter
                columns), or a static sequence string. Optional if cache exists.
            sequence_data_path: Path to a parquet file with sequence data.
            peaks_data: LazyFrame with observed masses (``mass_column`` plus any
                filter columns), used for matching on the Vue side.
            peaks_data_path: Path to a parquet file with peaks data.
            filters: Mapping of identifier names to column names. Typically
                ``{"proteinIndex": "proteoform_index", "scanIndex": "scan_id"}``.
            cache_path: Base path for cache storage. Default "." (current dir).
            sequence_column: Sequence column name. Default "sequence".
            mass_column: Observed-mass column name. Default "mass".
            tolerance_ppm: ppm tolerance for matching observed vs theoretical
                internal-fragment masses on the Vue side. Default 10.0.
            exclude_terminal: Exclude internal fragments coinciding with terminal
                ions (default True), matching the original.
            colors: Optional override of the per-type block colors.
            title: Optional title.
            height: Component height in pixels.
            **kwargs: Additional configuration options forwarded to Vue args.
        """
        self._cache_id = cache_id
        self._cache_path = Path(cache_path)
        self._cache_dir = self._cache_path / cache_id

        self._sequence_column = sequence_column
        self._mass_column = mass_column
        self._tolerance_ppm = tolerance_ppm
        self._exclude_terminal = exclude_terminal
        self._colors = {**self.DEFAULT_COLORS, **(colors or {})}
        self._title = title
        self._height = height
        self._config = kwargs

        has_sequence = sequence_data is not None or sequence_data_path is not None

        if not has_sequence:
            if not self._cache_exists():
                raise ValueError(
                    f"Cache not found at '{self._cache_dir}'. Provide "
                    f"sequence_data= or sequence_data_path= to create the cache."
                )
            self._load_from_cache()
        else:
            self._filters = filters or {}
            self._filter_defaults = dict.fromkeys(self._filters)

            # Resolve sequence source
            self._static_sequence: Optional[str] = None
            self._source_sequences: Optional[pl.LazyFrame] = None
            if sequence_data_path is not None:
                self._source_sequences = pl.scan_parquet(sequence_data_path)
            elif isinstance(sequence_data, pl.LazyFrame):
                self._source_sequences = sequence_data
            elif isinstance(sequence_data, str):
                self._static_sequence = sequence_data

            # Resolve peaks source
            self._source_peaks: Optional[pl.LazyFrame] = None
            if peaks_data_path is not None:
                self._source_peaks = pl.scan_parquet(peaks_data_path)
            elif peaks_data is not None:
                self._source_peaks = peaks_data

            self._create_cache()
            # Load cached frames for reading
            self._cached_sequences = (
                pl.scan_parquet(self._cache_dir / "sequences.parquet")
                if (self._cache_dir / "sequences.parquet").exists()
                else None
            )
            peaks_path = self._cache_dir / "peaks.parquet"
            self._cached_peaks = (
                pl.scan_parquet(peaks_path) if peaks_path.exists() else None
            )

    # ---- cache management (mirrors SequenceView) ----
    def _config_dict(self) -> Dict[str, Any]:
        return {
            "filters": self._filters,
            "sequence_column": self._sequence_column,
            "mass_column": self._mass_column,
            "tolerance_ppm": self._tolerance_ppm,
            "exclude_terminal": self._exclude_terminal,
            "colors": self._colors,
            "title": self._title,
            "height": self._height,
            "static_sequence": self._static_sequence,
        }

    def _cache_exists(self) -> bool:
        return (self._cache_dir / ".cache_config.json").exists()

    def _create_cache(self) -> None:
        self._cache_dir.mkdir(parents=True, exist_ok=True)

        # Sequences
        if self._source_sequences is not None:
            schema = self._source_sequences.collect_schema().names()
            filter_cols = [c for c in self._filters.values() if c in schema]
            cols = list(
                dict.fromkeys(
                    filter_cols
                    + ([self._sequence_column] if self._sequence_column in schema else [])
                )
            )
            lf = self._source_sequences.select(cols)
            if filter_cols:
                lf = lf.sort(filter_cols)
            lf.collect().write_parquet(
                self._cache_dir / "sequences.parquet", compression="zstd"
            )
        elif self._static_sequence is not None:
            pl.DataFrame({self._sequence_column: [self._static_sequence]}).write_parquet(
                self._cache_dir / "sequences.parquet", compression="zstd"
            )

        # Peaks
        if self._source_peaks is not None:
            schema = self._source_peaks.collect_schema().names()
            filter_cols = [c for c in self._filters.values() if c in schema]
            cols = list(
                dict.fromkeys(
                    filter_cols
                    + ([self._mass_column] if self._mass_column in schema else [])
                )
            )
            lf = self._source_peaks.select(cols)
            if filter_cols:
                lf = lf.sort(filter_cols)
            lf.collect().write_parquet(
                self._cache_dir / "peaks.parquet", compression="zstd"
            )

        with open(self._cache_dir / ".cache_config.json", "w") as f:
            json.dump(self._config_dict(), f, indent=2)

    def _load_from_cache(self) -> None:
        with open(self._cache_dir / ".cache_config.json") as f:
            cfg = json.load(f)
        self._filters = cfg.get("filters", {})
        self._filter_defaults = dict.fromkeys(self._filters)
        self._sequence_column = cfg.get("sequence_column", "sequence")
        self._mass_column = cfg.get("mass_column", "mass")
        self._tolerance_ppm = cfg.get("tolerance_ppm", 10.0)
        self._exclude_terminal = cfg.get("exclude_terminal", True)
        self._colors = cfg.get("colors", dict(self.DEFAULT_COLORS))
        self._title = cfg.get("title")
        self._height = cfg.get("height", 400)
        self._static_sequence = cfg.get("static_sequence")
        seq_path = self._cache_dir / "sequences.parquet"
        self._cached_sequences = (
            pl.scan_parquet(seq_path) if seq_path.exists() else None
        )
        peaks_path = self._cache_dir / "peaks.parquet"
        self._cached_peaks = (
            pl.scan_parquet(peaks_path) if peaks_path.exists() else None
        )

    # ---- data resolution ----
    def _get_sequence_for_state(self, state: Dict[str, Any]) -> str:
        if self._cached_sequences is None:
            return self._static_sequence or ""
        filtered = self._cached_sequences
        schema = filtered.collect_schema().names()
        for identifier, column in self._filters.items():
            if column in schema:
                value = state.get(identifier)
                if value is not None:
                    filtered = filtered.filter(pl.col(column) == value)
                else:
                    return ""
        try:
            df = filtered.select(self._sequence_column).head(1).collect()
            if df.height > 0:
                return df[self._sequence_column][0]
        except Exception:
            pass
        return ""

    def _get_observed_masses(self, state: Dict[str, Any]) -> List[float]:
        if self._cached_peaks is None:
            return []
        filtered = self._cached_peaks
        schema = filtered.collect_schema().names()
        for identifier, column in self._filters.items():
            if column in schema:
                value = state.get(identifier)
                if value is not None:
                    filtered = filtered.filter(pl.col(column) == value)
                else:
                    return []
        try:
            return filtered.select(self._mass_column).collect()[self._mass_column].to_list()
        except Exception:
            return []

    # ---- BaseComponent-compatible surface (duck-typed like SequenceView) ----
    def get_filters_mapping(self) -> Dict[str, str]:
        return self._filters.copy()

    def get_interactivity_mapping(self) -> Dict[str, str]:
        return {}

    def get_filter_defaults(self) -> Dict[str, Any]:
        return self._filter_defaults.copy()

    def get_state_dependencies(self) -> List[str]:
        return list(self._filters.keys())

    def _get_vue_component_name(self) -> str:
        return "InternalFragmentMap"

    def _get_data_key(self) -> str:
        return "internalFragmentData"

    def _prepare_vue_data(self, state: Dict[str, Any]) -> Dict[str, Any]:
        sequence = self._get_sequence_for_state(state)
        observed = self._get_observed_masses(state)

        if sequence:
            frag = internal_fragment_data(
                sequence, exclude_terminal=self._exclude_terminal
            )
        else:
            frag = {
                f"{prefix}_{t}": []
                for t in ("by", "bz", "cy")
                for prefix in ("fragment_masses", "start_indices", "end_indices")
            }

        payload = {
            "sequence": list(sequence),
            "observedMasses": observed,
            "tolerancePpm": self._tolerance_ppm,
            "colors": self._colors,
            **frag,
        }

        hash_src = f"{sequence}:{len(observed)}:{self._tolerance_ppm}"
        data_hash = hashlib.md5(hash_src.encode()).hexdigest()[:8]
        return {"internalFragmentData": payload, "_hash": data_hash}

    def _get_component_args(self) -> Dict[str, Any]:
        args: Dict[str, Any] = {
            "componentType": self._get_vue_component_name(),
            "height": self._height,
            "colors": self._colors,
            "tolerancePpm": self._tolerance_ppm,
        }
        if self._title:
            args["title"] = self._title
        for key, val in self._config.items():
            if key not in args:
                args[key] = val
        return args

    def __call__(
        self,
        key: Optional[str] = None,
        state_manager: Optional["StateManager"] = None,
        height: Optional[int] = None,
    ) -> Any:
        from ..core.state import get_default_state_manager
        from ..rendering.bridge import render_component

        if state_manager is None:
            state_manager = get_default_state_manager()
        render_height = height if height is not None else self._height
        return render_component(
            component=self, state_manager=state_manager, key=key, height=render_height
        )

    def __repr__(self) -> str:
        return (
            f"InternalFragmentMap(cache_id='{self._cache_id}', "
            f"filters={self._filters})"
        )


if TYPE_CHECKING:
    from ..core.state import StateManager
