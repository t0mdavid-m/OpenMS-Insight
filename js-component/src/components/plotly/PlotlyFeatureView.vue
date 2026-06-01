<template>
  <div :id="id" class="feature-view-container"></div>
</template>

<script lang="ts">
import { defineComponent, type PropType } from 'vue'
import Plotly from 'plotly.js-dist-min'
import type { Theme } from 'streamlit-component-lib'
import { Streamlit } from 'streamlit-component-lib'
import { useStreamlitDataStore } from '@/stores/streamlit-data'
import type { FeatureViewComponentArgs, FeatureData } from '@/types/component'

/**
 * PlotlyFeatureView — FLASHQuant feature-group mass-trace view.
 *
 * Consumes long-format trace points from Python (one row per point), already
 * filtered to the selected feature group:
 *   { feature_group, charge, mz, rt, intensity, isotope? }
 * and draws one 3D line per charge state (m/z vs retention time vs intensity),
 * matching the original FLASHQuantView trace3Dplot. Charges are separated and
 * each trace is bracketed with a z-sentinel so Plotly draws disjoint lines.
 */
export default defineComponent({
  name: 'PlotlyFeatureView',
  props: {
    args: {
      type: Object as PropType<FeatureViewComponentArgs>,
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
      return `feature-view-${this.index}`
    },
    theme(): Theme | undefined {
      return this.streamlitDataStore.theme
    },
    chargeColumn(): string {
      return this.args.chargeColumn || 'charge'
    },
    mzColumn(): string {
      return this.args.mzColumn || 'mz'
    },
    rtColumn(): string {
      return this.args.rtColumn || 'rt'
    },
    intensityColumn(): string {
      return this.args.intensityColumn || 'intensity'
    },
    points(): FeatureData[] {
      const data = this.streamlitDataStore.allDataForDrawing?.featureData
      return (data as FeatureData[]) || []
    },
    isDataReady(): boolean {
      return Array.isArray(this.points) && this.points.length > 0
    },
    data(): Plotly.Data[] {
      if (!this.isDataReady) return []

      const SENTINEL = -1000

      // Group points by charge, preserving row order (already sorted by RT
      // within a trace upstream).
      const byCharge = new Map<number, { mz: number[]; rt: number[]; inty: number[] }>()
      for (const row of this.points) {
        const charge = Number(row[this.chargeColumn])
        const mz = Number(row[this.mzColumn])
        const rt = Number(row[this.rtColumn])
        const inty = Number(row[this.intensityColumn])
        if (!Number.isFinite(charge)) continue
        if (!byCharge.has(charge)) byCharge.set(charge, { mz: [], rt: [], inty: [] })
        const entry = byCharge.get(charge)!
        entry.mz.push(mz)
        entry.rt.push(rt)
        entry.inty.push(inty)
      }

      let maxInty = 0
      const traces: Plotly.Data[] = []
      const charges = Array.from(byCharge.keys()).sort((a, b) => a - b)
      for (const charge of charges) {
        const entry = byCharge.get(charge)!
        if (entry.mz.length === 0) continue

        // Bracket each trace with z-sentinels (matches original -1000 trick) so
        // consecutive traces are not joined and baselines drop to the floor.
        const xs = [entry.mz[0], ...entry.mz, entry.mz[entry.mz.length - 1]]
        const ys = [entry.rt[0], ...entry.rt, entry.rt[entry.rt.length - 1]]
        const zs = [SENTINEL, ...entry.inty, SENTINEL]

        for (const v of entry.inty) {
          if (v > maxInty) maxInty = v
        }

        traces.push({
          x: xs,
          y: ys,
          z: zs,
          mode: 'lines',
          line: { color: this.args.traceColor || '#3366CC' },
          type: 'scatter3d',
          name: `Charge: ${charge}`,
        })
      }

      this.maximumIntensity = maxInty
      return traces
    },
    layout(): Partial<Plotly.Layout> {
      return {
        title: { text: this.args.title || 'Feature group signals' },
        paper_bgcolor: this.theme?.backgroundColor,
        plot_bgcolor: this.theme?.secondaryBackgroundColor,
        height: this.args.height || 800,
        font: {
          color: this.theme?.textColor,
          family: this.theme?.font,
        },
        scene: {
          xaxis: { title: { text: this.args.xLabel || 'm/z' } },
          yaxis: { title: { text: this.args.yLabel || 'retention time' } },
          zaxis: {
            title: { text: this.args.zLabel || 'intensity' },
            range: [0, this.maximumIntensity],
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
    'streamlitDataStore.allDataForDrawing.featureData': {
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
    async graph(): Promise<void> {
      try {
        const element = document.getElementById(this.id)
        if (!element) return
        await Plotly.newPlot(this.id, this.data, this.layout, { responsive: true })
        this.$nextTick(() => Streamlit.setFrameHeight())
      } catch (error) {
        console.error('PlotlyFeatureView: Error rendering plot:', error)
      }
    },
  },
})
</script>

<style scoped>
.feature-view-container {
  width: 100%;
  box-sizing: border-box;
}
</style>
