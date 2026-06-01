<template>
  <div :id="id" class="scatter3d-container"></div>
</template>

<script lang="ts">
import { defineComponent, type PropType } from 'vue'
import Plotly from 'plotly.js-dist-min'
import type { Theme } from 'streamlit-component-lib'
import { Streamlit } from 'streamlit-component-lib'
import { useStreamlitDataStore } from '@/stores/streamlit-data'
import type { Scatter3DComponentArgs } from '@/types/component'

type PeakRow = Record<string, unknown>

/**
 * Plotly3DScatter — 3D signal/noise stick plot (FLASHApp "Precursor Signals").
 *
 * Consumes long-format peak rows from Python (one row per peak):
 *   { mz, charge, intensity, kind, scan_id, ... }
 * filtered server-side to the selected scan (and optional mass). Each peak is
 * drawn as a vertical stick from the baseline up to its intensity, in two
 * traces: Signal and Noise. Matches the original Plotly3Dplot semantics —
 * x = mass, y = charge, z = intensity, signal #3366CC, noise #DC3912, with an
 * initial mass–intensity camera angle.
 */
export default defineComponent({
  name: 'Plotly3DScatter',
  props: {
    args: {
      type: Object as PropType<Scatter3DComponentArgs>,
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
      maximumIntensity: 0 as number,
      isInitialized: false as boolean,
    }
  },
  computed: {
    id(): string {
      return `scatter3d-${this.index}`
    },
    theme(): Theme | undefined {
      return this.streamlitDataStore.theme
    },
    title(): string {
      return (this.args.title as string) || ''
    },
    mzColumn(): string {
      return (this.args.mzColumn as string) || 'mz'
    },
    chargeColumn(): string {
      return (this.args.chargeColumn as string) || 'charge'
    },
    intensityColumn(): string {
      return (this.args.intensityColumn as string) || 'intensity'
    },
    kindColumn(): string {
      return (this.args.kindColumn as string) || 'kind'
    },
    signalValue(): string {
      return (this.args.signalValue as string) || 'signal'
    },
    noiseValue(): string {
      return (this.args.noiseValue as string) || 'noise'
    },
    signalColor(): string {
      return (this.args.signalColor as string) || '#3366CC'
    },
    noiseColor(): string {
      return (this.args.noiseColor as string) || '#DC3912'
    },
    peaks(): PeakRow[] {
      const data = this.streamlitDataStore.allDataForDrawing?.scatter3dData
      return (data as PeakRow[]) || []
    },
    isDataReady(): boolean {
      return Array.isArray(this.peaks) && this.peaks.length > 0
    },
    data(): Plotly.Data[] {
      if (!this.isDataReady) return []

      const signal = this.buildStickArrays(this.signalValue)
      const noise = this.buildStickArrays(this.noiseValue)

      this.maximumIntensity = Math.max(
        0,
        ...signal.z.filter((v) => v > 0),
        ...noise.z.filter((v) => v > 0)
      )

      return [
        {
          name: 'Signal',
          type: 'scatter3d',
          mode: 'lines',
          x: signal.x,
          y: signal.y,
          z: signal.z,
          line: { color: this.signalColor },
        },
        {
          name: 'Noise',
          type: 'scatter3d',
          mode: 'lines',
          x: noise.x,
          y: noise.y,
          z: noise.z,
          line: { color: this.noiseColor },
        },
      ]
    },
    layout(): Partial<Plotly.Layout> {
      return {
        title: { text: `<b>${this.title}</b>` },
        paper_bgcolor: this.theme?.backgroundColor,
        plot_bgcolor: this.theme?.secondaryBackgroundColor,
        height: (this.args.height as number) || 800,
        font: {
          color: this.theme?.textColor,
          family: this.theme?.font,
        },
        scene: {
          xaxis: { title: { text: (this.args.xLabel as string) || 'Mass' } },
          yaxis: {
            title: { text: (this.args.yLabel as string) || 'Charge' },
            dtick: 1,
            tick0: 0,
          },
          zaxis: {
            title: { text: (this.args.zLabel as string) || 'Intensity' },
            range: [0, this.maximumIntensity],
          },
          camera: {
            // Initial view: mass-intensity plane (matches FLASHApp).
            eye: { x: 2.5, y: 0, z: 0.2 },
          },
        },
        showlegend: true,
      }
    },
  },
  watch: {
    isDataReady: {
      handler(newVal: boolean) {
        if (newVal && this.isInitialized) this.graph()
      },
      immediate: true,
    },
    'streamlitDataStore.allDataForDrawing.scatter3dData': {
      handler() {
        if (this.isInitialized) this.graph()
      },
      deep: true,
    },
  },
  mounted() {
    this.isInitialized = true
    this.$nextTick(() => {
      if (this.isDataReady) this.graph()
    })
  },
  methods: {
    /**
     * Build flat x/y/z arrays where each peak becomes a 3-point vertical stick
     * (baseline, intensity, baseline) separated so Plotly draws disjoint lines.
     * Mirrors the original get3DplotInputFromSNRPeaks triplet trick.
     */
    buildStickArrays(kind: string): { x: number[]; y: number[]; z: number[] } {
      const xs: number[] = []
      const ys: number[] = []
      const zs: number[] = []
      const BASELINE = -100000
      for (const row of this.peaks) {
        if (String(row[this.kindColumn]) !== kind) continue
        const z = Number(row[this.intensityColumn])
        if (!(z > 0)) continue // ignore non-positive intensities
        const x = Number(row[this.mzColumn])
        const y = Number(row[this.chargeColumn])
        xs.push(x, x, x)
        ys.push(y, y, y)
        zs.push(BASELINE, z, BASELINE)
      }
      return { x: xs, y: ys, z: zs }
    },
    async graph(): Promise<void> {
      try {
        const element = document.getElementById(this.id)
        if (!element) return
        await Plotly.newPlot(this.id, this.data, this.layout, {
          modeBarButtonsToRemove: ['toImage', 'sendDataToCloud'],
          modeBarButtonsToAdd: [
            {
              title: 'Download as SVG',
              name: 'toImageSvg',
              icon: Plotly.Icons.camera,
              click: (plotlyElement) => {
                Plotly.downloadImage(plotlyElement as Plotly.PlotlyHTMLElement, {
                  filename: 'FLASHViewer-3d-plot',
                  height: 800,
                  width: 800,
                  format: 'svg',
                })
              },
            },
          ],
        })
        this.$nextTick(() => Streamlit.setFrameHeight())
      } catch (error) {
        console.error('Plotly3DScatter: Error rendering plot:', error)
      }
    },
  },
})
</script>

<style scoped>
.scatter3d-container {
  width: 100%;
  box-sizing: border-box;
  border: 1px solid #cccccc;
}
</style>
