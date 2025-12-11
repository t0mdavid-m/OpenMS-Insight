"""SequenceView component for peptide/protein sequence visualization with fragment matching."""

from typing import Any, Dict, List, Optional

import polars as pl

from ..core.base import BaseComponent
from ..core.registry import register_component


# Amino acid monoisotopic masses
AA_MASSES = {
    'A': 71.037114, 'R': 156.101111, 'N': 114.042927, 'D': 115.026943,
    'C': 103.009185, 'E': 129.042593, 'Q': 128.058578, 'G': 57.021464,
    'H': 137.058912, 'I': 113.084064, 'L': 113.084064, 'K': 128.094963,
    'M': 131.040485, 'F': 147.068414, 'P': 97.052764, 'S': 87.032028,
    'T': 101.047679, 'U': 150.953633, 'W': 186.079313, 'Y': 163.063329,
    'V': 99.068414, 'X': 0, 'Z': 0,
}

# Ion type mass adjustments
# These are approximate - for precise values, use pyOpenMS
H2O = 18.010565
NH3 = 17.026549
PROTON = 1.007276

# Ion type offsets (from N-terminus for prefix, C-terminus for suffix)
ION_OFFSETS = {
    'a': -27.994915,  # CO loss from b
    'b': 0.0,
    'c': 17.026549,   # NH3 addition to b
    'x': 43.989829,   # CO + CO addition to y
    'y': 18.010565,   # H2O addition (protonated)
    'z': 1.991841,    # NH loss from y
}


def calculate_prefix_mass(sequence: str, position: int) -> float:
    """Calculate mass of N-terminal fragment (positions 0 to position inclusive)."""
    mass = 0.0
    for i in range(position + 1):
        mass += AA_MASSES.get(sequence[i], 0.0)
    return mass


def calculate_suffix_mass(sequence: str, position: int) -> float:
    """Calculate mass of C-terminal fragment (positions position to end)."""
    mass = 0.0
    for i in range(position, len(sequence)):
        mass += AA_MASSES.get(sequence[i], 0.0)
    return mass


def calculate_fragment_masses(sequence: str) -> Dict[str, List[List[float]]]:
    """
    Calculate theoretical fragment masses for all ion types.

    Args:
        sequence: Amino acid sequence string

    Returns:
        Dict with keys fragment_masses_a, fragment_masses_b, etc.
        Each value is a list of lists (to support ambiguous modifications)
    """
    n = len(sequence)
    result = {}

    # Prefix ions (a, b, c) - from N-terminus
    for ion_type in ['a', 'b', 'c']:
        masses = []
        for i in range(n):
            prefix_mass = calculate_prefix_mass(sequence, i)
            ion_mass = prefix_mass + ION_OFFSETS[ion_type]
            masses.append([ion_mass])
        result[f'fragment_masses_{ion_type}'] = masses

    # Suffix ions (x, y, z) - from C-terminus
    for ion_type in ['x', 'y', 'z']:
        masses = []
        for i in range(n):
            # For suffix ions, position i means i+1 residues from C-terminus
            suffix_mass = calculate_suffix_mass(sequence, n - i - 1)
            ion_mass = suffix_mass + ION_OFFSETS[ion_type]
            masses.append([ion_mass])
        result[f'fragment_masses_{ion_type}'] = masses

    return result


def calculate_theoretical_mass(sequence: str) -> float:
    """Calculate monoisotopic mass of full sequence."""
    mass = H2O  # Add water for full peptide
    for aa in sequence:
        mass += AA_MASSES.get(aa, 0.0)
    return mass


@register_component("sequence_view")
class SequenceView(BaseComponent):
    """
    Interactive sequence view component for peptide/protein visualization.

    Displays amino acid sequence with fragment ion markers. When provided with
    observed masses from a spectrum, highlights matched theoretical fragments.

    Features:
    - Amino acid grid display with configurable row width
    - Fragment ion markers (a, b, c, x, y, z)
    - Tolerance-based fragment matching
    - Fragment table showing matches
    - Residue cleavage percentage calculation

    Example:
        sequence_view = SequenceView(
            cache_id="peptide_view",
            sequence="PEPTIDEK",
            observed_masses=[147.1, 244.2, 359.3, ...],
            precursor_mass=944.5,
        )
        sequence_view(state_manager=state_manager)
    """

    _component_type: str = "sequence_view"

    def __init__(
        self,
        cache_id: str,
        sequence: str,
        observed_masses: Optional[List[float]] = None,
        precursor_mass: Optional[float] = None,
        data: Optional[pl.LazyFrame] = None,  # Not used but required by base
        filters: Optional[Dict[str, str]] = None,
        interactivity: Optional[Dict[str, str]] = None,
        cache_path: str = ".",
        regenerate_cache: bool = False,
        fixed_modifications: Optional[List[str]] = None,
        title: Optional[str] = None,
        height: int = 400,
        deconvolved: bool = True,
        precursor_charge: int = 1,
        _precomputed_sequence_data: Optional[Dict[str, Any]] = None,
        **kwargs
    ):
        """
        Initialize the SequenceView component.

        Args:
            cache_id: Unique identifier for this component's cache.
            sequence: Amino acid sequence string (single-letter codes).
            observed_masses: List of observed peak masses from spectrum.
            precursor_mass: Observed precursor mass.
            data: Not used for SequenceView, but required by base class.
            filters: Mapping of identifier names to column names for filtering.
            interactivity: Mapping of identifier names to column names for clicks.
            cache_path: Base path for cache storage.
            regenerate_cache: If True, regenerate cache even if valid.
            fixed_modifications: List of amino acids with fixed modifications (e.g., ['C']).
            title: Optional title displayed above the sequence.
            height: Component height in pixels.
            deconvolved: If True (default), observed_masses are neutral masses.
                If False, observed_masses are m/z values and fragment matching
                considers charge states 1 to precursor_charge.
            precursor_charge: Maximum charge state to consider for fragment matching
                when deconvolved=False. Fragments can have charge 1 to this value.
            _precomputed_sequence_data: Optional pre-computed sequence data dict.
                If provided, skips fragment mass calculation (used when fragment
                masses are already cached externally, e.g., in identification preprocessing).
            **kwargs: Additional configuration options.
        """
        self._sequence = sequence.upper().replace(' ', '').replace('\n', '')
        self._observed_masses = observed_masses or []
        self._precursor_mass = precursor_mass or 0.0
        self._fixed_modifications = fixed_modifications or []
        self._title = title
        self._height = height
        self._deconvolved = deconvolved
        self._precursor_charge = max(1, precursor_charge)
        self._precomputed_sequence_data = _precomputed_sequence_data

        # Create dummy data if none provided (base class requires it)
        if data is None:
            data = pl.LazyFrame({'_dummy': [1]})

        super().__init__(
            cache_id=cache_id,
            data=data,
            filters=filters,
            interactivity=interactivity,
            cache_path=cache_path,
            regenerate_cache=regenerate_cache,
            **kwargs
        )

    def _get_cache_config(self) -> Dict[str, Any]:
        """Get configuration that affects cache validity."""
        return {
            'sequence': self._sequence,
            'fixed_modifications': self._fixed_modifications,
        }

    def _preprocess(self) -> None:
        """
        Preprocess sequence data.

        Calculates theoretical fragment masses for all ion types.
        This is cached so subsequent renders are fast.
        """
        # Calculate fragment masses
        fragment_masses = calculate_fragment_masses(self._sequence)

        # Calculate theoretical mass
        theoretical_mass = calculate_theoretical_mass(self._sequence)

        # Build sequence data structure
        sequence_data = {
            'sequence': list(self._sequence),
            'theoretical_mass': theoretical_mass,
            'fixed_modifications': self._fixed_modifications,
            **fragment_masses,
        }

        self._preprocessed_data['sequence_data'] = sequence_data

    def _get_vue_component_name(self) -> str:
        """Return the Vue component name."""
        return 'SequenceView'

    def _get_data_key(self) -> str:
        """Return the key used to send primary data to Vue."""
        return 'sequenceData'

    def _prepare_vue_data(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Prepare sequence data for Vue component.

        Args:
            state: Current selection state from StateManager

        Returns:
            Dict with sequenceData, observedMasses, precursorMass, and _hash
        """
        # Use precomputed data if available, otherwise use cached/computed data
        if self._precomputed_sequence_data is not None:
            sequence_data = self._precomputed_sequence_data
        else:
            sequence_data = self._preprocessed_data.get('sequence_data', {})

        # Create a hash based on sequence and observed masses
        import hashlib
        hash_input = f"{self._sequence}:{len(self._observed_masses)}:{self._precursor_mass}"
        data_hash = hashlib.md5(hash_input.encode()).hexdigest()[:8]

        return {
            'sequenceData': sequence_data,
            'observedMasses': self._observed_masses,
            'precursorMass': self._precursor_mass,
            '_hash': data_hash,
        }

    def _get_component_args(self) -> Dict[str, Any]:
        """Get component arguments to send to Vue."""
        args: Dict[str, Any] = {
            'componentType': self._get_vue_component_name(),
            'height': self._height,
            'deconvolved': self._deconvolved,
            'precursorCharge': self._precursor_charge,
        }

        if self._title:
            args['title'] = self._title

        args.update(self._config)
        return args

    def update_observed_masses(
        self,
        observed_masses: List[float],
        precursor_mass: Optional[float] = None
    ) -> 'SequenceView':
        """
        Update the observed masses for fragment matching.

        This allows reusing the same cached sequence data with different
        spectra for matching.

        Args:
            observed_masses: New list of observed peak masses.
            precursor_mass: Optional new precursor mass.

        Returns:
            Self for method chaining.
        """
        self._observed_masses = observed_masses
        if precursor_mass is not None:
            self._precursor_mass = precursor_mass
        return self
