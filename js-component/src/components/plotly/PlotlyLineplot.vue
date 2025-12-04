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

    /**
     * Get plot data from Python.
     */
    plotData(): PlotData | undefined {
      const data = this.streamlitDataStore.allDataForDrawing?.plotData
      return data as PlotData | undefined
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
     * Compute x range for the plot.
     */
    xRange(): number[] {
      if (!this.isDataReady || !this.plotData) return [0, 1]

      const xValues = this.plotData.x_values
      const minX = Math.min(...xValues)
      const maxX = Math.max(...xValues)
      const padding = (maxX - minX) * 0.02

      return [minX - padding, maxX + padding]
    },

    /**
     * Compute y range for the plot.
     */
    yRange(): number[] {
      if (!this.isDataReady || !this.plotData) return [0, 1]

      const yValues = this.plotData.y_values.filter((y) => y > 0)
      if (yValues.length === 0) return [0, 1]

      const maxY = Math.max(...yValues)
      return [0, maxY * 1.1]
    },

    /**
     * Build Plotly traces.
     */
    traces(): Plotly.Data[] {
      if (!this.isDataReady || !this.plotData) {
        return this.getFallbackData()
      }

      const traces: Plotly.Data[] = []
      const { x_values, y_values, highlight_mask } = this.plotData

      // If no highlight mask, show all as one trace
      if (!highlight_mask) {
        traces.push({
          x: x_values,
          y: y_values,
          mode: 'lines',
          type: 'scatter',
          connectgaps: false,
          marker: { color: this.styling.highlightHiddenColor },
          hoverinfo: 'x+y',
        })
        return traces
      }

      // Split into highlighted and unhighlighted based on mask
      const unhighlighted_x: number[] = []
      const unhighlighted_y: number[] = []
      const highlighted_x: number[] = []
      const highlighted_y: number[] = []

      // For stick plots, each data point has 3 values (x, x, x) and (0, y, 0)
      const isStickPlot = this.args.plotType === 'stick'
      const stepSize = isStickPlot ? 3 : 1

      for (let i = 0; i < x_values.length; i++) {
        const maskIndex = isStickPlot ? Math.floor(i / stepSize) : i
        const isHighlighted = highlight_mask[maskIndex]

        if (isHighlighted) {
          highlighted_x.push(x_values[i])
          highlighted_y.push(y_values[i])
        } else {
          unhighlighted_x.push(x_values[i])
          unhighlighted_y.push(y_values[i])
        }
      }

      // Unhighlighted trace
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

      // Highlighted trace
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

        // Add click event listener
        const plotElement = document.getElementById(this.id) as any
        if (plotElement) {
          plotElement.on('plotly_click', (eventData: any) => {
            this.onPlotClick(eventData)
          })
        }
      } catch (error) {
        console.error('PlotlyLineplot: Error rendering plot:', error)
        this.renderFallback()
      }
    },

    onPlotClick(eventData: any): void {
      if (eventData.points && eventData.points.length > 0) {
        const point = eventData.points[0]
        const x = point.x
        const y = point.y
        const pointIndex = point.pointIndex

        // Update selection store
        this.selectionStore.updateSelection('selectedPoint', {
          x,
          y,
          index: pointIndex,
        })
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
