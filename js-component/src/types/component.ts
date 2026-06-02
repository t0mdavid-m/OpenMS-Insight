/**
 * Type definitions for component configuration and data structures.
 */

import type { ColumnDefinition, Options as TabulatorOptions } from 'tabulator-tables'

/**
 * Base component arguments shared by all components.
 */
export interface BaseComponentArgs {
  componentType: string
}

/**
 * Interactivity mapping: identifier name -> column name
 */
export type InteractivityMapping = Record<string, string>

/**
 * Pagination state for server-side pagination.
 * Stored in StateManager via paginationIdentifier.
 */
export interface PaginationState {
  page: number
  page_size: number
  total_rows: number
  total_pages: number
  sort_column?: string
  sort_dir?: 'asc' | 'desc'
}

/**
 * Column metadata for server-side filter dialogs.
 * Precomputed during preprocessing to avoid client-side data scanning.
 */
export interface ColumnMetadata {
  type: 'categorical' | 'numeric' | 'text'
  /** Unique values for categorical columns (max 100 values) */
  unique_values?: (string | number | boolean)[]
  /** Min value for numeric columns */
  min?: number
  /** Max value for numeric columns */
  max?: number
}

/**
 * Table component arguments.
 *
 * `columnDefinitions` are raw Tabulator column dicts that round-trip through the
 * disk cache, so any `formatter` must be a JSON-serializable string (not an
 * inline JS function). String formatter names are resolved to functions in
 * `TabulatorTable.vue` via the `customFormatters` registry (formatters.ts).
 * Supported custom names: "scientific", "signed", "badge", "fixed",
 * "placeholder" (each accepts an optional `formatterParams` object).
 */
export interface TableComponentArgs extends BaseComponentArgs {
  componentType: 'TabulatorTable'
  columnDefinitions: ColumnDefinition[]
  tableIndexField?: string
  tableLayoutParam?: TabulatorOptions['layout']
  title?: string
  defaultRow?: number
  initialSort?: Array<{ column: string; dir: 'asc' | 'desc' }>
  goToFields?: string[]
  interactivity?: InteractivityMapping
  height?: number
  pagination?: boolean
  pageSize?: number
  /** State key for storing pagination state (page, sort, filters) */
  paginationIdentifier?: string
  /** Column metadata for filter dialogs (precomputed unique values, min/max) */
  columnMetadata?: Record<string, ColumnMetadata>
}

/**
 * Line plot component arguments.
 *
 * `mode` selects rendering behavior in-component:
 * - 'default': classic stick spectrum (highlight + per-row annotation labels).
 * - 'tagger': sequence-tag overlay with a derived two-level drill-down. Level is
 *   DERIVED from the `tagger_mass` selection (null => level 0). Heavy math
 *   (highlight masks, COG, sequence-arrow segments) is precomputed in Python and
 *   arrives as `plotData` (level 0) + `taggerSegmentsKey` + `taggerChargesKey`.
 */
export interface LinePlotComponentArgs extends BaseComponentArgs {
  componentType: 'PlotlyLineplotUnified' | 'PlotlyLineplot'
  mode?: 'default' | 'tagger'
  title: string
  /** Title shown at the annotated (level-1) drill-down (tagger). */
  titleLevel1?: string
  xLabel?: string
  /** X-axis label at the annotated (level-1) drill-down (tagger). */
  xLabelLevel1?: string
  yLabel?: string
  styling?: LinePlotStyling
  config?: LinePlotConfig
  interactivity?: InteractivityMapping
  xColumn?: string // Column name for x-axis values
  yColumn?: string // Column name for y-axis values
  highlightColumn?: string // Column name for highlight mask (boolean)
  /** Column name for the gold/selected mask (tagger). */
  selectedColumn?: string
  annotationColumn?: string // Column name for annotation text
  // --- tagger-specific ---
  /** Draw mass-button rects/labels above highlighted peaks (level 0). */
  taggerMassButtons?: boolean
  /** allDataForDrawing key holding the level-0 sequence-arrow segments. */
  taggerSegmentsKey?: string
  /** allDataForDrawing key holding the level-1 charge clusters. */
  taggerChargesKey?: string
  /** allDataForDrawing key holding the level-1 full annotated spectrum. */
  taggerLevel1Key?: string
  /** Oracle level-1 charge-label x scaling factor (27.5). */
  xPosScalingFactor?: number
  height?: number // Component height in pixels
}

/**
 * Density (target/decoy KDE / FDR) plot component arguments.
 *
 * Static two-series plot fed a tidy long {x, y, group} frame; no interactivity.
 */
export interface DensityPlotComponentArgs extends BaseComponentArgs {
  componentType: 'PlotlyDensityPlot'
  mode: 'density'
  title?: string
  xLabel?: string
  yLabel?: string
  /** Column names in the tidy long frame. */
  xColumn: string
  yColumn: string
  groupColumn: string
  /** Value in groupColumn that maps to the target (green) series. */
  targetValue: string
  /** Value in groupColumn that maps to the decoy (red) series. */
  decoyValue: string
  /** Legend noun, e.g. "QScore" (default) or "ProteoformLevelQvalue". */
  scoreLabel?: string
  styling?: { targetColor?: string; decoyColor?: string }
  config?: Record<string, unknown>
  height?: number
}

/**
 * One level-0 sequence-arrow segment (tagger). Precomputed in Python.
 */
export interface TaggerSegment {
  x_start: number
  x_end: number
  residue: string
  delta: number
  selected: boolean
}

/**
 * One level-1 charge-cluster peak (tagger). `cog` is the precomputed
 * intensity-weighted center-of-gravity m/z for the peak's charge group.
 */
export interface TaggerChargePeak {
  mz: number
  intensity: number
  charge: number
  cog: number
  charge_label: string
  selected: boolean
  peak_id: number
}

/**
 * Opaque TagData payload carried by the generic `tag` selection identifier
 * (set by the tag table, read by Python). Mirrors the oracle TagData shape.
 * Documentation-only — the generic store stores it as an opaque object value.
 */
export interface TaggerTagPayload {
  sequence: string
  nTerminal: boolean
  masses: number[]
  selectedAA: number
  startPos: number
  endPos: number
}

/**
 * Generic per-peak annotation descriptor (render-time, data coordinates).
 *
 * Self-describing label independent of the per-row column model: any caller can
 * emit `{x, text, color}` triplets. Charge labels are just `text="z="+charge`,
 * `x=COG`. Arrives via `allDataForDrawing.peakAnnotations`.
 */
export interface PeakAnnotation {
  /** Data-x of the label (e.g. intensity-weighted COG m/z). */
  x: number
  /** Label text (e.g. "z=12"). */
  text: string
  /** Badge fill; defaults to styling.highlightColor. */
  color?: string
  /** Optional hover text for an invisible hover point at the label. */
  hover?: string
  /** Optional group id for overlap-suppression scoping. */
  group?: string | number
  /** Optional explicit label y (defaults to the computed ypos band). */
  y?: number
}

export interface LinePlotStyling {
  highlightColor?: string
  selectedColor?: string
  unhighlightedColor?: string
  highlightHiddenColor?: string
  annotationColors?: {
    massButton?: string
    selectedMassButton?: string
    sequenceArrow?: string
    selectedSequenceArrow?: string
    background?: string
    buttonHover?: string
  }
}

export interface LinePlotConfig {
  xPosScalingFactor?: number
  xPosScalingThreshold?: number
  enableManualZoom?: boolean
  showChargeLabels?: boolean
  minAnnotationWidth?: number
}

/**
 * Heatmap component arguments.
 */
export interface HeatmapComponentArgs extends BaseComponentArgs {
  componentType: 'PlotlyHeatmap'
  title?: string
  xColumn: string
  yColumn: string
  intensityColumn: string
  xLabel?: string
  yLabel?: string
  colorscale?: string
  /** Reverse the colorscale direction (default: false) */
  reversescale?: boolean
  zoomIdentifier?: string
  interactivity?: InteractivityMapping
  height?: number
  /** Column for categorical coloring (if set, uses discrete colors instead of colorscale) */
  categoryColumn?: string
  /** Map of category values to colors (e.g., { "Control": "#FF0000", "Treatment": "#00FF00" }) */
  categoryColors?: Record<string, string>
  /** Use log10 transformation for intensity color mapping (default: true) */
  logScale?: boolean
  /** Custom label for the colorbar (default: "Intensity") */
  intensityLabel?: string
}

/**
 * SequenceView component arguments.
 */
export interface SequenceViewComponentArgs extends BaseComponentArgs {
  componentType: 'SequenceView'
  title?: string
  height?: number
  /** If true (default), observed masses are neutral masses. If false, they are m/z values. */
  deconvolved?: boolean
  /** Max charge state to consider for fragment matching when deconvolved=false. */
  precursorCharge?: number
  /** Interactivity mapping: identifier name -> column name for click handling. */
  interactivity?: InteractivityMapping
  /** When true, render the internal-fragment map below the terminal sequence map. */
  internalFragments?: boolean
  /** Default tolerance/unit for the internal-fragment matcher. */
  internalFragmentConfig?: { tolerance?: number; tolerancePpm?: boolean }
}

/**
 * VolcanoPlot component arguments.
 */
export interface VolcanoPlotComponentArgs extends BaseComponentArgs {
  componentType: 'PlotlyVolcano'
  /** Column name for log2 fold change (x-axis) */
  log2fcColumn: string
  /** Column name for -log10(p-value) (y-axis, pre-computed) */
  neglog10pColumn: string
  /** Column name for raw p-value (for hover display) */
  pvalueColumn: string
  /** Column name for point labels (hover and annotations) */
  labelColumn?: string
  title?: string
  xLabel?: string
  yLabel?: string
  /** Color for up-regulated points */
  upColor?: string
  /** Color for down-regulated points */
  downColor?: string
  /** Color for not significant points */
  nsColor?: string
  /** Show threshold lines on plot */
  showThresholdLines?: boolean
  /** Line style for thresholds ("dash", "solid", "dot") */
  thresholdLineStyle?: string
  /** Fold change threshold (|log2FC| >= fcThreshold is significant) */
  fcThreshold?: number
  /** P-value threshold (p < pThreshold is significant) */
  pThreshold?: number
  /** Max number of labels to show on significant points */
  maxLabels?: number
  interactivity?: InteractivityMapping
  height?: number
}

/**
 * Heatmap data format.
 * Each entry is a row with x, y, intensity, and any additional columns
 * needed for interactivity (e.g., scan_id, mass_idx).
 */
export type HeatmapData = Record<string, unknown>

/**
 * VolcanoPlot data format.
 * Each entry is a row with log2fc, neglog10p, pvalue, label, and any
 * additional columns needed for interactivity.
 */
export type VolcanoData = Record<string, unknown>

/**
 * MirrorPlot component arguments.
 */
export interface MirrorPlotComponentArgs extends BaseComponentArgs {
  componentType: 'PlotlyMirrorPlot'
  title?: string
  /** Label shown inside the top half of the figure. */
  titleTop?: string
  /** Label shown inside the bottom half of the figure. */
  titleBottom?: string
  xColumn: string
  yColumn: string
  highlightColumn?: string
  annotationColumn?: string
  xLabel?: string
  yLabel?: string
  interactivity?: InteractivityMapping
  styling?: MirrorPlotStyling
  config?: Record<string, unknown>
  height?: number
}

export interface MirrorPlotStyling {
  unhighlightedColor?: string
  highlightColor?: string
  selectedColor?: string
  annotationColors?: Record<string, string>
}

/**
 * Plot3D component arguments (Plotly scatter3d).
 */
export interface Plot3DComponentArgs extends BaseComponentArgs {
  componentType: 'Plotly3D'
  /** Column name for the x-axis (neutral mass) */
  xColumn: string
  /** Column name for the y-axis (charge state) */
  yColumn: string
  /** Column name for the z-axis (intensity) */
  zColumn: string
  /** Categorical column mapping each point to a series (e.g. Signal/Noise) */
  seriesColumn?: string
  /** Map of series value -> color (default Signal #3366CC / Noise #DC3912) */
  seriesColors?: Record<string, string>
  /** Plotly trace mode (render-time switch) */
  mode?: 'lines' | 'markers' | 'lines+markers'
  /** Render each point as a vertical stem (drop line) */
  stem?: boolean
  /** Baseline z value for stem triplets (clipped by z-axis range) */
  stemBaseline?: number
  title?: string
  xLabel?: string
  yLabel?: string
  zLabel?: string
  /** y-axis tick spacing (integer charge ticks => 1) */
  yDtick?: number
  /** y-axis tick origin */
  yTick0?: number
  /** Initial scene camera eye */
  cameraEye?: { x: number; y: number; z: number }
  /** Log10-transform z (default false = linear) */
  logZ?: boolean
  /** Extra tidy columns surfaced on hover */
  hoverColumns?: string[]
  interactivity?: InteractivityMapping
  height?: number
}

/**
 * Plot3D data format.
 * Each entry is a row with x, y, z, optional series, and any additional
 * columns needed for hover or interactivity.
 */
export type Plot3DData = Record<string, unknown>

/**
 * Union type for all component arguments.
 */
export type ComponentArgs =
  | TableComponentArgs
  | LinePlotComponentArgs
  | DensityPlotComponentArgs
  | HeatmapComponentArgs
  | SequenceViewComponentArgs
  | VolcanoPlotComponentArgs
  | MirrorPlotComponentArgs
  | Plot3DComponentArgs

/**
 * Component layout entry.
 */
export interface ComponentLayout {
  componentArgs: ComponentArgs
}

/**
 * Streamlit data structure received from Python.
 */
export interface StreamlitData {
  components?: ComponentLayout[][]
  selection_store?: Record<string, unknown>
  hash?: string
  [key: string]: unknown
}

/**
 * Table data format.
 */
export type TableData = Record<string, unknown>[]

/**
 * Plot data format for line plots.
 * x_values and y_values contain raw data points.
 * Vue component converts to stick plot format (triplets) for rendering.
 * Additional interactivity columns (e.g., interactivity_peak_id) are added dynamically.
 */
export interface PlotData {
  x_values: number[]
  y_values: number[]
  highlight_mask?: boolean[]
  /** Gold/selected mask (tagger level 0). */
  selected_mask?: boolean[]
  annotations?: string[]
  // Allow dynamic interactivity columns like interactivity_peak_id
  [key: string]: unknown[] | undefined
}

/**
 * Plot annotation data.
 */
export interface PlotAnnotations {
  shapes: Partial<Plotly.Shape>[]
  annotations: Partial<Plotly.Annotations>[]
  traces: Plotly.Data[]
}
