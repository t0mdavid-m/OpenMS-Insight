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
  zoomIdentifier?: string
  interactivity?: InteractivityMapping
  height?: number
  /** Column for categorical coloring (if set, uses discrete colors instead of colorscale) */
  categoryColumn?: string
  /** Map of category values to colors (e.g., { "Control": "#FF0000", "Treatment": "#00FF00" }) */
  categoryColors?: Record<string, string>
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
 * Union type for all component arguments.
 */
export type ComponentArgs =
  | TableComponentArgs
  | LinePlotComponentArgs
  | HeatmapComponentArgs
  | SequenceViewComponentArgs
  | VolcanoPlotComponentArgs

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
