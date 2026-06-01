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
# v2: added optional coverage / maxCoverage / fixed_modifications round-trip + settings.
CACHE_VERSION = 2

# Optional per-sequence columns carried through the cache when present in the
# source data (TnT proteoform coverage path). All are backward-compatible: when
# absent the Vue side falls back to no coverage shading and empty fixed mods.
OPTIONAL_SEQUENCE_COLUMNS = ["coverage", "maxCoverage", "fixed_modifications"]

# Amino acids that carry FLASHDeconv fixed modifications (Carbamidomethyl on C,
# oxidation on M). Mirrors src/render/sequence.py::setFixedModification, which
# returns a subset of ['C', 'M'].
FIXED_MOD_RESIDUES = ["C", "M"]


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


def compute_fixed_modifications(
    residues: List[str],
    fixed_mod_residues: Optional[List[str]] = None,
) -> List[str]:
    """Determine which residue types carry FLASHDeconv fixed modifications.

    Parity with FLASHApp ``src/render/sequence.py::setFixedModification``, which
    applies Carbamidomethyl (etc.) on every ``C`` and oxidation (etc.) on every
    ``M`` and returns the subset of ``['C', 'M']`` that actually occur.

    Args:
        residues: list of single-letter amino-acid codes for the sequence.
        fixed_mod_residues: residue types eligible for a fixed mod. Defaults to
            ``['C', 'M']``.

    Returns:
        Ordered list (``['C']``, ``['M']``, both, or empty) of residue types that
        appear in the sequence and are eligible for a fixed modification.
    """
    eligible = (
        fixed_mod_residues if fixed_mod_residues is not None else FIXED_MOD_RESIDUES
    )
    present = set(residues)
    return [aa for aa in eligible if aa in present]


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
        settings: Optional[Dict[str, Any]] = None,
        compute_fixed_mods: bool = False,
        cache_path: str = ".",
        title: Optional[str] = None,
        height: int = 400,
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
            deconvolved: If False (default), peaks are m/z values and matching considers
                charge states 1 to precursor_charge. If True, peaks are neutral masses.
            annotation_config: Configuration for fragment matching:
                - ion_types: List of ion types to consider (default: ["b", "y"])
                - neutral_losses: Whether to consider -H2O, -NH3 losses (default: True)
                - tolerance: Mass tolerance value (default: 20.0)
                - tolerance_ppm: True for ppm, False for Da (default: True)
                - colors: Dict mapping ion types to hex colors
            settings: Optional FLASHApp-style settings dict ``{'tolerance': float,
                'ion_types': list[str]}`` (TnT path). When provided, ``tolerance``
                overrides the annotation tolerance (interpreted as ppm) and
                ``ion_types`` drives the default selected fragment ion types in Vue.
                Optional and backward-compatible.
            compute_fixed_mods: If True, compute FLASHDeconv C/M fixed modifications
                from the sequence (Deconv path parity with ``setFixedModification``)
                when the source data does not already carry ``fixed_modifications``.
                Default False (no regression).
            cache_path: Base path for cache storage.
            title: Optional title displayed above the sequence.
            height: Component height in pixels.
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
            or settings is not None
            or compute_fixed_mods is not False
            or title is not None
            or height != 400
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
            self._filters = filters or {}
            self._filter_defaults = {}
            for identifier in self._filters.keys():
                self._filter_defaults[identifier] = None
            self._interactivity = interactivity or {}

            self._compute_fixed_mods = compute_fixed_mods

            # Store annotation config with defaults
            self._annotation_config = {**DEFAULT_ANNOTATION_CONFIG}
            if annotation_config:
                self._annotation_config.update(annotation_config)

            # FLASHApp-style settings (TnT). When present, tolerance/ion_types
            # take precedence over the annotation_config defaults so the Vue
            # component initializes to the deconvolution tolerance / ion types.
            self._settings: Dict[str, Any] = dict(settings) if settings else {}
            if self._settings.get("tolerance") is not None:
                # FLASHApp settings.tolerance is a ppm deconvolution tolerance.
                self._annotation_config["tolerance"] = self._settings["tolerance"]
                self._annotation_config["tolerance_ppm"] = True
            if self._settings.get("ion_types"):
                self._annotation_config["ion_types"] = list(self._settings["ion_types"])

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
            "settings": self._settings,
            "compute_fixed_mods": self._compute_fixed_mods,
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
        self._settings = config.get("settings", {})
        self._compute_fixed_mods = config.get("compute_fixed_mods", False)
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
            # per-sequence columns (coverage / maxCoverage / fixed_modifications)
            # when the source carries them. All optional columns are
            # backward-compatible: absent ones are simply not selected.
            required = ["sequence", "precursor_charge"]
            optional = [c for c in OPTIONAL_SEQUENCE_COLUMNS if c in schema.names()]
            cols = list(
                dict.fromkeys(
                    filter_cols
                    + [c for c in required if c in schema.names()]
                    + optional
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
        entry = self._get_sequence_entry_for_state(state)
        return entry["sequence"], entry["precursor_charge"]

    def _get_sequence_entry_for_state(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Get the full sequence entry (sequence, charge + optional coverage,
        maxCoverage, fixed_modifications) for the current state.

        Reads from cached sequences.parquet with predicate pushdown (e.g.
        ``filters={'proteinIndex': 'proteoform_index'}`` for TnT). The optional
        coverage columns are returned only when they exist in the cache.

        Returns:
            Dict with keys ``sequence`` (str), ``precursor_charge`` (int), and,
            when available, ``coverage`` (list[float]), ``maxCoverage`` (float),
            ``fixed_modifications`` (list[str]). Empty sequence ("") signals the
            empty/no-selection state.
        """
        empty: Dict[str, Any] = {"sequence": "", "precursor_charge": 1}

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
                    # Filter has None default and state is None - empty intentionally
                    return empty

        available = set(schema.names())
        select_cols = ["sequence", "precursor_charge"] + [
            c for c in OPTIONAL_SEQUENCE_COLUMNS if c in available
        ]

        try:
            df = filtered.select(select_cols).head(1).collect()
            if df.height > 0:
                entry: Dict[str, Any] = {
                    "sequence": df["sequence"][0],
                    "precursor_charge": df["precursor_charge"][0],
                }
                for col in OPTIONAL_SEQUENCE_COLUMNS:
                    if col in df.columns:
                        value = df[col][0]
                        if value is not None:
                            entry[col] = value
                return entry
        except Exception:
            pass

        return empty

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
        # Get sequence entry for current state (incl. optional coverage cols)
        entry = self._get_sequence_entry_for_state(state)
        sequence_str = entry["sequence"]
        precursor_charge = entry["precursor_charge"]

        # Parse sequence
        residues, modifications = parse_openms_sequence(sequence_str)

        # Calculate theoretical fragment masses
        fragment_masses = calculate_fragment_masses_pyopenms(sequence_str)

        # Calculate theoretical mass
        theoretical_mass = get_theoretical_mass(sequence_str)

        # Resolve fixed modifications: prefer source-provided value, otherwise
        # compute C/M for the Deconv path when requested (parity with
        # setFixedModification). Absent + not requested -> [] (no regression).
        if "fixed_modifications" in entry and entry["fixed_modifications"] is not None:
            fixed_modifications = list(entry["fixed_modifications"])
        elif self._compute_fixed_mods and residues:
            fixed_modifications = compute_fixed_modifications(residues)
        else:
            fixed_modifications = []

        # Build sequence data structure
        sequence_data: Dict[str, Any] = {
            "sequence": residues,
            "modifications": modifications,
            "theoretical_mass": theoretical_mass,
            "fixed_modifications": fixed_modifications,
            # Include settings for Vue initialization
            "fragment_tolerance": self._annotation_config.get("tolerance"),
            "fragment_tolerance_ppm": self._annotation_config.get("tolerance_ppm"),
            "neutral_losses": self._annotation_config.get("neutral_losses"),
            "proton_loss_addition": self._annotation_config.get("proton_loss_addition"),
            **fragment_masses,
        }

        # Per-residue coverage coloring (EXTEND). Only attached when provided so
        # the Vue side falls back to no shading otherwise.
        if "coverage" in entry and entry["coverage"] is not None:
            sequence_data["coverage"] = list(entry["coverage"])
        if "maxCoverage" in entry and entry["maxCoverage"] is not None:
            sequence_data["maxCoverage"] = entry["maxCoverage"]

        # Get filtered peaks
        peaks_df = self._get_peaks_for_state(state)

        # Extract arrays from peaks DataFrame for Vue
        # Vue expects observedMasses and peakIds as separate arrays
        observed_masses: List[float] = []
        peak_ids: List[int] = []
        precursor_mass: float = 0.0

        if peaks_df.height > 0:
            observed_masses = peaks_df["mass"].to_list()
            peak_ids = peaks_df["peak_id"].to_list()

        # Create hash for change detection. Include coverage/maxCoverage and
        # fixed mods so a change in those re-renders the Vue side even when the
        # raw sequence string is unchanged across proteoform selections.
        cov_sig = sequence_data.get("maxCoverage", "")
        fixed_sig = ",".join(fixed_modifications)
        hash_input = (
            f"{sequence_str}:{peaks_df.height}:{precursor_charge}:{cov_sig}:{fixed_sig}"
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

        # FLASHApp-style settings (tolerance / ion_types) for Vue initialization.
        # Only sent when configured to keep payload minimal and backward-compatible.
        if self._settings:
            result["settings"] = self._settings

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
