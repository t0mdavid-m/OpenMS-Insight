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
 *
 * When `traceKeyColumn` is provided, the charge polyline is additionally broken
 * (with the same z-sentinel) between consecutive points whose trace-key value
 * differs, so each isotope trace within a charge is drawn as its own polyline
 * (legacy per-trace break). Without it, every point of a charge forms a single
 * polyline (behavior unchanged).
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
    /**
     * Optional column identifying the individual trace a point belongs to. When
     * set, a z-sentinel break is inserted between consecutive points whose
     * value differs within the same charge, so each trace is its own polyline.
     */
    traceKeyColumn(): string | null {
      return this.args.traceKeyColumn ?? null
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
      const traceKeyColumn = this.traceKeyColumn

      // Group points by charge, preserving row order (already sorted by RT
      // within a trace upstream). When a trace-key column is configured, the
      // per-point key lets us break the charge polyline between traces.
      const byCharge = new Map<
        number,
        { mz: number[]; rt: number[]; inty: number[]; key: unknown[] }
      >()
      for (const row of this.points) {
        const charge = Number(row[this.chargeColumn])
        const mz = Number(row[this.mzColumn])
        const rt = Number(row[this.rtColumn])
        const inty = Number(row[this.intensityColumn])
        if (!Number.isFinite(charge)) continue
        if (!byCharge.has(charge)) byCharge.set(charge, { mz: [], rt: [], inty: [], key: [] })
        const entry = byCharge.get(charge)!
        entry.mz.push(mz)
        entry.rt.push(rt)
        entry.inty.push(inty)
        entry.key.push(traceKeyColumn ? row[traceKeyColumn] : null)
      }

      let maxInty = 0
      const traces: Plotly.Data[] = []
      const charges = Array.from(byCharge.keys()).sort((a, b) => a - b)
      for (const charge of charges) {
        const entry = byCharge.get(charge)!
        const n = entry.mz.length
        if (n === 0) continue

        // Bracket each charge with leading/trailing z-sentinels (original -1000
        // trick) so consecutive charges are not joined and baselines drop to the
        // floor. When a trace-key column is set, ALSO insert a sentinel break
        // between consecutive points whose key differs, so each trace within the
        // charge is its own polyline (legacy per-isotope-trace break). Each run
        // ends up bracketed exactly like a standalone charge, so the charge
        // carries 2 sentinels per trace run (2 with no key / one run).
        const xs: number[] = [entry.mz[0]]
        const ys: number[] = [entry.rt[0]]
        const zs: number[] = [SENTINEL]
        for (let i = 0; i < n; i++) {
          if (traceKeyColumn && i > 0 && entry.key[i] !== entry.key[i - 1]) {
            // Break between the previous trace's last point and this trace's
            // first point: drop to the floor and lift back up.
            xs.push(entry.mz[i - 1], entry.mz[i])
            ys.push(entry.rt[i - 1], entry.rt[i])
            zs.push(SENTINEL, SENTINEL)
          }
          xs.push(entry.mz[i])
          ys.push(entry.rt[i])
          zs.push(entry.inty[i])
          if (entry.inty[i] > maxInty) maxInty = entry.inty[i]
        }
        xs.push(entry.mz[n - 1])
        ys.push(entry.rt[n - 1])
        zs.push(SENTINEL)

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
