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
}

/**
 * Heatmap data format.
 * Each entry is a row with x, y, intensity, and any additional columns
 * needed for interactivity (e.g., scan_id, mass_idx).
 */
export type HeatmapData = Record<string, unknown>

/**
 * Union type for all component arguments.
 */
export type ComponentArgs = TableComponentArgs | LinePlotComponentArgs | HeatmapComponentArgs

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
