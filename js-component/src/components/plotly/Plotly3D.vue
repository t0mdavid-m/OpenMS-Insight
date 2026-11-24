<template>
  <div class="plot3d">
    <PlotToolbar :plot-id="id" :tools="toolbarTools" :stepper="args.stepper" />
    <div :id="id" class="plot-container" :class="{ bordered: args.border !== false }"></div>
  </div>
</template>

<script lang="ts">
import { defineComponent, type PropType } from 'vue'
import Plotly from '@/plotly/gl3d'
import { Streamlit, type Theme } from 'streamlit-component-lib'
import { useStreamlitDataStore } from '@/stores/streamlit-data'
import { useSelectionStore } from '@/stores/selection'
import type { Plot3DComponentArgs } from '@/types/component'
import { imageFormatOf } from '@/utils/imageExport'
import { downloadTool } from '@/utils/plotlyDownload'
import { ICONS, TOOLBAR_HEIGHT, type PlotTool } from '@/utils/plotTools'
import { useLayers, type Layer } from '@/composables/useLayers'
import PlotToolbar from './PlotToolbar.vue'

// Looking straight down the intensity axis: the scene as a flat RT x m/z map
const TOP_VIEW_CAMERA = {
  eye: { x: 0, y: 0, z: 2.2 },
  up: { x: 0, y: 1, z: 0 },
  center: { x: 0, y: 0, z: 0 },
}
const TOP_VIEW_ICON = 'M3 3h18v18H3V3zm2 2v14h14V5H5zm2 2h4v4H7V7zm6 0h4v4h-4V7zm-6 6h4v4H7v-4zm6 0h4v4h-4v-4z'

function formatIntensity(v: number): string {
  if (v >= 1e4 || (v > 0 && v < 0.01)) return v.toExponential(1)
  return String(Math.round(v * 100) / 100)
}

// Floor the stems and trace starts drop to. Far below zero so the vertical
// segment always reaches the bottom of the z range, which starts at 0.
const STEM_FLOOR = -100000
const TRACE_FLOOR = -1000

let plotIdCounter = 0

interface SeriesPoints {
  key: string
  name: string
  color: string
  x: (number | null)[]
  y: (number | null)[]
  z: (number | null)[]
  /** z of the point each vertex belongs to, for colouring by height */
  c: number[]
}

/** How the points are coloured: by their series, or by z scaled to the points shown or to all data. */
type ColourMode = 'series' | 'relative' | 'absolute'

// Light to dark blue; the square root of z, so weak points stay visible next to strong ones
const HEIGHT_COLORSCALE: [number, string][] = [
  [0, '#c6d3ff'],
  [0.5, '#3157e9'],
  [1, '#0b1a5c'],
]

export default defineComponent({
  name: 'Plotly3D',
  components: { PlotToolbar },
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
    return {
      streamlitDataStore,
      selectionStore,
      layers: useLayers(),
      uniqueId: `plot3d-${++plotIdCounter}`,
    }
  },
  data() {
    return {
      drawPending: false,
      /** Lowest z drawn; absent: every point. */
      minZ: undefined as number | undefined,
      /** Seen from above, as a flat map without perspective. */
      topView: false,
      colourMode: 'series' as ColourMode,
    }
  },
  computed: {
    toolbarTools(): PlotTool[] {
      const height = this.args.height || 800
      return [
        ...this.layers.tool(this.layerList, 'Series'),
        this.filterTool,
        this.colourTool,
        {
          id: 'top-view',
          group: 'view',
          icon: TOP_VIEW_ICON,
          label: 'View from above',
          short: 'From above',
          help: this.topView
            ? 'back to the 3D view'
            : 'flat map, seen along the ' + (this.args.zLabel || 'z') + ' axis',
          active: this.topView,
          run: () => {
            this.topView = !this.topView
          },
        },
        downloadTool({
          plotId: this.id,
          format: () => imageFormatOf(this.args.imageFormat),
          filename: () => this.args.svgFilename || this.title || 'plot3d',
          width: height,
          height,
        }),
      ]
    },
    /** The "Filter" button: the lowest z drawn, from 0 to the highest z of the data. */
    filterTool(): PlotTool {
      const hi = this.dataMaxZ
      const label = this.args.zLabel || 'z'
      return {
        id: 'filter',
        group: 'show',
        icon: ICONS.palette,
        label: 'Filter',
        short: this.minZ === undefined ? 'Filter' : `${label} ≥ ${formatIntensity(this.minZ)}`,
        help: `which points are drawn, by their ${label}`,
        active: this.minZ !== undefined,
        menu: [
          {
            kind: 'range',
            label: `Show ${label} from`,
            min: 0,
            max: hi,
            step: hi > 0 ? hi / 100 : 1,
            value: this.minZ ?? 0,
            format: (v: number) => (v <= 0 ? 'all' : `≥ ${formatIntensity(v)}`),
            input: (v: number) => {
              this.minZ = v <= 0 ? undefined : v
            },
          },
        ],
        run: () => {},
      }
    },
    /** The "Colour" button: by series, or by z relative to the points shown or absolute. */
    colourTool(): PlotTool {
      const label = this.args.zLabel || 'z'
      const shorts: Record<ColourMode, string> = {
        series: 'Colour',
        relative: 'Relative',
        absolute: 'Absolute',
      }
      return {
        id: 'colour',
        group: 'show',
        icon: ICONS.colorbar,
        label: 'Colour',
        short: shorts[this.colourMode],
        help: `colour the points by series or by their ${label}`,
        active: this.colourMode !== 'series',
        menu: [
          {
            kind: 'choice',
            label: 'Colour points',
            options: [
              { value: 'series', label: 'By series' },
              {
                value: 'relative',
                label: `By ${label}, scaled to the points shown`,
              },
              { value: 'absolute', label: `By ${label}, scaled to all data` },
            ],
            value: this.colourMode,
            select: (v: string) => {
              this.colourMode = v as ColourMode
            },
          },
        ],
        run: () => {},
      }
    },
    /** The z range the colour scale spans. Seen from above, points are always
     * coloured by height, scaled to the points shown unless "absolute" is picked. */
    colourRange(): [number, number] | null {
      const mode = this.colourMode === 'series' && this.topView ? 'relative' : this.colourMode
      if (mode === 'series') return null
      if (mode === 'absolute') return [0, this.dataMaxZ || 1]
      return [this.minZ ?? 0, this.maxZ || 1]
    },
    /** Highest z of the data, before the filter. */
    dataMaxZ(): number {
      const zs = (this.columns[this.args.zColumn] as number[]) || []
      let max = 0
      for (const z of zs) if (z > max) max = z
      return max
    },
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
    title(): string {
      for (const [identifier, title] of this.args.selectionTitles || []) {
        const value = this.selectionStore.$state[identifier]
        if (value !== undefined && value !== null) return title
      }
      return this.args.title || ''
    },
    seriesName(): (key: string) => string {
      const names = new Map<string, string>((this.args.seriesNames || []).map(([k, v]) => [String(k), v]))
      const template = this.args.seriesNameTemplate
      return (key: string) => names.get(key) ?? (template ? template.replace('{}', key) : key)
    },
    series(): SeriesPoints[] {
      const xs = (this.columns[this.args.xColumn] as number[]) || []
      const ys = (this.columns[this.args.yColumn] as number[]) || []
      const zs = (this.columns[this.args.zColumn] as number[]) || []
      const seriesColumn = this.args.seriesColumn
      const seriesValues = seriesColumn ? (this.columns[seriesColumn] as unknown[]) || [] : []
      const traceColumn = this.args.traceColumn
      const traceValues = traceColumn ? (this.columns[traceColumn] as unknown[]) || [] : []
      const colors = this.args.seriesColors || {}
      const stems = this.args.mode !== 'lines'

      // Named series are listed (even without points of their own) whenever
      // there is anything to draw
      const groups = new Map<string, SeriesPoints>()
      for (const [k] of xs.length > 0 ? this.args.seriesNames || [] : []) {
        const key = String(k)
        groups.set(key, {
          key,
          name: this.seriesName(key),
          color: colors[key] || this.args.color,
          x: [],
          y: [],
          z: [],
          c: [],
        })
      }
      // Last trace seen per series, to start a new polyline when it changes
      const lastTrace = new Map<string, unknown>()

      for (let i = 0; i < xs.length; i++) {
        const key = seriesColumn ? String(seriesValues[i]) : ''
        if (!groups.has(key)) {
          groups.set(key, {
            key,
            name: this.seriesName(key),
            color: colors[key] || this.args.color,
            x: [],
            y: [],
            z: [],
            c: [],
          })
        }
        const group = groups.get(key)!
        const x = xs[i]
        const y = ys[i]
        const z = zs[i]
        if (this.minZ !== undefined && !(z >= this.minZ)) continue

        if (stems) {
          // Points at or below the floor of the z range draw nothing
          if (!(z > 0)) continue
          group.x.push(x, x, x)
          group.y.push(y, y, y)
          group.z.push(STEM_FLOOR, z, STEM_FLOOR)
          group.c.push(z, z, z)
          continue
        }

        const trace = traceColumn ? traceValues[i] : undefined
        if (!lastTrace.has(key) || lastTrace.get(key) !== trace) {
          if (lastTrace.has(key)) {
            // Break the line between two traces of the same series
            group.x.push(null)
            group.y.push(null)
            group.z.push(null)
            group.c.push(0)
          }
          // Each trace rises from the floor at its first point
          group.x.push(x)
          group.y.push(y)
          group.z.push(TRACE_FLOOR)
          group.c.push(z)
          lastTrace.set(key, trace)
        }
        group.x.push(x)
        group.y.push(y)
        group.z.push(z)
        group.c.push(z)
      }
      return [...groups.values()]
    },
    /** Points of the selected value of a `highlight` identifier, sent apart by Python */
    highlightSeries(): SeriesPoints | null {
      if (!this.args.highlight) return null
      const points = this.streamlitDataStore.allDataForDrawing?.highlightData as
        | { x: number[]; y: number[]; z: number[] }
        | undefined
      const group: SeriesPoints = {
        key: '__highlight__',
        name: this.args.highlightName || 'Selected',
        color: this.args.highlightColor || '#ff7501',
        x: [],
        y: [],
        z: [],
        c: [],
      }
      const xs = points?.x || []
      const ys = points?.y || []
      const zs = points?.z || []
      const stems = this.args.mode !== 'lines'
      for (let i = 0; i < xs.length; i++) {
        if (stems) {
          if (!(zs[i] > 0)) continue
          group.x.push(xs[i], xs[i], xs[i])
          group.y.push(ys[i], ys[i], ys[i])
          group.z.push(STEM_FLOOR, zs[i], STEM_FLOOR)
        } else {
          group.x.push(xs[i])
          group.y.push(ys[i])
          group.z.push(zs[i])
        }
      }
      return group.x.length > 0 ? group : null
    },
    /** The series the toolbar shows or hides. */
    layerList(): Layer[] {
      return this.series.map((s) => ({
        key: s.key,
        label: s.name,
        color: s.color,
      }))
    },
    allSeries(): SeriesPoints[] {
      // The highlighted points last, so they are drawn on top
      const shown = this.series.filter((s) => this.layers.visible(s.key))
      return this.highlightSeries ? [...shown, this.highlightSeries] : shown
    },
    maxZ(): number {
      let max = 0
      for (const s of this.allSeries) {
        for (const z of s.z) {
          if (z !== null && z > max) max = z
        }
      }
      return max
    },
    traces(): Plotly.Data[] {
      if (this.topView) return this.topViewTraces
      const range = this.colourRange
      let scaleShown = false
      return this.allSeries.map((s) => {
        const highlight = s.key === '__highlight__'
        const line: Record<string, unknown> = {
          color: s.color,
          width: highlight ? 4 : 2,
        }
        if (range && !highlight) {
          Object.assign(line, this.heightColours(s.c, range, !scaleShown))
          scaleShown = true
        }
        return {
          name: s.name,
          type: 'scatter3d',
          mode: 'lines',
          x: s.x,
          y: s.y,
          z: s.z,
          line,
          connectgaps: false,
        } as Plotly.Data
      })
    },
    /** Seen from above a stem is a point: one marker per peak */
    topViewTraces(): Plotly.Data[] {
      const plain = this.allSeries.filter((s) => s.key !== '__highlight__')
      // Several series keep their colours unless a colouring by height is picked
      const range = this.colourMode === 'series' && plain.length > 1 ? null : this.colourRange
      let scaleShown = false
      return this.allSeries.map((s) => {
        const x: number[] = []
        const y: number[] = []
        const z: number[] = []
        for (let i = 0; i < s.z.length; i++) {
          const zi = s.z[i]
          if (zi === null || zi <= STEM_FLOOR || zi <= TRACE_FLOOR) continue
          x.push(s.x[i] as number)
          y.push(s.y[i] as number)
          z.push(zi)
        }
        const highlight = s.key === '__highlight__'
        const marker: Record<string, unknown> = highlight
          ? { color: s.color, size: 5 }
          : { color: s.color, size: 3, opacity: 0.9 }
        if (range && !highlight) {
          Object.assign(marker, this.heightColours(z, range, !scaleShown))
          scaleShown = true
        }
        return {
          name: s.name,
          type: 'scatter3d',
          mode: 'markers',
          x,
          y,
          z,
          marker,
          hovertemplate: `${this.args.xLabel || 'x'}: %{x}<br>${this.args.yLabel || 'y'}: %{y}<br>${this.args.zLabel || 'z'}: %{z:.3s}<extra>${s.name}</extra>`,
        } as Plotly.Data
      })
    },
    layout(): Partial<Plotly.Layout> {
      const yaxis: Record<string, unknown> = {
        title: { text: this.args.yLabel },
      }
      if (this.args.yDtick !== undefined && this.args.yDtick !== null) {
        yaxis.dtick = this.args.yDtick
        yaxis.tick0 = 0
      }
      const scene: Record<string, unknown> = {
        xaxis: { title: { text: this.args.xLabel } },
        yaxis,
        // Seen from above the z axis is a point: no title or ticks to overlap
        zaxis: this.topView
          ? {
              title: { text: '' },
              showticklabels: false,
              range: [0, this.maxZ],
            }
          : { title: { text: this.args.zLabel }, range: [0, this.maxZ] },
      }
      if (this.topView) {
        scene.camera = {
          ...TOP_VIEW_CAMERA,
          projection: { type: 'orthographic' },
        }
      } else if (this.args.cameraEye || this.args.cameraCenter) {
        scene.camera = {
          ...(this.args.cameraEye ? { eye: this.args.cameraEye } : {}),
          ...(this.args.cameraCenter ? { center: this.args.cameraCenter } : {}),
        }
      }
      // A rotation of the user stays across reruns; switching the view applies its camera
      scene.uirevision = this.topView ? 'top' : 'free'
      if (this.args.aspectRatio) {
        scene.aspectmode = 'manual'
        scene.aspectratio = this.args.aspectRatio
      }
      // Plotly's default margins (80 px on every side) leave a wide empty frame
      // around a 3D scene; keep room for the title only
      const margin = { l: 0, r: 0, b: 0, t: this.title ? 50 : 10 }
      return {
        title: {
          text: this.args.titleBold === false ? this.title : `<b>${this.title}</b>`,
        },
        paper_bgcolor: this.theme?.backgroundColor,
        plot_bgcolor: this.theme?.secondaryBackgroundColor,
        height: (this.args.height || 800) - TOOLBAR_HEIGHT,
        font: {
          color: this.theme?.textColor,
          family: this.theme?.font,
        },
        scene: scene as Partial<Plotly.Scene>,
        margin,
        showlegend: this.args.showLegend !== false,
      }
    },
  },
  watch: {
    // A series shown or hidden from the toolbar
    'layers.state.hidden'() {
      this.requestRender()
    },
    'streamlitDataStore.allDataForDrawing.plotData': {
      handler() {
        this.requestRender()
      },
      deep: true,
    },
    'streamlitDataStore.allDataForDrawing.highlightData': {
      handler() {
        this.requestRender()
      },
      deep: true,
    },
    title() {
      this.requestRender()
    },
    // By value: the arguments arrive as a new object on every rerun
    argsKey() {
      this.requestRender()
    },
    minZ() {
      this.requestRender()
    },
    topView() {
      this.requestRender()
    },
    colourMode() {
      this.requestRender()
    },
  },
  mounted() {
    this.requestRender()
  },
  methods: {
    /** Colour settings of a line or marker that colour each point by its z within `range`. */
    heightColours(values: number[], [lo, hi]: [number, number], withScale: boolean): Record<string, unknown> {
      const root = (v: number) => Math.sqrt(Math.max(0, Math.min(hi, v) - lo))
      return {
        color: values.map(root),
        cmin: 0,
        cmax: Math.sqrt(Math.max(hi - lo, 1e-12)),
        colorscale: HEIGHT_COLORSCALE,
        showscale: withScale,
        colorbar: withScale
          ? {
              title: { text: this.args.zLabel || 'z' },
              thickness: 12,
              len: 0.6,
              tickvals: [0, Math.sqrt(Math.max(hi - lo, 1e-12))],
              ticktext: [formatIntensity(lo), formatIntensity(hi)],
            }
          : undefined,
      }
    },
    /** Draw once per update: one update often changes several watched values
     * (the data and the selection), and each drawing costs a full Plotly render.
     * Drawn in a task of its own, so the other views of the page, which share
     * this thread and receive the same update, are not held up by the scene. */
    requestRender(): void {
      if (this.drawPending) return
      this.drawPending = true
      setTimeout(() => {
        this.drawPending = false
        this.renderPlot()
      }, 0)
    },
    async renderPlot(): Promise<void> {
      const element = document.getElementById(this.id)
      if (!element) return
      // react keeps the WebGL scene of the previous render; newPlot builds a new one
      await Plotly.react(element, this.traces, this.layout, {
        modeBarButtonsToRemove: ['toImage', 'sendDataToCloud'],
        displaylogo: false,
        responsive: true,
        // No "double-click to isolate" notice on a legend click
        showTips: false,
      } as Partial<Plotly.Config>)
      this.$nextTick(() => Streamlit.setFrameHeight())
    },
  },
})
</script>

<style scoped>
.plot-container {
  width: 100%;
  box-sizing: border-box;
}
.plot-container.bordered {
  border: 1px solid #cccccc;
}
</style>
