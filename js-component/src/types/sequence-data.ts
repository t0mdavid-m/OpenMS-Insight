/**
 * Type definitions for SequenceView component.
 */

/**
 * External peak annotation from idXML file (from search engine).
 */
export interface ExternalAnnotation {
  /** Identification index this annotation belongs to */
  id_idx: number
  /** m/z of the annotated peak */
  mz: number
  /** Ion annotation string (e.g., 'b5', 'y7²⁺') */
  annotation: string
  /** Charge state of the fragment */
  charge: number
  /** Ion type ('a', 'b', 'c', 'x', 'y', 'z', or 'unknown') */
  ion_type: string
}

/**
 * Theoretical internal-fragment arrays (enumerated in Python).
 *
 * Distinct from the per-position terminal `fragment_masses_a..z` (number[][]):
 * these are FLAT number[] (one entry per enumerated internal fragment). Only the
 * three families the oracle draws are present: by (label "by/cz"), bz, cy.
 * `start` is 0-based, `end` is 1-based (matches the fill predicate
 * `aaIndex > start && aaIndex <= end`).
 */
export interface InternalFragmentData {
  fragment_masses_by: number[]
  start_indices_by: number[]
  end_indices_by: number[]
  fragment_masses_bz: number[]
  start_indices_bz: number[]
  end_indices_bz: number[]
  fragment_masses_cy: number[]
  start_indices_cy: number[]
  end_indices_cy: number[]
}

/**
 * Sequence data structure containing peptide sequence and fragment information.
 */
export interface SequenceData {
  /** Array of single-letter amino acid codes */
  sequence: string[]
  /** Array of modification mass shifts per position (null for unmodified positions) */
  modifications?: (number | null)[]
  /** Pre-computed fragment masses for a ions (array of arrays for multiple masses due to modifications) */
  fragment_masses_a: number[][]
  /** Pre-computed fragment masses for b ions */
  fragment_masses_b: number[][]
  /** Pre-computed fragment masses for c ions */
  fragment_masses_c: number[][]
  /** Pre-computed fragment masses for x ions */
  fragment_masses_x: number[][]
  /** Pre-computed fragment masses for y ions */
  fragment_masses_y: number[][]
  /** Pre-computed fragment masses for z ions */
  fragment_masses_z: number[][]
  /** Calculated monoisotopic mass of the full sequence */
  theoretical_mass: number
  /** List of amino acids with fixed modifications (e.g., ['C', 'M']) */
  fixed_modifications: string[]
  /**
   * Per-residue coverage, ALREADY normalised to [0, 1] (value / maxCoverage),
   * one entry per residue. Present only when a `coverage_column` is configured
   * in Python; absent otherwise (no coverage gradient, back-compatible).
   */
  coverage?: number[]
  /**
   * Raw maximum coverage count (pre-normalisation). Used for the coverage scale
   * legend label (e.g. "5x"). Present iff `coverage` is present.
   */
  maxCoverage?: number
  /**
   * Reported proteoform N-terminus residue index (0-based). A NEGATIVE value
   * marks an UNDETERMINED N-terminus (renders a "??" terminal marker); a value
   * > 0 marks a truncated N-terminus (struck-through terminal letter + the
   * residues before it dimmed). Optional; absent -> full determined terminus.
   */
  proteoform_start?: number
  /**
   * Reported proteoform C-terminus residue index (0-based). A NEGATIVE value
   * marks an UNDETERMINED C-terminus; a value < length-1 marks a truncated
   * C-terminus. Optional; absent -> full determined terminus.
   */
  proteoform_end?: number
  /** External peak annotations from search engine (optional) */
  external_annotations?: ExternalAnnotation[]
  /** Fragment tolerance value from search parameters (optional) */
  fragment_tolerance?: number
  /** Whether fragment tolerance is in ppm (true) or Da (false) */
  fragment_tolerance_ppm?: boolean
  /** Whether to enable neutral loss matching (water loss, ammonium loss) by default */
  neutral_losses?: boolean
  /** Whether to enable proton loss/addition matching by default */
  proton_loss_addition?: boolean
  /** True when the internal-fragment arrays below are populated. */
  internal_fragments?: boolean
  /** Default tolerance value for the internal-fragment matcher. */
  internal_fragment_tolerance?: number
  /** Whether the internal-fragment tolerance is ppm (true) or Da (false). */
  internal_fragment_tolerance_ppm?: boolean
  /** Flat theoretical internal-fragment masses for the by/cz family. */
  fragment_masses_by?: number[]
  start_indices_by?: number[]
  end_indices_by?: number[]
  /** Flat theoretical internal-fragment masses for the bz family. */
  fragment_masses_bz?: number[]
  start_indices_bz?: number[]
  end_indices_bz?: number[]
  /** Flat theoretical internal-fragment masses for the cy family. */
  fragment_masses_cy?: number[]
  start_indices_cy?: number[]
  end_indices_cy?: number[]
}

/**
 * Observed spectrum data for fragment matching.
 */
export interface ObservedSpectrumData {
  /** Observed precursor mass */
  precursor_mass: number
  /** Array of observed peak masses */
  observed_masses: number[]
  /** Array of peak IDs corresponding to observed_masses (for interactivity) */
  peak_ids?: number[]
}

/**
 * Internal representation of an amino acid with fragment matching state.
 */
export interface SequenceObject {
  /** Single-letter amino acid code */
  aminoAcid: string
  /**
   * Per-residue coverage, normalised to [0, 1] (from SequenceData.coverage).
   * Undefined when no coverage is supplied -> no coverage gradient is drawn.
   */
  coverage?: number
  /** Whether this position has a matched a ion */
  aIon: boolean
  /** Whether this position has a matched b ion */
  bIon: boolean
  /** Whether this position has a matched c ion */
  cIon: boolean
  /** Whether this position has a matched x ion */
  xIon: boolean
  /** Whether this position has a matched y ion */
  yIon: boolean
  /** Whether this position has a matched z ion */
  zIon: boolean
  /** Extra fragment type labels (e.g., '-H2O', '-NH3') */
  extraTypes: string[]
}

/**
 * Fragment table row for display.
 */
export interface FragmentTableRow {
  /** Fragment name in Biemann notation (e.g., 'b5', 'y7' or 'b5²⁺' for charged) */
  Name: string
  /** Ion type with extra info (e.g., 'b', 'y-H2O') */
  IonType: string
  /** Ion number (position in sequence) */
  IonNumber: number
  /** Charge state of matched fragment (only for non-deconvolved data) */
  Charge?: number
  /** Calculated theoretical mass (neutral mass for deconvolved, m/z for non-deconvolved) */
  TheoreticalMass: string
  /** Observed mass/mz from spectrum */
  ObservedMass: number
  /** Peak ID of the matched peak (for interactivity linking) */
  PeakId?: number
  /** Mass difference in Daltons */
  MassDiffDa: string
  /** Mass difference in ppm */
  MassDiffPpm: string
}
