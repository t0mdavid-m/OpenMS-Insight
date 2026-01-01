<template>
  <div :id="id" class="volcano-container"></div>
</template>

<script lang="ts">
import { defineComponent, computed, type PropType } from 'vue'
import Plotly from 'plotly.js-dist-min'
import { useStreamlitDataStore } from '@/stores/streamlit-data'
import { usePlotlyScatter } from '@/composables/usePlotlyScatter'
import type { VolcanoPlotComponentArgs, VolcanoData } from '@/types/component'

/**
 * Compute significance category for a point.
 * Up-regulated: p < pThreshold AND log2fc >= fcThreshold
 * Down-regulated: p < pThreshold AND log2fc <= -fcThreshold
 * Not significant: otherwise
 */
function computeSignificance(
  log2fc: number,
  pvalue: number,
  fcThreshold: number,
  pThreshold: number
): 'up' | 'down' | 'ns' {
  if (pvalue >= pThreshold) return 'ns'
  if (log2fc >= fcThreshold) return 'up'
  if (log2fc <= -fcThreshold) return 'down'
  return 'ns'
}

export default defineComponent({
  name: 'PlotlyVolcano',
  props: {
    args: {
      type: Object as PropType<VolcanoPlotComponentArgs>,
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
      id: computed(() => `volcano-${props.index}`),
      interactivity: computed(() => props.args.interactivity || {}),
      getData: () => {
        const data = streamlitDataStore.allDataForDrawing?.volcanoData
        return (data as VolcanoData[]) || []
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
      return `volcano-${this.index}`
    },

    /**
     * Get volcano data from Python.
     */
    volcanoData(): VolcanoData[] {
      const data = this.streamlitDataStore.allDataForDrawing?.volcanoData
      return (data as VolcanoData[]) || []
    },

    /**
     * Check if data is ready for rendering.
     */
    isDataReady(): boolean {
      return Array.isArray(this.volcanoData) && this.volcanoData.length > 0
    },

    /**
     * Threshold values from args.
     */
    fcThreshold(): number {
      return this.args.fcThreshold ?? 1.0
    },

    pThreshold(): number {
      return this.args.pThreshold ?? 0.05
    },

    /**
     * -log10(pThreshold) for threshold line.
     */
    neglog10PThreshold(): number {
      return this.pThreshold > 0 ? -Math.log10(this.pThreshold) : 0
    },

    /**
     * Categorize points by significance.
     */
    categorizedData(): {
      up: { x: number[]; y: number[]; text: string[]; indices: number[] }
      down: { x: number[]; y: number[]; text: string[]; indices: number[] }
      ns: { x: number[]; y: number[]; text: string[]; indices: number[] }
    } {
      const up = { x: [] as number[], y: [] as number[], text: [] as string[], indices: [] as number[] }
      const down = { x: [] as number[], y: [] as number[], text: [] as string[], indices: [] as number[] }
      const ns = { x: [] as number[], y: [] as number[], text: [] as string[], indices: [] as number[] }

      const log2fcCol = this.args.log2fcColumn
      const neglog10pCol = this.args.neglog10pColumn
      const pvalueCol = this.args.pvalueColumn
      const labelCol = this.args.labelColumn

      this.volcanoData.forEach((row, idx) => {
        const log2fc = Number(row[log2fcCol]) || 0
        const neglog10p = Number(row[neglog10pCol]) || 0
        const pvalue = Number(row[pvalueCol]) || 1
        const label = labelCol ? String(row[labelCol] || '') : ''

        const hoverText = labelCol
          ? `${label}<br>log2FC: ${log2fc.toFixed(3)}<br>p-value: ${pvalue.toExponential(2)}`
          : `log2FC: ${log2fc.toFixed(3)}<br>p-value: ${pvalue.toExponential(2)}`

        const category = computeSignificance(log2fc, pvalue, this.fcThreshold, this.pThreshold)

        if (category === 'up') {
          up.x.push(log2fc)
          up.y.push(neglog10p)
          up.text.push(hoverText)
          up.indices.push(idx)
        } else if (category === 'down') {
          down.x.push(log2fc)
          down.y.push(neglog10p)
          down.text.push(hoverText)
          down.indices.push(idx)
        } else {
          ns.x.push(log2fc)
          ns.y.push(neglog10p)
          ns.text.push(hoverText)
          ns.indices.push(idx)
        }
      })

      return { up, down, ns }
    },

    /**
     * Build Plotly data traces.
     */
    plotData(): Plotly.Data[] {
      if (!this.isDataReady) {
        return this.getFallbackData()
      }

      const { up, down, ns } = this.categorizedData

      const traces: Plotly.Data[] = []

      // Not significant points (render first, behind)
      if (ns.x.length > 0) {
        traces.push({
          type: 'scattergl',
          name: 'Not significant',
          x: ns.x,
          y: ns.y,
          mode: 'markers',
          marker: {
            color: this.args.nsColor || '#95A5A6',
            size: 6,
            opacity: 0.6,
          },
          text: ns.text,
          hoverinfo: 'text',
          customdata: ns.indices,
        })
      }

      // Down-regulated points
      if (down.x.length > 0) {
        traces.push({
          type: 'scattergl',
          name: 'Down-regulated',
          x: down.x,
          y: down.y,
          mode: 'markers',
          marker: {
            color: this.args.downColor || '#3498DB',
            size: 8,
          },
          text: down.text,
          hoverinfo: 'text',
          customdata: down.indices,
        })
      }

      // Up-regulated points (render last, on top)
      if (up.x.length > 0) {
        traces.push({
          type: 'scattergl',
          name: 'Up-regulated',
          x: up.x,
          y: up.y,
          mode: 'markers',
          marker: {
            color: this.args.upColor || '#E74C3C',
            size: 8,
          },
          text: up.text,
          hoverinfo: 'text',
          customdata: up.indices,
        })
      }

      return traces
    },

    /**
     * Build threshold lines (shapes).
     */
    thresholdShapes(): Partial<Plotly.Shape>[] {
      if (!this.args.showThresholdLines) return []

      const lineStyle = this.args.thresholdLineStyle || 'dash'
      const shapes: Partial<Plotly.Shape>[] = []

      // Horizontal line at -log10(pThreshold)
      shapes.push({
        type: 'line',
        xref: 'paper',
        yref: 'y',
        x0: 0,
        x1: 1,
        y0: this.neglog10PThreshold,
        y1: this.neglog10PThreshold,
        line: {
          color: 'rgba(100, 100, 100, 0.5)',
          width: 1.5,
          dash: lineStyle as Plotly.Dash,
        },
      })

      // Vertical line at +fcThreshold
      shapes.push({
        type: 'line',
        xref: 'x',
        yref: 'paper',
        x0: this.fcThreshold,
        x1: this.fcThreshold,
        y0: 0,
        y1: 1,
        line: {
          color: 'rgba(100, 100, 100, 0.5)',
          width: 1.5,
          dash: lineStyle as Plotly.Dash,
        },
      })

      // Vertical line at -fcThreshold
      shapes.push({
        type: 'line',
        xref: 'x',
        yref: 'paper',
        x0: -this.fcThreshold,
        x1: -this.fcThreshold,
        y0: 0,
        y1: 1,
        line: {
          color: 'rgba(100, 100, 100, 0.5)',
          width: 1.5,
          dash: lineStyle as Plotly.Dash,
        },
      })

      return shapes
    },

    /**
     * Build annotations for top significant points.
     */
    pointAnnotations(): Partial<Plotly.Annotations>[] {
      if (!this.args.labelColumn) return []

      const maxLabels = this.args.maxLabels ?? 10
      if (maxLabels <= 0) return []

      const labelCol = this.args.labelColumn
      const log2fcCol = this.args.log2fcColumn
      const neglog10pCol = this.args.neglog10pColumn
      const pvalueCol = this.args.pvalueColumn

      // Get significant points and sort by -log10(p) descending
      const significantPoints: Array<{
        label: string
        log2fc: number
        neglog10p: number
      }> = []

      this.volcanoData.forEach((row) => {
        const log2fc = Number(row[log2fcCol]) || 0
        const pvalue = Number(row[pvalueCol]) || 1
        const neglog10p = Number(row[neglog10pCol]) || 0
        const label = String(row[labelCol] || '')

        const category = computeSignificance(log2fc, pvalue, this.fcThreshold, this.pThreshold)
        if (category !== 'ns' && label) {
          significantPoints.push({ label, log2fc, neglog10p })
        }
      })

      // Sort by significance (most significant first)
      significantPoints.sort((a, b) => b.neglog10p - a.neglog10p)

      // Take top N
      const topPoints = significantPoints.slice(0, maxLabels)

      return topPoints.map((point) => ({
        x: point.log2fc,
        y: point.neglog10p,
        text: point.label,
        showarrow: true,
        arrowhead: 0,
        arrowsize: 0.5,
        arrowwidth: 1,
        arrowcolor: 'rgba(100, 100, 100, 0.5)',
        ax: 0,
        ay: -25,
        font: {
          size: 10,
          color: this.theme?.textColor || 'black',
        },
        bgcolor: 'rgba(255, 255, 255, 0.8)',
        borderpad: 2,
      }))
    },

    /**
     * Build Plotly layout.
     */
    layout(): Partial<Plotly.Layout> {
      return {
        ...this.themeLayout,
        title: this.args.title ? { text: `<b>${this.args.title}</b>` } : undefined,
        showlegend: true,
        legend: {
          orientation: 'h',
          yanchor: 'bottom',
          y: 1.02,
          xanchor: 'right',
          x: 1,
        },
        height: this.args.height || 400,
        xaxis: {
          title: { text: this.args.xLabel || 'log2 Fold Change' },
          zeroline: true,
          zerolinecolor: 'rgba(150, 150, 150, 0.3)',
          zerolinewidth: 1,
        },
        yaxis: {
          title: { text: this.args.yLabel || '-log10(p-value)' },
          rangemode: 'tozero',
        },
        shapes: this.thresholdShapes,
        annotations: this.pointAnnotations,
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

    'streamlitDataStore.allDataForDrawing.volcanoData': {
      handler() {
        if (this.isInitialized) {
          this.renderPlot()
        }
      },
      deep: true,
    },

    // Re-render when thresholds change
    fcThreshold() {
      if (this.isInitialized && this.isDataReady) {
        this.renderPlot()
      }
    },

    pThreshold() {
      if (this.isInitialized && this.isDataReady) {
        this.renderPlot()
      }
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
          console.warn(`PlotlyVolcano: DOM element with id '${this.id}' not found`)
          return
        }

        await Plotly.newPlot(this.id, this.plotData, this.layout, this.getPlotConfig())
        this.setupClickHandler()

        // Update Streamlit iframe height after plot is rendered
        this.$nextTick(() => {
          this.updateFrameHeight()
        })
      } catch (error) {
        console.error('PlotlyVolcano: Error rendering plot:', error)
        this.renderFallback()
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
          xaxis: { title: { text: 'log2 Fold Change' } },
          yaxis: { title: { text: '-log10(p-value)' } },
        }

        await Plotly.newPlot(this.id, this.getFallbackData(), fallbackLayout, {
          staticPlot: true,
        })
      } catch (error) {
        console.error('PlotlyVolcano: Failed to render fallback:', error)
      }
    },
  },
})
</script>

<style scoped>
.volcano-container {
  position: relative;
  width: 100%;
  min-height: 100px;
}
</style>
