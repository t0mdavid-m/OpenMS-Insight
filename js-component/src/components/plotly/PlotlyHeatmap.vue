<template>
  <div ref="hoverRoot" class="heatmap-plot">
    <MeasureHint v-if="args.measure" :measure="measure" />
    <!-- As tall as the plot: a relayout that autosizes (Plotly does one when a
         box or lasso selection ends) measures this element -->
    <PlotToolbar
      :plot-id="view === '3d' ? sceneId : id"
      :tools="toolbarTools"
      :stepper="args.stepper"
      :settings="args.toolbarSettings"
      :selection="!!multiSelectEnabled && view === '2d'"
    />
    <div class="heatmap-views">
      <!-- The scene is drawn ahead, flat on the map's plot area and out of sight. Going to 3D, the map
           fades out over it as it starts to tilt up (should it not be drawn yet, the map stays until
           it is); back on the map, the map fades in over it as it lies down -->
      <div
        :id="id"
        class="heatmap-container"
        :style="{ minHeight: `${plotHeight}px`, ...(mapOver ? mapOverStyle : {}) }"
      ></div>
      <HeatmapScene3D
        v-if="args.view3d && (sceneWanted || view === '3d')"
        ref="scene"
        :class="{ 'scene-hidden': sceneHidden }"
        :active="view === '3d' || leaving3d"
        :plot-id="sceneId"
        :points="scenePoints"
        :highlight="sceneHighlight"
        :color-stops="colorStops"
        :cmin="colorRange[0]"
        :cmax="colorRange[1]"
        :x-range="sceneXRange"
        :y-range="sceneYRange"
        :x-label="args.xLabel || args.xColumn"
        :y-label="args.yLabel || args.yColumn"
        :z-label="args.zLabel || colorbarLabel"
        :hover-texts="hoverTexts"
        :title="args.title || ''"
        :height="plotHeight"
        :theme="theme"
        :map-area="mapArea"
        :animate="tiltScene"
        @pick="selectRow"
        @rendered="sceneRendered"
        @moved="updateFrameHeight"
        @depth="sceneDepth = $event"
      />
    </div>
    <HeatmapOverview
      v-if="view === '2d' && overviewShown && overviewData && overviewView && overviewPlace"
      :overview="overviewData"
      :view="overviewView"
      :stops="colorStops"
      :left="overviewPlace.left"
      :top="overviewPlace.top"
      :width="overviewPlace.width"
      :height="overviewPlace.height"
      :background="theme?.backgroundColor || '#ffffff'"
      :text="theme?.textColor || '#262730'"
      :accent="theme?.primaryColor || '#1436b8'"
      @move="moveView"
    />
    <PeakHoverTip
      :tip="hover.tip"
      :color="theme?.textColor || '#262730'"
      :background="theme?.backgroundColor || 'white'"
    />
    <ColorbarLegend v-if="showLegendBar" :items="legendItems" @change="setColorSpec" />
  </div>
</template>

<script lang="ts">
import { defineComponent, computed, type PropType } from 'vue'
import Plotly from '@/plotly/gl2d'
import { useStreamlitDataStore } from '@/stores/streamlit-data'
import { usePlotlyScatter } from '@/composables/usePlotlyScatter'
import { clearSelectionTool, selectionOverlay, SELECTION_LAYOUT, useMultiSelect } from '@/composables/useMultiSelect'
import type { HeatmapBox, HeatmapComponentArgs, HeatmapData } from '@/types/component'
import { useMeasure, type MeasureOverlay, type MeasureSpec } from '@/composables/useMeasure'
import { axisQuantity } from '@/utils/measure'
import MeasureHint from './MeasureHint.vue'
import { ICONS, TOOLBAR_HEIGHT, type PlotTool, boldTitle } from '@/utils/plotTools'
import PlotToolbar from './PlotToolbar.vue'
import PeakHoverTip from './PeakHoverTip.vue'
import { usePeakHover, textLines, formatValue as hoverValue } from '@/composables/usePeakHover'
import ColorbarLegend, { type ColorbarLegendItem } from './ColorbarLegend.vue'
import HeatmapOverview from './HeatmapOverview.vue'
import type { OverviewData, OverviewView } from '@/utils/overview'
import HeatmapScene3D, { loadPlotly3D, plotly3D, type MapArea, type ScenePoints } from './HeatmapScene3D.vue'
import { downloadTool as makeDownloadTool } from '@/utils/plotlyDownload'
import { imageFormatOf } from '@/utils/imageExport'
import { normalizeZoom } from '@/composables/useZoomState'
import { useLayers, type Layer } from '@/composables/useLayers'
import { scaleStops, specToStops, type ColorStops, type ColorbarSpec } from '@/utils/colorscale'

/** How far the scene is tilted up when the map over it has faded out (0 flat, 1 up) */
const MAP_FADE_DEPTH = 0.08
type FullLayout = {
  width?: number
  height?: number
  _size?: { l: number; t: number; w: number; h: number }
  xaxis?: { range?: number[] }
  yaxis?: { range?: number[] }
}

/** Height of the colorbar row below the plot. */
const LEGEND_HEIGHT = 30
/** The color option that stands for the intensity column. */
const INTENSITY = '__intensity__'
/** How much one click of "Zoom in" (3D) narrows the window */
const ZOOM_STEP = 0.5
const CUBE_ICON = 'M12 2 3 7v10l9 5 9-5V7l-9-5zm0 2.3L18.6 8 12 11.7 5.4 8 12 4.3zM5 9.7l6 3.4v6.6l-6-3.4V9.7zm8 10v-6.6l6-3.4v6.6l-6 3.4z'
const ZOOM_IN_ICON = 'M15.5 14h-.79l-.28-.27A6.47 6.47 0 0 0 16 9.5 6.5 6.5 0 1 0 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14zm.5-7H9v2H7v1h2v2h1v-2h2V9h-2V7z'
const ZOOM_OUT_ICON = 'M15.5 14h-.79l-.28-.27A6.47 6.47 0 0 0 16 9.5 6.5 6.5 0 1 0 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14zM7 9h5v1H7z'
const FULL_VIEW_ICON = 'M12 5V1L7 6l5 5V7c3.31 0 6 2.69 6 6s-2.69 6-6 6-6-2.69-6-6H4c0 4.42 3.58 8 8 8s8-3.58 8-8-3.58-8-8-8z'

function formatValue(v: number): string {
  if (!Number.isFinite(v)) return '-'
  const a = Math.abs(v)
  if (a !== 0 && (a >= 1e5 || a < 1e-3)) return v.toExponential(1)
  return String(Number(v.toPrecision(3)))
}

/** Longest tick label on a text axis; longer names keep their start and end. */
const MAX_TICK_LABEL = 18

/**
 * Ticks of an axis whose values are text (sample or protein names): long names
 * are shortened in the middle, so they leave the plot its room (the full name
 * stays in the hover), and at most `most` of them are labelled.
 */
function textTicks(values: unknown[], most: number): Partial<Plotly.LayoutAxis> {
  if (!values.length || typeof values[0] !== 'string') return {}
  const names = [...new Set(values as string[])]
  if (!names.some((n) => n.length > MAX_TICK_LABEL) && names.length <= most) return {}
  const step = Math.max(1, Math.ceil(names.length / most))
  const shown = names.filter((_, i) => i % step === 0)
  const half = Math.floor((MAX_TICK_LABEL - 1) / 2)
  return {
    tickmode: 'array',
    tickvals: shown,
    ticktext: shown.map((n) => (n.length > MAX_TICK_LABEL ? `${n.slice(0, half)}…${n.slice(-half)}` : n)),
  }
}

export default defineComponent({
  name: 'PlotlyHeatmap',
  components: { MeasureHint, PeakHoverTip, PlotToolbar, ColorbarLegend, HeatmapScene3D, HeatmapOverview },
  props: {
    args: {
      type: Object as PropType<HeatmapComponentArgs>,
      required: true,
    },
    index: {
      type: Number,
      required: true,
    },
  },
  setup(props) {
    const streamlitDataStore = useStreamlitDataStore()

    // Measuring: two points, labelled with their x and y differences
    const measure = useMeasure(() => !!props.args.measure)
    const measureSpec = computed<MeasureSpec>(() => ({
      kind: 'points',
      xQuantity: axisQuantity(props.args.xLabel, props.args.xColumn || 'x'),
      yQuantity: axisQuantity(props.args.yLabel, props.args.yColumn || 'y'),
    }))

    // Use shared Plotly scatter composable
    const plotlyScatter = usePlotlyScatter({
      id: computed(() => `heatmap-${props.index}`),
      onPointClick: (point) => measure.pick({ x: Number(point.x), y: Number(point.y) }, measureSpec.value),
      interactivity: computed(() => props.args.interactivity || {}),
      getData: () => {
        const data = streamlitDataStore.allDataForDrawing?.heatmapData
        return (data as HeatmapData[]) || []
      },
      title: computed(() => props.args.title),
      imageFormat: computed(() => props.args.imageFormat),
      svgFilename: computed(() => props.args.svgFilename as string | undefined),
      scrollZoom: computed(() => props.args.scrollZoom as boolean | undefined),
      onSelect: computed(() => props.args.onSelect),
    })

    const multi = useMultiSelect(computed(() => props.args.multiSelect))
    const layers = useLayers()
    const hover = usePeakHover()

    return {
      streamlitDataStore,
      ...plotlyScatter,
      measure,
      layers,
      multiSelectEnabled: multi.enabled,
      selectedCount: multi.selectedCount,
      clearMultiSelect: multi.clear,
      hover,
    }
  },
  data() {
    return {
      isInitialized: false as boolean,
      // Tilt the scene up from the map (not when the view opens in 3D)
      tiltScene: false,
      sceneReady: false,
      // Draw the scene ahead, once the map is drawn
      sceneWanted: false,
      // Back on the map, while the scene lies down
      leaving3d: false,
      // The map's plot area in its plot, for the scene to lie on exactly
      mapArea: null as MapArea | null,
      // How far up the scene is (0 flat on the map, 1 tilted), for the map's fade over it
      sceneDepth: 0,
      switching: false,
      dragmode: 'zoom' as string,
      removingOutline: false,
      selectModifier: 'replace' as 'replace' | 'add' | 'remove',
      zoomRange: undefined as { xRange: number[]; yRange: number[] } | undefined,
      colorbarVisible: true,
      userOverrideColorbar: false,
      heatmapResizeObserver: null as ResizeObserver | null,
      // Phase 1: Debounce zoom events to reduce Python round-trips
      zoomDebounceTimer: null as ReturnType<typeof setTimeout> | null,
      pendingZoomRange: undefined as { xRange: number[]; yRange: number[] } | undefined,
      // Phase 1b: Throttle to enforce minimum interval between updates
      zoomThrottleTimer: null as ReturnType<typeof setTimeout> | null,
      lastZoomUpdateTime: 0 as number,
      // Phase 2: Track plot initialization for Plotly.react() optimization
      plotInitialized: false as boolean,
      /** The color option shown: INTENSITY or a label of args.colorColumns. */
      colorBy: INTENSITY as string,
      /** Colors the user picked, per color option; absent: args.colorscale. */
      colorSpecs: {} as Record<string, ColorbarSpec | null>,
      /** Lowest value shown, per color option; absent: everything. */
      minValues: {} as Record<string, number>,
      /** The overview of the whole map is shown while zoomed (args.overview). */
      overviewVisible: true,
      /** The plot area inside the wrapper, in pixels (Plotly's margins move with automargin). */
      plotArea: null as { left: number; top: number; width: number; height: number } | null,
      /** The drawing shown: the 2D map, or (args.view3d) the points as stems in 3D. */
      view: (this.args.view3d && this.args.initialView === '3d' ? '3d' : '2d') as '2d' | '3d',
    }
  },
  computed: {
    /** Height of the plot below its toolbar (and colorbar row); the frame keeps args.height. */
    plotHeight(): number {
      return (this.args.height || 400) - TOOLBAR_HEIGHT - (this.showLegendBar ? LEGEND_HEIGHT : 0)
    },

    toolbarTools(): PlotTool[] {
      const tools: PlotTool[] = []
      const in3d = this.view === '3d'
      if (this.args.view3d) tools.push(this.viewTool)
      if (in3d) tools.push(...this.zoomTools)
      if (this.multiSelectEnabled) tools.push(clearSelectionTool(() => this.clearMultiSelect(), this.selectedCount))
      if (!in3d) tools.push(...this.measure.tools())
      tools.push(...this.layers.tool(this.layerList))
      if (!this.isCategoricalMode) {
        tools.push(this.colorTool)
        tools.push({
          id: 'colorbar',
          group: 'show',
          icon: ICONS.colorbar,
          label: 'Colorbar',
          short: 'Colorbar',
          active: this.effectiveColorbarVisible,
          run: () => this.toggleColorbar(),
        })
      }
      if (this.args.overview && !this.isCategoricalMode && !in3d) {
        tools.push({
          id: 'overview',
          group: 'show',
          icon: ICONS.overview,
          label: 'Overview',
          short: 'Overview',
          help: 'a small picture of the whole map while zoomed; click or drag in it to move the zoom',
          active: this.overviewVisible,
          run: () => {
            this.overviewVisible = !this.overviewVisible
          },
        })
      }
      tools.push(in3d ? this.sceneDownloadTool : this.downloadTool())
      return tools
    },

    /** The raster of the whole map, sent while the plot is zoomed. */
    overviewData(): OverviewData | undefined {
      if (!this.args.overview) return undefined
      return this.streamlitDataStore.allDataForDrawing?.overview as OverviewData | undefined
    },

    /** The zoomed region (an axis that is not zoomed spans the whole map); null when not zoomed. */
    overviewView(): OverviewView | null {
      const overview = this.overviewData
      const zoom = this.pendingZoomRange ?? this.zoomRange
      if (!overview || !zoom) return null
      const full = (range: number[]) => range[0] < 0 && range[1] < 0
      if (full(zoom.xRange) && full(zoom.yRange)) return null
      return {
        x: full(zoom.xRange) ? overview.x : [zoom.xRange[0], zoom.xRange[1]],
        y: full(zoom.yRange) ? overview.y : [zoom.yRange[0], zoom.yRange[1]],
      }
    },

    overviewShown(): boolean {
      return !!this.args.overview && this.overviewVisible && !this.isCategoricalMode
    },

    /**
     * Top right corner of the plot area, at most a fifth of its width and a
     * third of its height; none when the plot is too small to spare it.
     */
    overviewPlace(): { left: number; top: number; width: number; height: number } | null {
      const area = this.plotArea
      const overview = this.overviewData
      if (!area || !overview) return null
      const scale = Math.min(1, (area.width * 0.2) / overview.width, (area.height / 3) / overview.height)
      if (scale < 0.5) return null
      const width = Math.round(overview.width * scale)
      const height = Math.round(overview.height * scale)
      return { left: area.left + area.width - width - 8, top: area.top + 6, width, height }
    },

    /** The "3D" switch: the same points as stems as high as their intensity. */
    viewTool(): PlotTool {
      const in3d = this.view === '3d'
      return {
        id: 'view-3d',
        group: 'view',
        icon: CUBE_ICON,
        label: in3d ? 'Back to the 2D map' : 'Show in 3D',
        short: '3D',
        help: in3d
          ? 'the map seen from above, with box zoom and selection'
          : `the points shown as stems as high as their ${this.colorbarLabel.toLowerCase()}`,
        active: in3d,
        run: () => void this.setView(in3d ? '2d' : '3d'),
      }
    },

    /** Zoom in 3D, where Plotly's own zoom only moves the camera: the window of the map. */
    zoomTools(): PlotTool[] {
      return [
        {
          id: 'zoom-in',
          group: 'view',
          icon: ZOOM_IN_ICON,
          label: 'Zoom in',
          short: 'Zoom in',
          help: this.highlightPoints.x.length > 0 ? 'around the selected point' : 'around the centre',
          run: () => this.zoomBy(ZOOM_STEP),
        },
        {
          id: 'zoom-out',
          group: 'view',
          icon: ZOOM_OUT_ICON,
          label: 'Zoom out',
          short: 'Zoom out',
          run: () => this.zoomBy(1 / ZOOM_STEP),
        },
        {
          id: 'full-view',
          group: 'view',
          icon: FULL_VIEW_ICON,
          label: 'Full view',
          short: 'Full view',
          active: false,
          run: () => this.setZoom({ xRange: [-1, -1], yRange: [-1, -1] }),
        },
      ]
    },

    sceneId(): string {
      return `heatmap-scene-${this.index}`
    },

    sceneDownloadTool(): PlotTool {
      return makeDownloadTool({
        plotId: this.sceneId,
        format: () => imageFormatOf(this.args.imageFormat),
        filename: () => this.args.svgFilename || this.args.title || 'heatmap-3d',
        width: 1000,
        height: this.plotHeight,
        plotly: plotly3D,
      })
    },

    /** The points shown (layers, filter), as stems of the 3D drawing. */
    scenePoints(): ScenePoints {
      const shown = this.shownIndices
      const x = this.xValues
      const y = this.yValues
      const z = this.intensityValues
      const colours = this.shownColorValues
      return {
        x: shown.map((i) => x[i]),
        y: shown.map((i) => y[i]),
        z: shown.map((i) => z[i]),
        colour: shown.map((i) => colours[i]),
        rows: shown,
      }
    },

    sceneHighlight(): { x: number[]; y: number[]; z: number[] } {
      const points = this.streamlitDataStore.allDataForDrawing?.highlightPoints as
        | { x?: number[]; y?: number[]; z?: number[] }
        | undefined
      return { x: points?.x ?? [], y: points?.y ?? [], z: points?.z ?? [] }
    },

    /** Extent of the points sent: the window when nothing is zoomed. */
    dataExtent(): { x: [number, number]; y: [number, number] } | null {
      const xs = this.xValues
      const ys = this.yValues
      if (xs.length === 0) return null
      let x0 = Infinity
      let x1 = -Infinity
      let y0 = Infinity
      let y1 = -Infinity
      for (let i = 0; i < xs.length; i++) {
        if (xs[i] < x0) x0 = xs[i]
        if (xs[i] > x1) x1 = xs[i]
        if (ys[i] < y0) y0 = ys[i]
        if (ys[i] > y1) y1 = ys[i]
      }
      return { x: [x0, x1], y: [y0, y1] }
    },

    // The ranges the map shows (its padding included), so the scene lies exactly on it
    sceneXRange(): number[] | undefined {
      return this.mapArea?.xRange ?? this.xRange
    },

    sceneYRange(): number[] | undefined {
      return this.mapArea?.yRange ?? this.yRange
    },

    /** The scene is shown: in 3D once drawn, and while it lies down before the map returns */
    sceneShown(): boolean {
      return (this.view === '3d' && this.sceneReady) || this.leaving3d
    },
    sceneHidden(): boolean {
      return !this.sceneShown
    },
    /** The map lies over the scene while the scene is shown, fading as the scene tilts */
    mapOver(): boolean {
      return this.sceneShown
    },
    /** The map over the scene, gone once the scene has tilted up a little. In style, not a
     * class: a class binding would replace the classes Plotly gives the map's element. */
    mapOverStyle(): Record<string, string> {
      const opacity = Math.max(0, Math.min(1, 1 - this.sceneDepth / MAP_FADE_DEPTH))
      // Above the scene, whose Plotly layers are positioned too
      return {
        position: 'absolute',
        top: '0',
        left: '0',
        right: '0',
        zIndex: '1',
        pointerEvents: 'none',
        opacity: String(opacity),
      }
    },

    /** The "Color" button: what the points are colored by, and the lowest value shown. */
    colorTool(): PlotTool {
      const option = this.colorOptions.find((o) => o.value === this.colorBy) ?? this.colorOptions[0]
      const [lo, hi] = this.rawColorRange
      // Counts move in whole steps; other values in a hundredth of their range
      const step = this.colorIsInteger ? 1 : hi > lo ? (hi - lo) / 100 : 1
      const min = this.minValues[this.colorBy]
      const menu: PlotTool['menu'] = []
      if (this.colorOptions.length > 1) {
        menu.push({
          kind: 'choice',
          label: 'Color by',
          options: this.colorOptions,
          value: this.colorBy,
          select: (value: string) => this.setColorBy(value),
        })
      }
      menu.push({
        kind: 'range',
        label: `Show ${option.label} from`,
        min: lo,
        max: hi,
        step,
        value: min ?? lo,
        format: (v: number) => (v <= lo ? 'all' : `≥ ${formatValue(v)}`),
        input: (v: number) => this.setMinValue(v <= lo ? undefined : v),
      })
      return {
        id: 'color',
        group: 'show',
        icon: ICONS.palette,
        label: 'Color',
        short: this.colorOptions.length > 1 ? option.label : 'Filter',
        help: 'what the points are colored by, and which are shown',
        menu,
        run: () => {},
      }
    },

    /** Intensity first, then the extra columns of args.colorColumns. */
    colorOptions(): { value: string; label: string }[] {
      const extra = Object.keys(this.args.colorColumns || {}).map((label) => ({ value: label, label }))
      return [{ value: INTENSITY, label: this.args.intensityLabel || 'Intensity' }, ...extra]
    },

    /** Column of the color option shown. */
    activeColorColumn(): string {
      if (this.colorBy === INTENSITY) return this.args.intensityColumn
      return this.args.colorColumns?.[this.colorBy] ?? this.args.intensityColumn
    },

    /** Values of the shown color column, as numbers. */
    rawColorValues(): number[] {
      if (this.colorBy === INTENSITY) return this.intensityValues
      const col = this.activeColorColumn
      return this.heatmapData.map((row) => Number(row[col]))
    },

    /** Smallest and largest finite value of the shown color column. */
    rawColorRange(): [number, number] {
      let lo = Infinity
      let hi = -Infinity
      for (const v of this.rawColorValues) {
        if (!Number.isFinite(v)) continue
        if (v < lo) lo = v
        if (v > hi) hi = v
      }
      return Number.isFinite(lo) ? [lo, hi] : [0, 1]
    },

    /** Every value of the shown color column is a whole number (e.g. a count). */
    colorIsInteger(): boolean {
      const values = this.rawColorValues
      return values.length > 0 && values.every((v) => !Number.isFinite(v) || Number.isInteger(v))
    },

    /** The color option is on a log scale: only the intensity, when args.logScale. */
    colorIsLog(): boolean {
      return this.colorBy === INTENSITY && this.isLogScale
    },

    /** Values as colored: log10 for a log-scaled intensity. */
    shownColorValues(): number[] {
      return this.colorBy === INTENSITY ? this.effectiveColorValues : this.rawColorValues
    },

    /** Range of the colorscale; a filter leaves it as it is, so colors keep their meaning. */
    colorRange(): [number, number] {
      let lo = Infinity
      let hi = -Infinity
      for (const v of this.shownColorValues) {
        if (!Number.isFinite(v)) continue
        if (v < lo) lo = v
        if (v > hi) hi = v
      }
      return Number.isFinite(lo) ? [lo, hi > lo ? hi : lo + 1] : [0, 1]
    },

    /** Column whose values are the layers: args.layerColumn, else the category column. */
    layerColumn(): string | undefined {
      return this.args.layerColumn || this.args.categoryColumn || undefined
    },

    layerValues(): string[] {
      const col = this.layerColumn
      if (!col || !this.isDataReady) return []
      return this.heatmapData.map((row) => String(row[col]))
    },

    /** Layers in order of appearance, with their category color in categorical mode. */
    layerList(): Layer[] {
      const seen = new Set<string>()
      const list: Layer[] = []
      for (const key of this.layerValues) {
        if (seen.has(key)) continue
        seen.add(key)
        list.push({
          key,
          label: key,
          color: this.isCategoricalMode && this.layerColumn === this.args.categoryColumn ? this.getCategoryColor(key) : undefined,
        })
      }
      return list
    },

    /** Indices of the points shown: their layer is on and they pass the value filter. */
    shownIndices(): number[] {
      const n = this.xValues.length
      const layerVals = this.layerValues
      const min = this.isCategoricalMode ? undefined : this.minValues[this.colorBy]
      const values = this.rawColorValues
      const out: number[] = []
      for (let i = 0; i < n; i++) {
        if (layerVals.length && !this.layers.visible(layerVals[i])) continue
        if (min !== undefined && !(values[i] >= min)) continue
        out.push(i)
      }
      return out
    },

    /** The colorscale drawn: the user's colors, or args.colorscale. */
    colorStops(): ColorStops {
      const spec = this.colorSpecs[this.colorBy]
      if (spec) return specToStops(spec, this.theme?.backgroundColor || '#ffffff')
      return scaleStops(this.args.colorscale as string | ColorStops | undefined, this.args.reversescale ?? false)
    },

    showLegendBar(): boolean {
      return !this.isCategoricalMode && this.effectiveColorbarVisible
    },

    legendItems(): ColorbarLegendItem[] {
      const [lo, hi] = this.colorRange
      const label = this.colorOptions.find((o) => o.value === this.colorBy)?.label ?? 'Intensity'
      const text = (v: number) => (this.colorIsLog ? Math.pow(10, v).toExponential(0) : formatValue(v))
      return [
        {
          id: this.colorBy,
          label,
          stops: this.colorStops,
          spec: this.colorSpecs[this.colorBy] ?? null,
          low: text(lo),
          high: text(hi),
          editable: this.args.colorbarEditor !== false,
        },
      ]
    },

    id(): string {
      return `heatmap-${this.index}`
    },

    /** The colorbar sits below the plot and takes no width, so it stays on narrow panels too. */
    effectiveColorbarVisible(): boolean {
      return this.colorbarVisible
    },

    /**
     * Get heatmap data from Python.
     */
    heatmapData(): HeatmapData[] {
      const data = this.streamlitDataStore.allDataForDrawing?.heatmapData
      return (data as HeatmapData[]) || []
    },

    /**
     * Get interactivity mapping from args.
     */
    interactivity(): Record<string, string> {
      return this.args.interactivity || {}
    },

    /**
     * Check if data is ready for rendering.
     */
    isDataReady(): boolean {
      return Array.isArray(this.heatmapData) && this.heatmapData.length > 0
    },

    /**
     * Get x values from data.
     */
    xValues(): number[] {
      if (!this.isDataReady) return []
      const xCol = this.args.xColumn
      return this.heatmapData.map((row) => row[xCol] as number)
    },

    /**
     * Get y values from data.
     */
    yValues(): number[] {
      if (!this.isDataReady) return []
      const yCol = this.args.yColumn
      return this.heatmapData.map((row) => row[yCol] as number)
    },

    /** Tick labels of a text x axis, shortened (see textTicks). */
    xTicks(): Partial<Plotly.LayoutAxis> {
      return textTicks(this.xValues as unknown[], 40)
    },

    /** Tick labels of a text y axis, shortened (see textTicks). */
    yTicks(): Partial<Plotly.LayoutAxis> {
      return textTicks(this.yValues as unknown[], Math.max(4, Math.floor(this.plotHeight / 14)))
    },

    /**
     * Get intensity values from data.
     */
    intensityValues(): number[] {
      if (!this.isDataReady) return []
      const intensityCol = this.args.intensityColumn
      return this.heatmapData.map((row) => row[intensityCol] as number)
    },

    /**
     * Get log-scaled intensity values for coloring.
     */
    logIntensityValues(): number[] {
      return this.intensityValues.map((v) => (v > 0 ? Math.log10(v) : 0))
    },

    /**
     * Check if log scale is enabled (default: true).
     */
    isLogScale(): boolean {
      return this.args.logScale !== false
    },

    /**
     * Get effective color values based on log/linear scale setting.
     */
    effectiveColorValues(): number[] {
      if (!this.isLogScale) {
        return this.intensityValues
      }
      return this.logIntensityValues
    },

    /**
     * Hover text of each point: its intensity, below the hover column's text
     * when one is set.
     */
    hoverTexts(): string[] {
      const base = this.baseHoverTexts
      if (this.colorBy === INTENSITY) return base
      const label = this.colorOptions.find((o) => o.value === this.colorBy)?.label ?? this.colorBy
      const values = this.rawColorValues
      return base.map((text, i) => `${text}<br>${label}: ${formatValue(values[i])}`)
    },

    /** Hover text without the extra color option. */
    baseHoverTexts(): string[] {
      const hoverCol = this.args.hoverColumn
      if (!hoverCol) {
        return this.intensityValues.map((v) => v.toExponential(2))
      }
      const label = this.colorbarLabel
      return this.heatmapData.map((row, i) => {
        const v = this.intensityValues[i]
        const value =
          typeof v !== 'number' || !Number.isFinite(v)
            ? '-'
            : this.isLogScale
              ? v.toExponential(2)
              : String(Number(v.toPrecision(4)))
        const text = row[hoverCol]
        const head = text === null || text === undefined || text === '' ? '' : `${text}<br>`
        return `${head}${label}: ${value}`
      })
    },

    /**
     * Points of the selected value(s) of the `highlight` identifiers, sent by Python.
     */
    highlightPoints(): { x: number[]; y: number[] } {
      const points = this.streamlitDataStore.allDataForDrawing?.highlightPoints as
        | { x?: number[]; y?: number[] }
        | undefined
      return { x: points?.x ?? [], y: points?.y ?? [] }
    },

    /** Points of the selected set (multi_select), sent by Python. */
    multiSelectPoints(): { x: number[]; y: number[] } {
      const points = this.streamlitDataStore.allDataForDrawing?.multiSelectPoints as
        | { x?: number[]; y?: number[] }
        | undefined
      return { x: points?.x ?? [], y: points?.y ?? [] }
    },

    /** The selected set, accent dots with a glow over the points. */
    /** Points outside the selection fade while something is selected. */
    baseOpacity(): number {
      return this.multiSelectEnabled && this.multiSelectPoints.x.length > 0 ? 0.35 : 1
    },

    multiSelectTraces(): Plotly.Data[] {
      if (!this.multiSelectEnabled) return []
      return selectionOverlay(this.multiSelectPoints.x, this.multiSelectPoints.y, 7)
    },

    /**
     * Ring around the highlighted points, drawn over every other trace. It takes
     * no hover or click, so a click always lands on the point beneath it.
     */
    highlightTrace(): Plotly.Data | null {
      if (!this.args.highlight || this.highlightPoints.x.length === 0) return null
      return {
        type: 'scattergl',
        name: 'selected',
        x: this.highlightPoints.x,
        y: this.highlightPoints.y,
        mode: 'markers',
        marker: {
          symbol: 'circle-open',
          size: 16,
          color: this.theme?.textColor || 'black',
          line: { width: 2.5, color: this.theme?.textColor || 'black' },
        },
        hoverinfo: 'skip',
        showlegend: false,
      } as Plotly.Data
    },

    /**
     * Get the colorbar label.
     */
    colorbarLabel(): string {
      return this.args.intensityLabel || 'Intensity'
    },

    /**
     * Check if categorical coloring mode is enabled.
     */
    isCategoricalMode(): boolean {
      return !!this.args.categoryColumn
    },

    /**
     * Get category values from data (when in categorical mode).
     */
    categoryValues(): (string | number)[] {
      if (!this.isDataReady || !this.args.categoryColumn) return []
      return this.heatmapData.map((row) => row[this.args.categoryColumn!] as string | number)
    },

    /**
     * Get unique categories for building separate traces.
     */
    uniqueCategories(): (string | number)[] {
      if (!this.isCategoricalMode) return []
      const seen = new Set<string | number>()
      const unique: (string | number)[] = []
      for (const cat of this.categoryValues) {
        if (!seen.has(cat)) {
          seen.add(cat)
          unique.push(cat)
        }
      }
      return unique
    },

    /**
     * Default color palette for categorical mode.
     * Uses Plotly's qualitative color palette.
     */
    defaultCategoryColors(): string[] {
      return [
        '#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd',
        '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf',
      ]
    },

    /**
     * Get color for a specific category value.
     */
    getCategoryColor(): (category: string | number) => string {
      const customColors = this.args.categoryColors || {}
      const defaults = this.defaultCategoryColors
      let colorIndex = 0

      return (category: string | number): string => {
        const key = String(category)
        if (customColors[key]) {
          return customColors[key]
        }
        // Use default colors in order
        const idx = this.uniqueCategories.indexOf(category)
        return defaults[idx % defaults.length]
      }
    },

    /** The zoom in the shared state, normalized, as JSON (see useZoomState). */
    storedZoom(): string {
      const zoomIdentifier = this.args.zoomIdentifier || 'heatmap_zoom'
      return JSON.stringify(normalizeZoom(this.selectionStore.$state[zoomIdentifier]))
    },

    /**
     * Current x range from zoom state.
     */
    xRange(): number[] | undefined {
      const zoom = this.zoomRange
      if (!zoom) return undefined
      if (zoom.xRange[0] < 0 && zoom.xRange[1] < 0) return undefined
      return zoom.xRange
    },

    /**
     * Current y range from zoom state.
     */
    yRange(): number[] | undefined {
      const zoom = this.zoomRange
      if (!zoom) return undefined
      if (zoom.yRange[0] < 0 && zoom.yRange[1] < 0) return undefined
      return zoom.yRange
    },

    /** Rectangles drawn over the points (e.g. detected features), visible range only. */
    boxRows(): HeatmapBox[] {
      if (!this.args.boxes) return []
      const rows = this.streamlitDataStore.allDataForDrawing?.boxData
      return (rows as HeatmapBox[]) || []
    },

    /** Id of the box selected through ``boxes.selection``, from any component. */
    selectedBoxId(): unknown {
      const identifier = this.args.boxes?.selection
      if (!identifier) return undefined
      return this.selectionStore.$state[identifier]
    },

    /** One line trace with every box outline, each closed and separated by a gap. */
    boxTrace(): Plotly.Data | null {
      if (this.boxRows.length === 0) return null
      const x: (number | null)[] = []
      const y: (number | null)[] = []
      for (const b of this.boxRows) {
        x.push(b.x0, b.x1, b.x1, b.x0, b.x0, null)
        y.push(b.y0, b.y0, b.y1, b.y1, b.y0, null)
      }
      const label = this.args.boxes?.label
      return {
        type: 'scattergl',
        mode: 'lines',
        name: label || 'boxes',
        showlegend: !!label,
        x,
        y,
        line: { color: this.args.boxes?.color || '#2ca02c', width: 1 },
        hoverinfo: 'skip',
        // Not a row of heatmapData: keeps the shared click handler away from it
        customdata: x.map(() => 'box'),
      } as Plotly.Data
    },

    /**
     * Build Plotly data trace(s).
     * In categorical mode, creates separate traces per category.
     * In continuous mode, creates a single trace with colorscale.
     */
    data(): Plotly.Data[] {
      if (!this.isDataReady) {
        return this.getFallbackData()
      }

      const ring = this.highlightTrace
      const overlays = [...this.multiSelectTraces, ring].filter((t): t is Plotly.Data => t !== null)
      // Categorical mode: create separate traces per category
      if (this.isCategoricalMode) {
        return this.withBoxes([...this.buildCategoricalTraces(), ...overlays])
      }

      // Continuous mode: single trace with colorscale. The colorbar is drawn
      // below the plot (ColorbarLegend), where it can be edited.
      const shown = this.shownIndices
      const x = this.xValues
      const y = this.yValues
      const colors = this.shownColorValues
      const texts = this.hoverTexts
      const [cmin, cmax] = this.colorRange

      const points: Plotly.Data[] = [
        {
          type: 'scattergl',
          name: 'points',
          showlegend: false,
          x: shown.map((i) => x[i]),
          y: shown.map((i) => y[i]),
          mode: 'markers',
          marker: {
            color: shown.map((i) => colors[i]),
            colorscale: this.colorStops,
            cmin,
            cmax,
            showscale: false,
            opacity: this.baseOpacity,
          },
          hovertext: shown.map((i) => texts[i]),
          // The read-out is PeakHoverTip (hoverinfo 'none' still fires hover and click)
          hoverinfo: 'none',
          // Row of each point: a layer or filter leaves points out
          customdata: shown,
        } as Plotly.Data,
      ]
      return this.withBoxes([...points, ...overlays])
    },

    /** Thick outline around the selected box. */
    selectedBoxShapes(): Partial<Plotly.Shape>[] {
      const selected = this.selectedBoxId
      if (selected === undefined || selected === null) return []
      return this.boxRows
        .filter((b) => b.id === selected)
        .map((b) => ({
          type: 'rect',
          xref: 'x',
          yref: 'y',
          x0: b.x0,
          x1: b.x1,
          y0: b.y0,
          y1: b.y1,
          line: { color: this.args.boxes?.color || '#2ca02c', width: 3 },
        })) as Partial<Plotly.Shape>[]
    },

    /**
     * Lines of the measurements. They are kept while zooming, which sends
     * other points of the same data.
     */
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
      // In categorical mode, show legend instead of colorbar
      const showLegend = this.isCategoricalMode || !!this.args.boxes?.label
      // Extra right margin for the legend (categorical); the colorbar sits below the plot
      const needsExtraRightMargin = this.isCategoricalMode

      return {
        ...this.themeLayout,
        title: this.args.title ? { text: boldTitle(this.args.title, this.id).text } : undefined,
        showlegend: showLegend,
        legend: showLegend
          ? {
              // Continuous mode only lists the boxes: above the plot, clear of the colorbar
              ...(this.isCategoricalMode
                ? { x: 1.02, y: 1, xanchor: 'left', yanchor: 'top' }
                : { orientation: 'h', x: 0, y: 1.02, xanchor: 'left', yanchor: 'bottom' }),
              bgcolor:
                this.theme?.base === 'dark' ? 'rgba(14, 17, 23, 0.8)' : 'rgba(255, 255, 255, 0.8)',
              bordercolor: this.theme?.base === 'dark' ? '#555' : '#ccc',
              borderwidth: 1,
            }
          : undefined,
        height: this.plotHeight,
        dragmode: this.dragmode as Plotly.Layout['dragmode'],
        ...SELECTION_LAYOUT,
        shapes: [...this.selectedBoxShapes, ...this.measureOverlay.shapes],
        annotations: this.measureOverlay.annotations,
        // automargin: text tick labels (sample or protein names) push the
        // axis title out instead of running into it
        xaxis: {
          title: this.args.xLabel ? { text: this.args.xLabel, standoff: 8 } : undefined,
          range: this.xRange,
          automargin: true,
          ...this.xTicks,
        },
        yaxis: {
          title: this.args.yLabel ? { text: this.args.yLabel, standoff: 8 } : undefined,
          range: this.yRange,
          automargin: true,
          ...this.yTicks,
        },
        margin: {
          l: 60,
          r: needsExtraRightMargin ? 120 : 20,
          t: this.args.title ? 60 : 20,
          b: 60,
        },
      }
    },
  },

  watch: {
    // Measurements added or removed: redraw the overlay only. The height goes
    // along, or the relayout autosizes the figure to its container
    'measure.revision'() {
      if (!this.plotInitialized) return
      void Plotly.relayout(this.id, {
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

    'streamlitDataStore.allDataForDrawing.heatmapData': {
      handler() {
        if (this.isInitialized) {
          this.renderPlot()
        }
      },
      deep: true,
    },

    'streamlitDataStore.allDataForDrawing.boxData': {
      handler() {
        if (this.isInitialized) this.renderPlot()
      },
      deep: true,
    },

    selectedBoxId() {
      if (this.isInitialized && this.plotInitialized) this.renderPlot()
    },

    // Back on the map: draw it at its size, with what changed while it was hidden
    view(view: string) {
      if (view === '2d' && this.isInitialized && !this.plotInitialized) this.$nextTick(() => this.renderPlot())
      else this.$nextTick(() => this.updateFrameHeight())
    },

    // A layer shown or hidden from the toolbar
    'layers.state.hidden'() {
      if (this.isInitialized && this.plotInitialized) this.renderPlot()
    },

    zoomRange: {
      handler() {
        if (this.zoomRange === undefined) return
        // Already the stored zoom (set from Python): nothing to report
        if (JSON.stringify(normalizeZoom(this.zoomRange)) === this.storedZoom) return
        // Update selection store with zoom range
        const zoomIdentifier = this.args.zoomIdentifier || 'heatmap_zoom'
        this.selectionStore.updateSelection(zoomIdentifier, this.zoomRange)
      },
      deep: true,
    },

    // A zoom set from Python (a saved view opened): show it
    storedZoom: {
      handler(stored: string) {
        if (JSON.stringify(normalizeZoom(this.zoomRange)) === stored) return
        const zoom = JSON.parse(stored) as { x?: number[]; y?: number[] } | null
        if (!zoom && this.zoomRange === undefined) return
        this.zoomRange = { xRange: zoom?.x ?? [-1, -1], yRange: zoom?.y ?? [-1, -1] }
        if (this.isInitialized && this.plotInitialized) this.renderPlot()
      },
      immediate: true,
    },
  },

  mounted() {
    this.isInitialized = true
    this.$nextTick(() => {
      if (this.isDataReady) {
        this.renderPlot()
      }
      this.setupHeatmapResizeObserver()
    })
    // Load the 3D drawing early, so the switch to 3D does not wait for it
    if (this.args.view3d) {
      setTimeout(() => {
        void loadPlotly3D()
        this.sceneWanted = true
      }, 1500)
    }
  },

  beforeUnmount() {
    // Clean up debounce timer
    if (this.zoomDebounceTimer) {
      clearTimeout(this.zoomDebounceTimer)
      this.zoomDebounceTimer = null
    }
    // Clean up throttle timer
    if (this.zoomThrottleTimer) {
      clearTimeout(this.zoomThrottleTimer)
      this.zoomThrottleTimer = null
    }
    // Reset plot initialization state
    this.plotInitialized = false
    this.cleanupHeatmapResizeObserver()
  },

  methods: {
    sceneRendered(): void {
      this.sceneReady = true
      if (this.view === '3d') this.updateFrameHeight()
    },

    /** Switch between the map and the scene, tilting from one to the other. */
    async setView(view: '2d' | '3d'): Promise<void> {
      if (view === this.view || this.switching) return
      if (view === '3d') {
        this.tiltScene = true
        this.view = view
        return
      }
      // The toolbar switches at once; the scene lies down onto the map, which fades in over it
      const scene = this.$refs.scene as { flatten?: () => Promise<void> } | undefined
      this.switching = true
      const leave = !!scene && this.sceneReady
      this.leaving3d = leave
      this.view = view
      try {
        if (leave) {
          await scene?.flatten?.()
        }
      } finally {
        this.leaving3d = false
        this.switching = false
      }
    },

    /** Set the zoom of the map (both drawings), as a box zoom of the 2D map does. */
    setZoom(zoom: { xRange: number[]; yRange: number[] }): void {
      if (this.zoomRangesEqual(zoom, this.zoomRange)) return
      this.pendingZoomRange = zoom
      this.debouncedUpdateZoom()
    },

    /** Narrow (factor < 1) or widen the window, around the selected point when it is in it. */
    zoomBy(factor: number): void {
      const extent = this.dataExtent
      const x = this.xRange ?? extent?.x
      const y = this.yRange ?? extent?.y
      if (!x || !y) return
      const [x0, x1] = [Math.min(x[0], x[1]), Math.max(x[0], x[1])]
      const [y0, y1] = [Math.min(y[0], y[1]), Math.max(y[0], y[1])]
      let cx = (x0 + x1) / 2
      let cy = (y0 + y1) / 2
      const mark = this.highlightPoints
      if (factor < 1 && mark.x.length > 0) {
        const mx = mark.x[0]
        const my = mark.y[0]
        if (mx >= x0 && mx <= x1 && my >= y0 && my <= y1) {
          cx = mx
          cy = my
        }
      }
      const hx = ((x1 - x0) * factor) / 2
      const hy = ((y1 - y0) * factor) / 2
      // Zoomed out as far as the data reaches: the full view
      if (factor > 1 && this.xRange === undefined && this.yRange === undefined) return
      this.setZoom({ xRange: [cx - hx, cx + hx], yRange: [cy - hy, cy + hy] })
    },

    /** Select the point of a row, as a click on it in the 2D map does. */
    selectRow(row: number): void {
      const point = this.heatmapData[row]
      const interactivity = this.interactivity
      if (!point || Object.keys(interactivity).length === 0) return
      const changes = Object.entries(interactivity).some(
        ([identifier, column]) =>
          point[column] !== undefined && this.selectionStore.$state[identifier] !== point[column],
      )
      if (changes) {
        for (const [identifier, value] of Object.entries(this.args.onSelect || {})) {
          if (!(identifier in interactivity) && this.selectionStore.$state[identifier] !== value) {
            this.selectionStore.updateSelection(identifier, value)
          }
        }
      }
      for (const [identifier, column] of Object.entries(interactivity)) {
        const value = point[column]
        if (value !== undefined) this.selectionStore.updateSelection(identifier, value)
      }
    },

    /** Append the box outlines, last so trace 0 stays the points. */
    withBoxes(traces: Plotly.Data[]): Plotly.Data[] {
      return this.boxTrace ? [...traces, this.boxTrace] : traces
    },

    /** Select the smallest box containing a clicked position. */
    selectBoxAt(x: number, y: number): void {
      const identifier = this.args.boxes?.selection
      if (!identifier) return
      let best: HeatmapBox | undefined
      let bestArea = Infinity
      for (const b of this.boxRows) {
        if (x < b.x0 || x > b.x1 || y < b.y0 || y > b.y1) continue
        const area = (b.x1 - b.x0) * (b.y1 - b.y0)
        if (area < bestArea) {
          best = b
          bestArea = area
        }
      }
      if (best && best.id !== undefined && best.id !== null) {
        this.selectionStore.updateSelection(identifier, best.id)
      }
    },

    /**
     * Build separate traces for each category.
     * Each category gets its own color and appears in the legend.
     */
    buildCategoricalTraces(): Plotly.Data[] {
      const getColor = this.getCategoryColor
      const traces: Plotly.Data[] = []
      const shown = new Set(this.shownIndices)

      for (const category of this.uniqueCategories) {
        // Get indices of the shown points belonging to this category
        const indices: number[] = []
        for (let i = 0; i < this.categoryValues.length; i++) {
          if (this.categoryValues[i] === category && shown.has(i)) {
            indices.push(i)
          }
        }

        // Extract x, y, and hovertext for this category
        const x = indices.map((i) => this.xValues[i])
        const y = indices.map((i) => this.yValues[i])
        const texts = this.hoverTexts
        const hovertext = indices.map((i) => texts[i])

        traces.push({
          type: 'scattergl',
          name: String(category),
          x,
          y,
          mode: 'markers',
          marker: {
            color: getColor(category),
            size: 6,
            opacity: this.baseOpacity,
          },
          hovertext,
          // The read-out is PeakHoverTip (hoverinfo 'none' still fires hover and click)
          hoverinfo: 'none',
          // Flat row index per point. Plotly's pointIndex is relative to the trace, so
          // without this a click on any category but the first resolves to the wrong
          // row. See setupClickHandler in usePlotlyScatter.ts.
          customdata: indices,
        } as Plotly.Data)
      }

      return traces
    },

    async renderPlot(): Promise<void> {
      try {
        const element = document.getElementById(this.id)
        if (!element) {
          console.warn(`PlotlyHeatmap: DOM element with id '${this.id}' not found`)
          return
        }

        if (!this.plotInitialized) {
          // First render: use newPlot to create the plot
          console.debug('[PlotlyHeatmap] renderPlot: using Plotly.newPlot() (first render)')
          await Plotly.newPlot(this.id, this.data, this.layout, this.getHeatmapPlotConfig())
          this.setupPlotEventHandlers()
          this.measure.bindLabelClicks(element)
          this.plotInitialized = true
        } else {
          // Subsequent renders: use react for efficient updates
          // react() preserves WebGL context and event handlers
          console.debug('[PlotlyHeatmap] renderPlot: using Plotly.react() (update)')
          await Plotly.react(this.id, this.data, this.layout, this.getHeatmapPlotConfig())
          // The points under a hover label may be gone (e.g. after a zoom
          // reset); clear it as a new plot would
          ;(Plotly as unknown as { Fx: { unhover: (id: string) => void } }).Fx.unhover(this.id)
          // Note: No need to re-setup event handlers - they persist with react()
        }

        this.measureMapArea(element)
        // Update Streamlit iframe height after plot is rendered
        this.$nextTick(() => {
          this.updateFrameHeight()
        })
        this.readPlotArea()
      } catch (error) {
        console.error('PlotlyHeatmap: Error rendering plot:', error)
        this.plotInitialized = false // Reset on error so next render uses newPlot
        this.renderFallback()
      }
    },

    /** Where the map draws its points, and the ranges it shows, for the scene to lie on it */
    measureMapArea(element: HTMLElement): void {
      const full = (element as unknown as { _fullLayout?: FullLayout })._fullLayout
      const size = full?._size
      if (!full || !size || !full.width || !full.height || !size.w || !size.h) return
      const bottom = full.height - size.t - size.h
      const area: MapArea = {
        x: [size.l / full.width, (size.l + size.w) / full.width],
        y: [bottom / full.height, (bottom + size.h) / full.height],
        ratio: size.w / size.h,
        xRange: [...(full.xaxis?.range ?? [])] as number[],
        yRange: [...(full.yaxis?.range ?? [])] as number[],
      }
      if (JSON.stringify(area) !== JSON.stringify(this.mapArea)) this.mapArea = area
    },

    getHeatmapPlotConfig(): Partial<Plotly.Config> {
      return this.getPlotConfig()
    },

    setupPlotEventHandlers() {
      const plotElement = document.getElementById(this.id) as Plotly.PlotlyHTMLElement | null
      if (!plotElement) return

      // Handle zoom/pan events (heatmap-specific)
      // Uses debouncing to reduce Python round-trips during drag operations
      plotElement.on('plotly_relayout', (eventData: Plotly.PlotRelayoutEvent) => {
        let newZoom: { xRange: number[]; yRange: number[] } | undefined

        if (eventData['xaxis.autorange']) {
          // Reset zoom
          newZoom = { xRange: [-1, -1], yRange: [-1, -1] }
        } else if (
          eventData['xaxis.range[0]'] !== undefined &&
          eventData['xaxis.range[1]'] !== undefined &&
          eventData['yaxis.range[0]'] !== undefined &&
          eventData['yaxis.range[1]'] !== undefined
        ) {
          newZoom = {
            xRange: [
              eventData['xaxis.range[0]'] as number,
              eventData['xaxis.range[1]'] as number,
            ],
            yRange: [
              eventData['yaxis.range[0]'] as number,
              eventData['yaxis.range[1]'] as number,
            ],
          }
        }

        if (newZoom && !this.zoomRangesEqual(newZoom, this.zoomRange)) {
          // Store pending zoom and debounce the update
          this.pendingZoomRange = newZoom
          this.debouncedUpdateZoom()
        }
      })

      // Handle click events via composable
      this.setupClickHandler()
      this.hover.bindPoints(plotElement, this.$refs.hoverRoot as HTMLElement | null, (point) => [
        `${this.args.xLabel || 'x'} ${hoverValue(point.x)}`,
        `${this.args.yLabel || 'y'} ${hoverValue(point.y)}`,
        ...textLines(point.hovertext),
      ])

      // A click on a point inside a box also selects the box
      plotElement.on('plotly_click', (eventData: Plotly.PlotMouseEvent) => {
        // In measure mode the click measured (see setup)
        if (this.measure.active) return
        const point = eventData.points?.[0]
        if (point && typeof point.x === 'number' && typeof point.y === 'number') {
          this.selectBoxAt(point.x, point.y)
        }
      })
      this.setupMultiSelectHandlers(plotElement)
    },

    /**
     * A box or lasso drawn in select mode is sent to Python, which selects the
     * points in it from the full data (the plot shows only a level of it).
     */
    setupMultiSelectHandlers(plotElement: Plotly.PlotlyHTMLElement) {
      if (!this.multiSelectEnabled) return
      plotElement.addEventListener('mousedown', (e: MouseEvent) => {
        this.selectModifier = e.shiftKey ? 'add' : 'replace'
      }, true)
      plotElement.on('plotly_relayout', (eventData: Plotly.PlotRelayoutEvent) => {
        const mode = (eventData as Record<string, unknown>).dragmode
        if (typeof mode === 'string') this.dragmode = mode
      })
      plotElement.on('plotly_selected', (eventData: Plotly.PlotSelectionEvent | undefined) => {
        if (!eventData) return
        // Plotly reports the removed outline as an empty selection
        if (this.removingOutline) return
        const event = eventData as unknown as {
          range?: { x?: number[]; y?: number[] }
          lassoPoints?: { x?: number[]; y?: number[] }
        }
        let region: Record<string, unknown> | null = null
        if (event.lassoPoints?.x && event.lassoPoints?.y) {
          region = { type: 'lasso', x: event.lassoPoints.x, y: event.lassoPoints.y }
        } else if (event.range?.x && event.range?.y) {
          region = { type: 'box', x: event.range.x, y: event.range.y }
        }
        if (!region) return
        this.streamlitDataStore.sendEvent({ type: 'multi_select', region, mode: this.selectModifier })
        // Python marks the selection; Plotly's own outline would only show the last region.
        // Removing it may fire plotly_deselect, which must not clear the selection just sent.
        this.removingOutline = true
        Promise.resolve(
          Plotly.relayout(this.id, { selections: [] } as unknown as Partial<Plotly.Layout>)
        ).finally(() => {
          this.removingOutline = false
        })
      })
      plotElement.on('plotly_deselect', () => {
        if (this.removingOutline) return
        this.clearMultiSelect()
      })
    },

    /**
     * Debounced zoom update with minimum interval enforcement.
     * - Debounce: Waits 150ms after last event before attempting update
     * - Throttle: Ensures at least 500ms between actual state updates
     */
    debouncedUpdateZoom() {
      const DEBOUNCE_MS = 150
      const MIN_INTERVAL_MS = 500

      // Clear existing debounce timer
      if (this.zoomDebounceTimer) {
        clearTimeout(this.zoomDebounceTimer)
        console.debug('[PlotlyHeatmap] Zoom debounced (timer reset)')
      }

      // Clear existing throttle timer - user is still interacting
      if (this.zoomThrottleTimer) {
        clearTimeout(this.zoomThrottleTimer)
        this.zoomThrottleTimer = null
        console.debug('[PlotlyHeatmap] Throttle timer cancelled (user still interacting)')
      }

      // Set debounce timer
      this.zoomDebounceTimer = setTimeout(() => {
        this.zoomDebounceTimer = null

        // Check if minimum interval has passed since last update
        const now = Date.now()
        const timeSinceLastUpdate = now - this.lastZoomUpdateTime

        if (timeSinceLastUpdate >= MIN_INTERVAL_MS) {
          // Interval passed - update now
          this.applyZoomUpdate()
        } else {
          // Clear any existing throttle timer (we have newer data)
          if (this.zoomThrottleTimer) {
            clearTimeout(this.zoomThrottleTimer)
          }
          // Schedule update for when minimum interval elapses
          const delay = MIN_INTERVAL_MS - timeSinceLastUpdate
          console.debug(`[PlotlyHeatmap] Throttling zoom update, waiting ${delay}ms`)
          this.zoomThrottleTimer = setTimeout(() => {
            this.zoomThrottleTimer = null
            this.applyZoomUpdate()
          }, delay)
        }
      }, DEBOUNCE_MS)
    },

    /**
     * Apply the pending zoom update to state.
     */
    applyZoomUpdate() {
      if (this.pendingZoomRange) {
        console.debug('[PlotlyHeatmap] Applying zoom update:', this.pendingZoomRange)
        this.lastZoomUpdateTime = Date.now()
        this.zoomRange = this.pendingZoomRange
        this.pendingZoomRange = undefined
      }
    },

    /**
     * Check if two zoom ranges are equal (prevents Plotly feedback loops).
     */
    zoomRangesEqual(
      a: { xRange: number[]; yRange: number[] } | undefined,
      b: { xRange: number[]; yRange: number[] } | undefined
    ): boolean {
      if (a === b) return true
      if (!a || !b) return false
      return (
        a.xRange[0] === b.xRange[0] &&
        a.xRange[1] === b.xRange[1] &&
        a.yRange[0] === b.yRange[0] &&
        a.yRange[1] === b.yRange[1]
      )
    },

    async toggleColorbar() {
      this.colorbarVisible = !this.colorbarVisible
      this.userOverrideColorbar = true
      await this.updatePlot()
    },

    /** Redraw after the colorbar row came or went: the plot's height changed with it. */
    async updatePlot() {
      if (!this.plotInitialized) return
      await this.$nextTick()
      await this.renderPlot()
    },

    /** Show or hide a layer, or change the color option: redraw the points. */
    setColorBy(value: string): void {
      this.colorBy = value
      if (this.plotInitialized) void this.renderPlot()
    },

    setMinValue(value: number | undefined): void {
      const next = { ...this.minValues }
      if (value === undefined) delete next[this.colorBy]
      else next[this.colorBy] = value
      this.minValues = next
      if (this.plotInitialized) void this.renderPlot()
    },

    /** New colors from the colorbar editor (null: the plot's own colorscale). */
    setColorSpec(id: string, spec: ColorbarSpec | null): void {
      this.colorSpecs = { ...this.colorSpecs, [id]: spec }
      if (this.plotInitialized) void this.renderPlot()
    },

    setupHeatmapResizeObserver() {
      const plotElement = document.getElementById(this.id)
      if (plotElement && window.ResizeObserver) {
        this.heatmapResizeObserver = new ResizeObserver((entries) => {
          for (const entry of entries) {
            const newWidth = entry.contentRect.width
            if (Math.abs(newWidth - this.plotWidth) > 10) {
              this.plotWidth = newWidth
            }
            requestAnimationFrame(() => this.readPlotArea())
          }
        })
        this.heatmapResizeObserver.observe(plotElement)
      }
    },

    /** Where Plotly drew the plot area, relative to the wrapper (for the overview). */
    readPlotArea(): void {
      const element = document.getElementById(this.id) as (HTMLElement & { _fullLayout?: any }) | null
      const size = element?._fullLayout?._size
      if (!element || !size) return
      // Relative to the wrapper, whatever element in between is positioned
      const outer = (this.$el as HTMLElement).getBoundingClientRect()
      const inner = element.getBoundingClientRect()
      const area = {
        left: inner.left - outer.left + size.l,
        top: inner.top - outer.top + size.t,
        width: size.w,
        height: size.h,
      }
      const old = this.plotArea
      if (old && Object.keys(area).every((k) => old[k as keyof typeof old] === area[k as keyof typeof area])) return
      this.plotArea = area
    },

    /** A click or drag in the overview: zoom to that region, as a box zoom would. */
    moveView(view: OverviewView): void {
      const zoom = this.pendingZoomRange ?? this.zoomRange
      // A reversed axis keeps its direction
      const ordered = (range: [number, number], current?: number[]) =>
        current && current[0] > current[1] ? [range[1], range[0]] : range
      const x = ordered(view.x, zoom?.xRange)
      const y = ordered(view.y, zoom?.yRange)
      void Plotly.relayout(this.id, {
        'xaxis.range[0]': x[0],
        'xaxis.range[1]': x[1],
        'yaxis.range[0]': y[0],
        'yaxis.range[1]': y[1],
      })
    },

    cleanupHeatmapResizeObserver() {
      if (this.heatmapResizeObserver) {
        this.heatmapResizeObserver.disconnect()
        this.heatmapResizeObserver = null
      }
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
          xaxis: { title: { text: 'X' } },
          yaxis: { title: { text: 'Y' } },
        }

        await Plotly.newPlot(this.id, this.getFallbackData(), fallbackLayout, {
          staticPlot: true,
        })
      } catch (error) {
        console.error('PlotlyHeatmap: Failed to render fallback:', error)
      }
    },
  },
})
</script>

<style scoped>
.heatmap-plot {
  position: relative;
}
.heatmap-views {
  position: relative;
}
/* Out of sight under the map: drawn ahead, or until its first drawing is done */
.scene-hidden {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  opacity: 0;
  pointer-events: none;
}

.heatmap-container {
  position: relative;
  width: 100%;
  min-height: 100px;
}
</style>
