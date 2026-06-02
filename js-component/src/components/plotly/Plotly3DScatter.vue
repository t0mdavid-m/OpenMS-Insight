<template>
  <div :id="id" class="plot-container-3d" style="width: 100%; border: 1px solid #cccccc; box-sizing: border-box;"></div>
</template>

<script lang="ts">
import { defineComponent, type PropType } from 'vue'
import Plotly from 'plotly.js-dist-min'
import { Streamlit, type Theme } from 'streamlit-component-lib'
import { useStreamlitDataStore } from '@/stores/streamlit-data'

/**
 * Arguments sent from the Python Scatter3D component.
 */
interface Plotly3DScatterArgs {
  componentType: string
  title?: string
  signalColor?: string
  noiseColor?: string
  height?: number
  config?: Record<string, unknown>
}

/**
 * Payload sent under `scatter3dData` by Python `_prepare_vue_data`.
 *
 * `signalPeaks` / `noisyPeaks` may arrive in two shapes; `normalizePeaks`
 * flattens both to a flat list of peak records (number[][]):
 *   - number[][][] : the selected scan's per-mass nested arrays (no mass
 *     selected, and the precursor cross-scan lookup is NOT wired).
 *   - number[][]   : a single mass's per-peak records, already subscripted —
 *     either because a mass IS selected (massSelected=true) OR because the
 *     precursor cross-scan lookup resolved the precursor scan's matching mass
 *     for a selected MS2 scan (massSelected=false, title stays "Precursor
 *     signals", mirroring FLASHApp getPrecursorSignal).
 * Each inner record is the 4-tuple [peak_index, mz, intensity, charge].
 */
interface Scatter3DData {
  hasSelection: boolean
  massSelected: boolean
  // When no mass: per-mass list of per-peak records -> number[][][]
  // When a mass:  per-peak records for that mass     -> number[][]
  signalPeaks: number[][][] | number[][] | null
  noisyPeaks: number[][][] | number[][] | null
}

const DEFAULT_SIGNAL_COLOR = '#3366CC'
const DEFAULT_NOISE_COLOR = '#DC3912'

export default defineComponent({
  name: 'Plotly3DScatter',
  props: {
    args: {
      type: Object as PropType<Plotly3DScatterArgs>,
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
      return `graph-3d-${this.index}`
    },

    theme(): Theme | undefined {
      return this.streamlitDataStore.theme
    },

    signalColor(): string {
      return this.args.signalColor || DEFAULT_SIGNAL_COLOR
    },

    noiseColor(): string {
      return this.args.noiseColor || DEFAULT_NOISE_COLOR
    },

    plotHeight(): number {
      return this.args.height || 800
    },

    /**
     * The raw payload from Python.
     */
    scatter3dData(): Scatter3DData | undefined {
      return this.streamlitDataStore.allDataForDrawing?.scatter3dData as
        | Scatter3DData
        | undefined
    },

    /**
     * Title text — reproduces FLASHApp Plotly3Dplot.vue dynamic title:
     *   no scan selected  -> ''         (blank)
     *   scan only         -> 'Precursor signals'
     *   scan + mass       -> 'Mass signals'
     */
    plotTitle(): string {
      const d = this.scatter3dData
      if (!d || !d.hasSelection) return ''
      return d.massSelected ? 'Mass signals' : 'Precursor signals'
    },

    /**
     * Build the two scatter3d line traces (Signal + Noise) from the payload.
     */
    dataForDrawing(): Plotly.Data[] {
      const d = this.scatter3dData
      if (!d || !d.hasSelection) return []

      const signalPeaks = this.normalizePeaks(d.signalPeaks)
      const noisyPeaks = this.normalizePeaks(d.noisyPeaks)

      if (signalPeaks.length === 0 && noisyPeaks.length === 0) return []

      const signals = this.getSignalNoiseObject(signalPeaks, noisyPeaks)

      // save max z value for layout (mirror updateMaximumIntensity)
      this.updateMaximumIntensity(signals)

      return [
        {
          name: 'Signal',
          type: 'scatter3d',
          mode: 'lines',
          x: signals.signal_x,
          y: signals.signal_y,
          z: signals.signal_z,
          line: { color: this.signalColor },
        },
        {
          name: 'Noise',
          type: 'scatter3d',
          mode: 'lines',
          x: signals.noise_x,
          y: signals.noise_y,
          z: signals.noise_z,
          line: { color: this.noiseColor },
        },
      ]
    },

    /**
     * Build the Plotly layout (mirror Plotly3Dplot.vue layout()).
     */
    layout(): Partial<Plotly.Layout> {
      return {
        title: { text: `<b>${this.plotTitle}</b>` },
        paper_bgcolor: this.theme?.backgroundColor,
        plot_bgcolor: this.theme?.secondaryBackgroundColor,
        height: this.plotHeight,
        font: {
          color: this.theme?.textColor,
          family: this.theme?.font,
        },
        scene: {
          xaxis: { title: { text: 'Mass' } },
          yaxis: { title: { text: 'Charge' }, dtick: 1, tick0: 0 },
          zaxis: { title: { text: 'Intensity' }, range: [0, this.maximumIntensity] },
          camera: {
            // initial view of the plot: mass-intensity plane
            eye: { x: 2.5, y: 0, z: 0.2 },
          },
        },
        showlegend: true,
      }
    },
  },

  watch: {
    scatter3dData: {
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
    /**
     * Normalize the peaks payload into a flat list of peak records (number[][]).
     *
     * Python sends either the per-mass nested array (number[][][], no mass
     * selected) or a single mass's per-peak array (number[][], mass selected,
     * already subscripted). Flatten the per-mass nesting so the stick builder
     * always receives a flat list of [peak_index, mz, intensity, charge] records.
     */
    normalizePeaks(
      peaks: number[][][] | number[][] | null | undefined
    ): number[][] {
      if (peaks == null || peaks.length === 0) return []
      // Detect nesting depth: a record is number[]; a per-mass list is number[][].
      const first = peaks[0] as unknown
      if (Array.isArray(first) && first.length > 0 && Array.isArray(first[0])) {
        // number[][][] -> flatten one level (per-mass -> records)
        const flat: number[][] = []
        for (const massGroup of peaks as number[][][]) {
          if (massGroup) {
            for (const rec of massGroup) flat.push(rec)
          }
        }
        return flat
      }
      // already number[][]
      return peaks as number[][]
    },

    updateMaximumIntensity(signals: Record<string, number[]>) {
      this.maximumIntensity = signals.signal_z
        .concat(signals.noise_z)
        .reduce((a, b) => Math.max(a, b), -Infinity)
      // Guard: empty -> -Infinity. Fall back to a sane positive range.
      if (!isFinite(this.maximumIntensity) || this.maximumIntensity <= 0) {
        this.maximumIntensity = 1
      }
    },

    getSignalNoiseObject(
      signal_peaks: number[][],
      noisy_peaks: number[][]
    ): Record<string, number[]> {
      const signal_object = this.get3DplotInputFromSNRPeaks(signal_peaks, true)
      const noisy_object = this.get3DplotInputFromSNRPeaks(noisy_peaks, false)
      Object.assign(signal_object, noisy_object)
      return signal_object
    },

    /**
     * Turn per-peak records into stick lines (baseline -> peak -> baseline).
     * Mirrors FLASHApp Plotly3Dplot.vue get3DplotInputFromSNRPeaks:
     *   x = mz * charge  (record[1] * record[3])   -> Mass
     *   y = charge       (record[3])               -> Charge
     *   z = intensity    (record[2])               -> Intensity
     * Peaks with intensity <= 0 are skipped. Baseline sentinel is -100000.
     */
    get3DplotInputFromSNRPeaks(
      peaks: number[][],
      is_signal: boolean
    ): Record<string, number[]> {
      const xs: number[] = []
      const ys: number[] = []
      const zs: number[] = []
      for (let i = 0, len = peaks.length; i < len; i++) {
        const rec = peaks[i]
        if (!rec || rec.length < 4) continue
        const z = rec[2] // intensity
        if (z <= 0) continue // ignore non-positive intensity
        zs.push(-100000, z, -100000)
        const x = rec[1] * rec[3] // mz * charge = mass
        xs.push(x, x, x)
        const y = rec[3] // charge
        ys.push(y, y, y)
      }
      return is_signal
        ? { signal_x: xs, signal_y: ys, signal_z: zs }
        : { noise_x: xs, noise_y: ys, noise_z: zs }
    },

    async graph(): Promise<void> {
      const element = document.getElementById(this.id)
      if (!element) {
        console.warn(`Plotly3DScatter: DOM element '${this.id}' not found`)
        return
      }
      await Plotly.newPlot(this.id, this.dataForDrawing, this.layout, {
        modeBarButtonsToRemove: ['toImage', 'sendDataToCloud'],
        modeBarButtonsToAdd: [
          {
            title: 'Download as SVG',
            name: 'toImageSvg',
            icon: Plotly.Icons.camera,
            click: (plotlyElement: any) => {
              Plotly.downloadImage(plotlyElement, {
                filename: 'FLASHViewer-3d-plot',
                height: 800,
                width: 800,
                format: 'svg',
              })
            },
          },
        ],
      })

      this.$nextTick(() => {
        Streamlit.setFrameHeight(this.plotHeight)
      })
    },
  },
})
</script>

<style scoped>
.plot-container-3d {
  position: relative;
  width: 100%;
  min-height: 100px;
}
</style>
