<template>
  <div :id="id" class="density-container"></div>
</template>

<script lang="ts">
import { defineComponent, type PropType } from 'vue'
import Plotly from 'plotly.js-dist-min'
import { useStreamlitDataStore } from '@/stores/streamlit-data'
import { Streamlit } from 'streamlit-component-lib'
import type { DensityPlotComponentArgs, DensityData } from '@/types/component'

/**
 * PlotlyDensity — static dual-KDE score-distribution plot.
 *
 * Port of FLASHApp's FDRPlotly (FDR_plotly.vue). Renders two lines+markers
 * scatter traces: Target (green) and Decoy (red). The x-axis is labelled
 * "QScore" and the y-axis "Density" (nonnegative, fixedrange) on every workflow,
 * matching the FLASHApp original exactly. SVG export button writes "FDR-plot".
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
    xColumn(): string {
      return this.args.xColumn || 'x'
    },
    yColumn(): string {
      return this.args.yColumn || 'y'
    },
    targetRows(): DensityData[] {
      const data = this.streamlitDataStore.allDataForDrawing?.densityTarget
      return (data as DensityData[]) || []
    },
    decoyRows(): DensityData[] {
      const data = this.streamlitDataStore.allDataForDrawing?.densityDecoy
      return (data as DensityData[]) || []
    },
    xValuesTarget(): number[] {
      return this.targetRows.map((r) => Number(r[this.xColumn]))
    },
    yValuesTarget(): number[] {
      return this.targetRows.map((r) => Number(r[this.yColumn]))
    },
    xValuesDecoy(): number[] {
      return this.decoyRows.map((r) => Number(r[this.xColumn]))
    },
    yValuesDecoy(): number[] {
      return this.decoyRows.map((r) => Number(r[this.yColumn]))
    },
    layout(): Partial<Plotly.Layout> {
      return {
        title: { text: `<b>${this.args.title ?? ''}</b>` },
        showlegend: true,
        height: this.args.height || 400,
        xaxis: {
          title: { text: this.args.xLabel || 'QScore' },
          showgrid: false,
        },
        yaxis: {
          title: { text: this.args.yLabel || 'Density' },
          showgrid: true,
          rangemode: 'nonnegative',
          fixedrange: true,
        },
        paper_bgcolor: 'white',
        plot_bgcolor: 'white',
        font: {
          color: 'black',
          family: 'Arial',
        },
      }
    },
    data(): Plotly.Data[] {
      return [
        {
          x: this.xValuesTarget,
          y: this.yValuesTarget,
          mode: 'lines+markers',
          type: 'scatter',
          name: this.args.targetName || 'Target QScores',
          marker: { color: this.args.targetColor || 'green' },
        },
        {
          x: this.xValuesDecoy,
          y: this.yValuesDecoy,
          mode: 'lines+markers',
          type: 'scatter',
          name: this.args.decoyName || 'Decoy QScores',
          marker: { color: this.args.decoyColor || 'red' },
        },
      ]
    },
  },
  watch: {
    'streamlitDataStore.allDataForDrawing.densityTarget': {
      handler() {
        if (this.isInitialized) {
          this.graph()
        }
      },
      deep: true,
    },
    'streamlitDataStore.allDataForDrawing.densityDecoy': {
      handler() {
        if (this.isInitialized) {
          this.graph()
        }
      },
      deep: true,
    },
  },
  mounted() {
    this.isInitialized = true
    this.$nextTick(() => {
      this.graph()
    })
  },
  methods: {
    async graph(): Promise<void> {
      const element = document.getElementById(this.id)
      if (!element) {
        console.warn(`PlotlyDensity: DOM element with id '${this.id}' not found`)
        return
      }
      await Plotly.newPlot(this.id, this.data, this.layout, {
        modeBarButtonsToRemove: ['toImage', 'sendDataToCloud'],
        modeBarButtonsToAdd: [
          {
            title: 'Download as SVG',
            name: 'toImageSvg',
            icon: Plotly.Icons.camera,
            click: (plotlyElement: Plotly.PlotlyHTMLElement) => {
              Plotly.downloadImage(plotlyElement, {
                filename: 'FDR-plot',
                height: 400,
                width: 1200,
                format: 'svg',
              })
            },
          },
        ],
      })
      this.$nextTick(() => {
        Streamlit.setFrameHeight(this.args.height || 400)
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
