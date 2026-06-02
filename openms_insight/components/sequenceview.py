"""SequenceView component for peptide/protein sequence visualization with fragment matching."""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple, Union

import polars as pl

from ..core.registry import register_component
from ..preprocessing.filtering import optimize_for_transfer

# Proton mass for m/z calculations
PROTON_MASS = 1.007276

# Cache version - increment when cache format changes
CACHE_VERSION = 1

# Sentinel column value for residue-position interactivity. When an
# ``interactivity`` entry maps an identifier to this exact string (e.g.
# ``interactivity={"AApos": "<position>"}``), a residue click emits that
# residue's 0-based index within the displayed sequence under the identifier,
# instead of the matched peak's id. The 0-based base matches how the Vue
# numbers residues internally (``aaIndex`` in the sequence grid) and how
# FLASHApp tags carry StartPos/EndPos so that ``StartPos <= AApos <= EndPos``
# holds. Any other column value keeps the legacy peak-id emission.
POSITION_SENTINEL = "<position>"


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


def _normalize_fragment_masses(raw: Any) -> List[List[float]]:
    """Normalize a precomputed fragment-mass column value to list[list[float]].

    Accepts the legacy per-residue ``list[list[float]]`` shape (outer index =
    residue, inner list = modification-ambiguity variants) and returns it as a
    plain nested list of floats. A flat ``list[float]`` (one mass per residue)
    is wrapped so each residue carries a single-element variant list. ``None``
    entries are dropped from inner lists; missing inner values become ``[]``.
    """
    if raw is None:
        return []
    outer = list(raw)
    normalized: List[List[float]] = []
    for entry in outer:
        if entry is None:
            normalized.append([])
        elif isinstance(entry, (list, tuple)) or (
            hasattr(entry, "__iter__") and not isinstance(entry, (str, bytes))
        ):
            normalized.append([float(v) for v in entry if v is not None])
        else:
            # Flat list[float]: one mass per residue -> single-variant list.
            normalized.append([float(entry)])
    return normalized


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
    - Returns annotation dataframe for linked components
    - Supports filtering by spectrum and sequence identifiers
    - Optional residue-position interactivity: with
      ``interactivity={"AApos": "<position>"}`` a residue click emits the
      residue's 0-based index under the chosen identifier (peak-id interactivity
      for other identifiers is unaffected)

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
        interactivity: Optional[Dict[str, str]] = None,
        deconvolved: bool = False,
        annotation_config: Optional[Dict[str, Any]] = None,
        cache_path: str = ".",
        title: Optional[str] = None,
        height: int = 400,
        fixed_modifications: Optional[List[str]] = None,
        coverage_column: Optional[str] = None,
        max_coverage_column: Optional[str] = None,
        theoretical_mass_column: Optional[str] = None,
        observed_mass_column: Optional[str] = None,
        fragment_mass_columns: Optional[Dict[str, str]] = None,
        modifications_column: Optional[str] = None,
        proteoform_start_column: Optional[str] = None,
        proteoform_end_column: Optional[str] = None,
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
            interactivity: Mapping of identifier names to column names for clicks.
                Example: {"peak": "peak_id"} sets 'peak' selection to clicked peak's ID.
                As a special case, mapping an identifier to the sentinel string
                ``"<position>"`` (see ``POSITION_SENTINEL``) makes a residue click
                ALSO emit that residue's 0-based index within the displayed
                sequence under the identifier — e.g.
                ``interactivity={"AApos": "<position>"}`` emits ``AApos`` = the
                clicked residue's 0-based position. The base is 0-based to match
                the Vue residue numbering and FLASHApp's StartPos/EndPos tag
                filtering (``StartPos <= AApos <= EndPos``). Peak-id emission for
                any other (non-sentinel) identifier keeps working unchanged.
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
            fixed_modifications: List of amino acids carrying a fixed modification
                (e.g. ["C", "M"]). Rendered with the fixed-mod styling in the
                frontend, matching FLASHApp's fixed_mod_cysteine/methionine. When
                a LazyFrame sequence source carries a per-row fixed-mods list
                column, that takes precedence (see kwargs note below).
            coverage_column: Optional column in a LazyFrame sequence source holding
                a per-residue coverage array (floats), used to shade residues by
                tag/fragment coverage (FLASHTnT). Requires max_coverage_column.
            max_coverage_column: Optional column holding the scalar maximum
                coverage used to normalize ``coverage_column``.
            theoretical_mass_column: Optional column in a LazyFrame sequence
                source holding the scalar theoretical proteoform mass (float).
                When set (together with ``observed_mass_column`` for the Δ), the
                frontend renders a "Theoretical mass | Observed mass | Δ" header
                above the sequence grid (FLASHTnT parity). Carried through cache.
            observed_mass_column: Optional column holding the scalar observed
                proteoform mass (float). Also used to populate the precursor mass
                emitted to the frontend when available.
            fragment_mass_columns: Optional mapping of ion type
                ("a"/"b"/"c"/"x"/"y"/"z") to a column in a LazyFrame sequence
                source holding PRECOMPUTED per-residue theoretical fragment
                masses. Each column value is the legacy ``list[list[float]]``
                shape (outer index = residue, inner list = modification-ambiguity
                variants, usually length 1); a flat ``list[float]`` is also
                accepted and wrapped per residue. When provided, these masses
                override the pyOpenMS-from-sequence recomputation for both the
                b/y annotation flags and the "Matching Fragments" table. Carried
                through cache. When None, the recompute path is used unchanged.
            modifications_column: Optional column holding a PER-RESIDUE
                modification-mass array (one entry per residue of the full
                sequence; mass float or null). When set it overrides the
                modifications parsed from the sequence string -- used by FLASHTnT,
                which supplies a bare residue sequence plus a separate mod array.
            proteoform_start_column: Optional column holding the 0-based start
                residue of the identified proteoform window (inclusive). Residues
                outside ``[start, end]`` render greyed ("truncated") and the
                precomputed fragment positions are offset by ``start`` so they
                land on the right residues of the full sequence (FLASHTnT).
            proteoform_end_column: Optional column holding the 0-based end residue
                of the proteoform window (inclusive). See proteoform_start_column.
            **kwargs: Additional configuration options.
        """
        self._cache_id = cache_id
        self._cache_path = Path(cache_path)
        self._cache_dir = self._cache_path / cache_id

        # Determine if data is provided (creation mode vs reconstruction mode)
        has_sequence_data = sequence_data is not None or sequence_data_path is not None

        # Check if any configuration arguments were provided
        has_config = (
            peaks_data is not None
            or peaks_data_path is not None
            or filters is not None
            or interactivity is not None
            or deconvolved is not False
            or annotation_config is not None
            or title is not None
            or height != 400
            or fixed_modifications is not None
            or coverage_column is not None
            or max_coverage_column is not None
            or theoretical_mass_column is not None
            or observed_mass_column is not None
            or fragment_mass_columns is not None
            or modifications_column is not None
            or proteoform_start_column is not None
            or proteoform_end_column is not None
            or bool(kwargs)
        )

        if not has_sequence_data:
            # Reconstruction mode - only cache_id and cache_path allowed
            if has_config:
                raise ValueError(
                    "Configuration arguments require sequence_data= or sequence_data_path= to be provided. "
                    "For reconstruction from cache, use only cache_id and cache_path."
                )
            if not self._cache_exists():
                raise ValueError(
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
            self._fixed_modifications = fixed_modifications or []
            self._coverage_column = coverage_column
            self._max_coverage_column = max_coverage_column
            self._theoretical_mass_column = theoretical_mass_column
            self._observed_mass_column = observed_mass_column
            self._fragment_mass_columns = dict(fragment_mass_columns or {})
            self._modifications_column = modifications_column
            self._proteoform_start_column = proteoform_start_column
            self._proteoform_end_column = proteoform_end_column
            self._filters = filters or {}
            self._filter_defaults = {}
            for identifier in self._filters.keys():
                self._filter_defaults[identifier] = None
            self._interactivity = interactivity or {}

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
        """Get all configuration to store in cache."""
        return {
            "version": CACHE_VERSION,
            "filters": self._filters,
            "interactivity": self._interactivity,
            "title": self._title,
            "height": self._height,
            "deconvolved": self._deconvolved,
            "annotation_config": self._annotation_config,
            "fixed_modifications": self._fixed_modifications,
            "coverage_column": self._coverage_column,
            "max_coverage_column": self._max_coverage_column,
            "theoretical_mass_column": self._theoretical_mass_column,
            "observed_mass_column": self._observed_mass_column,
            "fragment_mass_columns": self._fragment_mass_columns,
            "modifications_column": self._modifications_column,
            "proteoform_start_column": self._proteoform_start_column,
            "proteoform_end_column": self._proteoform_end_column,
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
        self._filter_defaults = {}
        for identifier in self._filters.keys():
            self._filter_defaults[identifier] = None
        self._interactivity = config.get("interactivity", {})
        self._title = config.get("title")
        self._height = config.get("height", 400)
        self._deconvolved = config.get("deconvolved", False)
        self._annotation_config = config.get(
            "annotation_config", {**DEFAULT_ANNOTATION_CONFIG}
        )
        self._fixed_modifications = config.get("fixed_modifications", [])
        self._coverage_column = config.get("coverage_column")
        self._max_coverage_column = config.get("max_coverage_column")
        self._theoretical_mass_column = config.get("theoretical_mass_column")
        self._observed_mass_column = config.get("observed_mass_column")
        self._fragment_mass_columns = config.get("fragment_mass_columns") or {}
        self._modifications_column = config.get("modifications_column")
        self._proteoform_start_column = config.get("proteoform_start_column")
        self._proteoform_end_column = config.get("proteoform_end_column")
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

            # Build column list: filter columns + required columns + optional
            # columns kept verbatim so per-residue shading, the mass header and
            # precomputed fragment masses survive into the cache.
            required = ["sequence", "precursor_charge"]
            optional = [
                c
                for c in (
                    self._coverage_column,
                    self._max_coverage_column,
                    self._theoretical_mass_column,
                    self._observed_mass_column,
                    self._modifications_column,
                    self._proteoform_start_column,
                    self._proteoform_end_column,
                    *self._fragment_mass_columns.values(),
                )
                if c is not None
            ]
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

    def _get_coverage_for_state(
        self, state: Dict[str, Any]
    ) -> Tuple[Optional[List[float]], Optional[float]]:
        """Get the per-residue coverage array and its max for the current state.

        Returns (coverage_list, max_coverage) when both coverage columns are
        configured and present in the cached sequences; otherwise (None, None).
        Applies the same None-default filter semantics as the sequence getter.
        """
        if self._coverage_column is None or self._cached_sequences is None:
            return None, None

        filtered = self._cached_sequences
        schema = filtered.collect_schema().names()
        if self._coverage_column not in schema:
            return None, None

        for identifier, column in self._filters.items():
            if column in schema:
                filter_value = state.get(identifier)
                if filter_value is not None:
                    filtered = filtered.filter(pl.col(column) == filter_value)
                elif (
                    identifier in self._filter_defaults
                    and self._filter_defaults[identifier] is None
                ):
                    return None, None

        cols = [self._coverage_column]
        if self._max_coverage_column and self._max_coverage_column in schema:
            cols.append(self._max_coverage_column)
        try:
            df = filtered.select(cols).head(1).collect()
            if df.height == 0:
                return None, None
            coverage = df[self._coverage_column][0]
            coverage = list(coverage) if coverage is not None else None
            max_cov = None
            if self._max_coverage_column and self._max_coverage_column in df.columns:
                max_cov = df[self._max_coverage_column][0]
            elif coverage:
                max_cov = max(coverage)
            return coverage, max_cov
        except Exception:
            return None, None

    def _select_row_for_state(
        self, state: Dict[str, Any], cols: List[str]
    ) -> Optional[pl.DataFrame]:
        """Fetch the first cached-sequence row for ``state`` limited to ``cols``.

        Applies the same None-default filter semantics as the sequence getter.
        Returns a 1-row DataFrame, or None when no row matches / a required
        column is missing / a None-default filter blocks the selection.
        """
        if self._cached_sequences is None:
            return None
        schema = self._cached_sequences.collect_schema().names()
        if any(c not in schema for c in cols):
            return None

        filtered = self._cached_sequences
        for identifier, column in self._filters.items():
            if column in schema:
                filter_value = state.get(identifier)
                if filter_value is not None:
                    filtered = filtered.filter(pl.col(column) == filter_value)
                elif (
                    identifier in self._filter_defaults
                    and self._filter_defaults[identifier] is None
                ):
                    return None
        try:
            df = filtered.select(cols).head(1).collect()
        except Exception:
            return None
        return df if df.height > 0 else None

    def _get_header_masses_for_state(
        self, state: Dict[str, Any]
    ) -> Tuple[Optional[float], Optional[float]]:
        """Return (theoretical_mass, observed_mass) for the mass header.

        Each is None when its column is not configured/present or no row matches.
        """
        theo: Optional[float] = None
        obs: Optional[float] = None
        if self._theoretical_mass_column is not None:
            df = self._select_row_for_state(state, [self._theoretical_mass_column])
            if df is not None:
                val = df[self._theoretical_mass_column][0]
                theo = float(val) if val is not None else None
        if self._observed_mass_column is not None:
            df = self._select_row_for_state(state, [self._observed_mass_column])
            if df is not None:
                val = df[self._observed_mass_column][0]
                obs = float(val) if val is not None else None
        return theo, obs

    def _get_precomputed_fragments_for_state(
        self, state: Dict[str, Any]
    ) -> Optional[Dict[str, List[List[float]]]]:
        """Return precomputed per-residue fragment masses keyed by ion type.

        Reads each configured ``fragment_mass_columns`` column for the selected
        row and normalizes its value to ``list[list[float]]`` (wrapping a flat
        ``list[float]`` as one variant per residue). Returns None when no
        columns are configured or no row matches; skips ion types whose value
        is missing/null.
        """
        if not self._fragment_mass_columns:
            return None
        cols = list(dict.fromkeys(self._fragment_mass_columns.values()))
        df = self._select_row_for_state(state, cols)
        if df is None:
            return None

        result: Dict[str, List[List[float]]] = {}
        for ion_type, column in self._fragment_mass_columns.items():
            if column not in df.columns:
                continue
            raw = df[column][0]
            if raw is None:
                continue
            result[ion_type] = _normalize_fragment_masses(raw)
        return result or None

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

        # Select available columns
        cols = ["peak_id", "mass"]
        if "intensity" in schema.names():
            cols.append("intensity")

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

        # Per-residue coverage (FLASHTnT): shade residues by tag/fragment coverage
        coverage, max_coverage = self._get_coverage_for_state(state)

        # Precomputed theoretical/observed proteoform masses for the header.
        header_theoretical, header_observed = self._get_header_masses_for_state(state)

        # Precomputed per-residue fragment masses (override pyOpenMS recompute).
        precomputed_fragments = self._get_precomputed_fragments_for_state(state)

        # Per-residue modifications override (FLASHTnT supplies a bare sequence plus
        # a separate per-residue modification-mass array) and the proteoform
        # truncation window [start, end] (residues outside it are greyed and the
        # precomputed fragment positions are offset by start).
        mods_override = None
        if self._modifications_column is not None:
            df = self._select_row_for_state(state, [self._modifications_column])
            if df is not None and df[self._modifications_column][0] is not None:
                mods_override = [
                    float(m) if m is not None else None
                    for m in df[self._modifications_column][0]
                ]
        proteoform_start = None
        proteoform_end = None
        if self._proteoform_start_column is not None:
            df = self._select_row_for_state(state, [self._proteoform_start_column])
            if df is not None and df[self._proteoform_start_column][0] is not None:
                proteoform_start = int(df[self._proteoform_start_column][0])
        if self._proteoform_end_column is not None:
            df = self._select_row_for_state(state, [self._proteoform_end_column])
            if df is not None and df[self._proteoform_end_column][0] is not None:
                proteoform_end = int(df[self._proteoform_end_column][0])

        # Build sequence data structure
        sequence_data = {
            "sequence": residues,
            "modifications": modifications,
            "theoretical_mass": theoretical_mass,
            "fixed_modifications": list(self._fixed_modifications),
            # Include settings for Vue initialization
            "fragment_tolerance": self._annotation_config.get("tolerance"),
            "fragment_tolerance_ppm": self._annotation_config.get("tolerance_ppm"),
            "neutral_losses": self._annotation_config.get("neutral_losses"),
            "proton_loss_addition": self._annotation_config.get("proton_loss_addition"),
            "ion_types": self._annotation_config.get("ion_types"),
            **fragment_masses,
        }
        if coverage is not None:
            sequence_data["coverage"] = coverage
            sequence_data["maxCoverage"] = max_coverage
        # Mass header (FLASHTnT parity): only present when configured + available.
        if header_theoretical is not None:
            sequence_data["theoretical_mass"] = header_theoretical
        if header_observed is not None:
            sequence_data["observed_mass"] = header_observed
        # Precomputed fragment masses: the Vue side matches THESE against the
        # observed peaks instead of recomputing from the bare sequence.
        if precomputed_fragments is not None:
            sequence_data["precomputed_fragment_masses"] = precomputed_fragments
        # Per-residue modification masses (overrides the parsed-from-string array).
        if mods_override is not None:
            sequence_data["modifications"] = mods_override
        # Proteoform truncation window (0-based, inclusive). Drives residue greying
        # and the fragment-position offset on the Vue side.
        if proteoform_start is not None:
            sequence_data["proteoform_start"] = proteoform_start
        if proteoform_end is not None:
            sequence_data["proteoform_end"] = proteoform_end

        # Get filtered peaks
        peaks_df = self._get_peaks_for_state(state)

        # Extract arrays from peaks DataFrame for Vue
        # Vue expects observedMasses and peakIds as separate arrays
        observed_masses: List[float] = []
        peak_ids: List[int] = []
        # Use the configured observed proteoform mass as the precursor mass when
        # available; otherwise keep the legacy 0.0 default.
        precursor_mass: float = header_observed if header_observed is not None else 0.0

        if peaks_df.height > 0:
            observed_masses = peaks_df["mass"].to_list()
            peak_ids = peaks_df["peak_id"].to_list()

        # Create hash for change detection (include coverage, header masses and a
        # precomputed-fragments signature so the bridge re-sends when only those
        # change).
        cov_sig = ""
        if coverage is not None:
            cov_sig = f"{len(coverage)}:{max_coverage}"
        frag_sig = ""
        if precomputed_fragments is not None:
            frag_sig = ":".join(
                f"{ion}={len(vals)}"
                for ion, vals in sorted(precomputed_fragments.items())
            )
        mods_sig = ""
        if mods_override is not None:
            mods_sig = ":".join(
                "" if m is None else f"{i}={m}"
                for i, m in enumerate(mods_override)
                if m is not None
            )
        hash_input = (
            f"{sequence_str}:{peaks_df.height}:{precursor_charge}:{cov_sig}"
            f":{header_theoretical}:{header_observed}:{frag_sig}"
            f":{proteoform_start}:{proteoform_end}:{mods_sig}"
        )
        data_hash = hashlib.md5(hash_input.encode()).hexdigest()[:8]

        result = {
            "sequenceData": sequence_data,
            "observedMasses": observed_masses,
            "peakIds": peak_ids,
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
