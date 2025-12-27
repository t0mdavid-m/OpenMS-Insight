<template>
  <div :id="id" class="heatmap-container"></div>
</template>

<script lang="ts">
import { defineComponent, computed, type PropType } from 'vue'
import Plotly from 'plotly.js-dist-min'
import { useStreamlitDataStore } from '@/stores/streamlit-data'
import { usePlotlyScatter } from '@/composables/usePlotlyScatter'
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
  setup(props) {
    const streamlitDataStore = useStreamlitDataStore()

    // Use shared Plotly scatter composable
    const plotlyScatter = usePlotlyScatter({
      id: computed(() => `heatmap-${props.index}`),
      interactivity: computed(() => props.args.interactivity || {}),
      getData: () => {
        const data = streamlitDataStore.allDataForDrawing?.heatmapData
        return (data as HeatmapData[]) || []
      },
      title: computed(() => props.args.title),
    })

    return {
      streamlitDataStore,
      ...plotlyScatter,
    }
  },
  data() {
    return {
      isInitialized: false as boolean,
      zoomRange: undefined as { xRange: number[]; yRange: number[] } | undefined,
      colorbarVisible: true,
      userOverrideColorbar: false,
      heatmapResizeObserver: null as ResizeObserver | null,
    }
  },
  computed: {
    id(): string {
      return `heatmap-${this.index}`
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
     * Check if categorical coloring mode is enabled.
     */
    isCategoricalMode(): boolean {
      return !!this.args.categoryColumn
    },

    /**
     * Get category values from data (when in categorical mode).
     */
    categoryValues(): (string | number)[] {
      if (!this.isDataReady || !this.args.categoryColumn) return []
      return this.heatmapData.map((row) => row[this.args.categoryColumn!] as string | number)
    },

    /**
     * Get unique categories for building separate traces.
     */
    uniqueCategories(): (string | number)[] {
      if (!this.isCategoricalMode) return []
      const seen = new Set<string | number>()
      const unique: (string | number)[] = []
      for (const cat of this.categoryValues) {
        if (!seen.has(cat)) {
          seen.add(cat)
          unique.push(cat)
        }
      }
      return unique
    },

    /**
     * Default color palette for categorical mode.
     * Uses Plotly's qualitative color palette.
     */
    defaultCategoryColors(): string[] {
      return [
        '#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd',
        '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf',
      ]
    },

    /**
     * Get color for a specific category value.
     */
    getCategoryColor(): (category: string | number) => string {
      const customColors = this.args.categoryColors || {}
      const defaults = this.defaultCategoryColors
      let colorIndex = 0

      return (category: string | number): string => {
        const key = String(category)
        if (customColors[key]) {
          return customColors[key]
        }
        // Use default colors in order
        const idx = this.uniqueCategories.indexOf(category)
        return defaults[idx % defaults.length]
      }
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
     * Build Plotly data trace(s).
     * In categorical mode, creates separate traces per category.
     * In continuous mode, creates a single trace with colorscale.
     */
    data(): Plotly.Data[] {
      if (!this.isDataReady) {
        return this.getFallbackData()
      }

      // Categorical mode: create separate traces per category
      if (this.isCategoricalMode) {
        return this.buildCategoricalTraces()
      }

      // Continuous mode: single trace with colorscale
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
      // In categorical mode, show legend instead of colorbar
      const showLegend = this.isCategoricalMode
      // Use extra right margin for colorbar (continuous) or legend (categorical)
      const needsExtraRightMargin = this.isCategoricalMode || this.effectiveColorbarVisible

      return {
        ...this.themeLayout,
        title: this.args.title ? { text: `<b>${this.args.title}</b>` } : undefined,
        showlegend: showLegend,
        legend: showLegend
          ? {
              x: 1.02,
              y: 1,
              xanchor: 'left',
              yanchor: 'top',
              bgcolor: 'rgba(255, 255, 255, 0.8)',
              bordercolor: '#ccc',
              borderwidth: 1,
            }
          : undefined,
        height: this.args.height || 400,
        xaxis: {
          title: this.args.xLabel ? { text: this.args.xLabel } : undefined,
          range: this.xRange,
        },
        yaxis: {
          title: this.args.yLabel ? { text: this.args.yLabel } : undefined,
          range: this.yRange,
        },
        margin: {
          l: 60,
          r: needsExtraRightMargin ? 120 : 20,
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
      this.setupHeatmapResizeObserver()
    })
  },

  beforeUnmount() {
    this.cleanupHeatmapResizeObserver()
  },

  methods: {
    /**
     * Build separate traces for each category.
     * Each category gets its own color and appears in the legend.
     */
    buildCategoricalTraces(): Plotly.Data[] {
      const getColor = this.getCategoryColor
      const traces: Plotly.Data[] = []

      for (const category of this.uniqueCategories) {
        // Get indices of points belonging to this category
        const indices: number[] = []
        for (let i = 0; i < this.categoryValues.length; i++) {
          if (this.categoryValues[i] === category) {
            indices.push(i)
          }
        }

        // Extract x, y, and hovertext for this category
        const x = indices.map((i) => this.xValues[i])
        const y = indices.map((i) => this.yValues[i])
        const hovertext = indices.map((i) => this.intensityValues[i].toExponential(2))

        traces.push({
          type: 'scattergl',
          name: String(category),
          x,
          y,
          mode: 'markers',
          marker: {
            color: getColor(category),
            size: 6,
          },
          hovertext,
          hoverinfo: 'x+y+text',
        } as Plotly.Data)
      }

      return traces
    },

    async renderPlot(): Promise<void> {
      try {
        const element = document.getElementById(this.id)
        if (!element) {
          console.warn(`PlotlyHeatmap: DOM element with id '${this.id}' not found`)
          return
        }

        await Plotly.newPlot(this.id, this.data, this.layout, this.getHeatmapPlotConfig())
        this.setupPlotEventHandlers()

        // Update Streamlit iframe height after plot is rendered
        this.$nextTick(() => {
          this.updateFrameHeight()
        })
      } catch (error) {
        console.error('PlotlyHeatmap: Error rendering plot:', error)
        this.renderFallback()
      }
    },

    getHeatmapPlotConfig(): Partial<Plotly.Config> {
      // Use base config from composable with additional colorbar toggle button
      const colorbarToggleButton: Plotly.ModeBarButton = {
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
      }
      return this.getPlotConfig([colorbarToggleButton])
    },

    setupPlotEventHandlers() {
      const plotElement = document.getElementById(this.id) as Plotly.PlotlyHTMLElement | null
      if (!plotElement) return

      // Handle zoom/pan events (heatmap-specific)
      plotElement.on('plotly_relayout', (eventData: Plotly.PlotRelayoutEvent) => {
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
            xRange: [
              eventData['xaxis.range[0]'] as number,
              eventData['xaxis.range[1]'] as number,
            ],
            yRange: [
              eventData['yaxis.range[0]'] as number,
              eventData['yaxis.range[1]'] as number,
            ],
          }
        }
      })

      // Handle click events via composable
      this.setupClickHandler()
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

    setupHeatmapResizeObserver() {
      const plotElement = document.getElementById(this.id)
      if (plotElement && window.ResizeObserver) {
        this.heatmapResizeObserver = new ResizeObserver((entries) => {
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
        this.heatmapResizeObserver.observe(plotElement)
      }
    },

    cleanupHeatmapResizeObserver() {
      if (this.heatmapResizeObserver) {
        this.heatmapResizeObserver.disconnect()
        this.heatmapResizeObserver = null
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
          ...this.themeLayout,
          title: { text: '<b>No Data Available</b>' },
          showlegend: false,
          xaxis: { title: { text: 'X' } },
          yaxis: { title: { text: 'Y' } },
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
