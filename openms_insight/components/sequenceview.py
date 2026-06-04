"""SequenceView component for peptide/protein sequence visualization with fragment matching."""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple, Union

import polars as pl

from ..core.cache import CacheMissError
from ..core.registry import register_component
from ..preprocessing.filtering import optimize_for_transfer

# Proton mass for m/z calculations
PROTON_MASS = 1.007276

# Cache version - increment when cache format changes
CACHE_VERSION = 1


def parse_openms_sequence(sequence_str: str) -> Tuple[List[str], List[Optional[float]]]:
    """Parse OpenMS sequence format to extract residues and modification mass shifts.

    Converts e.g. 'SHC(Carbamidomethyl)IAEVEK' to:
    - residues: ['S', 'H', 'C', 'I', 'A', 'E', 'V', 'E', 'K']
    - modifications: [None, None, 57.02, None, None, None, None, None, None]

    Args:
        sequence_str: Peptide sequence in OpenMS format with modifications in parentheses

    Returns:
        Tuple of (residues list, modifications list where None means unmodified)
    """
    try:
        from pyopenms import AASequence

        aa_seq = AASequence.fromString(sequence_str)
        residues = []
        modifications = []

        for i in range(aa_seq.size()):
            residue = aa_seq.getResidue(i)
            one_letter = residue.getOneLetterCode()
            residues.append(one_letter)

            mod = residue.getModification()
            if mod:
                diff_mono = mod.getDiffMonoMass()
                modifications.append(round(diff_mono, 2))
            else:
                modifications.append(None)

        return residues, modifications
    except ImportError:
        # Fallback: just extract single-letter codes (naive parsing)
        residues = []
        modifications = []
        i = 0
        while i < len(sequence_str):
            if sequence_str[i].isupper():
                residues.append(sequence_str[i])
                modifications.append(None)
                i += 1
            elif sequence_str[i] == "(":
                # Skip modification name in parentheses
                end = sequence_str.find(")", i)
                if end > i:
                    i = end + 1
                else:
                    i += 1
            else:
                i += 1
        return residues, modifications
    except Exception:
        # On any error, return the raw sequence as single letters
        return list(sequence_str), [None] * len(sequence_str)


def calculate_fragment_masses_pyopenms(
    sequence_str: str,
) -> Dict[str, List[List[float]]]:
    """Calculate theoretical fragment masses using pyOpenMS TheoreticalSpectrumGenerator.

    Args:
        sequence_str: Peptide sequence string (can include modifications)

    Returns:
        Dict with fragment_masses_a, fragment_masses_b, etc.
        Each is a list of lists (one per position, supporting multiple masses).
    """
    try:
        from pyopenms import AASequence, MSSpectrum, TheoreticalSpectrumGenerator

        aa_seq = AASequence.fromString(sequence_str)
        n = aa_seq.size()

        # Configure TheoreticalSpectrumGenerator
        tsg = TheoreticalSpectrumGenerator()
        params = tsg.getParameters()

        params.setValue("add_a_ions", "true")
        params.setValue("add_b_ions", "true")
        params.setValue("add_c_ions", "true")
        params.setValue("add_x_ions", "true")
        params.setValue("add_y_ions", "true")
        params.setValue("add_z_ions", "true")
        params.setValue("add_first_prefix_ion", "true")  # Include b1/a1/c1 ions
        params.setValue("add_metainfo", "true")

        tsg.setParameters(params)

        # Generate spectrum for charge 1, then convert to neutral masses
        spec = MSSpectrum()
        tsg.getSpectrum(spec, aa_seq, 1, 1)

        ion_types = ["a", "b", "c", "x", "y", "z"]
        result = {f"fragment_masses_{ion}": [[] for _ in range(n)] for ion in ion_types}

        # Get ion names from StringDataArrays
        ion_names = []
        sdas = spec.getStringDataArrays()
        for sda in sdas:
            if sda.getName() == "IonNames":
                for i in range(sda.size()):
                    name = sda[i]
                    if isinstance(name, bytes):
                        name = name.decode("utf-8")
                    ion_names.append(name)
                break

        # Parse peaks and organize by ion type and position
        for i in range(spec.size()):
            peak = spec[i]
            # Convert singly-charged m/z to neutral mass
            mz_charge1 = peak.getMZ()
            neutral_mass = mz_charge1 - PROTON_MASS
            ion_name = ion_names[i] if i < len(ion_names) else ""

            if not ion_name:
                continue

            # Parse ion name (e.g., "b3+", "y5++")
            ion_type = None
            ion_number = None

            for t in ion_types:
                if ion_name.lower().startswith(t):
                    ion_type = t
                    try:
                        num_str = ""
                        for c in ion_name[1:]:
                            if c.isdigit():
                                num_str += c
                            else:
                                break
                        if num_str:
                            ion_number = int(num_str)
                    except (ValueError, IndexError):
                        pass
                    break

            if ion_type and ion_number and 1 <= ion_number <= n:
                idx = ion_number - 1
                key = f"fragment_masses_{ion_type}"
                if idx < len(result[key]):
                    result[key][idx].append(neutral_mass)

        return result

    except ImportError:
        # Fallback to simple calculation without pyOpenMS
        return _calculate_fragment_masses_simple(sequence_str)
    except Exception as e:
        print(f"Error calculating fragments for {sequence_str}: {e}")
        return {f"fragment_masses_{ion}": [] for ion in ["a", "b", "c", "x", "y", "z"]}


def _calculate_fragment_masses_simple(
    sequence_str: str,
) -> Dict[str, List[List[float]]]:
    """Fallback fragment calculation without pyOpenMS."""
    # Amino acid monoisotopic masses
    AA_MASSES = {
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
        "U": 150.953633,
        "W": 186.079313,
        "Y": 163.063329,
        "V": 99.068414,
    }

    # Ion type offsets
    ION_OFFSETS = {
        "a": -27.994915,
        "b": 0.0,
        "c": 17.026549,
        "x": 43.989829,
        "y": 18.010565,
        "z": 1.991841,
    }

    # Extract plain sequence
    residues, _ = parse_openms_sequence(sequence_str)
    n = len(residues)
    result = {}

    # Calculate prefix masses
    prefix_masses = []
    mass = 0.0
    for aa in residues:
        mass += AA_MASSES.get(aa, 0.0)
        prefix_masses.append(mass)

    # Calculate suffix masses
    suffix_masses = []
    mass = 0.0
    for aa in reversed(residues):
        mass += AA_MASSES.get(aa, 0.0)
        suffix_masses.append(mass)
    suffix_masses = list(reversed(suffix_masses))

    # Prefix ions (a, b, c)
    for ion_type in ["a", "b", "c"]:
        masses = []
        for i in range(n):
            ion_mass = prefix_masses[i] + ION_OFFSETS[ion_type]
            masses.append([ion_mass])
        result[f"fragment_masses_{ion_type}"] = masses

    # Suffix ions (x, y, z)
    for ion_type in ["x", "y", "z"]:
        masses = []
        for i in range(n):
            idx = n - i - 1
            ion_mass = suffix_masses[idx] + ION_OFFSETS[ion_type]
            masses.append([ion_mass])
        result[f"fragment_masses_{ion_type}"] = masses

    return result


# ---------------------------------------------------------------------------
# Internal fragment math
#
# Ported verbatim from FLASHApp/src/render/sequence.py
# (`getInternalFragmentMassesWithSeq` + `getInternalFragmentDataFromSeq`) so the
# theoretical-internal-fragment enumeration runs in Python. The Vue side only
# matches these enumerated masses against the selected scan's observed masses
# (mirroring how the terminal map already works).
#
# Parity-critical details (do NOT "fix" these without re-deriving golden values):
#   * minimum internal length 5 (`if j < i + min_length - 1: continue`)
#   * start index is 0-based (i); end index is 1-based, exclusive-style (j+1)
#   * the start is barred from the first and last residue (i in [1, L-2]); the
#     end MAY reach the C-terminus (end == L includes the last residue)
#   * per-family neutral shift: by/cz -> +0, bz -> -NH3, cy -> +NH3
#   * ambiguous (partially overlapping) modifications fork into TWO candidates at
#     the same (start, end); fully-contained mods add once to the single candidate
#   * the per-candidate terminal-collision filter drops internals matching any
#     terminal b/y/c/z neutral mass within `terminal_collision_ppm` (default ON)
# ---------------------------------------------------------------------------

# Oracle constants (kept as separate literals to match the oracle arithmetic;
# H2O_INTERNAL == 18.010564683 is also written verbatim inside the mass formula).
H2O_INTERNAL = 18.010564683
NH3_INTERNAL = 17.0265491015

# Verbatim copy of `aa_masses` from FLASHApp/src/render/sequence.py. The internal
# fragment math uses THIS table (not pyOpenMS) for the residue sum, including the
# X/Z -> 0 and the high-resolution U mass.
INTERNAL_AA_MASSES: Dict[str, float] = {
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
    "X": 0,
    "Z": 0,
}

# Default internal-fragment configuration (parity defaults). Surfaced so callers
# can override per instance; `remove_terminal_collisions` defaults ON for parity.
DEFAULT_INTERNAL_FRAGMENT_CONFIG: Dict[str, Any] = {
    "min_length": 5,
    "ion_types": ["by", "bz", "cy"],
    "tolerance": 10.0,
    "tolerance_ppm": True,
    "remove_terminal_collisions": True,
    "terminal_collision_ppm": 10.0,
}


def _internal_shift(res_type: str) -> float:
    """Neutral-mass shift for an internal-ion family (oracle logic, verbatim)."""
    if res_type in ("by", "cz"):
        return -H2O_INTERNAL
    if res_type == "bz":
        return -H2O_INTERNAL - NH3_INTERNAL
    return -H2O_INTERNAL + NH3_INTERNAL  # "cy"


def _is_match_with_tolerance(
    sorted_masses: List[float], target: float, ppm: float
) -> bool:
    """Port of `isMatchWithTolerance`: binary search a sorted mass list.

    Returns True if any value in ``sorted_masses`` is within ``ppm`` of
    ``target`` (tolerance computed as ``target * ppm / 1e6``).
    """
    tol = target * ppm / 1e6
    lo, hi = 0, len(sorted_masses) - 1
    while lo <= hi:
        mid = (lo + hi) // 2
        if abs(sorted_masses[mid] - target) <= tol:
            return True
        elif sorted_masses[mid] < target:
            lo = mid + 1
        else:
            hi = mid - 1
    return False


def _terminal_collision_masses(
    fragment_masses: Dict[str, List[List[float]]],
) -> List[float]:
    """Build the sorted terminal-mass list for the collision filter.

    The oracle uses ``byp + bys + czp + czs`` (b/y prefix-suffix + c/z
    prefix-suffix neutral masses for charge 0; FLASHApp
    ``src/render/sequence.py:213-215``). Those four families correspond to the
    terminal ``b, y, c, z`` neutral masses, which Insight already computes via
    :func:`calculate_fragment_masses_pyopenms`. Flatten those per-position lists
    and sort ascending. (Using ``x`` instead of ``z`` here would diverge by ~42 Da
    — ``z`` ≈ ``y - NH3`` while ``x`` ≈ ``y + CO`` — so drop decisions could differ.)
    """
    masses: List[float] = []
    for ion in ("b", "y", "c", "z"):
        for per_pos in fragment_masses.get(f"fragment_masses_{ion}", []):
            masses.extend(per_pos)
    masses.sort()
    return masses


def compute_internal_fragment_masses(
    residues: List[str],
    res_type: str,
    *,
    min_length: int = 5,
    modifications: Optional[List[Tuple[int, int, float]]] = None,
    terminal_masses: Optional[List[float]] = None,
    terminal_collision_ppm: float = 10.0,
) -> Tuple[List[float], List[int], List[int]]:
    """Enumerate theoretical internal-fragment masses for one family.

    Pure port of ``getInternalFragmentMassesWithSeq`` (FLASHApp). Returns three
    parallel flat lists ``(masses, start_indices, end_indices)`` where each entry
    is one enumerated internal fragment. ``start`` is 0-based, ``end`` is 1-based
    (exclusive-style), matching the Vue fill predicate
    ``aaIndex > start && aaIndex <= end``.

    Args:
        residues: Plain single-letter residue list (no modification syntax).
        res_type: Internal-ion family ('by', 'cz', 'bz', or 'cy').
        min_length: Minimum internal-fragment residue length (default 5).
        modifications: Optional list of ``(start_1based, end_1based, mass)``
            ranges. Fully-contained mods add to the single candidate; partially
            overlapping mods fork into a second ``mass + m`` candidate.
        terminal_masses: Optional sorted terminal masses for the collision
            filter. When provided, candidates matching any terminal mass within
            ``terminal_collision_ppm`` are dropped.
        terminal_collision_ppm: ppm window for the terminal-collision filter.

    Returns:
        Tuple of (masses, start_indices, end_indices).
    """
    shift = _internal_shift(res_type)
    masses: List[float] = []
    starts: List[int] = []
    ends: List[int] = []
    length = len(residues)

    for i in range(length):
        # First position cannot start an internal fragment.
        if i == 0:
            continue
        # Last position cannot start one (and ends the i-loop).
        if i == length - 1:
            break

        mass = 0.0
        for j in range(length):
            # Accumulate residues from i..j inclusive.
            if j >= i:
                mass += INTERNAL_AA_MASSES[residues[j]]
            # Enforce minimum length (oracle: i + 5 - 1).
            if j < i + min_length - 1:
                continue

            candidates = [mass]
            if modifications is not None:
                for (s, e, m) in modifications:
                    # Modification fully contained in [i+1, j+1].
                    if (s >= i + 1) and (e <= j + 1):
                        candidates[0] += m
                    # Modification partially overlaps: emit BOTH variants.
                    elif (s >= i + 1) or (e <= j + 1):
                        candidates.append(mass + m)

            for mm in candidates:
                # Per-candidate terminal-collision filter.
                if (
                    terminal_masses is not None
                    and _is_match_with_tolerance(
                        terminal_masses, mm, terminal_collision_ppm
                    )
                ):
                    continue
                masses.append(mm + 18.010564683 + shift)
                starts.append(i)  # 0-based N bound
                ends.append(j + 1)  # 1-based C bound (exclusive-style)

    return masses, starts, ends


def compute_internal_fragment_data(
    residues: List[str],
    *,
    ion_types: Tuple[str, ...] = ("by", "bz", "cy"),
    min_length: int = 5,
    modifications: Optional[List[Tuple[int, int, float]]] = None,
    terminal_masses: Optional[List[float]] = None,
    remove_terminal_collisions: bool = True,
    terminal_collision_ppm: float = 10.0,
) -> Dict[str, List]:
    """Enumerate internal fragments for all requested families.

    Pure port of ``getInternalFragmentDataFromSeq`` (FLASHApp). Produces, for each
    family in ``ion_types``, three flat lists keyed
    ``fragment_masses_<fam>`` / ``start_indices_<fam>`` / ``end_indices_<fam>``.

    Note: ``by`` and ``cz`` share the same shift and the oracle only emits three
    families (``by``, ``bz``, ``cy``).
    """
    term = terminal_masses if remove_terminal_collisions else None
    out: Dict[str, List] = {}
    for it in ion_types:
        m, s, e = compute_internal_fragment_masses(
            residues,
            it,
            min_length=min_length,
            modifications=modifications,
            terminal_masses=term,
            terminal_collision_ppm=terminal_collision_ppm,
        )
        out[f"fragment_masses_{it}"] = m
        out[f"start_indices_{it}"] = s
        out[f"end_indices_{it}"] = e
    return out


def get_theoretical_mass(sequence_str: str) -> float:
    """Calculate monoisotopic mass of a peptide sequence."""
    try:
        from pyopenms import AASequence

        aa_seq = AASequence.fromString(sequence_str)
        return aa_seq.getMonoWeight()
    except ImportError:
        # Fallback
        H2O = 18.010565
        AA_MASSES = {
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
            "U": 150.953633,
            "W": 186.079313,
            "Y": 163.063329,
            "V": 99.068414,
        }
        residues, _ = parse_openms_sequence(sequence_str)
        mass = H2O
        for aa in residues:
            mass += AA_MASSES.get(aa, 0.0)
        return mass
    except Exception:
        return 0.0


# ---------------------------------------------------------------------------
# Per-residue sequence coverage
#
# Generic port of the oracle's per-residue coverage gradient (FLASHApp uses it
# for sequence-tag coverage, but coverage is a general proteomics concept). The
# oracle (`FLASHApp/src/render/sequence.py` + `src/parse/tnt.py`) supplies the
# component a per-residue list `coverage` ALREADY normalised to [0, 1]
# (`p_cov = coverage / max(coverage)`) plus the raw integer `maxCoverage`
# (used only for the scale legend label, e.g. "5x").
#
# Insight keeps that exact contract: the caller provides a per-residue coverage
# list (a `coverage_column` in the sequence frame). We normalise it the same way
# the oracle does and emit both `coverage` (per-residue, [0, 1]) and
# `maxCoverage` (raw max) into `sequenceData`. The Vue side renders the
# `rgba(228, 87, 46, alpha)` gradient per residue and a coverage scale legend.
# When no coverage is configured, neither key is emitted (back-compatible: the
# existing secondary-background cells are unchanged).
# ---------------------------------------------------------------------------

# Oracle coverage gradient base color (E4572E), kept here for documentation /
# test reference. The actual rgba() string is built in AminoAcidCell.vue.
COVERAGE_COLOR_RGB = (228, 87, 46)


def normalize_coverage(
    raw_coverage: List[float],
) -> Tuple[List[float], float]:
    """Normalise a raw per-residue coverage list the way the oracle does.

    Mirrors ``FLASHApp/src/parse/tnt.py`` (``p_cov = coverage / max(coverage)``
    when ``max(coverage) > 0`` else all-zeros, and ``maxCoverage = max(coverage)``).

    Args:
        raw_coverage: Per-residue raw coverage counts (one entry per residue).

    Returns:
        Tuple of ``(normalized_coverage, max_coverage)`` where
        ``normalized_coverage`` is in ``[0, 1]`` (per residue) and
        ``max_coverage`` is the raw maximum (0.0 when empty / all-zero).
    """
    if not raw_coverage:
        return [], 0.0
    max_cov = max(raw_coverage)
    if max_cov > 0:
        normalized = [float(c) / max_cov for c in raw_coverage]
    else:
        normalized = [0.0 for _ in raw_coverage]
    return normalized, float(max_cov)


# Default annotation configuration
DEFAULT_ANNOTATION_CONFIG = {
    "ion_types": ["b", "y"],
    "neutral_losses": True,
    "proton_loss_addition": False,
    "tolerance": 20.0,
    "tolerance_ppm": True,
    "colors": {
        "a": "#9B59B6",
        "b": "#E74C3C",
        "c": "#E67E22",
        "x": "#1ABC9C",
        "y": "#3498DB",
        "z": "#2ECC71",
    },
}


@dataclass
class SequenceViewResult:
    """Result returned by SequenceView.__call__().

    Attributes:
        annotations: DataFrame with columns (peak_id, highlight_color, annotation)
            containing fragment annotations computed by Vue. None if not yet available.
    """

    annotations: Optional[pl.DataFrame] = None


@register_component("sequence_view")
class SequenceView:
    """
    Interactive sequence view component for peptide/protein visualization.

    Displays amino acid sequence with fragment ion markers. When provided with
    peaks data, performs fragment matching on the Vue side and returns annotations.

    Features:
    - Amino acid grid display with configurable row width
    - Fragment ion markers (a, b, c, x, y, z) with configurable colors
    - Tolerance-based fragment matching (done in Vue)
    - Optional mass-info header (theoretical / observed / delta mass) when an
      ``observed_mass_column`` is supplied (oracle ``preparePrecursorInfo`` parity)
    - Optional inbound mass -> fragment-table-row highlight via
      ``mass_selection_identifier`` (oracle ``updateFragmentTableFromMassSelection``)
    - Returns annotation dataframe for linked components
    - Supports filtering by spectrum and sequence identifiers

    Example:
        sequence_view = SequenceView(
            cache_id="peptide_view",
            sequence_data=pl.scan_parquet("sequences.parquet"),
            peaks_data=pl.scan_parquet("peaks.parquet"),
            filters={"spectrum": "scan_id", "sequence": "sequence_id"},
            annotation_config={"ion_types": ["b", "y"], "tolerance": 20.0},
        )
        result = sequence_view(key="sv", state_manager=state_manager)
        # result.annotations contains the matched fragment annotations
    """

    _component_type: str = "sequence_view"

    def __init__(
        self,
        cache_id: str,
        sequence_data: Optional[Union[pl.LazyFrame, Tuple[str, int], str]] = None,
        sequence_data_path: Optional[str] = None,
        peaks_data: Optional[pl.LazyFrame] = None,
        peaks_data_path: Optional[str] = None,
        filters: Optional[Dict[str, str]] = None,
        filter_defaults: Optional[Dict[str, Any]] = None,
        interactivity: Optional[Dict[str, str]] = None,
        residue_identifier: Optional[str] = None,
        fragment_mass_identifier: Optional[str] = None,
        deconvolved: bool = False,
        annotation_config: Optional[Dict[str, Any]] = None,
        cache_path: str = ".",
        title: Optional[str] = None,
        height: int = 400,
        internal_fragments: bool = False,
        internal_fragment_config: Optional[Dict[str, Any]] = None,
        coverage_column: Optional[str] = None,
        proteoform_start_column: Optional[str] = None,
        proteoform_end_column: Optional[str] = None,
        observed_mass_column: Optional[str] = None,
        mass_header_title: str = "Proteoform",
        mass_selection_identifier: Optional[str] = None,
        **kwargs,
    ):
        """
        Initialize the SequenceView component.

        Args:
            cache_id: Unique identifier for this component instance.
            sequence_data: Sequence information in one of three formats:
                - LazyFrame with columns: sequence_id (if filtered), sequence, precursor_charge
                - Tuple of (sequence_string, precursor_charge)
                - String with just the sequence (charge defaults to 1)
            sequence_data_path: Path to parquet file with sequence data.
            peaks_data: LazyFrame with columns: scan_id (if filtered), peak_id, mass, intensity
            peaks_data_path: Path to parquet file with peaks data.
            filters: Mapping of identifier names to column names for filtering.
                Example: {"spectrum": "scan_id", "sequence": "sequence_id"}
            filter_defaults: Optional default values for filter identifiers when
                no selection is present in state. Mirrors the canonical
                ``filter_defaults`` of the other components. Any filter identifier
                not present here defaults to ``None`` (the historical behavior).
            interactivity: Mapping of identifier names to column names for clicks.
                Example: {"peak": "peak_id"} sets 'peak' selection to clicked peak's ID.
            residue_identifier: Optional selection identifier published when a
                sequence residue is clicked (0-based residue index). This is the
                oracle's TWO-PATH PATH 1 (aa / sequence-tag selection):
                - When ``coverage_column`` is configured (coverage shown), only
                  residues with sequence-tag coverage (coverage > 0) publish, the
                  selection TOGGLES (re-clicking the selected residue clears it),
                  and it auto-clears when the sequence changes (oracle parity).
                - When no coverage is configured (back-compat), a residue with a
                  matching fragment publishes its index on click (no toggle), the
                  historical Insight behavior. ``None`` (default) -> not published.
            fragment_mass_identifier: Optional selection identifier for the
                oracle's PATH 2 (mass / fragment selection). When set, clicking a
                residue that has a matching FRAGMENT ion publishes that fragment
                peak's mass-selection value to this identifier — reproducing the
                oracle ``updateMassTableFromFragmentMass`` -> ``updateSelectedMass``.
                The value is resolved via the ``interactivity`` column of the same
                name when present (e.g. ``interactivity={"mass": "mass_in_scan"}``
                with ``fragment_mass_identifier="mass"`` publishes the matched
                peak's ``mass_in_scan`` = the deconvolved-mass index), else the
                global peak id. ``None`` (default) -> PATH 2 off (back-compatible).
                PATH 1 and PATH 2 fire INDEPENDENTLY on a single residue click.
            deconvolved: If False (default), peaks are m/z values and matching considers
                charge states 1 to precursor_charge. If True, peaks are neutral masses.
            annotation_config: Configuration for fragment matching:
                - ion_types: List of ion types to consider (default: ["b", "y"])
                - neutral_losses: Whether to consider -H2O, -NH3 losses (default: True)
                - tolerance: Mass tolerance value (default: 20.0)
                - tolerance_ppm: True for ppm, False for Da (default: True)
                - colors: Dict mapping ion types to hex colors
            cache_path: Base path for cache storage.
            title: Optional title displayed above the sequence.
            height: Component height in pixels.
            internal_fragments: If True, also render an internal-fragment map
                below the terminal sequence map. The theoretical internal
                fragments are enumerated in Python (from the same ``sequence``
                string) and matched against observed masses in Vue. This is
                cache-invalidating config (like ``deconvolved``).
            internal_fragment_config: Optional overrides for internal-fragment
                enumeration/matching. Recognised keys (all optional):
                - min_length: minimum internal length (default 5)
                - ion_types: families to enumerate (default ["by", "bz", "cy"])
                - tolerance: default match tolerance (default 10.0)
                - tolerance_ppm: ppm (True) vs Da (False) default (default True)
                - remove_terminal_collisions: drop internals colliding with a
                  terminal b/y/c/z mass (default True, for parity)
                - terminal_collision_ppm: ppm window for that filter (default 10.0)
            coverage_column: Optional name of a column in the sequence frame that
                holds a per-residue coverage list (one numeric entry per residue
                of the sequence). When provided, the component normalises it the
                way the oracle does (per residue / max) and renders a per-residue
                coverage gradient + a coverage scale legend. When ``None``
                (default) no coverage is emitted and rendering is unchanged
                (backward compatible).
            proteoform_start_column: Optional name of a column holding the 0-based
                proteoform N-terminus residue index. A NEGATIVE value marks an
                UNDETERMINED N-terminus (rendered as a "??" terminal marker); a
                value > 0 marks a truncated N-terminus. ``None`` (default) ->
                full determined N-terminus (no visual change).
            proteoform_end_column: Optional name of a column holding the 0-based
                proteoform C-terminus residue index. A NEGATIVE value marks an
                UNDETERMINED C-terminus; a value < length-1 marks a truncated
                C-terminus. ``None`` (default) -> full determined C-terminus.
            observed_mass_column: Optional name of a column holding the per-row
                OBSERVED mass (e.g. the proteoform's measured/computed mass). When
                provided, the component renders the oracle's MASS-INFO HEADER above
                the sequence grid (3-seqview-004): ``massTitle`` plus three fields
                ``Theoretical mass`` (from the computed ``theoretical_mass``),
                ``Observed mass`` (this column) and ``Δ Mass (Da)``
                (``|theoretical - observed|``). This reproduces the oracle
                ``preparePrecursorInfo`` proteoform branch. A NEGATIVE / null value
                renders the observed + delta fields as "-" (oracle parity for a
                non-positive computed mass). ``None`` (default) -> no header
                (back-compatible: existing callers render byte-unchanged).
            mass_header_title: Title shown to the LEFT of the mass-info header
                fields (oracle ``massTitle``; defaults to "Proteoform"). Only used
                when ``observed_mass_column`` is configured.
            mass_selection_identifier: Optional selection identifier the component
                LISTENS to for the INBOUND mass -> fragment-table-row highlight
                (3-seqview-003, oracle ``updateFragmentTableFromMassSelection``).
                When set, an external change to this selection (the same slot
                ``fragment_mass_identifier`` publishes to, e.g. ``"mass"``) finds
                the matched peak whose interactivity value equals the selection and
                highlights the corresponding fragment-table row locally. ``None``
                (default) -> no inbound highlight (back-compatible).
            **kwargs: Additional configuration options.
        """
        self._cache_id = cache_id
        self._cache_path = Path(cache_path)
        self._cache_dir = self._cache_path / cache_id

        # Determine if data is provided (creation mode vs reconstruction mode)
        has_sequence_data = sequence_data is not None or sequence_data_path is not None

        # Check if any DATA-SHAPING configuration arguments were provided.
        # title/height are render-time (presentation) params and intentionally
        # NOT part of this guard — passing them does not require data, mirroring
        # how BaseComponent treats presentation params.
        has_config = (
            peaks_data is not None
            or peaks_data_path is not None
            or filters is not None
            or filter_defaults is not None
            or interactivity is not None
            or residue_identifier is not None
            or fragment_mass_identifier is not None
            or deconvolved is not False
            or annotation_config is not None
            or internal_fragments is not False
            or internal_fragment_config is not None
            or coverage_column is not None
            or proteoform_start_column is not None
            or proteoform_end_column is not None
            or observed_mass_column is not None
            or mass_header_title != "Proteoform"
            or mass_selection_identifier is not None
            or bool(kwargs)
        )

        if not has_sequence_data:
            # Reconstruction mode - only cache_id and cache_path allowed
            if has_config:
                raise CacheMissError(
                    "Configuration arguments require sequence_data= or sequence_data_path= to be provided. "
                    "For reconstruction from cache, use only cache_id and cache_path."
                )
            if not self._cache_exists():
                raise CacheMissError(
                    f"Cache not found at '{self._cache_dir}'. "
                    f"Provide sequence_data= or sequence_data_path= to create the cache."
                )
            self._load_from_cache()
        else:
            # Creation mode - use provided config
            self._title = title
            self._height = height
            self._deconvolved = deconvolved
            self._config = kwargs

            # Internal-fragment config (parity defaults; merge any overrides).
            self._internal_fragments = internal_fragments
            self._internal_fragment_config = {**DEFAULT_INTERNAL_FRAGMENT_CONFIG}
            if internal_fragment_config:
                self._internal_fragment_config.update(internal_fragment_config)

            # Per-residue coverage column (generic; off when None).
            self._coverage_column = coverage_column
            # Optional proteoform terminal-index columns (truncated/undetermined
            # N/C terminals; off when None).
            self._proteoform_start_column = proteoform_start_column
            self._proteoform_end_column = proteoform_end_column
            # Optional per-row observed mass -> drives the mass-info header
            # (off when None). mass_header_title is the oracle massTitle.
            self._observed_mass_column = observed_mass_column
            self._mass_header_title = mass_header_title
            # Optional inbound mass-selection identifier -> drives the inbound
            # fragment-row highlight in Vue (off when None).
            self._mass_selection_identifier = mass_selection_identifier
            self._filters = filters or {}
            # filter_defaults: caller-supplied overrides; any filter identifier
            # not listed defaults to None (historical behavior).
            provided_defaults = filter_defaults or {}
            self._filter_defaults = {}
            for identifier in self._filters.keys():
                self._filter_defaults[identifier] = provided_defaults.get(
                    identifier, None
                )
            self._interactivity = interactivity or {}
            # Identifier emitted when a sequence residue is clicked (0-based residue
            # index). Lets a downstream tagger derive the tag-relative selectedAA.
            self._residue_identifier = residue_identifier
            # PATH 2 identifier: when set, clicking a residue with a matching
            # fragment publishes that fragment peak's mass-selection value to this
            # identifier (resolved via the same-named interactivity column when
            # present, else the peak id). None -> PATH 2 off (back-compatible).
            self._fragment_mass_identifier = fragment_mass_identifier

            # Store annotation config with defaults
            self._annotation_config = {**DEFAULT_ANNOTATION_CONFIG}
            if annotation_config:
                self._annotation_config.update(annotation_config)

            # Parse sequence data input
            if sequence_data is not None and sequence_data_path is not None:
                raise ValueError(
                    "Provide either 'sequence_data' or 'sequence_data_path', not both"
                )

            self._source_sequence_data: Optional[pl.LazyFrame] = None
            self._source_static_sequence: Optional[str] = None
            self._source_static_charge: int = 1

            if sequence_data_path is not None:
                self._source_sequence_data = pl.scan_parquet(sequence_data_path)
            elif isinstance(sequence_data, pl.LazyFrame):
                self._source_sequence_data = sequence_data
            elif isinstance(sequence_data, tuple):
                self._source_static_sequence = sequence_data[0]
                self._source_static_charge = sequence_data[1]
            elif isinstance(sequence_data, str):
                self._source_static_sequence = sequence_data
                self._source_static_charge = 1

            # Parse peaks data input
            if peaks_data is not None and peaks_data_path is not None:
                raise ValueError(
                    "Provide either 'peaks_data' or 'peaks_data_path', not both"
                )

            self._source_peaks_data: Optional[pl.LazyFrame] = None
            if peaks_data_path is not None:
                self._source_peaks_data = pl.scan_parquet(peaks_data_path)
            elif peaks_data is not None:
                self._source_peaks_data = peaks_data

            # Create and save cache
            self._create_cache()

            # Discard source references - only cache is used from now on
            self._source_sequence_data = None
            self._source_static_sequence = None
            self._source_peaks_data = None

            # Load cached LazyFrames for reading
            self._cached_sequences = pl.scan_parquet(
                self._cache_dir / "sequences.parquet"
            )
            peaks_path = self._cache_dir / "peaks.parquet"
            self._cached_peaks = (
                pl.scan_parquet(peaks_path) if peaks_path.exists() else None
            )

    def _get_cache_config(self) -> Dict[str, Any]:
        """Get all configuration to store in cache.

        ``title``/``height`` are render-time presentation params but are still
        persisted here so a cache-only reconstruction restores them faithfully
        (they are simply not part of the ``has_config`` reconstruction guard).
        """
        return {
            "version": CACHE_VERSION,
            "filters": self._filters,
            "filter_defaults": self._filter_defaults,
            "interactivity": self._interactivity,
            "residue_identifier": self._residue_identifier,
            "fragment_mass_identifier": self._fragment_mass_identifier,
            "title": self._title,
            "height": self._height,
            "deconvolved": self._deconvolved,
            "annotation_config": self._annotation_config,
            "internal_fragments": self._internal_fragments,
            "internal_fragment_config": self._internal_fragment_config,
            "coverage_column": self._coverage_column,
            "proteoform_start_column": self._proteoform_start_column,
            "proteoform_end_column": self._proteoform_end_column,
            "observed_mass_column": self._observed_mass_column,
            "mass_header_title": self._mass_header_title,
            "mass_selection_identifier": self._mass_selection_identifier,
        }

    def _cache_exists(self) -> bool:
        """Check if a valid cache exists that can be loaded."""
        config_file = self._cache_dir / ".cache_config.json"
        sequences_file = self._cache_dir / "sequences.parquet"

        if not config_file.exists() or not sequences_file.exists():
            return False

        try:
            with open(config_file, "r") as f:
                cached_config = json.load(f)
            # Just check version matches
            return cached_config.get("version") == CACHE_VERSION
        except Exception:
            return False

    def _load_from_cache(self) -> None:
        """Load all configuration and data from cache."""
        config_file = self._cache_dir / ".cache_config.json"

        with open(config_file, "r") as f:
            config = json.load(f)

        # Restore all configuration
        self._filters = config.get("filters", {})
        # Restore caller-supplied filter defaults (falling back to None for any
        # filter identifier not present, preserving historical behavior and
        # back-compat with caches written before filter_defaults was stored).
        stored_defaults = config.get("filter_defaults") or {}
        self._filter_defaults = {}
        for identifier in self._filters.keys():
            self._filter_defaults[identifier] = stored_defaults.get(identifier, None)
        self._interactivity = config.get("interactivity", {})
        self._residue_identifier = config.get("residue_identifier")
        self._fragment_mass_identifier = config.get("fragment_mass_identifier")
        self._title = config.get("title")
        self._height = config.get("height", 400)
        self._deconvolved = config.get("deconvolved", False)
        self._annotation_config = config.get(
            "annotation_config", {**DEFAULT_ANNOTATION_CONFIG}
        )
        self._internal_fragments = config.get("internal_fragments", False)
        self._internal_fragment_config = {**DEFAULT_INTERNAL_FRAGMENT_CONFIG}
        self._internal_fragment_config.update(
            config.get("internal_fragment_config", {})
        )
        self._coverage_column = config.get("coverage_column")
        self._proteoform_start_column = config.get("proteoform_start_column")
        self._proteoform_end_column = config.get("proteoform_end_column")
        self._observed_mass_column = config.get("observed_mass_column")
        self._mass_header_title = config.get("mass_header_title", "Proteoform")
        self._mass_selection_identifier = config.get("mass_selection_identifier")
        self._config = {}

        # Load cached LazyFrames
        self._cached_sequences = pl.scan_parquet(self._cache_dir / "sequences.parquet")
        peaks_path = self._cache_dir / "peaks.parquet"
        self._cached_peaks = (
            pl.scan_parquet(peaks_path) if peaks_path.exists() else None
        )

    def _create_cache(self) -> None:
        """Create cache from source data."""
        # Create cache directory
        self._cache_dir.mkdir(parents=True, exist_ok=True)

        # Preprocess and write caches
        self._preprocess_sequences()
        self._preprocess_peaks()

        # Write config
        config_file = self._cache_dir / ".cache_config.json"
        with open(config_file, "w") as f:
            json.dump(self._get_cache_config(), f, indent=2)

    def _preprocess_sequences(self) -> None:
        """Preprocess and cache sequence data."""
        output_path = self._cache_dir / "sequences.parquet"

        if self._source_sequence_data is not None:
            # LazyFrame input - select required columns, sort by filters
            schema = self._source_sequence_data.collect_schema()
            filter_cols = [c for c in self._filters.values() if c in schema.names()]

            # Build column list: filter columns + required columns
            # (+ the optional per-residue coverage list column, when configured).
            required = ["sequence", "precursor_charge"]
            optional = []
            if self._coverage_column is not None:
                optional.append(self._coverage_column)
            if self._proteoform_start_column is not None:
                optional.append(self._proteoform_start_column)
            if self._proteoform_end_column is not None:
                optional.append(self._proteoform_end_column)
            if self._observed_mass_column is not None:
                optional.append(self._observed_mass_column)
            cols = list(
                dict.fromkeys(
                    filter_cols
                    + [c for c in required if c in schema.names()]
                    + [c for c in optional if c in schema.names()]
                )
            )

            lf = self._source_sequence_data.select(cols)

            # Sort by filter columns for predicate pushdown
            if filter_cols:
                lf = lf.sort(filter_cols)

            df = lf.collect()
        else:
            # Static input (string or tuple) - create single-row DataFrame
            df = pl.DataFrame(
                {
                    "sequence": [self._source_static_sequence or ""],
                    "precursor_charge": [self._source_static_charge],
                }
            )

        # Optimize types and write
        df = optimize_for_transfer(df)
        df.write_parquet(output_path, compression="zstd")

    def _preprocess_peaks(self) -> None:
        """Preprocess and cache peaks data."""
        if self._source_peaks_data is None:
            return  # No peaks to cache

        output_path = self._cache_dir / "peaks.parquet"
        schema = self._source_peaks_data.collect_schema()
        filter_cols = [c for c in self._filters.values() if c in schema.names()]

        # Build column list: filter columns + required columns
        required = ["peak_id", "mass"]
        optional = ["intensity"]
        cols = list(
            dict.fromkeys(
                filter_cols
                + [c for c in required if c in schema.names()]
                + [c for c in optional if c in schema.names()]
            )
        )

        lf = self._source_peaks_data.select(cols)

        # Sort by filter columns for predicate pushdown
        if filter_cols:
            lf = lf.sort(filter_cols)

        df = lf.collect()

        # Optimize types and write
        df = optimize_for_transfer(df)
        df.write_parquet(output_path, compression="zstd")

    def _get_sequence_for_state(self, state: Dict[str, Any]) -> Tuple[str, int]:
        """Get sequence and charge for current state.

        Reads from cached sequences.parquet with predicate pushdown.

        Returns:
            Tuple of (sequence_string, precursor_charge)
        """
        filtered = self._cached_sequences

        # Apply filters for columns that exist in cached data
        schema = filtered.collect_schema()
        for identifier, column in self._filters.items():
            if column in schema.names():
                filter_value = state.get(identifier)
                if filter_value is not None:
                    filtered = filtered.filter(pl.col(column) == filter_value)
                elif (
                    identifier in self._filter_defaults
                    and self._filter_defaults[identifier] is None
                ):
                    # Filter has None default and state is None - return empty intentionally
                    return "", 1

        # Collect and get first row
        try:
            df = filtered.select(["sequence", "precursor_charge"]).head(1).collect()
            if df.height > 0:
                return df["sequence"][0], df["precursor_charge"][0]
        except Exception:
            pass

        return "", 1

    def _get_coverage_for_state(self, state: Dict[str, Any]) -> List[float]:
        """Get the raw per-residue coverage list for the current state.

        Reads ``self._coverage_column`` from cached sequences.parquet with the
        same predicate pushdown / None-default semantics as
        :meth:`_get_sequence_for_state`. Returns an empty list when coverage is
        not configured, the column is absent, the filter is unset, or no row
        matches (so the gradient stays off and back-compat is preserved).

        Returns:
            Raw per-residue coverage values (one per residue), or ``[]``.
        """
        if self._coverage_column is None:
            return []

        filtered = self._cached_sequences
        schema = filtered.collect_schema()
        if self._coverage_column not in schema.names():
            return []

        # Apply filters (matching _get_sequence_for_state behaviour exactly).
        for identifier, column in self._filters.items():
            if column in schema.names():
                filter_value = state.get(identifier)
                if filter_value is not None:
                    filtered = filtered.filter(pl.col(column) == filter_value)
                elif (
                    identifier in self._filter_defaults
                    and self._filter_defaults[identifier] is None
                ):
                    # Filter has None default and state is None - empty intentionally
                    return []

        try:
            df = filtered.select([self._coverage_column]).head(1).collect()
            if df.height > 0:
                value = df[self._coverage_column][0]
                if value is None:
                    return []
                # Polars list cell -> Python list of floats.
                return [float(v) for v in value]
        except Exception:
            pass

        return []

    def _get_proteoform_terminals_for_state(
        self, state: Dict[str, Any]
    ) -> Tuple[Optional[int], Optional[int]]:
        """Get the proteoform (start, end) terminal indices for the state.

        Reads ``self._proteoform_start_column`` / ``_proteoform_end_column`` from
        cached sequences.parquet with the same predicate-pushdown / None-default
        semantics as :meth:`_get_sequence_for_state`. Each is ``None`` when the
        column is not configured / absent / unmatched (so the terminal markers
        stay in their default determined state, back-compatible).

        Returns:
            Tuple of ``(start_index, end_index)``, each ``Optional[int]``.
        """
        if (
            self._proteoform_start_column is None
            and self._proteoform_end_column is None
        ):
            return None, None

        filtered = self._cached_sequences
        schema = filtered.collect_schema()
        cols = [
            c
            for c in (self._proteoform_start_column, self._proteoform_end_column)
            if c is not None and c in schema.names()
        ]
        if not cols:
            return None, None

        # Apply filters (matching _get_sequence_for_state behaviour exactly).
        for identifier, column in self._filters.items():
            if column in schema.names():
                filter_value = state.get(identifier)
                if filter_value is not None:
                    filtered = filtered.filter(pl.col(column) == filter_value)
                elif (
                    identifier in self._filter_defaults
                    and self._filter_defaults[identifier] is None
                ):
                    return None, None

        start_val: Optional[int] = None
        end_val: Optional[int] = None
        try:
            df = filtered.select(cols).head(1).collect()
            if df.height > 0:
                if (
                    self._proteoform_start_column in cols
                    and df[self._proteoform_start_column][0] is not None
                ):
                    start_val = int(df[self._proteoform_start_column][0])
                if (
                    self._proteoform_end_column in cols
                    and df[self._proteoform_end_column][0] is not None
                ):
                    end_val = int(df[self._proteoform_end_column][0])
        except Exception:
            pass

        return start_val, end_val

    def _get_observed_mass_for_state(
        self, state: Dict[str, Any]
    ) -> Optional[float]:
        """Get the per-row observed mass for the current state (mass header).

        Reads ``self._observed_mass_column`` from cached sequences.parquet with the
        same predicate-pushdown / None-default semantics as
        :meth:`_get_sequence_for_state`. Returns ``None`` when the column is not
        configured / absent / unmatched (so the mass header stays off and
        back-compat is preserved).

        Returns:
            The observed mass as a float, or ``None``.
        """
        if self._observed_mass_column is None:
            return None

        filtered = self._cached_sequences
        schema = filtered.collect_schema()
        if self._observed_mass_column not in schema.names():
            return None

        # Apply filters (matching _get_sequence_for_state behaviour exactly).
        for identifier, column in self._filters.items():
            if column in schema.names():
                filter_value = state.get(identifier)
                if filter_value is not None:
                    filtered = filtered.filter(pl.col(column) == filter_value)
                elif (
                    identifier in self._filter_defaults
                    and self._filter_defaults[identifier] is None
                ):
                    return None

        try:
            df = filtered.select([self._observed_mass_column]).head(1).collect()
            if df.height > 0:
                value = df[self._observed_mass_column][0]
                if value is None:
                    return None
                return float(value)
        except Exception:
            pass

        return None

    def _get_peaks_for_state(self, state: Dict[str, Any]) -> pl.DataFrame:
        """Get filtered peaks data for current state.

        Reads from cached peaks.parquet with predicate pushdown.

        Returns:
            DataFrame with columns: peak_id, mass, (intensity if available)
        """
        if self._cached_peaks is None:
            return pl.DataFrame(schema={"peak_id": pl.Int64, "mass": pl.Float64})

        filtered = self._cached_peaks

        # Apply filters for columns that exist in cached data
        schema = filtered.collect_schema()
        for identifier, column in self._filters.items():
            if column in schema.names():
                filter_value = state.get(identifier)
                if filter_value is not None:
                    filtered = filtered.filter(pl.col(column) == filter_value)
                elif (
                    identifier in self._filter_defaults
                    and self._filter_defaults[identifier] is None
                ):
                    # Filter has None default and state is None - return empty intentionally
                    return pl.DataFrame(
                        schema={"peak_id": pl.Int64, "mass": pl.Float64}
                    )

        # Select available columns: the required peak_id/mass (+ optional intensity)
        # plus any interactivity columns present, so a fragment click can emit the
        # mapped column's value (e.g. a per-scan mass ordinal) rather than only the
        # global peak_id.
        cols = ["peak_id", "mass"]
        if "intensity" in schema.names():
            cols.append("intensity")
        for column in self._interactivity.values():
            if column in schema.names() and column not in cols:
                cols.append(column)

        try:
            return filtered.select(cols).collect()
        except Exception:
            return pl.DataFrame(schema={"peak_id": pl.Int64, "mass": pl.Float64})

    def _prepare_vue_data(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Prepare data for Vue component.

        Args:
            state: Current selection state from StateManager

        Returns:
            Dict with sequenceData, peaksData, annotationConfig, etc.
        """
        # Get sequence for current state
        sequence_str, precursor_charge = self._get_sequence_for_state(state)

        # Parse sequence
        residues, modifications = parse_openms_sequence(sequence_str)

        # Calculate theoretical fragment masses
        fragment_masses = calculate_fragment_masses_pyopenms(sequence_str)

        # Calculate theoretical mass
        theoretical_mass = get_theoretical_mass(sequence_str)

        # Build sequence data structure
        sequence_data = {
            "sequence": residues,
            "modifications": modifications,
            "theoretical_mass": theoretical_mass,
            "fixed_modifications": [],
            # Include settings for Vue initialization
            "fragment_tolerance": self._annotation_config.get("tolerance"),
            "fragment_tolerance_ppm": self._annotation_config.get("tolerance_ppm"),
            "neutral_losses": self._annotation_config.get("neutral_losses"),
            "proton_loss_addition": self._annotation_config.get("proton_loss_addition"),
            **fragment_masses,
        }

        # Internal-fragment payload (enumerated in Python; matched in Vue).
        if self._internal_fragments:
            terminal_masses = _terminal_collision_masses(fragment_masses)
            internal = compute_internal_fragment_data(
                residues,
                ion_types=tuple(self._internal_fragment_config["ion_types"]),
                min_length=self._internal_fragment_config["min_length"],
                modifications=None,  # Phase-1 plain path; wire proteoform mods later
                terminal_masses=terminal_masses,
                remove_terminal_collisions=self._internal_fragment_config[
                    "remove_terminal_collisions"
                ],
                terminal_collision_ppm=self._internal_fragment_config[
                    "terminal_collision_ppm"
                ],
            )
            # Adds the nine flat number[] arrays
            # (fragment_masses_{by,bz,cy} + start_indices_* + end_indices_*).
            sequence_data.update(internal)
            sequence_data["internal_fragments"] = True
            sequence_data["internal_fragment_tolerance"] = (
                self._internal_fragment_config["tolerance"]
            )
            sequence_data["internal_fragment_tolerance_ppm"] = (
                self._internal_fragment_config["tolerance_ppm"]
            )

        # Per-residue coverage payload (generic; gated on coverage_column).
        # Emit `coverage` (normalised per residue, like the oracle's p_cov) and
        # `maxCoverage` (raw max, for the scale legend). Absent when no coverage
        # is supplied (back-compatible: no visual change).
        if self._coverage_column is not None:
            raw_coverage = self._get_coverage_for_state(state)
            if raw_coverage:
                normalized, max_cov = normalize_coverage(raw_coverage)
                sequence_data["coverage"] = normalized
                sequence_data["maxCoverage"] = max_cov

        # Optional proteoform terminal indices (truncated / undetermined "??"
        # terminals). Emit only the values that were supplied; absent values keep
        # the Vue default (full determined terminus). Back-compatible.
        if (
            self._proteoform_start_column is not None
            or self._proteoform_end_column is not None
        ):
            start_val, end_val = self._get_proteoform_terminals_for_state(state)
            if start_val is not None:
                sequence_data["proteoform_start"] = start_val
            if end_val is not None:
                sequence_data["proteoform_end"] = end_val

        # Optional observed mass -> mass-info header (3-seqview-004). Emit
        # `observed_mass` (+ the header title) alongside the always-present
        # `theoretical_mass`; the Vue side derives the delta. Absent when no
        # observed_mass_column is configured (back-compatible: no header).
        if self._observed_mass_column is not None:
            observed_mass = self._get_observed_mass_for_state(state)
            if observed_mass is not None:
                sequence_data["observed_mass"] = observed_mass
                sequence_data["mass_header_title"] = self._mass_header_title

        # Get filtered peaks
        peaks_df = self._get_peaks_for_state(state)

        # Extract arrays from peaks DataFrame for Vue
        # Vue expects observedMasses and peakIds as separate arrays
        observed_masses: List[float] = []
        peak_ids: List[int] = []
        precursor_mass: float = 0.0
        # peak_id -> {column: value} for any configured interactivity columns, so a
        # fragment click can emit the mapped column's value (e.g. a per-scan mass
        # ordinal) instead of only the global peak_id.
        peak_interactivity: Dict[int, Dict[str, Any]] = {}

        if peaks_df.height > 0:
            observed_masses = peaks_df["mass"].to_list()
            peak_ids = peaks_df["peak_id"].to_list()
            interactivity_cols = [
                col
                for col in self._interactivity.values()
                if col in peaks_df.columns and col != "peak_id"
            ]
            if interactivity_cols:
                for record in peaks_df.select(
                    ["peak_id", *interactivity_cols]
                ).to_dicts():
                    pid = record["peak_id"]
                    peak_interactivity[pid] = {
                        col: record[col] for col in interactivity_cols
                    }

        # Create hash for change detection. Fold the internal-fragments flag and
        # the coverage flag in so flipping either re-renders (both ride
        # sequenceData).
        coverage_in_payload = int("coverage" in sequence_data)
        term_start = sequence_data.get("proteoform_start", "")
        term_end = sequence_data.get("proteoform_end", "")
        observed_mass_in_payload = sequence_data.get("observed_mass", "")
        hash_input = (
            f"{sequence_str}:{peaks_df.height}:{precursor_charge}"
            f":{int(self._internal_fragments)}"
            f":{int(self._coverage_column is not None)}:{coverage_in_payload}"
            f":{term_start}:{term_end}"
            f":{observed_mass_in_payload}"
        )
        data_hash = hashlib.md5(hash_input.encode()).hexdigest()[:8]

        result = {
            "sequenceData": sequence_data,
            "observedMasses": observed_masses,
            "peakIds": peak_ids,
            "peakInteractivity": peak_interactivity,
            "precursorMass": precursor_mass,
            "annotationConfig": self._annotation_config,
            "precursorCharge": precursor_charge,
            "_hash": data_hash,
        }

        return result

    def _get_vue_component_name(self) -> str:
        """Return the Vue component name."""
        return "SequenceView"

    def _get_data_key(self) -> str:
        """Return the key used to send primary data to Vue."""
        return "sequenceData"

    def _get_component_args(self) -> Dict[str, Any]:
        """Get component arguments to send to Vue."""
        args: Dict[str, Any] = {
            "componentType": self._get_vue_component_name(),
            "height": self._height,
            "deconvolved": self._deconvolved,
        }

        if self._title:
            args["title"] = self._title

        if self._interactivity:
            args["interactivity"] = self._interactivity

        if self._residue_identifier:
            args["residueIdentifier"] = self._residue_identifier

        # PATH 2 mass identifier — emitted only when configured (default-OFF).
        if self._fragment_mass_identifier:
            args["fragmentMassIdentifier"] = self._fragment_mass_identifier

        # Inbound mass->fragment-row highlight identifier (3-seqview-003) — emitted
        # only when configured (default-OFF), so existing callers are unaffected.
        if self._mass_selection_identifier:
            args["massSelectionIdentifier"] = self._mass_selection_identifier

        # Internal-fragment args only when on, so existing callers are unaffected.
        if self._internal_fragments:
            args["internalFragments"] = True
            args["internalFragmentConfig"] = {
                "tolerance": self._internal_fragment_config["tolerance"],
                "tolerancePpm": self._internal_fragment_config["tolerance_ppm"],
            }

        args.update(self._config)
        return args

    @property
    def peaks_data(self) -> Optional[pl.LazyFrame]:
        """Return the cached peaks LazyFrame for linked components."""
        return self._cached_peaks

    def get_filters_mapping(self) -> Dict[str, str]:
        """Return the filters identifier-to-column mapping."""
        return self._filters.copy()

    def get_interactivity_mapping(self) -> Dict[str, str]:
        """Return the interactivity identifier-to-column mapping."""
        return self._interactivity.copy()

    def get_state_dependencies(self) -> List[str]:
        """Return list of state keys that affect this component's data."""
        return list(self._filters.keys())

    def __call__(
        self,
        key: Optional[str] = None,
        state_manager: Optional["StateManager"] = None,
        height: Optional[int] = None,
    ) -> SequenceViewResult:
        """
        Render the component in Streamlit.

        Args:
            key: Optional unique key for the Streamlit component
            state_manager: Optional StateManager for cross-component state.
                If not provided, uses a default shared StateManager.
            height: Optional height in pixels for the component

        Returns:
            SequenceViewResult with annotations DataFrame (if available)
        """
        from ..core.state import get_default_state_manager
        from ..rendering.bridge import get_component_annotations, render_component

        if state_manager is None:
            state_manager = get_default_state_manager()

        # Use provided height or default
        render_height = height if height is not None else self._height

        render_component(
            component=self, state_manager=state_manager, key=key, height=render_height
        )

        # Get annotations from session state (set by Vue)
        annotations = get_component_annotations(key) if key else None

        return SequenceViewResult(annotations=annotations)

    def __repr__(self) -> str:
        return (
            f"SequenceView("
            f"cache_id='{self._cache_id}', "
            f"filters={self._filters}, "
            f"interactivity={self._interactivity})"
        )


if TYPE_CHECKING:
    from ..core.state import StateManager
