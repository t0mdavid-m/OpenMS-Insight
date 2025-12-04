<template>
  <div :id="id" class="heatmap-container"></div>
</template>

<script lang="ts">
import { defineComponent, type PropType } from 'vue'
import Plotly from 'plotly.js-dist-min'
import { Streamlit, type Theme } from 'streamlit-component-lib'
import { useStreamlitDataStore } from '@/stores/streamlit-data'
import { useSelectionStore } from '@/stores/selection'
import type { HeatmapComponentArgs, HeatmapData } from '@/types/component'

export default defineComponent({
  name: 'PlotlyHeatmap',
  props: {
    args: {
      type: Object as PropType<HeatmapComponentArgs>,
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
      zoomRange: undefined as { xRange: number[]; yRange: number[] } | undefined,
      colorbarVisible: true,
      userOverrideColorbar: false,
      plotWidth: 800,
      resizeObserver: null as ResizeObserver | null,
    }
  },
  computed: {
    id(): string {
      return `heatmap-${this.index}`
    },

    theme(): Theme | undefined {
      return this.streamlitDataStore.theme
    },

    isNarrowPlot(): boolean {
      return this.plotWidth < 600
    },

    effectiveColorbarVisible(): boolean {
      if (this.userOverrideColorbar) {
        return this.colorbarVisible
      }
      return this.isNarrowPlot ? false : this.colorbarVisible
    },

    /**
     * Get heatmap data from Python.
     */
    heatmapData(): HeatmapData[] {
      const data = this.streamlitDataStore.allDataForDrawing?.heatmapData
      return (data as HeatmapData[]) || []
    },

    /**
     * Get interactivity mapping from args.
     */
    interactivity(): Record<string, string> {
      return this.args.interactivity || {}
    },

    /**
     * Check if data is ready for rendering.
     */
    isDataReady(): boolean {
      return Array.isArray(this.heatmapData) && this.heatmapData.length > 0
    },

    /**
     * Get x values from data.
     */
    xValues(): number[] {
      if (!this.isDataReady) return []
      const xCol = this.args.xColumn
      return this.heatmapData.map((row) => row[xCol] as number)
    },

    /**
     * Get y values from data.
     */
    yValues(): number[] {
      if (!this.isDataReady) return []
      const yCol = this.args.yColumn
      return this.heatmapData.map((row) => row[yCol] as number)
    },

    /**
     * Get intensity values from data.
     */
    intensityValues(): number[] {
      if (!this.isDataReady) return []
      const intensityCol = this.args.intensityColumn
      return this.heatmapData.map((row) => row[intensityCol] as number)
    },

    /**
     * Get log-scaled intensity values for coloring.
     */
    logIntensityValues(): number[] {
      return this.intensityValues.map((v) => (v > 0 ? Math.log10(v) : 0))
    },

    /**
     * Current x range from zoom state.
     */
    xRange(): number[] | undefined {
      const zoom = this.zoomRange
      if (!zoom) return undefined
      if (zoom.xRange[0] < 0 && zoom.xRange[1] < 0) return undefined
      return zoom.xRange
    },

    /**
     * Current y range from zoom state.
     */
    yRange(): number[] | undefined {
      const zoom = this.zoomRange
      if (!zoom) return undefined
      if (zoom.yRange[0] < 0 && zoom.yRange[1] < 0) return undefined
      return zoom.yRange
    },

    /**
     * Build colorbar tick values and text for log scale.
     */
    colorbarTicks(): { tickvals: number[]; ticktext: string[] } {
      const intensities = this.intensityValues.filter((x) => x > 0)
      if (intensities.length === 0) {
        return { tickvals: [0], ticktext: ['0'] }
      }

      const minIntensity = Math.min(...intensities)
      const maxIntensity = Math.max(...intensities)

      const minPower = Math.floor(Math.log10(minIntensity))
      const maxPower = Math.ceil(Math.log10(maxIntensity))

      const tickValues = Array.from(
        { length: maxPower - minPower + 1 },
        (_, i) => Math.pow(10, minPower + i)
      )

      return {
        tickvals: tickValues.map((v) => Math.log10(v)),
        ticktext: tickValues.map((v) => v.toExponential(0)),
      }
    },

    /**
     * Build Plotly data trace.
     */
    data(): Plotly.Data[] {
      if (!this.isDataReady) {
        return this.getFallbackData()
      }

      const { tickvals, ticktext } = this.colorbarTicks

      return [
        {
          type: 'scattergl',
          name: 'points',
          x: this.xValues,
          y: this.yValues,
          mode: 'markers',
          marker: {
            color: this.logIntensityValues,
            colorscale: this.args.colorscale || 'Portland',
            showscale: this.effectiveColorbarVisible,
            colorbar: {
              title: { text: 'Intensity' },
              tickvals: tickvals,
              ticktext: ticktext,
              tickmode: 'array' as const,
            },
          },
          hovertext: this.intensityValues.map((v) => v.toExponential(2)),
          hoverinfo: 'x+y+text',
        },
      ]
    },

    /**
     * Build Plotly layout.
     */
    layout(): Partial<Plotly.Layout> {
      return {
        title: this.args.title ? { text: `<b>${this.args.title}</b>` } : undefined,
        showlegend: false,
        height: this.args.height || 400,
        xaxis: {
          title: this.args.xLabel ? { text: this.args.xLabel } : undefined,
          range: this.xRange,
        },
        yaxis: {
          title: this.args.yLabel ? { text: this.args.yLabel } : undefined,
          range: this.yRange,
        },
        paper_bgcolor: this.theme?.backgroundColor || 'white',
        plot_bgcolor: this.theme?.secondaryBackgroundColor || '#f5f5f5',
        font: {
          color: this.theme?.textColor || 'black',
          family: this.theme?.font || 'Arial',
        },
        margin: {
          l: 60,
          r: this.effectiveColorbarVisible ? 120 : 20,
          t: this.args.title ? 60 : 20,
          b: 60,
        },
      }
    },
  },

  watch: {
    isDataReady: {
      handler(newVal: boolean) {
        if (newVal && this.isInitialized) {
          this.renderPlot()
        }
      },
      immediate: true,
    },

    'streamlitDataStore.allDataForDrawing.heatmapData': {
      handler() {
        if (this.isInitialized) {
          this.renderPlot()
        }
      },
      deep: true,
    },

    zoomRange: {
      handler() {
        if (this.zoomRange === undefined) return
        // Update selection store with zoom range
        const zoomIdentifier = this.args.zoomIdentifier || 'heatmap_zoom'
        this.selectionStore.updateSelection(zoomIdentifier, this.zoomRange)
      },
      deep: true,
    },
  },

  mounted() {
    this.isInitialized = true
    this.$nextTick(() => {
      if (this.isDataReady) {
        this.renderPlot()
      }
      this.setupResizeObserver()
    })
  },

  beforeUnmount() {
    this.cleanupResizeObserver()
  },

  methods: {
    async renderPlot(): Promise<void> {
      try {
        const element = document.getElementById(this.id)
        if (!element) {
          console.warn(`PlotlyHeatmap: DOM element with id '${this.id}' not found`)
          return
        }

        await Plotly.newPlot(this.id, this.data, this.layout, this.getPlotConfig())
        this.setupPlotEventHandlers()

        // Update Streamlit iframe height after plot is rendered
        this.$nextTick(() => {
          Streamlit.setFrameHeight()
        })
      } catch (error) {
        console.error('PlotlyHeatmap: Error rendering plot:', error)
        this.renderFallback()
      }
    },

    getPlotConfig(): Partial<Plotly.Config> {
      return {
        modeBarButtonsToRemove: ['toImage', 'sendDataToCloud'] as any,
        modeBarButtonsToAdd: [
          {
            title: 'Download as SVG',
            name: 'toImageSvg',
            icon: Plotly.Icons.camera,
            click: (plotlyElement: any) => {
              Plotly.downloadImage(plotlyElement, {
                filename: this.args.title || 'heatmap',
                height: 400,
                width: 1200,
                format: 'svg',
              })
            },
          },
          {
            title: 'Toggle Colorbar',
            name: 'toggleColorbar',
            icon: {
              width: 1792,
              height: 1792,
              path: 'M1408 768v192q0 40-28 68t-68 28H480q-40 0-68-28t-28-68V768q0-40 28-68t68-28h832q40 0 68 28t28 68zm0-384v192q0 40-28 68t-68 28H480q-40 0-68-28t-28-68V384q0-40 28-68t68-28h832q40 0 68 28t28 68zm0-384v192q0 40-28 68t-68 28H480q-40 0-68-28t-28-68V0q0-40 28-68t68-28h832q40 0 68 28t28 68z',
              transform: 'matrix(1 0 0 -1 0 1792)',
            },
            click: () => {
              this.toggleColorbar()
            },
          },
        ],
        scrollZoom: true,
        responsive: true,
      }
    },

    setupPlotEventHandlers() {
      const plotElement = document.getElementById(this.id) as any
      if (!plotElement) return

      // Handle zoom/pan events
      plotElement.on('plotly_relayout', (eventData: any) => {
        if (eventData['xaxis.autorange']) {
          // Reset zoom
          this.zoomRange = {
            xRange: [-1, -1],
            yRange: [-1, -1],
          }
        } else if (
          eventData['xaxis.range[0]'] !== undefined &&
          eventData['xaxis.range[1]'] !== undefined &&
          eventData['yaxis.range[0]'] !== undefined &&
          eventData['yaxis.range[1]'] !== undefined
        ) {
          this.zoomRange = {
            xRange: [eventData['xaxis.range[0]'], eventData['xaxis.range[1]']],
            yRange: [eventData['yaxis.range[0]'], eventData['yaxis.range[1]']],
          }
        }
      })

      // Handle click events
      plotElement.on('plotly_click', (eventData: any) => {
        if (!this.interactivity || Object.keys(this.interactivity).length === 0) {
          return
        }

        if (eventData.points && eventData.points.length > 0) {
          const pointIndex = eventData.points[0].pointIndex
          const pointData = this.heatmapData[pointIndex]

          if (pointData) {
            // Update selection store for each interactivity mapping
            for (const [identifier, column] of Object.entries(this.interactivity)) {
              const value = pointData[column]
              if (value !== undefined) {
                this.selectionStore.updateSelection(identifier, value)
              }
            }
          }
        }
      })
    },

    async toggleColorbar() {
      this.colorbarVisible = !this.colorbarVisible
      this.userOverrideColorbar = true
      await this.updatePlot()
    },

    async updatePlot() {
      const plotElement = document.getElementById(this.id) as any
      if (plotElement) {
        try {
          await Plotly.restyle(plotElement, {
            'marker.showscale': this.effectiveColorbarVisible,
          }, [0])

          await Plotly.relayout(plotElement, {
            margin: {
              r: this.effectiveColorbarVisible ? 120 : 20,
            },
          })
        } catch (error) {
          // Silently handle errors
        }
      }
    },

    setupResizeObserver() {
      const plotElement = document.getElementById(this.id)
      if (plotElement && window.ResizeObserver) {
        this.resizeObserver = new ResizeObserver((entries) => {
          for (const entry of entries) {
            const newWidth = entry.contentRect.width
            if (Math.abs(newWidth - this.plotWidth) > 10) {
              const wasNarrow = this.isNarrowPlot
              this.plotWidth = newWidth
              const isNowNarrow = this.isNarrowPlot

              if (wasNarrow !== isNowNarrow && !this.userOverrideColorbar) {
                this.colorbarVisible = !isNowNarrow
                this.updatePlot()
              }
            }
          }
        })
        this.resizeObserver.observe(plotElement)
      }
    },

    cleanupResizeObserver() {
      if (this.resizeObserver) {
        this.resizeObserver.disconnect()
        this.resizeObserver = null
      }
    },

    getFallbackData(): Plotly.Data[] {
      return [
        {
          type: 'scattergl',
          x: [0],
          y: [0],
          mode: 'markers',
          marker: { color: 'grey' },
          name: 'No Data',
        },
      ]
    },

    async renderFallback(): Promise<void> {
      try {
        const fallbackLayout: Partial<Plotly.Layout> = {
          title: { text: '<b>No Data Available</b>' },
          showlegend: false,
          xaxis: { title: { text: 'X' } },
          yaxis: { title: { text: 'Y' } },
          paper_bgcolor: this.theme?.backgroundColor || 'white',
          plot_bgcolor: this.theme?.secondaryBackgroundColor || '#f5f5f5',
          font: {
            color: this.theme?.textColor || 'black',
            family: this.theme?.font || 'Arial',
          },
        }

        await Plotly.newPlot(this.id, this.getFallbackData(), fallbackLayout, {
          staticPlot: true,
        })
      } catch (error) {
        console.error('PlotlyHeatmap: Failed to render fallback:', error)
      }
    },
  },
})
</script>

<style scoped>
.heatmap-container {
  position: relative;
  width: 100%;
  min-height: 400px;
}
</style>
