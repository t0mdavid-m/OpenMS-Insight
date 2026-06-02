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
 */
export interface LinePlotComponentArgs extends BaseComponentArgs {
  componentType: 'PlotlyLineplotUnified' | 'PlotlyLineplot'
  title: string
  xLabel?: string
  yLabel?: string
  styling?: LinePlotStyling
  config?: LinePlotConfig
  interactivity?: InteractivityMapping
  xColumn?: string // Column name for x-axis values
  yColumn?: string // Column name for y-axis values
  highlightColumn?: string // Column name for highlight mask (boolean)
  annotationColumn?: string // Column name for annotation text
  height?: number // Component height in pixels
  // --- Tagger extension (all optional; absent → single-series behavior) ---
  x2Column?: string | null // Second overlaid series x column (e.g. MonoMass_Anno)
  y2Column?: string | null // Second overlaid series y column (e.g. SumIntensity_Anno)
  highlight2Column?: string | null // Second series highlight mask
  annotation2Column?: string | null // Second series annotation text
  hasSecondSeries?: boolean // True when both x2Column and y2Column are set
  signalPeakColumn?: string | null // Boolean column flagging SignalPeaks membership
  // Charge drill-down: per-row signal-peak arrays (lists per deconv-peak row)
  signalMzColumn?: string | null // list[float] of signal-peak m/z per row
  signalChargeColumn?: string | null // list[int] of signal-peak charges per row
  signalIntensityColumn?: string | null // list[float] of signal-peak intensities per row
  hasSignalDrilldown?: boolean // True when signalMz + signalCharge columns are wired
  showSignalMarkers?: boolean // Draw signal-peak dot markers (default false, parity)
  tagHighlightColumn?: string | null // Boolean column for tag-overlay highlight
  tagAnnotationColumn?: string | null // Text column for tag-overlay labels
  tagWalkEnabled?: boolean // True when a tag (residue) walk overlay is wired
}

/**
 * Tag-walk (residue walk) payload sent at render time alongside plotData.
 * Carries the selected tag's ordered fragment masses and the residue letter
 * for each consecutive-mass gap. residues[i] labels the gap between masses[i]
 * and masses[i+1]. Drawn as arrows + letters over the deconv sticks with the
 * x-axis auto-zoomed to the tag's mass span (FLASHApp PlotlyLineplotTagger).
 */
export interface TagWalk {
  masses: number[]
  residues: string[]
  /** OPTIONAL direction anchor (FLASHApp selectedTag.nTerminal). */
  nTerminal?: boolean
  /** OPTIONAL within-tag residue index the user selected (FLASHApp selectedAA). */
  selectedAA?: number
}

export interface LinePlotStyling {
  highlightColor?: string
  selectedColor?: string
  unhighlightedColor?: string
  highlightHiddenColor?: string
  // Tagger extension colors
  secondSeriesColor?: string
  signalPeakColor?: string
  tagHighlightColor?: string
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
  /**
   * Legacy box-width scaling divisor used by the tag-walk / augmented-view paths
   * (FLASHApp xPosScalingFactor = 27.5). Box half-width = rangeWidth / this value.
   */
  legacyXPosScalingFactor?: number
  /**
   * Legacy all-or-nothing annotation hide threshold (FLASHApp = 30). When the
   * per-mass box half-width exceeds this (in legacy data units), ALL augmented-view
   * mass annotations are suppressed.
   */
  legacyXPosScalingThreshold?: number
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
 * DensityPlot data format.
 * Each entry is a {x, y} row of the KDE grid (target or decoy series).
 */
export type DensityData = Record<string, unknown>

/**
 * DensityPlot component arguments.
 * Static dual-KDE score-distribution plot (FLASHApp FDRPlotly port).
 */
export interface DensityPlotComponentArgs extends BaseComponentArgs {
  componentType: 'PlotlyDensity'
  title?: string
  xLabel?: string
  yLabel?: string
  /** Column name for x values in the {x,y} frames (default "x"). */
  xColumn?: string
  /** Column name for y (density) values (default "y"). */
  yColumn?: string
  /** Target trace legend name (default "Target QScores"). */
  targetName?: string
  /** Decoy trace legend name (default "Decoy QScores"). */
  decoyName?: string
  /** Target line/marker color (default "green"). */
  targetColor?: string
  /** Decoy line/marker color (default "red"). */
  decoyColor?: string
  interactivity?: InteractivityMapping
  height?: number
}

/**
 * Scatter3D component arguments.
 * 3D precursor-signal scatter (FLASHApp Plotly3Dplot port).
 */
export interface Scatter3DComponentArgs extends BaseComponentArgs {
  componentType: 'Plotly3DScatter'
  title?: string
  height?: number
  interactivity?: InteractivityMapping
}

/**
 * FeatureView component arguments.
 * FLASHQuant feature-group table + 3D signal plot (FLASHApp FLASHQuantView port).
 */
export interface FeatureViewComponentArgs extends BaseComponentArgs {
  componentType: 'PlotlyFeatureView'
  title?: string
  height?: number
}

/**
 * InternalFragmentMap component arguments.
 * Per-ion-type internal-fragment matrix over a sequence (FLASHApp port).
 */
export interface InternalFragmentMapComponentArgs extends BaseComponentArgs {
  componentType: 'InternalFragmentMap'
  title?: string
  height?: number
  interactivity?: InteractivityMapping
}

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
 * Union type for all component arguments.
 */
export type ComponentArgs =
  | TableComponentArgs
  | LinePlotComponentArgs
  | HeatmapComponentArgs
  | SequenceViewComponentArgs
  | VolcanoPlotComponentArgs
  | MirrorPlotComponentArgs
  | DensityPlotComponentArgs
  | Scatter3DComponentArgs
  | FeatureViewComponentArgs
  | InternalFragmentMapComponentArgs

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
  annotations?: string[]
  // --- Tagger extension ---
  x2_values?: number[] // Second overlaid series x values
  y2_values?: number[] // Second overlaid series y values
  highlight2_mask?: boolean[] // Second series highlight mask
  annotations2?: string[] // Second series annotation text
  signal_mask?: boolean[] // SignalPeaks membership flags (first series)
  tag_mask?: boolean[] // Tag-overlay highlight flags (first series)
  tag_annotations?: string[] // Tag-overlay labels (first series)
  // Charge drill-down: per deconv-peak row, the signal-peak arrays composing it.
  signal_mzs?: number[][] // signal-peak m/z values per row
  signal_charges?: number[][] // signal-peak charges per row
  signal_intensities?: number[][] // signal-peak intensities per row
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
