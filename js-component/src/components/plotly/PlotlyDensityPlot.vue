<template>
  <div :id="id" class="density-container"></div>
</template>

<script lang="ts">
import { defineComponent, type PropType } from 'vue'
import Plotly from 'plotly.js-dist-min'
import { Streamlit, type Theme } from 'streamlit-component-lib'
import { useStreamlitDataStore } from '@/stores/streamlit-data'
import type { DensityPlotComponentArgs } from '@/types/component'

const DEFAULT_TARGET_COLOR = 'green'
const DEFAULT_DECOY_COLOR = 'red'
const DEFAULT_HEIGHT = 400

/**
 * Two-series target/decoy KDE (FDR) plot.
 *
 * Reads a precomputed tidy long {x, y, group} frame from
 * `allDataForDrawing.plotData` (column-parsed, like PlotlyLineplot), splits it
 * by `group` into a target (green) and decoy (red) `lines+markers` trace, and
 * draws two continuous density curves. Legend on; no selection / zoom-state /
 * stick machinery. The decoy trace is dropped when it has zero rows (parity with
 * FLASHApp's empty `density_decoy`). No KDE is computed in Vue — Python (or the
 * caller) produces the curves. Reproduces oracle FDR_plotly.vue, themed.
 */
export default defineComponent({
  name: 'PlotlyDensityPlot',
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
  setup() {
    const streamlitDataStore = useStreamlitDataStore()
    return { streamlitDataStore }
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
    theme(): Theme | undefined {
      return this.streamlitDataStore.theme
    },
    scoreLabel(): string {
      return this.args.scoreLabel || 'QScore'
    },
    targetColor(): string {
      return this.args.styling?.targetColor || DEFAULT_TARGET_COLOR
    },
    decoyColor(): string {
      return this.args.styling?.decoyColor || DEFAULT_DECOY_COLOR
    },
    /**
     * Raw column arrays {x:[…], y:[…], group:[…]} from Python (Arrow-parsed).
     */
    rawData(): Record<string, unknown[]> | undefined {
      return this.streamlitDataStore.allDataForDrawing?.plotData as
        | Record<string, unknown[]>
        | undefined
    },
    /**
     * Split the tidy frame into target/decoy {x, y} series by `group`.
     */
    series(): {
      target: { x: number[]; y: number[] }
      decoy: { x: number[]; y: number[] }
    } {
      const empty = {
        target: { x: [] as number[], y: [] as number[] },
        decoy: { x: [] as number[], y: [] as number[] },
      }
      const data = this.rawData
      if (!data) return empty

      const xCol = this.args.xColumn || 'x'
      const yCol = this.args.yColumn || 'y'
      const groupCol = this.args.groupColumn || 'group'

      const xs = (data[xCol] as number[]) || []
      const ys = (data[yCol] as number[]) || []
      const groups = (data[groupCol] as unknown[]) || []

      for (let i = 0; i < groups.length; i++) {
        const g = groups[i]
        if (g === this.args.targetValue) {
          empty.target.x.push(xs[i])
          empty.target.y.push(ys[i])
        } else if (g === this.args.decoyValue) {
          empty.decoy.x.push(xs[i])
          empty.decoy.y.push(ys[i])
        }
      }
      return empty
    },
    traces(): Plotly.Data[] {
      const { target, decoy } = this.series
      const traces: Plotly.Data[] = [
        {
          x: target.x,
          y: target.y,
          mode: 'lines+markers',
          type: 'scatter',
          name: `${this.scoreLabel} (Target)`,
          marker: { color: this.targetColor },
          line: { color: this.targetColor },
        },
      ]
      // Drop the decoy trace entirely when empty (parity with empty density_decoy).
      if (decoy.x.length > 0) {
        traces.push({
          x: decoy.x,
          y: decoy.y,
          mode: 'lines+markers',
          type: 'scatter',
          name: `${this.scoreLabel} (Decoy)`,
          marker: { color: this.decoyColor },
          line: { color: this.decoyColor },
        })
      }
      return traces
    },
    layout(): Partial<Plotly.Layout> {
      return {
        title: this.args.title ? { text: `<b>${this.args.title}</b>` } : undefined,
        showlegend: true,
        height: this.args.height || DEFAULT_HEIGHT,
        xaxis: {
          title: { text: this.args.xLabel || 'QScore' },
          showgrid: false,
          showline: true,
          linecolor: 'grey',
          linewidth: 1,
        },
        yaxis: {
          title: { text: this.args.yLabel || 'Density' },
          showgrid: true,
          gridcolor: this.theme?.secondaryBackgroundColor || '#f0f0f0',
          rangemode: 'nonnegative',
          fixedrange: true,
          showline: true,
          linecolor: 'grey',
          linewidth: 1,
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
  },
  watch: {
    'streamlitDataStore.allDataForDrawing.plotData': {
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
      this.renderPlot()
    })
  },
  methods: {
    async renderPlot(): Promise<void> {
      const element = document.getElementById(this.id)
      if (!element) return

      const filename = this.args.title || 'FDR-plot'
      await Plotly.newPlot(this.id, this.traces, this.layout, {
        modeBarButtonsToRemove: ['toImage', 'sendDataToCloud'],
        modeBarButtonsToAdd: [
          {
            title: 'Download as SVG',
            name: 'toImageSvg',
            icon: Plotly.Icons.camera,
            click: (plotlyElement: unknown) => {
              Plotly.downloadImage(plotlyElement as Plotly.PlotlyHTMLElement, {
                filename,
                height: DEFAULT_HEIGHT,
                width: 1200,
                format: 'svg',
              })
            },
          },
        ],
        responsive: true,
      })

      this.$nextTick(() => {
        if (this.args.height) {
          Streamlit.setFrameHeight(this.args.height)
        } else {
          Streamlit.setFrameHeight()
        }
      })
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
