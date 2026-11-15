<template>
  <div class="volcano-plot">
    <!-- As tall as the plot: a relayout that autosizes (Plotly does one when a
         box or lasso selection ends) measures this element -->
    <div class="volcano-plot-area">
      <PlotToolbar :plot-id="id" :tools="toolbarTools" :stepper="args.stepper" :settings="args.toolbarSettings" :selection="!!multiSelectEnabled" />
      <div :id="id" class="volcano-container" :style="{ minHeight: `${plotHeight}px` }"></div>
      <MeasureHint v-if="args.measure" :measure="measure" />
    </div>
  </div>
</template>

<script lang="ts">
import { defineComponent, computed, type PropType } from 'vue'
import Plotly from '@/plotly/gl2d'
import { useStreamlitDataStore } from '@/stores/streamlit-data'
import { isClickedRow, usePlotlyScatter } from '@/composables/usePlotlyScatter'
import { placeLabels, type LabelOffset } from '@/composables/labelPlacement'
import { clearSelectionTool, selectionOverlay, SELECTION_LAYOUT, useMultiSelect } from '@/composables/useMultiSelect'
import type { VolcanoPlotComponentArgs, VolcanoData } from '@/types/component'
import { useMeasure, type MeasureOverlay, type MeasureSpec } from '@/composables/useMeasure'
import { axisQuantity, pointsKey } from '@/utils/measure'
import MeasureHint from './MeasureHint.vue'
import { ICONS, TOOLBAR_HEIGHT, type PlotTool } from '@/utils/plotTools'
import { useLayers, type Layer } from '@/composables/useLayers'
import PlotToolbar from './PlotToolbar.vue'
import { useZoomState, withZoom, type ZoomValue } from '@/composables/useZoomState'

/**
 * Compute significance category for a point.
 * Up-regulated: p < pThreshold AND log2fc >= fcThreshold
 * Down-regulated: p < pThreshold AND log2fc <= -fcThreshold
 * Not significant: otherwise
 */
function computeSignificance(
  log2fc: number,
  pvalue: number,
  fcThreshold: number,
  pThreshold: number
): 'up' | 'down' | 'ns' {
  if (pvalue >= pThreshold) return 'ns'
  if (log2fc >= fcThreshold) return 'up'
  if (log2fc <= -fcThreshold) return 'down'
  return 'ns'
}

export default defineComponent({
  name: 'PlotlyVolcano',
  components: { MeasureHint, PlotToolbar },
  props: {
    args: {
      type: Object as PropType<VolcanoPlotComponentArgs>,
      required: true,
    },
    index: {
      type: Number,
      required: true,
    },
  },
  setup(props) {
    const streamlitDataStore = useStreamlitDataStore()

    // Measuring: two points, labelled with their fold change and p-value differences
    const measure = useMeasure(() => !!props.args.measure)
    const measureSpec = computed<MeasureSpec>(() => ({
      kind: 'points',
      xQuantity: axisQuantity(props.args.xLabel, 'log2 Fold Change'),
      yQuantity: axisQuantity(props.args.yLabel, '-log10(p-value)'),
    }))

    // Use shared Plotly scatter composable
    const plotlyScatter = usePlotlyScatter({
      id: computed(() => `volcano-${props.index}`),
      onPointClick: (point) => measure.pick({ x: Number(point.x), y: Number(point.y) }, measureSpec.value),
      interactivity: computed(() => props.args.interactivity || {}),
      getData: () => {
        const data = streamlitDataStore.allDataForDrawing?.volcanoData
        return (data as VolcanoData[]) || []
      },
      title: computed(() => props.args.title),
      imageFormat: computed(() => props.args.imageFormat),
    })

    const zoom = useZoomState(() => props.args.zoomIdentifier)
    const multi = useMultiSelect(computed(() => props.args.multiSelect))

    return {
      streamlitDataStore,
      ...plotlyScatter,
      measure,
      layers: useLayers(),
      multiSelectEnabled: multi.enabled,
      selectedCount: multi.selectedCount,
      multiSelectionKey: multi.selectionKey,
      isRowSelected: multi.isRowSelected,
      applySelectedRows: multi.applyRows,
      clearSelection: multi.clear,
      zoom,
      zoomStamp: zoom.stamp,
    }
  },
  data() {
    return {
      isInitialized: false as boolean,
      // The zoom the plot shows, kept across redraws (Plotly.newPlot resets it)
      nativeZoom: null as ZoomValue | null,
      // Zoom until the user picks box or lasso select in the toolbar; kept
      // across re-renders when the user switches
      dragmode: 'zoom' as string,
      shiftHeld: false as boolean,
      // Where each label (by its place in labelledPoints) sits relative to its point
      labelOffsets: [] as LabelOffset[],
    }
  },
  computed: {
    /** Height of the plot below its toolbar and selection presets; the frame keeps args.height. */
    plotHeight(): number {
      return Math.max(120, (this.args.height || 400) - TOOLBAR_HEIGHT)
    },

    toolbarTools(): PlotTool[] {
      return [
        ...(this.multiSelectEnabled
          ? [this.args.selectionPresets ? this.selectTool() : clearSelectionTool(() => this.clearSelection(), this.selectedCount)]
          : []),
        ...this.measure.tools(),
        ...this.layers.tool(this.layerList),
        this.downloadTool(),
      ]
    },

    /** The point classes the toolbar shows or hides. */
    layerList(): Layer[] {
      return [
        { key: 'up', label: 'Up-regulated', color: this.args.upColor || '#E74C3C' },
        { key: 'down', label: 'Down-regulated', color: this.args.downColor || '#3498DB' },
        { key: 'ns', label: 'Not significant', color: this.args.nsColor || '#95A5A6' },
      ]
    },

    id(): string {
      return `volcano-${this.index}`
    },

    /**
     * Get volcano data from Python.
     */
    volcanoData(): VolcanoData[] {
      const data = this.streamlitDataStore.allDataForDrawing?.volcanoData
      return (data as VolcanoData[]) || []
    },

    /**
     * Check if data is ready for rendering.
     */
    isDataReady(): boolean {
      return Array.isArray(this.volcanoData) && this.volcanoData.length > 0
    },

    /**
     * Threshold values from args.
     */
    fcThreshold(): number {
      return this.args.fcThreshold ?? 1.0
    },

    pThreshold(): number {
      return this.args.pThreshold ?? 0.05
    },

    /**
     * -log10(pThreshold) for threshold line.
     */
    neglog10PThreshold(): number {
      return this.pThreshold > 0 ? -Math.log10(this.pThreshold) : 0
    },

    /**
     * Categorize points by significance.
     */
    categorizedData(): {
      up: { x: number[]; y: number[]; text: string[]; indices: number[] }
      down: { x: number[]; y: number[]; text: string[]; indices: number[] }
      ns: { x: number[]; y: number[]; text: string[]; indices: number[] }
    } {
      const up = { x: [] as number[], y: [] as number[], text: [] as string[], indices: [] as number[] }
      const down = { x: [] as number[], y: [] as number[], text: [] as string[], indices: [] as number[] }
      const ns = { x: [] as number[], y: [] as number[], text: [] as string[], indices: [] as number[] }

      const log2fcCol = this.args.log2fcColumn
      const neglog10pCol = this.args.neglog10pColumn
      const pvalueCol = this.args.pvalueColumn
      const labelCol = this.args.labelColumn

      this.volcanoData.forEach((row, idx) => {
        const log2fc = Number(row[log2fcCol]) || 0
        const neglog10p = Number(row[neglog10pCol]) || 0
        const pvalue = Number(row[pvalueCol]) || 1
        const label = labelCol ? String(row[labelCol] || '') : ''

        const hoverText = labelCol
          ? `${label}<br>log2FC: ${log2fc.toFixed(3)}<br>p-value: ${pvalue.toExponential(2)}`
          : `log2FC: ${log2fc.toFixed(3)}<br>p-value: ${pvalue.toExponential(2)}`

        const category = computeSignificance(log2fc, pvalue, this.fcThreshold, this.pThreshold)

        if (category === 'up') {
          up.x.push(log2fc)
          up.y.push(neglog10p)
          up.text.push(hoverText)
          up.indices.push(idx)
        } else if (category === 'down') {
          down.x.push(log2fc)
          down.y.push(neglog10p)
          down.text.push(hoverText)
          down.indices.push(idx)
        } else {
          ns.x.push(log2fc)
          ns.y.push(neglog10p)
          ns.text.push(hoverText)
          ns.indices.push(idx)
        }
      })

      return { up, down, ns }
    },

    /**
     * The view a volcano opens with: centred on a fold change of 0 so the
     * two arms are equally wide, from 0 up, with the threshold lines inside
     * and some room around the outermost points. A few far outliers (more than
     * three times the 95th percentile away) do not squeeze the volcano: they
     * are left out of the first view and Reset axes keeps it, zooming out
     * shows them.
     */
    initialRange(): { x: [number, number]; y: [number, number] } {
      const xs: number[] = []
      const ys: number[] = []
      for (const row of this.volcanoData) {
        const x = Number(row[this.args.log2fcColumn])
        const y = Number(row[this.args.neglog10pColumn])
        if (Number.isFinite(x)) xs.push(Math.abs(x))
        if (Number.isFinite(y)) ys.push(y)
      }
      const reach = (values: number[], floor: number): number => {
        if (!values.length) return floor
        const sorted = [...values].sort((a, b) => a - b)
        const top = sorted[sorted.length - 1]
        const p95 = sorted[Math.min(sorted.length - 1, Math.floor(sorted.length * 0.95))]
        const cap = p95 > 0 ? p95 * 3 : top
        return Math.max(floor, Math.min(top, cap))
      }
      const xReach = reach(xs, this.fcThreshold * 1.5) * 1.12 || 1
      const yReach = reach(ys, this.neglog10PThreshold * 1.3) * 1.12 || 1
      return { x: [-xReach, xReach], y: [0, yReach] }
    },

    /** Number of points each selection button selects. */
    presetCounts(): { changed: number; up: number; down: number } {
      const { up, down } = this.categorizedData
      return { changed: up.x.length + down.x.length, up: up.x.length, down: down.x.length }
    },

    /** Row indices of the selected points (empty when nothing is selected). */
    selectedRowIndices(): Set<number> {
      const selected = new Set<number>()
      if (!this.multiSelectEnabled) return selected
      // Depend on the selection itself, not only on the data
      void this.multiSelectionKey
      this.volcanoData.forEach((row, idx) => {
        if (this.isRowSelected(row as Record<string, unknown>)) selected.add(idx)
      })
      return selected
    },

    /** The values of this plot's interactivity identifiers, to redraw the ring when one changes. */
    clickedKey(): string {
      const state = this.selectionStore.$state as Record<string, unknown>
      return JSON.stringify(Object.keys(this.args.interactivity || {}).map((identifier) => state[identifier] ?? null))
    },

    /** Row indices of the point a click selected (shown when no set is selected). */
    clickedRowIndices(): Set<number> {
      const clicked = new Set<number>()
      const interactivity = this.args.interactivity || {}
      if (Object.keys(interactivity).length === 0) return clicked
      const state = this.selectionStore.$state as Record<string, unknown>
      this.volcanoData.forEach((row, idx) => {
        if (isClickedRow(row as Record<string, unknown>, interactivity, state)) clicked.add(idx)
      })
      return clicked
    },

    /**
     * Build Plotly data traces.
     */
    plotData(): Plotly.Data[] {
      if (!this.isDataReady) {
        return this.getFallbackData()
      }

      const { up, down, ns } = this.categorizedData

      const traces: Plotly.Data[] = []

      // Not significant points (render first, behind)
      if (ns.x.length > 0 && this.layers.visible('ns')) {
        traces.push({
          type: 'scattergl',
          name: 'Not significant',
          x: ns.x,
          y: ns.y,
          mode: 'markers',
          marker: {
            color: this.args.nsColor || '#95A5A6',
            size: 6,
            opacity: 0.6,
          },
          text: ns.text,
          hoverinfo: 'text',
          customdata: ns.indices,
          ...this.selectionStyle(ns.indices),
        })
      }

      // Down-regulated points
      if (down.x.length > 0 && this.layers.visible('down')) {
        traces.push({
          type: 'scattergl',
          name: 'Down-regulated',
          x: down.x,
          y: down.y,
          mode: 'markers',
          marker: {
            color: this.args.downColor || '#3498DB',
            size: 8,
          },
          text: down.text,
          hoverinfo: 'text',
          customdata: down.indices,
          ...this.selectionStyle(down.indices),
        })
      }

      // Up-regulated points (render last, on top)
      if (up.x.length > 0 && this.layers.visible('up')) {
        traces.push({
          type: 'scattergl',
          name: 'Up-regulated',
          x: up.x,
          y: up.y,
          mode: 'markers',
          marker: {
            color: this.args.upColor || '#E74C3C',
            size: 8,
          },
          text: up.text,
          hoverinfo: 'text',
          customdata: up.indices,
          ...this.selectionStyle(up.indices),
        })
      }

      const ringed = this.multiSelectEnabled && this.selectedRowIndices.size > 0
        ? this.selectedRowIndices
        : this.clickedRowIndices
      if (ringed.size > 0) {
        const x: number[] = []
        const y: number[] = []
        for (const group of [ns, down, up]) {
          group.indices.forEach((rowIndex, i) => {
            if (ringed.has(rowIndex)) {
              x.push(group.x[i])
              y.push(group.y[i])
            }
          })
        }
        traces.push(...selectionOverlay(x, y, 8))
      }

      return traces
    },

    /**
     * Build threshold lines (shapes).
     */
    thresholdShapes(): Partial<Plotly.Shape>[] {
      if (!this.args.showThresholdLines) return []

      const lineStyle = this.args.thresholdLineStyle || 'dash'
      const shapes: Partial<Plotly.Shape>[] = []

      // Horizontal line at -log10(pThreshold)
      shapes.push({
        type: 'line',
        xref: 'paper',
        yref: 'y',
        x0: 0,
        x1: 1,
        y0: this.neglog10PThreshold,
        y1: this.neglog10PThreshold,
        line: {
          color: 'rgba(100, 100, 100, 0.5)',
          width: 1.5,
          dash: lineStyle as Plotly.Dash,
        },
      })

      // Vertical line at +fcThreshold
      shapes.push({
        type: 'line',
        xref: 'x',
        yref: 'paper',
        x0: this.fcThreshold,
        x1: this.fcThreshold,
        y0: 0,
        y1: 1,
        line: {
          color: 'rgba(100, 100, 100, 0.5)',
          width: 1.5,
          dash: lineStyle as Plotly.Dash,
        },
      })

      // Vertical line at -fcThreshold
      shapes.push({
        type: 'line',
        xref: 'x',
        yref: 'paper',
        x0: -this.fcThreshold,
        x1: -this.fcThreshold,
        y0: 0,
        y1: 1,
        line: {
          color: 'rgba(100, 100, 100, 0.5)',
          width: 1.5,
          dash: lineStyle as Plotly.Dash,
        },
      })

      return shapes
    },

    /** The most significant changed points, labelled (at most args.maxLabels). */
    labelledPoints(): Array<{ label: string; log2fc: number; neglog10p: number }> {
      if (!this.args.labelColumn) return []
      const maxLabels = this.args.maxLabels ?? 10
      if (maxLabels <= 0) return []

      const labelCol = this.args.labelColumn
      const log2fcCol = this.args.log2fcColumn
      const neglog10pCol = this.args.neglog10pColumn
      const pvalueCol = this.args.pvalueColumn

      const significantPoints: Array<{ label: string; log2fc: number; neglog10p: number }> = []
      this.volcanoData.forEach((row) => {
        const log2fc = Number(row[log2fcCol]) || 0
        const pvalue = Number(row[pvalueCol]) || 1
        const neglog10p = Number(row[neglog10pCol]) || 0
        const label = String(row[labelCol] || '')
        const category = computeSignificance(log2fc, pvalue, this.fcThreshold, this.pThreshold)
        if (category !== 'ns' && label) {
          significantPoints.push({ label, log2fc, neglog10p })
        }
      })
      // Most significant first
      significantPoints.sort((a, b) => b.neglog10p - a.neglog10p)
      return significantPoints.slice(0, maxLabels)
    },

    /**
     * Labels of the top significant points, each placed where its box
     * covers no other point and no other label (labelOffsets).
     */
    pointAnnotations(): Partial<Plotly.Annotations>[] {
      return this.labelledPoints.map((point, i) => {
        const offset = this.labelOffsets[i] ?? { ax: 0, ay: -25 }
        return {
          x: point.log2fc,
          y: point.neglog10p,
          text: point.label,
          showarrow: true,
          arrowhead: 0,
          arrowsize: 0.5,
          arrowwidth: 1,
          arrowcolor: 'rgba(100, 100, 100, 0.5)',
          ax: offset.ax,
          ay: offset.ay,
          font: {
            size: 10,
            color: this.theme?.textColor || 'black',
          },
          bgcolor: this.theme?.base === 'dark' ? 'rgba(14, 17, 23, 0.8)' : 'rgba(255, 255, 255, 0.8)',
          borderpad: 2,
        }
      })
    },

    /** Identity of the plotted points: other data drops the measurements. */
    measureKey(): string {
      const x = this.args.log2fcColumn
      const y = this.args.neglog10pColumn
      return pointsKey(
        this.volcanoData.map((row) => row[x]),
        this.volcanoData.map((row) => row[y]),
      )
    },

    /** Lines of the measurements. */
    measureOverlay(): MeasureOverlay {
      return this.measure.overlay({
        color: this.theme?.textColor || '#262730',
        background: this.theme?.backgroundColor || 'white',
      })
    },

    /**
     * Build Plotly layout.
     */
    layout(): Partial<Plotly.Layout> {
      return {
        ...this.themeLayout,
        title: this.args.title ? { text: `<b>${this.args.title}</b>` } : undefined,
        showlegend: true,
        legend: {
          orientation: 'h',
          yanchor: 'bottom',
          y: 1.02,
          xanchor: 'right',
          x: 1,
        },
        height: this.plotHeight,
        dragmode: this.dragmode as Plotly.Layout['dragmode'],
        ...SELECTION_LAYOUT,
        xaxis: {
          title: { text: this.args.xLabel || 'log2 Fold Change' },
          range: this.initialRange.x,
          autorange: false,
          zeroline: true,
          zerolinecolor: 'rgba(150, 150, 150, 0.3)',
          zerolinewidth: 1,
        },
        yaxis: {
          title: { text: this.args.yLabel || '-log10(p-value)' },
          range: this.initialRange.y,
          autorange: false,
        },
        shapes: [...this.thresholdShapes, ...this.measureOverlay.shapes],
        annotations: [...this.pointAnnotations, ...this.measureOverlay.annotations],
        margin: {
          l: 60,
          r: 20,
          t: this.args.title ? 80 : 40,
          b: 60,
        },
      }
    },
  },

  watch: {
    // A point class shown or hidden from the toolbar
    'layers.state.hidden'() {
      this.renderPlot()
    },
    // A zoom set from Python (a saved view opened)
    zoomStamp() {
      const incoming = this.zoom.incoming()
      if (incoming === undefined) return
      this.nativeZoom = incoming
      const element = document.getElementById(this.id)
      if (element && (element as unknown as { _fullLayout?: unknown })._fullLayout) {
        const update = this.zoom.layoutFor(incoming)
        // An axis the saved view leaves free opens at the first view, not the full extent
        for (const axis of ['x', 'y'] as const) {
          if (update[`${axis}axis.autorange`] === true) {
            update[`${axis}axis.autorange`] = false
            update[`${axis}axis.range`] = [...this.initialRange[axis]]
          }
        }
        void Plotly.relayout(element, update)
      }
    },
    // The presets bar wrapped or unwrapped: the plot takes the rest of args.height
    plotHeight(height: number) {
      const element = document.getElementById(this.id)
      if (!element || !(element as unknown as { _fullLayout?: unknown })._fullLayout) return
      void Plotly.relayout(element, { height }).then(() => this.updateFrameHeight())
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
      if (!this.isInitialized || !this.isDataReady) return
      const element = document.getElementById(this.id)
      if (!element || !(element as unknown as { _fullLayout?: unknown })._fullLayout) return
      void Plotly.relayout(element, {
        shapes: this.layout.shapes,
        annotations: this.layout.annotations,
        height: this.layout.height,
      })
    },

    isDataReady: {
      handler(newVal: boolean) {
        if (newVal && this.isInitialized) {
          this.renderPlot()
        }
      },
      immediate: true,
    },

    'streamlitDataStore.allDataForDrawing.volcanoData': {
      handler() {
        if (this.isInitialized) {
          this.renderPlot()
        }
      },
      deep: true,
    },

    // Re-render when thresholds change
    fcThreshold() {
      if (this.isInitialized && this.isDataReady) {
        this.renderPlot()
      }
    },

    pThreshold() {
      if (this.isInitialized && this.isDataReady) {
        this.renderPlot()
      }
    },

    // The clicked point changed (here or in another component)
    clickedKey() {
      if (this.isInitialized && this.isDataReady) {
        this.renderPlot()
      }
    },

    // The selected set changed (here or in another component)
    multiSelectionKey() {
      if (this.isInitialized && this.isDataReady) {
        this.renderPlot()
      }
    },
  },

  mounted() {
    this.isInitialized = true
    this.nativeZoom = this.zoom.incoming() ?? null
    this.$nextTick(() => {
      if (this.isDataReady) {
        this.renderPlot()
      }
      this.setupResizeObserver()
    })
  },

  beforeUnmount() {
    this.cleanupResizeObserver()
  },

  methods: {
    async renderPlot(): Promise<void> {
      try {
        const element = document.getElementById(this.id)
        if (!element) {
          console.warn(`PlotlyVolcano: DOM element with id '${this.id}' not found`)
          return
        }

        await Plotly.newPlot(
          this.id, this.plotData, withZoom(this.layout, this.nativeZoom),
          this.getPlotConfig(),
        )
        this.setupClickHandler()
        this.setupSelectHandlers()
        this.placePointLabels()
        // Zoomed or panned: the labels find their free side again
        ;(element as Plotly.PlotlyHTMLElement).on('plotly_relayout', (eventData: Plotly.PlotRelayoutEvent) => {
          if (Object.keys(eventData || {}).some((k) => k.startsWith('xaxis') || k.startsWith('yaxis'))) {
            this.placePointLabels()
          }
        })
        this.zoom.bindNative(element as Plotly.PlotlyHTMLElement, (z) => { this.nativeZoom = z })
        this.measure.bindLabelClicks(element)

        // Update Streamlit iframe height after plot is rendered
        this.$nextTick(() => {
          this.updateFrameHeight()
        })
      } catch (error) {
        console.error('PlotlyVolcano: Error rendering plot:', error)
        this.renderFallback()
      }
    },

    /**
     * Move labels that cover another point or label to a free side, using the
     * axes as drawn; relayouts the annotations when an offset changed.
     */
    placePointLabels(): void {
      const element = document.getElementById(this.id) as (Plotly.PlotlyHTMLElement & {
        _fullLayout?: {
          xaxis: { l2p: (v: number) => number }
          yaxis: { l2p: (v: number) => number }
          _size: { w: number; h: number }
        }
      }) | null
      const full = element?._fullLayout
      if (!element || !full || this.labelledPoints.length === 0) return
      const toPx = (x: number, y: number) => ({ px: full.xaxis.l2p(x), py: full.yaxis.l2p(y) })
      const hidden = new Set(this.layers.state.hidden)
      const { up, down, ns } = this.categorizedData
      const points: Array<{ px: number; py: number }> = []
      for (const [name, group] of [['ns', ns], ['down', down], ['up', up]] as const) {
        if (hidden.has(name)) continue
        group.x.forEach((x, i) => points.push(toPx(x, group.y[i])))
      }
      const offsets = placeLabels(
        this.labelledPoints.map((p) => ({ ...toPx(p.log2fc, p.neglog10p), text: p.label })),
        points, full._size.w, full._size.h,
      )
      if (JSON.stringify(offsets) === JSON.stringify(this.labelOffsets)) return
      this.labelOffsets = offsets
      void Plotly.relayout(element, { annotations: this.layout.annotations })
    },

    /** Plotly's selection styling for a trace whose points are rows `indices`. */
    selectionStyle(indices: number[]): Record<string, unknown> {
      const selected = this.selectedRowIndices
      if (!this.multiSelectEnabled || selected.size === 0) return {}
      const points: number[] = []
      indices.forEach((rowIndex, pointIndex) => {
        if (selected.has(rowIndex)) points.push(pointIndex)
      })
      return {
        selectedpoints: points,
        selected: { marker: { opacity: 1 } },
        unselected: { marker: { opacity: 0.15 } },
      }
    },

    presetLabel(name: string): string {
      const defaults: Record<string, string> = {
        changed: 'All changed', up: 'Up', down: 'Down', clear: 'Clear',
      }
      return this.args.presetLabels?.[name] || defaults[name] || name
    },

    /** Select: the changed, up- or down-regulated points at once, and clear (with the count selected). */
    selectTool(): PlotTool {
      const counts = this.presetCounts
      return {
        id: 'select-presets',
        group: 'view',
        icon: ICONS.select,
        label: 'Select',
        short: 'Select',
        keep: true,
        help: this.selectedCount > 0 ? `${this.selectedCount} selected` : 'select the changed points',
        count: this.selectedCount,
        clear: { label: this.presetLabel('clear'), run: () => this.clearSelection() },
        menu: [{
          kind: 'actions',
          label: 'Select',
          items: [
            { value: 'changed', label: this.presetLabel('changed'), count: counts.changed, disabled: !counts.changed },
            { value: 'up', label: this.presetLabel('up'), count: counts.up, color: this.args.upColor || '#E74C3C', disabled: !counts.up },
            { value: 'down', label: this.presetLabel('down'), count: counts.down, color: this.args.downColor || '#3498DB', disabled: !counts.down },
            { value: 'clear', label: this.presetLabel('clear'), disabled: !this.selectedCount },
          ],
          run: (value: string) => {
            if (value === 'clear') this.clearSelection()
            else this.selectPreset(value as 'changed' | 'up' | 'down')
          },
        }],
        run: () => undefined,
      }
    },

    /** Select every significant (changed), up- or down-regulated point. */
    selectPreset(preset: 'changed' | 'up' | 'down'): void {
      const { up, down } = this.categorizedData
      const indices = preset === 'up' ? up.indices : preset === 'down' ? down.indices : [...up.indices, ...down.indices]
      const rows = indices.map((i) => this.volcanoData[i] as Record<string, unknown>)
      this.applySelectedRows(rows, 'replace')
    },

    setupSelectHandlers(): void {
      if (!this.multiSelectEnabled) return
      const element = document.getElementById(this.id) as Plotly.PlotlyHTMLElement | null
      if (!element) return
      // Whether Shift was held while dragging: then the points are added
      if (!element.dataset.shiftListener) {
        element.dataset.shiftListener = '1'
        element.addEventListener('mousedown', (e: MouseEvent) => {
          this.shiftHeld = e.shiftKey
        }, true)
      }
      element.on('plotly_relayout', (eventData: Plotly.PlotRelayoutEvent) => {
        const mode = (eventData as Record<string, unknown>).dragmode
        if (typeof mode === 'string') this.dragmode = mode
      })
      element.on('plotly_selected', (eventData: Plotly.PlotSelectionEvent | undefined) => {
        // A click without dragging also ends in plotly_selected, without points
        if (!eventData || !eventData.points) return
        const rows: Record<string, unknown>[] = []
        for (const point of eventData.points) {
          const rowIndex = (point as unknown as { customdata?: unknown }).customdata
          if (typeof rowIndex === 'number' && this.volcanoData[rowIndex]) {
            rows.push(this.volcanoData[rowIndex] as Record<string, unknown>)
          }
        }
        if (rows.length === 0 && !this.shiftHeld) {
          this.clearSelection()
          return
        }
        this.applySelectedRows(rows, this.shiftHeld ? 'add' : 'replace')
      })
      element.on('plotly_deselect', () => {
        this.clearSelection()
      })
    },

    getFallbackData(): Plotly.Data[] {
      return [
        {
          type: 'scattergl',
          x: [0],
          y: [0],
          mode: 'markers',
          marker: { color: 'grey' },
          name: 'No Data',
        },
      ]
    },

    async renderFallback(): Promise<void> {
      try {
        const fallbackLayout: Partial<Plotly.Layout> = {
          ...this.themeLayout,
          title: { text: '<b>No Data Available</b>' },
          showlegend: false,
          xaxis: { title: { text: 'log2 Fold Change' } },
          yaxis: { title: { text: '-log10(p-value)' } },
        }

        await Plotly.newPlot(this.id, this.getFallbackData(), fallbackLayout, {
          staticPlot: true,
        })
      } catch (error) {
        console.error('PlotlyVolcano: Failed to render fallback:', error)
      }
    },
  },
})
</script>

<style scoped>
.volcano-plot-area {
  position: relative;
}

.volcano-container {
  position: relative;
  width: 100%;
  min-height: 100px;
}
</style>
