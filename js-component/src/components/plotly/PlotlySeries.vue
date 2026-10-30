<template>
  <div :id="id" class="plot-container"></div>
</template>

<script lang="ts">
import { defineComponent, type PropType } from 'vue'
import Plotly from 'plotly.js-dist-min'
import { Streamlit, type Theme } from 'streamlit-component-lib'
import { useStreamlitDataStore } from '@/stores/streamlit-data'
import { useSelectionStore } from '@/stores/selection'
import type { SeriesPlotComponentArgs } from '@/types/component'

const SVG_ICON = {
  width: 1792,
  height: 1792,
  path: 'M1152 1376v-160q0-14-9-23t-23-9h-96v-512q0-14-9-23t-23-9h-320q-14 0-23 9t-9 23v160q0 14 9 23t23 9h96v320h-96q-14 0-23 9t-9 23v160q0 14 9 23t23 9h320q14 0 23-9t9-23zm-128-896v-160q0-14-9-23t-23-9h-192q-14 0-23 9t-9 23v160q0 14 9 23t23 9h192q14 0 23-9t9-23zm640 416q0 209-103 385.5t-279.5 279.5-385.5 103-385.5-103-279.5-279.5-103-385.5 103-385.5 279.5-279.5 385.5-103 385.5 103 279.5 279.5 103 385.5z',
}

let plotIdCounter = 0

export default defineComponent({
  name: 'PlotlySeries',
  props: {
    args: {
      type: Object as PropType<SeriesPlotComponentArgs>,
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
    return { streamlitDataStore, selectionStore, uniqueId: `series-plot-${++plotIdCounter}` }
  },
  data() {
    return {
      drawPending: false,
    }
  },
  computed: {
    argsKey(): string {
      return JSON.stringify(this.args)
    },
    id(): string {
      return this.uniqueId
    },
    theme(): Theme | undefined {
      return this.streamlitDataStore.theme
    },
    columns(): Record<string, unknown[]> {
      return (this.streamlitDataStore.allDataForDrawing?.plotData as Record<string, unknown[]>) || {}
    },
    /** Points grouped by series, in series_names order then order of appearance. */
    series(): Array<{ key: string; name: string; x: number[]; y: number[]; rows: number[] }> {
      const xs = (this.columns[this.args.xColumn] as number[]) || []
      const ys = (this.columns[this.args.yColumn] as number[]) || []
      const seriesColumn = this.args.seriesColumn
      const seriesValues = seriesColumn ? (this.columns[seriesColumn] as unknown[]) || [] : []
      const names = new Map<string, string>((this.args.seriesNames || []).map(([k, v]) => [String(k), v]))

      const groups = new Map<string, { key: string; name: string; x: number[]; y: number[]; rows: number[] }>()
      for (const key of names.keys()) {
        groups.set(key, { key, name: names.get(key) as string, x: [], y: [], rows: [] })
      }
      for (let i = 0; i < xs.length; i++) {
        const key = seriesColumn ? String(seriesValues[i]) : ''
        if (!groups.has(key)) {
          groups.set(key, { key, name: names.get(key) ?? key, x: [], y: [], rows: [] })
        }
        const group = groups.get(key)!
        group.x.push(xs[i])
        group.y.push(ys[i])
        group.rows.push(i)
      }
      return [...groups.values()]
    },
    traces(): Plotly.Data[] {
      const colors = this.args.seriesColors || {}
      return this.series.map((s) => {
        const trace: Record<string, unknown> = {
          x: s.x,
          y: s.y,
          mode: this.args.mode || 'lines+markers',
          type: 'scatter',
          name: s.name,
        }
        const color = colors[s.key]
        if (color) {
          trace.marker = { color }
          trace.line = { color }
        }
        return trace as Plotly.Data
      })
    },
    layout(): Partial<Plotly.Layout> {
      return {
        title: this.args.title ? { text: `<b>${this.args.title}</b>` } : undefined,
        showlegend: this.args.showLegend !== false,
        height: this.args.height || 400,
        xaxis: {
          title: this.args.xLabel ? { text: this.args.xLabel } : undefined,
          showgrid: false,
        },
        yaxis: {
          title: this.args.yLabel ? { text: this.args.yLabel } : undefined,
          showgrid: true,
          rangemode: 'nonnegative',
          fixedrange: !!this.args.fixedYRange,
        },
        paper_bgcolor: this.theme?.backgroundColor || 'white',
        plot_bgcolor: this.theme?.backgroundColor || 'white',
        font: {
          color: this.theme?.textColor || 'black',
          family: this.theme?.font || 'Arial',
          ...(this.args.font || {}),
        },
      }
    },
  },
  watch: {
    'streamlitDataStore.allDataForDrawing.plotData': {
      handler() {
        this.requestRender()
      },
      deep: true,
    },
    // By value: the arguments arrive as a new object on every rerun
    argsKey() {
      this.requestRender()
    },
  },
  mounted() {
    this.requestRender()
  },
  methods: {
    /** Draw once per tick: one update often changes several watched values
     * (the data and the selection), and each drawing costs a full Plotly render. */
    requestRender(): void {
      if (this.drawPending) return
      this.drawPending = true
      this.$nextTick(() => {
        this.drawPending = false
        this.renderPlot()
      })
    },
    async renderPlot(): Promise<void> {
      const element = document.getElementById(this.id)
      if (!element) return
      await Plotly.newPlot(element, this.traces, this.layout, {
        modeBarButtonsToRemove: ['toImage', 'sendDataToCloud'],
        modeBarButtonsToAdd: [
          {
            title: 'Download as SVG',
            name: 'toImageSvg',
            icon: SVG_ICON,
            click: (plotElement: HTMLElement) => {
              Plotly.downloadImage(plotElement, {
                filename: this.args.svgFilename || this.args.title || 'plot',
                height: this.args.height || 400,
                width: 1200,
                format: 'svg',
              })
            },
          },
        ],
        responsive: true,
      })
      const plotElement = element as unknown as {
        on: (event: string, handler: (data: { points: Array<{ curveNumber: number; pointIndex: number }> }) => void) => void
      }
      plotElement.on('plotly_click', (eventData) => this.onClick(eventData))
      this.$nextTick(() => Streamlit.setFrameHeight())
    },
    onClick(eventData: { points: Array<{ curveNumber: number; pointIndex: number }> }): void {
      const interactivity = this.args.interactivity || {}
      if (Object.keys(interactivity).length === 0 || !eventData.points?.length) return
      const point = eventData.points[0]
      const row = this.series[point.curveNumber]?.rows[point.pointIndex]
      if (row === undefined) return
      for (const [identifier, column] of Object.entries(interactivity)) {
        const values = this.columns[column] as unknown[] | undefined
        // Skip no-op writes (see ProteinSequenceView)
        if (values && this.selectionStore.$state[identifier] !== values[row]) {
          this.selectionStore.updateSelection(identifier, values[row])
        }
      }
    },
  },
})
</script>

<style scoped>
.plot-container {
  width: 100%;
}
</style>
