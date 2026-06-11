<template>
  <div :id="id" style="width: 100%; border: 1px solid #cccccc; box-sizing: border-box;"></div>
</template>

<script lang="ts">
import { defineComponent, type PropType } from 'vue'
import Plotly from 'plotly.js-dist-min'
import type { Theme } from 'streamlit-component-lib'
import { Streamlit } from 'streamlit-component-lib'
import { useStreamlitDataStore } from '@/stores/streamlit-data'
import { useSelectionStore } from '@/stores/selection'
import type { Plot3DComponentArgs, Plot3DData } from '@/types/component'

const DEFAULT_CATEGORY_COLORS: Record<string, string> = {
  Signal: '#3366CC',
  Noise: '#DC3912',
}
const DEFAULT_CAMERA_EYE = { x: 2.5, y: 0, z: 0.2 }
const DEFAULT_STEM_BASELINE = -100000
const DEFAULT_HEIGHT = 800
const FALLBACK_CATEGORY = 'Signal'

/**
 * Plotly scatter3d component reproducing FLASHApp's precursor Signal/Noise
 * 3D stem plot in a generic, tidy-long form.
 *
 * Reads one row per point from `allDataForDrawing.plot3dData`, groups rows by
 * `categoryColumn` (one trace per category), and draws each point as a vertical
 * stem (drop line) using the oracle stem-triplet construction
 * (baseline -> peak -> baseline). The huge negative baseline is clipped off-view
 * by the z-axis range `[0, maxIntensity]`, so each stick visually rises from 0.
 *
 * Optional additive behaviors (default off, current behavior unchanged):
 *  - `seriesColumn`: within each category trace, the line breaks (a NaN gap is
 *    inserted) between consecutive distinct series values (e.g. isotopes within
 *    a charge), so independent sub-traces do not connect — while staying one
 *    trace per category. Rows are pre-sorted Python-side so each series is
 *    contiguous in within-series (RT) order.
 *  - `categoryNameTemplate`: legend name = `template.replace('{}', category)`
 *    (e.g. `'Charge: {}'` -> `'Charge: 2'`), else the bare category value.
 */
export default defineComponent({
  name: 'Plotly3D',
  props: {
    args: {
      type: Object as PropType<Plot3DComponentArgs>,
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
    return { streamlitDataStore, selectionStore }
  },
  data() {
    return {
      isInitialized: false as boolean,
      maximumIntensity: 0 as number,
    }
  },
  computed: {
    id(): string {
      return `plot3d-${this.index}`
    },
    theme(): Theme | undefined {
      return this.streamlitDataStore.theme
    },
    /**
     * Tidy point rows from Python (one row per point).
     */
    rows(): Plot3DData[] {
      const data = this.streamlitDataStore.allDataForDrawing?.plot3dData
      return (data as Plot3DData[]) || []
    },
    categoryColors(): Record<string, string> {
      return this.args.categoryColors || DEFAULT_CATEGORY_COLORS
    },
    traceMode(): Plot3DComponentArgs['traceMode'] {
      return this.args.traceMode || 'lines'
    },
    useStem(): boolean {
      const stem = this.args.stem !== false
      return stem && (this.traceMode === 'lines' || this.traceMode === 'lines+markers')
    },
    /**
     * Build one scatter3d trace per distinct category value.
     *
     * Stem mode expands each point into the contiguous triplet
     * `z:[baseline, z, baseline]`, `x:[x,x,x]`, `y:[y,y,y]` — reproducing the
     * oracle `get3DplotInputFromSNRPeaks`. Marker-only mode emits one point each.
     */
    plotData(): Plotly.Data[] {
      const xCol = this.args.xColumn
      const yCol = this.args.yColumn
      const zCol = this.args.zColumn
      const categoryCol = this.args.categoryColumn
      const seriesCol = this.args.seriesColumn
      const categoryNameTemplate = this.args.categoryNameTemplate
      const stemBaseline = this.args.stemBaseline ?? DEFAULT_STEM_BASELINE
      const interactivityCols = Object.values(this.args.interactivity || {})
      const hoverCols = this.args.hoverColumns || []

      // Preserve first-seen category order so trace/legend ordering is stable.
      const order: string[] = []
      const groups: Record<string, Plot3DData[]> = {}
      for (const row of this.rows) {
        const category = categoryCol ? String(row[categoryCol]) : FALLBACK_CATEGORY
        if (!(category in groups)) {
          groups[category] = []
          order.push(category)
        }
        groups[category].push(row)
      }

      const traces: Plotly.Data[] = []
      for (const category of order) {
        const groupRows = groups[category]
        const xs: (number | null)[] = []
        const ys: (number | null)[] = []
        const zs: (number | null)[] = []
        const customdata: unknown[] = []
        const text: string[] = []

        // Tracks the previous row's series value within this category so a NaN
        // gap can be inserted at each series boundary (off when seriesCol unset).
        let prevSeries: string | undefined
        let seenSeries = false
        for (const row of groupRows) {
          const x = Number(row[xCol])
          const y = Number(row[yCol])
          const z = Number(row[zCol])

          // Break the line between consecutive distinct series within this
          // category by pushing a null gap (Plotly breaks mode:lines at null).
          // Never before the first series, and category boundaries are already
          // separate traces. customdata/text get aligned null/empty entries.
          if (seriesCol) {
            const series = String(row[seriesCol])
            if (seenSeries && series !== prevSeries) {
              xs.push(null)
              ys.push(null)
              zs.push(null)
              customdata.push(null)
              text.push('')
            }
            prevSeries = series
            seenSeries = true
          }

          const hover = this.buildHoverText(row, x, y, z, hoverCols)
          // customdata packs interactivity column values for click routing.
          const cd: Record<string, unknown> = {}
          for (const col of interactivityCols) cd[col] = row[col]

          if (this.useStem) {
            // Contiguous triplet array (matches oracle visual identity).
            xs.push(x, x, x)
            ys.push(y, y, y)
            zs.push(stemBaseline, z, stemBaseline)
            customdata.push(cd, cd, cd)
            text.push(hover, hover, hover)
          } else {
            xs.push(x)
            ys.push(y)
            zs.push(z)
            customdata.push(cd)
            text.push(hover)
          }
        }

        const color =
          this.categoryColors[category] || DEFAULT_CATEGORY_COLORS[category] || '#3366CC'
        // Templated legend label (e.g. "Charge: 2") when a template is set,
        // else the bare category value (unchanged default behavior).
        const name = categoryNameTemplate
          ? categoryNameTemplate.replace('{}', category)
          : category
        traces.push({
          name,
          type: 'scatter3d',
          mode: this.traceMode,
          x: xs as Plotly.Datum[],
          y: ys as Plotly.Datum[],
          z: zs as unknown as Plotly.Datum[],
          line: { color },
          marker: { color },
          customdata: customdata as Plotly.Datum[],
          text,
          hoverinfo: 'text',
        })
      }

      return traces
    },
    /**
     * Dynamic title (FLASHApp parity). When ``titleSelection`` maps the scan +
     * mass selection identifiers, the title is computed reactively from the
     * selection store EXACTLY like the oracle Plotly3Dplot.vue ``title`` computed:
     *   '' when the scan selection is unset,
     *   'Precursor signals' when the scan is set but the mass is unset,
     *   'Mass signals' when both are set.
     * When ``titleSelection`` is absent, falls back to the static ``args.title``
     * (default behavior unchanged). The Python ``compute_dynamic_title`` mirrors
     * this for tests; the live title is reactive so it updates with NO round-trip.
     */
    displayTitle(): string | undefined {
      const ts = this.args.titleSelection
      if (!ts) return this.args.title
      const scanIdent = ts.scan
      const massIdent = ts.mass
      const scanVal = scanIdent ? this.selectionStore.$state[scanIdent] : undefined
      const massVal = massIdent ? this.selectionStore.$state[massIdent] : undefined
      if (scanVal === undefined || scanVal === null) return ''
      if (massVal === undefined || massVal === null) return 'Precursor signals'
      return 'Mass signals'
    },
    layout(): Partial<Plotly.Layout> {
      const cameraEye = this.args.cameraEye || DEFAULT_CAMERA_EYE
      const title = this.displayTitle
      return {
        title: title ? { text: `<b>${title}</b>` } : undefined,
        paper_bgcolor: this.theme?.backgroundColor,
        plot_bgcolor: this.theme?.secondaryBackgroundColor,
        height: this.args.height ?? DEFAULT_HEIGHT,
        font: {
          color: this.theme?.textColor,
          family: this.theme?.font,
        },
        scene: {
          xaxis: { title: { text: this.args.xLabel || 'Mass' } },
          yaxis: {
            title: { text: this.args.yLabel || 'Charge' },
            dtick: this.args.yDtick ?? 1,
            tick0: this.args.yTick0 ?? 0,
          },
          zaxis: {
            title: { text: this.args.zLabel || 'Intensity' },
            range: [0, this.maximumIntensity],
          },
          camera: {
            // initial view of the plot: mass-intensity plane
            eye: cameraEye,
          },
        },
        showlegend: true,
      }
    },
  },
  watch: {
    'streamlitDataStore.allDataForDrawing.plot3dData': {
      handler() {
        if (this.isInitialized) {
          this.renderPlot()
        }
      },
      deep: true,
    },
    // Re-render when render-time trace mode changes (sticks <-> marker cloud).
    traceMode() {
      if (this.isInitialized) {
        this.renderPlot()
      }
    },
    // Re-render when the selection changes so the dynamic title (FLASHApp parity)
    // updates reactively. Only relevant when titleSelection is configured; the
    // re-render is a cheap relayout (no new data). Default (no titleSelection)
    // plots still re-render harmlessly on selection but their title is static.
    'selectionStore.$state': {
      handler() {
        if (this.isInitialized && this.args.titleSelection) {
          this.renderPlot()
        }
      },
      deep: true,
    },
  },
  mounted() {
    this.renderPlot()
  },
  methods: {
    /**
     * Max z over all displayed points (Signal ∪ Noise). Pins z range
     * `[0, maxIntensity]` so the negative stem baselines clip at 0.
     * Mirrors oracle `updateMaximumIntensity`.
     */
    computeMaximumIntensity(): number {
      const zCol = this.args.zColumn
      let maxZ = 0
      for (const row of this.rows) {
        const z = Number(row[zCol])
        if (Number.isFinite(z) && z > maxZ) maxZ = z
      }
      return maxZ
    },
    buildHoverText(
      row: Plot3DData,
      x: number,
      y: number,
      z: number,
      hoverCols: string[],
    ): string {
      const xLabel = this.args.xLabel || 'Mass'
      const yLabel = this.args.yLabel || 'Charge'
      const zLabel = this.args.zLabel || 'Intensity'
      let hover = `${xLabel}: ${x}<br>${yLabel}: ${y}<br>${zLabel}: ${z}`
      for (const col of hoverCols) {
        hover += `<br>${col}: ${String(row[col])}`
      }
      return hover
    },
    async renderPlot(): Promise<void> {
      const element = document.getElementById(this.id)
      if (!element) return

      this.maximumIntensity = this.computeMaximumIntensity()

      await Plotly.newPlot(this.id, this.plotData, this.layout, {
        modeBarButtonsToRemove: ['toImage', 'sendDataToCloud'],
        modeBarButtonsToAdd: [
          {
            title: 'Download as SVG',
            name: 'toImageSvg',
            icon: Plotly.Icons.camera,
            click: (plotlyElement: unknown) => {
              Plotly.downloadImage(plotlyElement as Plotly.PlotlyHTMLElement, {
                filename: this.displayTitle || this.args.title || 'FLASHViewer-3d-plot',
                height: DEFAULT_HEIGHT,
                width: DEFAULT_HEIGHT,
                format: 'svg',
              })
            },
          },
        ],
      })

      this.isInitialized = true
      this.setupClickHandler()

      this.$nextTick(() => {
        Streamlit.setFrameHeight()
      })
    },
    /**
     * Outgoing selection is OFF by default (oracle emits nothing). When
     * `interactivity` is provided, route the clicked point's customdata value
     * into the selection store (mirrors PlotlyMirrorPlot / PlotlyLineplot).
     */
    setupClickHandler(): void {
      const interactivity = this.args.interactivity
      const plotEl = document.getElementById(this.id) as Plotly.PlotlyHTMLElement | null
      if (!plotEl) return

      plotEl.removeAllListeners?.('plotly_click')
      if (!interactivity || Object.keys(interactivity).length === 0) return

      plotEl.on('plotly_click', (event: Plotly.PlotMouseEvent) => {
        const pt = event.points?.[0]
        if (!pt) return
        const cd = pt.customdata as unknown as Record<string, unknown> | undefined
        if (!cd) return
        for (const [identifier, column] of Object.entries(interactivity)) {
          const value = cd[column]
          if (value !== undefined) {
            this.selectionStore.updateSelection(identifier, value)
          }
        }
      })
    },
  },
})
</script>

<style scoped></style>
