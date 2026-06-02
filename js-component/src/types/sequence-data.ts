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
 * Sentinel value for an OPEN / undetermined proteoform terminus (mirrors the
 * Python `UNDETERMINED_TERMINUS`). When `proteoform_start`/`proteoform_end`
 * equals this, the corresponding terminus is rendered as undetermined (red "??").
 */
export const UNDETERMINED_TERMINUS = -2

/**
 * Ambiguous modification range (P0). Describes a spanning dotted modification
 * region over residues [start, end] (0-based, inclusive) carrying a mass badge
 * and a "Possible Modifications" label list. DISTINCT from the per-residue
 * fixed-mod `modifications` field.
 */
export interface ModRange {
  /** 0-based inclusive start residue index of the spanning modification */
  start: number
  /** 0-based inclusive end residue index of the spanning modification */
  end: number
  /** Mass difference (Da) of the ambiguous modification */
  mass_diff: number
  /** Human-readable list of possible modification labels (for the tooltip) */
  labels: string
}

/**
 * Selected tag span for the tag-highlight overlay (P0). Carries the protein-
 * absolute (0-based, inclusive) start/end residue indices of the selected
 * sequence tag and whether it is N-terminal. Delivered to SequenceView through
 * the optional `tag_span` interactivity sentinel.
 */
export interface TagSpan {
  /** Start residue index (protein-absolute, 0-based, inclusive) */
  start: number
  /** End residue index (protein-absolute, 0-based, inclusive) */
  end: number
  /** Whether this is an N-terminal tag */
  nTerminal?: boolean
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
   * Per-residue sequence-tag coverage, normalized to [0, 1] against maxCoverage
   * (FLASHApp TnT path). One entry per residue in `sequence`. Optional: when
   * absent, no coverage shading is applied. (EXTEND)
   */
  coverage?: number[]
  /**
   * Raw maximum coverage (number of tags) used to normalize `coverage`. Drives
   * the coverage scale legend ("{maxCoverage}x" .. "1x"). Optional. (EXTEND)
   */
  maxCoverage?: number
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
  /**
   * Offset added to a residue's 0-based grid index to obtain its PROTEIN-ABSOLUTE
   * 0-based position. Used by the residue-click Tag-Table cross-link so the emitted
   * position matches protein-absolute tag coordinates (StartPos/EndPos) even when
   * the displayed sequence is a proteoform substring. Defaults to 0 (the displayed
   * sequence is the full protein / starts at protein position 0). Optional. (EXTEND)
   */
  sequence_offset?: number
  /**
   * 0-based inclusive index of the FIRST determined residue of the proteoform
   * within the displayed sequence. Residues before it are a truncated N-flank.
   * Sentinel `UNDETERMINED_TERMINUS` (-2) => the N-terminus is undetermined
   * (open). Absent => 0 (no N truncation). (EXTEND, P0)
   */
  proteoform_start?: number
  /**
   * 0-based inclusive index of the LAST determined residue of the proteoform.
   * Residues after it are a truncated C-flank. Sentinel -2 => C-terminus
   * undetermined (open). Absent => last residue (no C truncation). (EXTEND, P0)
   */
  proteoform_end?: number
  /**
   * Observed/deconvolved proteoform mass (Da). Its presence switches the mass
   * header title to "Proteoform" (vs "Precursor") and marks the TnT path.
   * Optional. (EXTEND, P1)
   */
  computed_mass?: number
  /**
   * Ambiguous modification ranges (spanning dotted mod regions with mass badge
   * and possible-mod labels). DISTINCT from per-residue `modifications`.
   * Optional. (EXTEND, P0)
   */
  mod_ranges?: ModRange[]
}

/**
 * FLASHApp-style settings (TnT path) used to initialize fragment matching
 * defaults: deconvolution tolerance (ppm) and default fragment ion types.
 */
export interface SequenceViewSettings {
  /** Fragment mass tolerance in ppm */
  tolerance?: number
  /** Default fragment ion types to select (e.g., ['b', 'y']) */
  ion_types?: string[]
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
   * Per-residue normalized coverage in [0, 1], or undefined when no coverage
   * data is available for this residue. Drives coverage coloring. (EXTEND)
   */
  coverage?: number
  /**
   * Whether this residue is a truncated proteoform flank (struck through).
   * (EXTEND, P0)
   */
  truncated?: boolean
  /** Whether the selected tag's left bracket starts at this residue (P0) */
  tagStart?: boolean
  /** Whether the selected tag's right bracket ends at this residue (P0) */
  tagEnd?: boolean
  /** Ambiguous-modification region: this residue is the span start (P0) */
  modStart?: boolean
  /** Ambiguous-modification region: this residue is interior to the span (P0) */
  modCenter?: boolean
  /** Ambiguous-modification region: this residue is the span end (P0) */
  modEnd?: boolean
  /** Mass badge for an ambiguous-modification span end (e.g. "+134.99") (P0) */
  modMass?: string
  /** Possible-modification labels for the span tooltip (P0) */
  modLabels?: string
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
