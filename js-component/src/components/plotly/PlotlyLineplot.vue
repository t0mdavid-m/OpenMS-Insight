<template>
  <div :id="id" class="plot-container" :style="cssCustomProperties"></div>
</template>

<script lang="ts">
import { defineComponent, type PropType } from 'vue'
import Plotly from 'plotly.js-dist-min'
import type { Theme } from 'streamlit-component-lib'
import { useStreamlitDataStore } from '@/stores/streamlit-data'
import { useSelectionStore } from '@/stores/selection'
import type { LinePlotComponentArgs, PlotData } from '@/types/component'

// Default styling configuration
const DEFAULT_STYLING = {
  highlightColor: '#E4572E',
  selectedColor: '#F3A712',
  unhighlightedColor: 'lightblue',
  highlightHiddenColor: '#1f77b4',
  annotationBackground: '#f8f8f8',
}

// Default config for annotation scaling
const DEFAULT_CONFIG = {
  xPosScalingFactor: 80,
  xPosScalingThreshold: 500,
  minAnnotationWidth: 40,
}

export default defineComponent({
  name: 'PlotlyLineplot',
  props: {
    args: {
      type: Object as PropType<LinePlotComponentArgs>,
      required: true,
    },
    index: {
      type: Number,
      required: true,
    },
  },
  setup() {
    const streamlitDataStore = useStreamlitDataStore()
    const selectionStore = useSelectionStore()
    return { streamlitDataStore, selectionStore }
  },
  data() {
    return {
      isInitialized: false as boolean,
      manualXRange: undefined as number[] | undefined,
    }
  },
  computed: {
    id(): string {
      return `plot-${this.index}`
    },

    theme(): Theme | undefined {
      return this.streamlitDataStore.theme
    },

    styling() {
      return {
        ...DEFAULT_STYLING,
        ...this.args.styling,
      }
    },

    config() {
      return {
        ...DEFAULT_CONFIG,
        ...this.args.config,
      }
    },

    /**
     * Get actual plot width from DOM.
     */
    actualPlotWidth(): number {
      const element = document.getElementById(this.id)
      if (element) {
        const rect = element.getBoundingClientRect()
        if (rect.width > 0) {
          return rect.width
        }
      }
      return 800 // default
    },

    /**
     * Get plot data from Python.
     */
    plotData(): PlotData | undefined {
      const data = this.streamlitDataStore.allDataForDrawing?.plotData
      return data as PlotData | undefined
    },

    /**
     * Get interactivity mapping from args.
     * Maps identifier names to column names.
     */
    interactivity(): Record<string, string> {
      return this.args.interactivity || {}
    },

    /**
     * Get the selected x value from the selection store.
     * Returns undefined if no selection or interactivity not configured.
     */
    selectedXValue(): number | undefined {
      // For each identifier in interactivity, check if there's a selection
      // that maps to x_column (we use x values for selection in plots)
      for (const [identifier, column] of Object.entries(this.interactivity)) {
        // Check if this interactivity uses the x column
        if (column === this.args.xColumn) {
          const value = this.selectionStore.$state[identifier]
          if (value !== undefined && value !== null) {
            return value as number
          }
        }
      }
      return undefined
    },

    /**
     * Find the index of the selected peak based on selectedXValue.
     */
    selectedPeakIndex(): number | undefined {
      const selectedX = this.selectedXValue
      if (selectedX === undefined || !this.isDataReady || !this.plotData) {
        return undefined
      }

      // Find the peak with matching x value
      const xValues = this.plotData.x_values
      for (let i = 0; i < xValues.length; i++) {
        if (xValues[i] === selectedX) {
          return i
        }
      }
      return undefined
    },

    /**
     * Check if data is ready for rendering.
     */
    isDataReady(): boolean {
      if (!this.plotData) return false
      return (
        Array.isArray(this.plotData.x_values) &&
        Array.isArray(this.plotData.y_values) &&
        this.plotData.x_values.length > 0
      )
    },

    /**
     * Generate stick format x values from raw data.
     * Each data point (x) becomes triplet: [x, x, x]
     */
    xValuesStick(): number[] {
      if (!this.isDataReady || !this.plotData) return []
      const result: number[] = []
      for (const x of this.plotData.x_values) {
        result.push(x, x, x)
      }
      return result
    },

    /**
     * Generate stick format y values from raw data.
     * Each data point (y) becomes triplet: [-10000000, y, -10000000]
     * Using large negative value (matching FLASHApp) to avoid visual artifacts.
     */
    yValuesStick(): number[] {
      if (!this.isDataReady || !this.plotData) return []
      const result: number[] = []
      const baseline = -10000000
      for (const y of this.plotData.y_values) {
        result.push(baseline, y, baseline)
      }
      return result
    },

    /**
     * Compute x range for the plot.
     */
    xRange(): number[] {
      // Use manual range if set (from zoom)
      if (this.manualXRange) {
        return this.manualXRange
      }

      if (!this.isDataReady || !this.plotData) return [0, 1]

      const xValues = this.plotData.x_values
      const minX = Math.min(...xValues)
      const maxX = Math.max(...xValues)
      const padding = (maxX - minX) * 0.02

      return [minX - padding, maxX + padding]
    },

    /**
     * Compute y range for the plot based on visible x range.
     * Adds extra space at top for annotations.
     */
    yRange(): number[] {
      if (!this.isDataReady || !this.plotData) return [0, 1]

      const { x_values, y_values } = this.plotData
      const xRange = this.xRange

      // Find max y within the visible x range
      let maxY = 0
      for (let i = 0; i < x_values.length; i++) {
        const x = x_values[i]
        const y = y_values[i]
        if (x >= xRange[0] && x <= xRange[1] && y > maxY) {
          maxY = y
        }
      }

      if (maxY === 0) return [0, 1]

      // Add headroom for annotations (1.8x like FLASHApp)
      return [0, maxY * 1.8]
    },

    /**
     * Compute x position scaling factor based on current zoom level.
     */
    xPosScalingFactor(): number {
      const xRange = this.xRange
      const rangeWidth = xRange[1] - xRange[0]
      const actualWidth = this.actualPlotWidth
      return (1200 / actualWidth) * rangeWidth / this.config.xPosScalingFactor
    },

    /**
     * Get annotation data: positions, labels, and visibility based on overlap.
     * Uses raw x_values/y_values (not stick format triplets).
     */
    annotatedPeaks(): Array<{
      x: number
      y: number
      label: string
      index: number
    }> {
      if (!this.isDataReady || !this.plotData) return []

      const { x_values, y_values, annotations, highlight_mask } = this.plotData
      if (!annotations) return []

      const peaks: Array<{ x: number; y: number; label: string; index: number }> = []

      for (let i = 0; i < annotations.length; i++) {
        const label = annotations[i]
        // Only include highlighted peaks with non-empty labels
        if (!label || label.length === 0) continue
        if (highlight_mask && !highlight_mask[i]) continue

        peaks.push({
          x: x_values[i],
          y: y_values[i],
          label: label,
          index: i,
        })
      }

      return peaks
    },

    /**
     * Compute annotation boxes with overlap detection.
     * Returns which annotations should be visible.
     * Only checks for collisions between labels within the visible x range.
     */
    annotationBoxData(): Array<{
      x: number
      y: number
      width: number
      height: number
      label: string
      visible: boolean
    }> {
      const peaks = this.annotatedPeaks
      if (peaks.length === 0) return []

      const yRange = this.yRange
      const xRange = this.xRange

      if (yRange[1] <= 0 || xRange[1] <= xRange[0]) return []

      const ymax = yRange[1] / 1.8
      const ypos_low = ymax * 1.18
      const ypos_high = ymax * 1.32
      const boxHeight = ypos_high - ypos_low

      const xpos_scaling = this.xPosScalingFactor

      const boxes: Array<{
        x: number
        y: number
        width: number
        height: number
        label: string
        visible: boolean
        inVisibleRange: boolean
      }> = []

      // Create boxes for each annotation, marking if they're in visible range
      for (const peak of peaks) {
        const inVisibleRange = peak.x >= xRange[0] && peak.x <= xRange[1]
        boxes.push({
          x: peak.x,
          y: (ypos_low + ypos_high) / 2,
          width: xpos_scaling * 2,
          height: boxHeight,
          label: peak.label,
          visible: inVisibleRange, // Only visible if in range
          inVisibleRange: inVisibleRange,
        })
      }

      // Filter to only visible boxes for overlap detection
      const visibleBoxes = boxes.filter((box) => box.inVisibleRange)

      // Check for overlaps only among visible boxes
      if (visibleBoxes.length > 1) {
        let hasOverlap = false
        const xPadding = (xRange[1] - xRange[0]) * 0.01

        for (let i = 0; i < visibleBoxes.length && !hasOverlap; i++) {
          for (let j = i + 1; j < visibleBoxes.length; j++) {
            const box1Left = visibleBoxes[i].x - visibleBoxes[i].width / 2 - xPadding
            const box1Right = visibleBoxes[i].x + visibleBoxes[i].width / 2 + xPadding
            const box2Left = visibleBoxes[j].x - visibleBoxes[j].width / 2 - xPadding
            const box2Right = visibleBoxes[j].x + visibleBoxes[j].width / 2 + xPadding

            // Check x overlap (y is the same for all boxes)
            if (!(box1Right < box2Left || box2Right < box1Left)) {
              hasOverlap = true
              break
            }
          }
        }

        // If overlap detected, hide all visible boxes
        if (hasOverlap) {
          boxes.forEach((box) => {
            if (box.inVisibleRange) {
              box.visible = false
            }
          })
        }
      }

      return boxes
    },

    /**
     * Build Plotly shapes for annotation background boxes.
     */
    annotationShapes(): Partial<Plotly.Shape>[] {
      const boxes = this.annotationBoxData
      const shapes: Partial<Plotly.Shape>[] = []

      const yRange = this.yRange
      if (yRange[1] <= 0) return shapes

      const ymax = yRange[1] / 1.8
      const ypos_low = ymax * 1.18
      const ypos_high = ymax * 1.32

      for (const box of boxes) {
        if (!box.visible) continue

        shapes.push({
          type: 'rect',
          x0: box.x - box.width / 2,
          y0: ypos_low,
          x1: box.x + box.width / 2,
          y1: ypos_high,
          fillcolor: this.styling.highlightColor,
          line: { width: 0 },
        })
      }

      return shapes
    },

    /**
     * Build Plotly annotations for peak labels.
     */
    peakAnnotations(): Partial<Plotly.Annotations>[] {
      const boxes = this.annotationBoxData
      const annotations: Partial<Plotly.Annotations>[] = []

      const yRange = this.yRange
      if (yRange[1] <= 0) return annotations

      const ymax = yRange[1] / 1.8
      const ypos = ymax * 1.25

      for (const box of boxes) {
        if (!box.visible) continue

        annotations.push({
          x: box.x,
          y: ypos,
          xref: 'x',
          yref: 'y',
          text: box.label,
          showarrow: false,
          font: {
            size: 14,
            color: 'white',
          },
        })
      }

      return annotations
    },

    /**
     * Build Plotly traces.
     * Uses stick format triplets generated from raw data.
     * Includes a separate gold trace for the selected peak.
     */
    traces(): Plotly.Data[] {
      if (!this.isDataReady || !this.plotData) {
        return this.getFallbackData()
      }

      const traces: Plotly.Data[] = []
      const { highlight_mask } = this.plotData
      const selectedIndex = this.selectedPeakIndex
      const baseline = -10000000

      // Split into unhighlighted, highlighted, and selected
      const unhighlighted_x: number[] = []
      const unhighlighted_y: number[] = []
      const highlighted_x: number[] = []
      const highlighted_y: number[] = []
      const selected_x: number[] = []
      const selected_y: number[] = []

      const numPoints = this.plotData.x_values.length

      for (let i = 0; i < numPoints; i++) {
        const x = this.plotData.x_values[i]
        const y = this.plotData.y_values[i]
        const isHighlighted = highlight_mask ? highlight_mask[i] : false
        const isSelected = selectedIndex !== undefined && i === selectedIndex

        if (isSelected) {
          // Selected peak goes in gold trace (drawn last, on top)
          selected_x.push(x, x, x)
          selected_y.push(baseline, y, baseline)
        } else if (isHighlighted) {
          // Highlighted peaks (annotated)
          highlighted_x.push(x, x, x)
          highlighted_y.push(baseline, y, baseline)
        } else {
          // Normal unhighlighted peaks
          unhighlighted_x.push(x, x, x)
          unhighlighted_y.push(baseline, y, baseline)
        }
      }

      // Unhighlighted trace (drawn first, bottom layer)
      if (unhighlighted_x.length > 0) {
        traces.push({
          x: unhighlighted_x,
          y: unhighlighted_y,
          mode: 'lines',
          type: 'scatter',
          connectgaps: false,
          marker: { color: this.styling.unhighlightedColor },
          hoverinfo: 'x+y',
        })
      }

      // Highlighted trace (middle layer)
      if (highlighted_x.length > 0) {
        traces.push({
          x: highlighted_x,
          y: highlighted_y,
          mode: 'lines',
          type: 'scatter',
          connectgaps: false,
          marker: { color: this.styling.highlightColor },
          hoverinfo: 'x+y',
        })
      }

      // Selected trace (top layer, gold color)
      if (selected_x.length > 0) {
        traces.push({
          x: selected_x,
          y: selected_y,
          mode: 'lines',
          type: 'scatter',
          connectgaps: false,
          marker: { color: this.styling.selectedColor },
          line: { width: 3 }, // Make selected peak slightly thicker
          hoverinfo: 'x+y',
        })
      }

      // If no data was added (no highlight mask and no selection), show all as default
      if (traces.length === 0) {
        traces.push({
          x: this.xValuesStick,
          y: this.yValuesStick,
          mode: 'lines',
          type: 'scatter',
          connectgaps: false,
          marker: { color: this.styling.highlightHiddenColor },
          hoverinfo: 'x+y',
        })
      }

      return traces
    },

    /**
     * Build Plotly layout.
     */
    layout(): Partial<Plotly.Layout> {
      return {
        title: this.args.title ? `<b>${this.args.title}</b>` : undefined,
        showlegend: false,
        height: 400,
        xaxis: {
          title: this.args.xLabel,
          showgrid: false,
          showline: true,
          linecolor: 'grey',
          linewidth: 1,
          range: this.xRange,
        },
        yaxis: {
          title: this.args.yLabel,
          showgrid: true,
          gridcolor: this.theme?.secondaryBackgroundColor || '#f0f0f0',
          rangemode: 'nonnegative',
          fixedrange: false,
          showline: true,
          linecolor: 'grey',
          linewidth: 1,
          range: this.yRange,
        },
        paper_bgcolor: this.theme?.backgroundColor || 'white',
        plot_bgcolor: this.theme?.backgroundColor || 'white',
        font: {
          color: this.theme?.textColor || 'black',
          family: this.theme?.font || 'Arial',
        },
        margin: {
          l: 60,
          r: 20,
          t: this.args.title ? 50 : 20,
          b: 50,
        },
        shapes: this.annotationShapes,
        annotations: this.peakAnnotations,
      }
    },

    cssCustomProperties(): Record<string, string> {
      return {
        '--highlight-color': this.styling.highlightColor,
        '--selected-color': this.styling.selectedColor,
        '--unhighlighted-color': this.styling.unhighlightedColor,
      }
    },
  },

  watch: {
    isDataReady: {
      handler(newVal: boolean) {
        if (newVal) {
          this.renderPlot()
        }
      },
      immediate: true,
    },

    'streamlitDataStore.allDataForDrawing.plotData': {
      handler() {
        this.renderPlot()
      },
      deep: true,
    },

    // Re-render when selection changes (to update gold highlighting)
    'selectionStore.$state': {
      handler() {
        if (this.isDataReady) {
          this.renderPlot()
        }
      },
      deep: true,
    },
  },

  mounted() {
    this.isInitialized = true
    if (this.isDataReady) {
      this.renderPlot()
    }
  },

  methods: {
    async renderPlot(): Promise<void> {
      try {
        const element = document.getElementById(this.id)
        if (!element) {
          console.warn(`PlotlyLineplot: DOM element with id '${this.id}' not found`)
          return
        }

        const modeBarButtons = [
          {
            title: 'Download as SVG',
            name: 'toImageSvg',
            icon: {
              width: 1792,
              height: 1792,
              path: 'M1152 1376v-160q0-14-9-23t-23-9h-96v-512q0-14-9-23t-23-9h-320q-14 0-23 9t-9 23v160q0 14 9 23t23 9h96v320h-96q-14 0-23 9t-9 23v160q0 14 9 23t23 9h320q14 0 23-9t9-23zm-128-896v-160q0-14-9-23t-23-9h-192q-14 0-23 9t-9 23v160q0 14 9 23t23 9h192q14 0 23-9t9-23zm640 416q0 209-103 385.5t-279.5 279.5-385.5 103-385.5-103-279.5-279.5-103-385.5 103-385.5 279.5-279.5 385.5-103 385.5 103 279.5 279.5 103 385.5z',
            },
            click: () => {
              const element = document.getElementById(this.id)
              if (element) {
                Plotly.downloadImage(element, {
                  filename: this.args.title || 'plot',
                  height: 400,
                  width: 1200,
                  format: 'svg',
                })
              }
            },
          },
        ]

        await Plotly.newPlot(this.id, this.traces, this.layout, {
          modeBarButtonsToRemove: ['toImage', 'sendDataToCloud'],
          modeBarButtonsToAdd: modeBarButtons,
          scrollZoom: true,
          responsive: true,
        })

        // Add event listeners
        const plotElement = document.getElementById(this.id) as any
        if (plotElement) {
          plotElement.on('plotly_click', (eventData: any) => {
            this.onPlotClick(eventData)
          })

          plotElement.on('plotly_relayout', (eventData: any) => {
            this.onRelayout(eventData)
          })
        }
      } catch (error) {
        console.error('PlotlyLineplot: Error rendering plot:', error)
        this.renderFallback()
      }
    },

    onRelayout(eventData: any): void {
      // Handle zoom/pan events
      if (eventData['xaxis.range[0]'] !== undefined && eventData['xaxis.range[1]'] !== undefined) {
        const newXRange = [eventData['xaxis.range[0]'], eventData['xaxis.range[1]']]
        if (newXRange[0] < 0) {
          newXRange[0] = 0
        }
        this.manualXRange = newXRange
        this.renderPlot()
      } else if (eventData['xaxis.autorange'] === true) {
        // Reset to auto range
        this.manualXRange = undefined
        this.renderPlot()
      }
    },

    onPlotClick(eventData: any): void {
      // Only handle clicks if interactivity is configured
      if (!this.interactivity || Object.keys(this.interactivity).length === 0) {
        return
      }

      if (eventData.points && eventData.points.length > 0) {
        const point = eventData.points[0]
        const clickedX = point.x

        // Find the nearest peak to the clicked x position
        // Plotly click returns triplet index, we need to find the actual peak
        if (!this.plotData) return

        const xValues = this.plotData.x_values
        let nearestIndex = 0
        let nearestDistance = Infinity

        for (let i = 0; i < xValues.length; i++) {
          const distance = Math.abs(xValues[i] - clickedX)
          if (distance < nearestDistance) {
            nearestDistance = distance
            nearestIndex = i
          }
        }

        const selectedXValue = xValues[nearestIndex]

        // Update selection store using the interactivity mapping
        for (const [identifier, column] of Object.entries(this.interactivity)) {
          // For now, we assume interactivity column matches x_column
          // (selection is by x value / mass)
          if (column === this.args.xColumn) {
            this.selectionStore.updateSelection(identifier, selectedXValue)
          }
        }
      }
    },

    getFallbackData(): Plotly.Data[] {
      return [
        {
          x: [0, 1],
          y: [0, 0],
          mode: 'lines',
          type: 'scatter',
          marker: { color: this.styling.unhighlightedColor },
          name: 'No Data',
        },
      ]
    },

    async renderFallback(): Promise<void> {
      try {
        const fallbackLayout: Partial<Plotly.Layout> = {
          title: '<b>No Data Available</b>',
          showlegend: false,
          height: 400,
          xaxis: { title: 'X', showgrid: false },
          yaxis: { title: 'Y', showgrid: true, rangemode: 'nonnegative' },
          paper_bgcolor: this.theme?.backgroundColor || 'white',
          plot_bgcolor: this.theme?.backgroundColor || 'white',
          font: {
            color: this.theme?.textColor || 'black',
            family: this.theme?.font || 'Arial',
          },
        }

        await Plotly.newPlot(this.id, this.getFallbackData(), fallbackLayout, {
          staticPlot: true,
        })
      } catch (error) {
        console.error('PlotlyLineplot: Failed to render fallback:', error)
      }
    },
  },
})
</script>

<style scoped>
.plot-container {
  position: relative;
  width: 100%;
  min-height: 400px;
}
</style>
