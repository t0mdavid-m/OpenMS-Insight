<template>
  <div :id="id" class="density-container"></div>
</template>

<script lang="ts">
import { defineComponent, computed, type PropType } from 'vue'
import Plotly from 'plotly.js-dist-min'
import { useStreamlitDataStore } from '@/stores/streamlit-data'
import { usePlotlyScatter } from '@/composables/usePlotlyScatter'
import type { DensityPlotComponentArgs, DensityData, DensitySeries } from '@/types/component'

/**
 * PlotlyDensity — kernel-density-estimate curves (e.g. target vs decoy FDR).
 *
 * Data arrives in long format from Python (one row per (series, grid point)):
 *   { series: string, x: number, y: number }
 * The densities are precomputed in Python (scipy.gaussian_kde), so this
 * component only groups rows by series and draws one line trace each. It is a
 * static plot: no click/zoom interactivity is wired.
 */
export default defineComponent({
  name: 'PlotlyDensity',
  props: {
    args: {
      type: Object as PropType<DensityPlotComponentArgs>,
      required: true,
    },
    index: {
      type: Number,
      required: true,
    },
  },
  setup(props) {
    const streamlitDataStore = useStreamlitDataStore()

    // Reuse the shared scatter composable for theme + resize + SVG export.
    // No interactivity mapping (static plot), so click handling is a no-op.
    const plotlyScatter = usePlotlyScatter({
      id: computed(() => `density-${props.index}`),
      interactivity: computed(() => ({})),
      getData: () => {
        const data = streamlitDataStore.allDataForDrawing?.densityData
        return (data as DensityData[]) || []
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
    }
  },
  computed: {
    id(): string {
      return `density-${this.index}`
    },

    densityData(): DensityData[] {
      const data = this.streamlitDataStore.allDataForDrawing?.densityData
      return (data as DensityData[]) || []
    },

    isDataReady(): boolean {
      return Array.isArray(this.densityData) && this.densityData.length > 0
    },

    /**
     * Ordered series presentation from Python args. If absent, derive a stable
     * order from the data itself (first-seen) with default colors.
     */
    series(): DensitySeries[] {
      if (Array.isArray(this.args.series) && this.args.series.length > 0) {
        return this.args.series
      }
      // Fallback: derive from data with a default palette.
      const palette = ['green', 'red', '#3366CC', '#FF9900', '#990099', '#0099C6']
      const seen: string[] = []
      this.densityData.forEach((row) => {
        const name = String(row.series)
        if (!seen.includes(name)) seen.push(name)
      })
      return seen.map((name, idx) => ({
        name,
        label: name,
        color: palette[idx % palette.length],
      }))
    },

    /**
     * Build one Plotly line trace per configured series, in series order.
     */
    plotData(): Plotly.Data[] {
      if (!this.isDataReady) {
        return this.getFallbackData()
      }

      const mode = this.args.showMarkers === false ? 'lines' : 'lines+markers'

      // Group rows by series value once.
      const bySeries = new Map<string, { x: number[]; y: number[] }>()
      this.densityData.forEach((row) => {
        const name = String(row.series)
        const x = Number(row.x)
        const y = Number(row.y)
        if (!Number.isFinite(x) || !Number.isFinite(y)) return
        if (!bySeries.has(name)) bySeries.set(name, { x: [], y: [] })
        const entry = bySeries.get(name)!
        entry.x.push(x)
        entry.y.push(y)
      })

      const traces: Plotly.Data[] = []
      this.series.forEach((s) => {
        const entry = bySeries.get(s.name)
        if (!entry || entry.x.length === 0) return
        traces.push({
          x: entry.x,
          y: entry.y,
          mode,
          type: 'scatter',
          name: s.label,
          marker: { color: s.color },
          line: { color: s.color },
        })
      })

      // Include any series present in data but absent from config order.
      const known = new Set(this.series.map((s) => s.name))
      bySeries.forEach((entry, name) => {
        if (known.has(name) || entry.x.length === 0) return
        traces.push({
          x: entry.x,
          y: entry.y,
          mode,
          type: 'scatter',
          name,
        })
      })

      return traces
    },

    layout(): Partial<Plotly.Layout> {
      return {
        ...this.themeLayout,
        title: this.args.title ? { text: `<b>${this.args.title}</b>` } : undefined,
        showlegend: true,
        height: this.args.height || 400,
        xaxis: {
          title: { text: this.args.xLabel || 'Value' },
          showgrid: false,
        },
        yaxis: {
          title: { text: this.args.yLabel || 'Density' },
          showgrid: true,
          rangemode: 'nonnegative',
          fixedrange: true,
        },
        margin: {
          l: 60,
          r: 20,
          t: this.args.title ? 80 : 40,
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

    'streamlitDataStore.allDataForDrawing.densityData': {
      handler() {
        if (this.isInitialized) {
          this.renderPlot()
        }
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
          console.warn(`PlotlyDensity: DOM element with id '${this.id}' not found`)
          return
        }
        await Plotly.newPlot(this.id, this.plotData, this.layout, this.getPlotConfig())
        this.$nextTick(() => {
          this.updateFrameHeight()
        })
      } catch (error) {
        console.error('PlotlyDensity: Error rendering plot:', error)
        this.renderFallback()
      }
    },

    getFallbackData(): Plotly.Data[] {
      return [
        {
          x: [0],
          y: [0],
          mode: 'lines',
          type: 'scatter',
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
          xaxis: { title: { text: this.args.xLabel || 'Value' } },
          yaxis: { title: { text: this.args.yLabel || 'Density' } },
        }
        await Plotly.newPlot(this.id, this.getFallbackData(), fallbackLayout, {
          staticPlot: true,
        })
      } catch (error) {
        console.error('PlotlyDensity: Failed to render fallback:', error)
      }
    },
  },
})
</script>

<style scoped>
.density-container {
  position: relative;
  width: 100%;
  min-height: 100px;
}
</style>
