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
  xColumn?: string // Column name for x-axis, used for click-to-select
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
 * Union type for all component arguments.
 */
export type ComponentArgs = TableComponentArgs | LinePlotComponentArgs

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
 */
export interface PlotData {
  x_values: number[]
  y_values: number[]
  highlight_mask?: boolean[]
  annotations?: string[]
}

/**
 * Plot annotation data.
 */
export interface PlotAnnotations {
  shapes: Partial<Plotly.Shape>[]
  annotations: Partial<Plotly.Annotations>[]
  traces: Plotly.Data[]
}
