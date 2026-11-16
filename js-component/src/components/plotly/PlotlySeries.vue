<template>
  <div class="series-plot">
    <MeasureHint v-if="measurable" :measure="measure" />
    <PlotToolbar :plot-id="id" :tools="toolbarTools" :stepper="args.stepper" :settings="args.toolbarSettings">
      <!-- The views in the toolbar's row, left of the tools: one row of controls -->
      <template v-if="views.length > 1 || switches.length > 1" #lead>
        <div v-if="views.length > 1" class="view-switch" role="tablist" :style="switchStyle">
          <button
            v-for="[value, label] in views"
            :key="value"
            type="button"
            role="tab"
            class="view-button"
            :class="{ active: value === currentView }"
            :aria-selected="value === currentView"
            @click="pickView(value)"
          >
            {{ label }}
          </button>
        </div>
        <!-- A second switch whose value the caller reads (switch_identifier) -->
        <div v-if="switches.length > 1" class="view-switch" role="tablist" :style="switchStyle">
          <button
            v-for="[value, label] in switches"
            :key="value"
            type="button"
            role="tab"
            class="view-button"
            :class="{ active: value === currentSwitch }"
            :aria-selected="value === currentSwitch"
            @click="pickSwitch(value)"
          >
            {{ label }}
          </button>
        </div>
      </template>
    </PlotToolbar>
    <div :id="id" class="plot-container" :style="{ minHeight: `${plotHeight}px` }"></div>
  </div>
</template>

<script lang="ts">
import { defineComponent, type PropType } from 'vue'
// The cartesian bundle: scatter, bar and box traces
import Plotly from '@/plotly/cartesian'
import { Streamlit, type Theme } from 'streamlit-component-lib'
import { useStreamlitDataStore } from '@/stores/streamlit-data'
import { useSelectionStore } from '@/stores/selection'
import type { SeriesPlotComponentArgs } from '@/types/component'
import { useMeasure, type MeasureOverlay, type MeasureSpec } from '@/composables/useMeasure'
import { axisQuantity, pointsKey } from '@/utils/measure'
import MeasureHint from './MeasureHint.vue'
import { imageFormatOf } from '@/utils/imageExport'
import { downloadTool } from '@/utils/plotlyDownload'
import { ICONS, TOOLBAR_HEIGHT, type PlotTool, boldTitle } from '@/utils/plotTools'
import { useLayers, type Layer } from '@/composables/useLayers'
import PlotToolbar from './PlotToolbar.vue'
import { useZoomState, withZoom, type ZoomValue } from '@/composables/useZoomState'
import { SELECTION_ACCENT, clearSelectionTool } from '@/composables/useMultiSelect'

let plotIdCounter = 0

/** Height of the row of view buttons in pixels. */
/** Space of the title and the value axis around the bars of a growing plot. */
const BAR_PLOT_MARGIN = 110

export default defineComponent({
  name: 'PlotlySeries',
  components: { MeasureHint, PlotToolbar },
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
  setup(props) {
    const streamlitDataStore = useStreamlitDataStore()
    const selectionStore = useSelectionStore()
    // Bars and boxes stand on categories: nothing to measure between them
    const measure = useMeasure(
      () => !!props.args.measure && props.args.mode !== 'bars' && props.args.mode !== 'box',
    )
    const zoom = useZoomState(() => props.args.zoomIdentifier)
    return {
      streamlitDataStore,
      selectionStore,
      measure,
      layers: useLayers(),
      zoom,
      zoomStamp: zoom.stamp,
      uniqueId: `series-plot-${++plotIdCounter}`,
    }
  },
  data() {
    return {
      drawPending: false,
      // The zoom the plot shows, kept across redraws (Plotly.newPlot resets it)
      nativeZoom: null as ZoomValue | null,
      // The view and the number of rows picked in this browser
      pickedView: null as string | null,
      pickedTop: null as number | null,
    }
  },
  computed: {
    /** [value, label] of every view, in view_names order then order of appearance. */
    views(): Array<[string, string]> {
      const column = this.args.viewColumn
      if (!column) return []
      const names = new Map<string, string>((this.args.viewNames || []).map(([k, v]) => [String(k), v]))
      const out = new Map<string, string>(names)
      for (const value of (this.columns[column] as unknown[]) || []) {
        const key = String(value)
        if (!out.has(key)) out.set(key, key)
      }
      return [...out.entries()]
    },
    /** The view shown: the state's value, else this browser's pick, else the default. */
    currentView(): string | null {
      const values = this.views.map(([value]) => value)
      if (!values.length) return null
      const identifier = this.args.viewIdentifier
      const fromState = identifier ? this.selectionStore.$state[identifier] : undefined
      for (const candidate of [fromState, this.pickedView, this.args.viewDefault]) {
        if (candidate !== undefined && candidate !== null && values.includes(String(candidate))) {
          return String(candidate)
        }
      }
      return values[0]
    },
    /** [value, label] of the buttons of switch_identifier. */
    switches(): Array<[string, string]> {
      if (!this.args.switchIdentifier) return []
      return (this.args.switchNames || []).map(([k, v]) => [String(k), v] as [string, string])
    },
    /** The switch button that is on: the state's value, else the default. */
    currentSwitch(): string | null {
      const values = this.switches.map(([value]) => value)
      if (!values.length) return null
      const identifier = this.args.switchIdentifier as string
      for (const candidate of [this.selectionStore.$state[identifier], this.args.switchDefault]) {
        if (candidate !== undefined && candidate !== null && values.includes(String(candidate))) {
          return String(candidate)
        }
      }
      return values[0]
    },
    /** Entries of the first clear identifier holding a list. */
    clearCount(): number {
      for (const identifier of this.args.clearIdentifiers || []) {
        const value = this.selectionStore.$state[identifier]
        if (Array.isArray(value)) return value.length
      }
      return 0
    },
    currentViewLabel(): string {
      const view = this.views.find(([value]) => value === this.currentView)
      return view ? view[1] : ''
    },
    topCount(): number | null {
      const choices = this.args.topChoices
      if (!choices || !choices.length) return null
      if (this.pickedTop !== null && choices.includes(this.pickedTop)) return this.pickedTop
      return this.args.topDefault ?? choices[Math.floor(choices.length / 2)]
    },
    /** Rows drawn: those of the view shown, up to the first `topCount` x values. */
    shownRows(): number[] {
      const xs = (this.columns[this.args.xColumn] as unknown[]) || []
      const viewColumn = this.args.viewColumn
      const viewValues = viewColumn ? (this.columns[viewColumn] as unknown[]) || [] : []
      const view = this.currentView
      const limit = this.topCount
      const kept = new Set<string>()
      const rows: number[] = []
      for (let i = 0; i < xs.length; i++) {
        if (view !== null && String(viewValues[i]) !== view) continue
        if (limit !== null) {
          const x = String(xs[i])
          if (!kept.has(x)) {
            if (kept.size >= limit) continue
            kept.add(x)
          }
        }
        rows.push(i)
      }
      return rows
    },
    /** Categories drawn (distinct x values of the rows shown). */
    shownCategories(): number {
      const xs = (this.columns[this.args.xColumn] as unknown[]) || []
      return new Set(this.shownRows.map((i) => String(xs[i]))).size
    },
    /** Height of the whole component: grows with the bars when bar_height is set. */
    totalHeight(): number {
      const base = this.args.height || 400
      const barHeight = this.args.barHeight
      if (!barHeight || !this.horizontal) return base
      return Math.max(base, BAR_PLOT_MARGIN + TOOLBAR_HEIGHT + barHeight * this.shownCategories)
    },
    plotHeight(): number {
      return this.totalHeight - TOOLBAR_HEIGHT
    },
    shownTitle(): string | undefined {
      const title = this.args.title
      if (!title) return undefined
      const shown = title.split('{view}').join(this.currentViewLabel)
      const column = this.args.subtitleColumn
      if (!column) return shown
      const values = (this.columns[column] as unknown[]) || []
      const first = this.shownRows.length ? values[this.shownRows[0]] : undefined
      return first === undefined || first === null || first === '' ? shown : `${shown}: ${first}`
    },
    switchStyle(): Record<string, string> {
      const theme = this.theme
      return {
        '--vs-text': theme?.textColor || '#262730',
        '--vs-background': theme?.backgroundColor || '#ffffff',
        '--vs-accent': theme?.primaryColor || '#1436b8',
        '--vs-font': theme?.font || 'sans-serif',
      }
    },
    measurable(): boolean {
      return !!this.args.measure && this.args.mode !== 'bars' && this.args.mode !== 'box'
    },
    horizontal(): boolean {
      return this.args.orientation === 'h'
    },
    toolbarTools(): PlotTool[] {
      const choices = this.args.topChoices || []
      const top: PlotTool[] = choices.length && this.topCount !== null
        ? [{
            id: 'top',
            group: 'show',
            icon: ICONS.number,
            label: 'Rows shown',
            short: `Top ${this.topCount}`,
            help: 'how many of the first rows the plot shows',
            menu: [{
              kind: 'choice',
              label: 'Show the first',
              options: choices.map((n) => ({ value: String(n), label: String(n) })),
              value: String(this.topCount),
              select: (value: string) => { this.pickedTop = Number(value) },
            }],
            run: () => {},
          }]
        : []
      const clear: PlotTool[] = (this.args.clearIdentifiers || []).length
        ? [{ ...clearSelectionTool(() => this.clearIdentifiers(), this.clearCount), short: 'Clear selection', keep: true }]
        : []
      return [
        ...clear,
        ...top,
        ...(this.measurable ? this.measure.tools(this.measureTitle) : []),
        ...this.layers.tool(this.layerList, 'Series'),
        downloadTool({
          plotId: this.id,
          format: () => imageFormatOf(this.args.imageFormat),
          filename: () => this.args.svgFilename || this.args.title || 'plot',
          height: this.totalHeight,
        }),
      ]
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
    /** True when some position holds points of two or more series. */
    sharedPositions(): boolean {
      const seen = new Map<unknown, string>()
      for (const group of this.series) {
        for (const x of group.x) {
          const owner = seen.get(x)
          if (owner !== undefined && owner !== group.key) return true
          seen.set(x, group.key)
        }
      }
      return false
    },
    /** Points grouped by series, in series_names order then order of appearance. */
    series(): Array<{ key: string; name: string; x: number[]; y: number[]; rows: number[]; text: string[] }> {
      const hoverColumn = this.args.hoverColumn
      const hover = hoverColumn ? (this.columns[hoverColumn] as unknown[]) || [] : []
      const xs = (this.columns[this.args.xColumn] as number[]) || []
      const ys = (this.columns[this.args.yColumn] as number[]) || []
      const seriesColumn = this.args.seriesColumn
      const seriesValues = seriesColumn ? (this.columns[seriesColumn] as unknown[]) || [] : []
      const names = new Map<string, string>((this.args.seriesNames || []).map(([k, v]) => [String(k), v]))

      const groups = new Map<string, { key: string; name: string; x: number[]; y: number[]; rows: number[]; text: string[] }>()
      for (const key of names.keys()) {
        groups.set(key, { key, name: names.get(key) as string, x: [], y: [], rows: [], text: [] })
      }
      for (const i of this.shownRows) {
        const key = seriesColumn ? String(seriesValues[i]) : ''
        if (!groups.has(key)) {
          groups.set(key, { key, name: names.get(key) ?? key, x: [], y: [], rows: [], text: [] })
        }
        const group = groups.get(key)!
        group.x.push(xs[i])
        group.y.push(ys[i])
        group.rows.push(i)
        if (hoverColumn) group.text.push(String(hover[i] ?? ''))
      }
      return [...groups.values()]
    },
    /** The series the toolbar shows or hides. */
    layerList(): Layer[] {
      const colors = this.args.seriesColors || {}
      return this.series.map((s) => ({ key: s.key, label: s.name, color: colors[s.key] }))
    },
    traces(): Plotly.Data[] {
      const colors = this.args.seriesColors || {}
      return this.series.filter((s) => this.layers.visible(s.key)).map((s) => {
        const mode = this.args.mode || 'lines+markers'
        // Horizontal: the categories (x column) on the vertical axis
        const [x, y] = this.horizontal ? [s.y, s.x] : [s.x, s.y]
        const trace: Record<string, unknown> = { x, y, name: s.name }
        if (mode === 'bars') {
          trace.type = 'bar'
          trace.orientation = this.horizontal ? 'h' : 'v'
        } else if (mode === 'box') {
          trace.type = 'box'
          trace.orientation = this.horizontal ? 'h' : 'v'
          // The marks of the picked rows sit in the same group as their box
          trace.offsetgroup = s.key
          trace.boxpoints = 'outliers'
        } else {
          trace.type = 'scatter'
          trace.mode = (this.args.seriesModes || {})[s.key] || mode
        }
        if (this.args.hoverColumn) {
          trace.text = s.text
          trace.hovertemplate = '%{text}<br>%{x}, %{y}<extra>%{fullData.name}</extra>'
          // Hover text only: a bar would otherwise print it on itself
          if (mode === 'bars') trace.textposition = 'none'
        }
        const color = colors[s.key]
        if (color) {
          trace.marker = { color }
          trace.line = { color }
          if (mode === 'box') trace.fillcolor = color + '55'
        }
        return trace as Plotly.Data
      }).concat(this.highlightTraces)
    },
    /** The rows the highlight identifiers pick, drawn on top of the series:
     * a box plot only shows its outliers, so the picked value is marked here. */
    highlightTraces(): Plotly.Data[] {
      const points = this.streamlitDataStore.allDataForDrawing?.highlightPoints as
        | { x: unknown[]; y: unknown[]; series?: unknown[]; text?: unknown[] }
        | undefined
      if (!points || !points.x || points.x.length === 0) return []
      const grouped = this.args.mode === 'box' && this.sharedPositions
      // Grouped boxes: one set of marks per series, each beside its own box
      const groups = grouped
        ? this.series.filter((s) => this.layers.visible(s.key)).map((s) => s.key)
        : [undefined]
      const out: Plotly.Data[] = []
      for (const group of groups) {
        const rows = points.x.map((_, i) => i).filter((i) => group === undefined || String(points.series?.[i]) === group)
        if (rows.length === 0) {
          // Holds the group's place, so the other marks stay beside their boxes
          const [x, y] = this.horizontal ? [[points.y[0]], [points.x[0]]] : [[points.x[0]], [points.y[0]]]
          out.push({ x, y, type: 'scatter', mode: 'markers', showlegend: false, hoverinfo: 'skip',
            offsetgroup: group, marker: { opacity: 0 } } as Plotly.Data)
          continue
        }
        const px = rows.map((i) => points.x[i])
        const py = rows.map((i) => points.y[i])
        const [x, y] = this.horizontal ? [py, px] : [px, py]
        const text = rows.map((i) => String(points.text?.[i] ?? ''))
        const hasText = text.some((t) => t !== '')
        const common: Record<string, unknown> = { x, y, type: 'scatter', mode: 'markers', showlegend: false }
        if (group !== undefined) common.offsetgroup = group
        out.push(
          { ...common, hoverinfo: 'skip', marker: { size: 22, color: SELECTION_ACCENT, opacity: 0.18 } } as Plotly.Data,
          {
            ...common,
            hoverinfo: 'skip',
            marker: { symbol: 'circle-open', size: 17, color: SELECTION_ACCENT, line: { width: 2.5, color: SELECTION_ACCENT } },
          } as Plotly.Data,
          {
            ...common,
            name: 'picked',
            text,
            hovertemplate: hasText ? '%{text}<br>%{x}, %{y}<extra>picked</extra>' : '%{x}, %{y}<extra>picked</extra>',
            marker: { size: 9, color: SELECTION_ACCENT, line: { width: 1.5, color: '#ffffff' } },
          } as Plotly.Data,
        )
      }
      return out
    },
    /** Value-axis range while picked rows are marked over grouped boxes. */
    groupedMarkExtent(): [number, number] | null {
      if (this.args.mode !== 'box' || !this.sharedPositions) return null
      const points = this.streamlitDataStore.allDataForDrawing?.highlightPoints as { y?: unknown[] } | undefined
      if (!points?.y?.length) return null
      let lo = Infinity
      let hi = -Infinity
      for (const s of this.series) {
        if (!this.layers.visible(s.key)) continue
        for (const v of s.y as unknown[]) {
          const n = Number(v)
          if (Number.isFinite(n)) { lo = Math.min(lo, n); hi = Math.max(hi, n) }
        }
      }
      for (const v of points.y) {
        const n = Number(v)
        if (Number.isFinite(n)) { lo = Math.min(lo, n); hi = Math.max(hi, n) }
      }
      if (!Number.isFinite(lo)) return null
      const mode = this.args.yRangeMode || 'nonnegative'
      if (mode === 'tozero') { lo = Math.min(lo, 0); hi = Math.max(hi, 0) }
      if (mode === 'nonnegative') lo = Math.max(lo, 0)
      const pad = (hi - lo || Math.abs(hi) || 1) * 0.05
      return [mode === 'nonnegative' ? Math.max(lo - pad, 0) : lo - pad, hi + pad]
    },
    /** x positions of the points selected through this plot's interactivity
     * identifiers, also when the selection was made in another component. */
    selectedX(): number[] {
      const interactivity = this.args.interactivity || {}
      const xs = (this.columns[this.args.xColumn] as number[]) || []
      const out: number[] = []
      for (const [identifier, column] of Object.entries(interactivity)) {
        const selected = this.selectionStore.$state[identifier]
        const values = this.columns[column] as unknown[] | undefined
        if (selected === undefined || selected === null || !values) continue
        for (let i = 0; i < values.length; i++) {
          if (values[i] === selected) out.push(xs[i])
        }
      }
      return out
    },
    /** Differences along x only: a series has no residue masses to match. */
    measureSpec(): MeasureSpec {
      return { kind: 'span', xQuantity: axisQuantity(this.args.xLabel, 'x') }
    },
    measureTitle(): string {
      return `click two points for their ${this.measureSpec.xQuantity} difference (Esc cancels)`
    },
    /** Identity of the plotted points: other data drops the measurements. */
    measureKey(): string {
      return pointsKey(this.columns[this.args.xColumn], this.columns[this.args.yColumn])
    },
    /** Brackets of the measurements, spaced by the tallest point. */
    measureOverlay(): MeasureOverlay {
      const ys = (this.columns[this.args.yColumn] as number[]) || []
      let yScale = 0
      for (const y of ys) {
        if (Number.isFinite(y) && Math.abs(y) > yScale) yScale = Math.abs(y)
      }
      return this.measure.overlay({
        color: this.theme?.textColor || '#262730',
        background: this.theme?.backgroundColor || 'white',
        yScale,
      })
    },
    layout(): Partial<Plotly.Layout> {
      const line = { color: '#d62728', width: 1.5, dash: 'dash' }
      const selectionShapes = this.selectedX.map((x) =>
        this.horizontal
          ? { type: 'line', xref: 'paper', yref: 'y', x0: 0, x1: 1, y0: x, y1: x, line }
          : { type: 'line', xref: 'x', yref: 'paper', x0: x, x1: x, y0: 0, y1: 1, line },
      ) as Partial<Plotly.Shape>[]
      const mode = this.args.mode || 'lines+markers'
      // The axis along the x column (positions or categories) and the value axis
      const positionAxis: Record<string, unknown> = {
        title: this.args.xLabel ? { text: this.args.xLabel } : undefined,
        showgrid: false,
        automargin: true,
        fixedrange: mode === 'bars',
      }
      const valueAxis: Record<string, unknown> = {
        title: this.args.yLabel ? { text: this.args.yLabel } : undefined,
        showgrid: true,
        rangemode: this.args.yRangeMode || 'nonnegative',
        fixedrange: !!this.args.fixedYRange || mode === 'bars',
        automargin: true,
      }
      // Grouped marks are placed like bars, which would stretch the value axis
      // to zero: the axis keeps the extent of the values instead
      const extent = this.groupedMarkExtent
      if (extent) valueAxis.range = extent
      // Horizontal categories read from the top, in the order of the data
      if (this.horizontal) positionAxis.autorange = 'reversed'
      const xaxis = this.horizontal ? valueAxis : positionAxis
      const yaxis = this.horizontal ? positionAxis : valueAxis
      // A long title wraps to the plot's width instead of running off both edges
      const title = this.shownTitle ? boldTitle(this.shownTitle, this.id) : undefined
      return {
        shapes: [...selectionShapes, ...this.measureOverlay.shapes],
        annotations: this.measureOverlay.annotations,
        // The title just above the plot area: Plotly's own margin leaves a wide gap
        title: title
          ? { text: title.text, y: 1, yref: 'paper', yanchor: 'bottom', pad: { b: 10 } }
          : undefined,
        margin: { t: title ? 18 + 20 * title.lines : 12, r: 16, b: 40, l: 48 },
        showlegend: this.args.showLegend !== false,
        height: this.plotHeight,
        // Bars are read, not explored: no zoom, pan or box select
        ...(mode === 'bars' ? { dragmode: false } : {}),
        xaxis,
        yaxis,
        // Side by side only where series share a position, else full width
        ...(mode === 'bars' ? { barmode: this.sharedPositions ? 'group' : 'overlay' } : {}),
        ...(mode === 'box' ? { boxmode: this.sharedPositions ? 'group' : 'overlay' } : {}),
        // Picked rows drawn over grouped boxes take the boxes' positions
        ...(mode === 'box' && this.sharedPositions ? { scattermode: 'group', scattergap: 0.3, boxgap: 0.3 } : {}),
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
    // A series shown or hidden from the toolbar
    'layers.state.hidden'() {
      this.requestRender()
    },
    // A zoom set from Python (a saved view opened)
    zoomStamp() {
      const incoming = this.zoom.incoming()
      if (incoming === undefined) return
      this.nativeZoom = incoming
      const element = document.getElementById(this.id)
      if (element && (element as unknown as { _fullLayout?: unknown })._fullLayout) {
        void Plotly.relayout(element, this.zoom.layoutFor(incoming))
      }
    },
    measureKey: {
      handler(key: string) {
        this.measure.setDataKey(key)
      },
      immediate: true,
    },
    // Measurements added or removed: redraw the overlay only. The height goes
    // along, or the relayout autosizes the figure to its container
    'measure.revision'() {
      const element = document.getElementById(this.id)
      if (!element || !(element as unknown as { _fullLayout?: unknown })._fullLayout) return
      void Plotly.relayout(element, {
        shapes: this.layout.shapes,
        annotations: this.layout.annotations,
        height: this.layout.height,
      })
    },
    'streamlitDataStore.allDataForDrawing.highlightPoints': {
      handler() {
        this.requestRender()
      },
      deep: true,
    },
    'streamlitDataStore.allDataForDrawing.plotData': {
      handler() {
        this.requestRender()
      },
      deep: true,
    },
    selectedX(next: number[], previous: number[]) {
      if (JSON.stringify(next) !== JSON.stringify(previous)) this.requestRender()
    },
    // Another view or number of rows: a fresh drawing of its own extent
    shownRows(next: number[], previous: number[]) {
      if (next.length === previous.length && next.every((v, i) => v === previous[i])) return
      this.nativeZoom = null
      this.requestRender()
    },
    // By value: the arguments arrive as a new object on every rerun
    argsKey() {
      this.requestRender()
    },
  },
  mounted() {
    this.nativeZoom = this.zoom.incoming() ?? null
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
      await Plotly.newPlot(element, this.traces, withZoom(this.layout, this.nativeZoom), {
        modeBarButtonsToRemove: this.args.mode === 'bars'
          ? ['toImage', 'sendDataToCloud', 'zoom2d', 'pan2d', 'select2d', 'lasso2d', 'zoomIn2d', 'zoomOut2d', 'autoScale2d', 'resetScale2d']
          : ['toImage', 'sendDataToCloud'],
        displaylogo: false,
        responsive: true,
      })
      const plotElement = element as unknown as {
        on: (event: string, handler: (data: { points: Array<{ curveNumber: number; pointIndex: number }> }) => void) => void
      }
      plotElement.on('plotly_click', (eventData) => this.onClick(eventData))
      this.zoom.bindNative(element as unknown as Plotly.PlotlyHTMLElement, (z) => { this.nativeZoom = z })
      this.measure.bindLabelClicks(element)
      this.$nextTick(() => Streamlit.setFrameHeight())
    },
    pickView(value: string): void {
      this.pickedView = value
      const identifier = this.args.viewIdentifier
      // Skip no-op writes (see ProteinSequenceView)
      if (identifier && this.selectionStore.$state[identifier] !== value) {
        this.selectionStore.updateSelection(identifier, value)
      }
    },
    pickSwitch(value: string): void {
      const identifier = this.args.switchIdentifier
      // Skip no-op writes (see ProteinSequenceView)
      if (identifier && this.selectionStore.$state[identifier] !== value) {
        this.selectionStore.updateSelection(identifier, value)
      }
    },
    clearIdentifiers(): void {
      for (const identifier of this.args.clearIdentifiers || []) {
        const value = this.selectionStore.$state[identifier]
        if (value !== undefined && value !== null) {
          this.selectionStore.updateSelection(identifier, null)
        }
      }
    },
    onClick(eventData: { points: Array<{ curveNumber: number; pointIndex: number }> }): void {
      // In measure mode a click picks a point to measure, not a selection
      if (this.measure.active) {
        const point = eventData.points?.[0]
        const s = point ? this.series[point.curveNumber] : undefined
        if (point && s && point.pointIndex < s.x.length) {
          this.measure.pick({ x: s.x[point.pointIndex], y: s.y[point.pointIndex] }, this.measureSpec)
        }
        return
      }
      const interactivity = this.args.interactivity || {}
      if (Object.keys(interactivity).length === 0 || !eventData.points?.length) return
      const point = eventData.points[0]
      // A box stands for many rows: a click on it picks none
      if (this.args.mode === 'box') return
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
.series-plot {
  position: relative;
}

.plot-container {
  width: 100%;
}

.view-switch {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-wrap: nowrap;
  font-family: var(--vs-font);
  font-size: 12px;
}

.view-button {
  height: 24px;
  padding: 0 10px;
  border: 1px solid color-mix(in srgb, var(--vs-text) 16%, transparent);
  border-radius: 999px;
  background: var(--vs-background);
  color: color-mix(in srgb, var(--vs-text) 72%, transparent);
  font: inherit;
  font-weight: 600;
  white-space: nowrap;
  cursor: pointer;
}

.view-button:hover {
  background: color-mix(in srgb, var(--vs-text) 7%, var(--vs-background));
  color: var(--vs-text);
}

.view-button:focus-visible {
  outline: 2px solid var(--vs-accent);
  outline-offset: 1px;
}

.view-button.active {
  background: color-mix(in srgb, var(--vs-accent) 13%, var(--vs-background));
  border-color: var(--vs-accent);
  color: var(--vs-accent);
}
</style>
