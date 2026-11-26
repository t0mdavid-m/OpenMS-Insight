<template>
  <!-- Plotly marks the plot element with classes of its own: classes given from outside go on this wrapper -->
  <div class="heatmap-scene-box">
    <div :id="plotId" class="heatmap-scene" data-own-size :style="{ minHeight: `${height}px` }"></div>
  </div>
</template>

<script lang="ts">
import { defineComponent, type PropType } from 'vue'
import type { Theme } from 'streamlit-component-lib'
import type { ColorStops } from '@/utils/colorscale'

/** The 3D Plotly bundle, loaded once the first scene is drawn. Taken from the
 * package itself, so the 2D bundle stays the one the rest of the view uses. */
type PlotlyModule = typeof import('plotly.js-dist-min')
let plotlyLoading: Promise<PlotlyModule> | null = null
let plotlyLoaded: PlotlyModule | null = null
export function loadPlotly3D(): Promise<PlotlyModule> {
  if (!plotlyLoading) {
    plotlyLoading = import('plotly.js-gl3d-dist-min').then((module) => {
      plotlyLoaded = ((module as unknown as { default?: PlotlyModule }).default ?? module) as PlotlyModule
      return plotlyLoaded
    })
  }
  return plotlyLoading
}
/** The 3D bundle once loaded, for the image download of a scene. */
export function plotly3D(): PlotlyModule | null {
  return plotlyLoaded
}

// Floor the stems drop to. Far below zero so the vertical segment always
// reaches the bottom of the z range, which starts at 0.
const STEM_FLOOR = -1e12

type Vec = { x: number; y: number; z: number }
/** Where the camera looks from (around the centre, angles in radians), and the scene box's shape */
interface SceneCamera {
  azimuth: number
  elevation: number
  distance: number
  /** Width and height of the scene box against its depth (y) */
  width: number
  height: number
  /** Where in the plot the scene is drawn, as fractions of its width and height */
  domain: { x: number[]; y: number[] }
  /** How strongly the axes show: 0 flat on the map, whose own axes are there, 1 tilted */
  axes: number
}
/** Where a 2D map draws its points (fractions of its plot), its width against its height, and its ranges */
export interface MapArea {
  x: number[]
  y: number[]
  ratio: number
  xRange: number[]
  yRange: number[]
}
const FULL = { x: [0, 1], y: [0, 1] }
const UP: Vec = { x: 0, y: 0, z: 1 }
function cameraOf(eye: Vec, width: number, height: number): SceneCamera {
  const distance = Math.hypot(eye.x, eye.y, eye.z) || 1
  return {
    azimuth: Math.atan2(eye.y, eye.x),
    elevation: Math.asin(Math.max(-1, Math.min(1, eye.z / distance))),
    distance,
    width,
    height,
    domain: FULL,
    axes: 1,
  }
}
function eyeOf(camera: SceneCamera): Vec {
  const r = camera.distance * Math.cos(camera.elevation)
  return {
    x: r * Math.cos(camera.azimuth),
    y: r * Math.sin(camera.azimuth),
    z: camera.distance * Math.sin(camera.elevation),
  }
}
/** The view the scene opens with: tilted, retention time along the long side */
const TILTED_EYE: Vec = { x: -0.95, y: -1.6, z: 0.9 }
const TILTED: SceneCamera = cameraOf(TILTED_EYE, 1.8, 0.7)
/** Height of the flat scene box on screen against the camera's distance, measured on Plotly's 3D camera */
const FLAT_FIT = 0.824
/** Length of the tilt between the map and the scene, in ms */
const TILT_MS = 900
const TILT_STEPS = 30
/** How far up the scene is before its stems start to rise */
const STEMS_FROM = 0.12
/** How far up the scene is before its axes start to show */
const AXES_FROM = 0.08
/** Wait of a drawing out of sight after the last change, so zooming the map stays quick */
const HIDDEN_DELAY_MS = 400

const ease = (t: number) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2)
/** From one camera to the other: round the centre the short way, the box's shape along */
function between(a: SceneCamera, b: SceneCamera, t: number): SceneCamera {
  let turn = b.azimuth - a.azimuth
  if (turn > Math.PI) turn -= 2 * Math.PI
  if (turn < -Math.PI) turn += 2 * Math.PI
  const lerp = (u: number, v: number) => u + (v - u) * t
  // The stems rise only once the scene has lifted off the map (and are down before it lies on it),
  // so none show through the map as it fades
  const axes = lerp(a.axes, b.axes)
  let height = lerp(a.height, b.height)
  if (a.axes !== b.axes) {
    const [low, high] = a.axes < b.axes ? [a, b] : [b, a]
    const up = (axes - low.axes) / (high.axes - low.axes)
    height = low.height + (high.height - low.height) * Math.max(0, (up - STEMS_FROM) / (1 - STEMS_FROM))
  }
  return {
    azimuth: a.azimuth + turn * t,
    elevation: lerp(a.elevation, b.elevation),
    distance: lerp(a.distance, b.distance),
    width: lerp(a.width, b.width),
    height,
    domain: {
      x: [lerp(a.domain.x[0], b.domain.x[0]), lerp(a.domain.x[1], b.domain.x[1])],
      y: [lerp(a.domain.y[0], b.domain.y[0]), lerp(a.domain.y[1], b.domain.y[1])],
    },
    axes,
  }
}
/** After the next paint: a change shown at once, before a slow drawing */
function afterPaint(): Promise<void> {
  return new Promise((resolve) => requestAnimationFrame(() => setTimeout(resolve, 0)))
}
/** A CSS colour (#rgb, #rrggbb or rgb()) as red, green and blue */
function rgbOf(colour: string, fallback: number[]): number[] {
  let rgb: number[] | null = null
  const hex = /^#([0-9a-f]{3}|[0-9a-f]{6})$/i.exec(colour.trim())
  if (hex) {
    const h = hex[1].length === 3 ? hex[1].replace(/./g, (c) => c + c) : hex[1]
    rgb = [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16))
  } else {
    const m = /^rgba?\(([^)]+)\)$/i.exec(colour.trim())
    if (m)
      rgb = m[1]
        .split(',')
        .slice(0, 3)
        .map((v) => parseFloat(v))
  }
  return rgb && !rgb.some((v) => Number.isNaN(v)) ? rgb : fallback
}
/** A colour part of the way from the background to the foreground. Opaque: the 3D scene draws a
 * transparent line light, not faint. */
function mix(background: number[], foreground: number[], part: number): string {
  const t = Math.max(0, Math.min(1, part))
  const [r, g, b] = background.map((v, i) => Math.round(v + (foreground[i] - v) * t))
  return `rgb(${r}, ${g}, ${b})`
}
function reducedMotion(): boolean {
  return typeof window !== 'undefined' && !!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
}

export interface ScenePoints {
  x: number[]
  y: number[]
  z: number[]
  /** Colour value of each point, on the scale of `cmin`..`cmax` */
  colour: number[]
  /** Row of each point in the data, for clicks */
  rows: number[]
}

export default defineComponent({
  name: 'HeatmapScene3D',
  props: {
    plotId: { type: String, required: true },
    points: { type: Object as PropType<ScenePoints>, required: true },
    highlight: {
      type: Object as PropType<{ x: number[]; y: number[]; z: number[] }>,
      default: () => ({ x: [], y: [], z: [] }),
    },
    colorStops: { type: Array as unknown as PropType<ColorStops>, required: true },
    cmin: { type: Number, required: true },
    cmax: { type: Number, required: true },
    /** The window drawn: the zoom, else the extent of the points */
    xRange: { type: Array as unknown as PropType<number[] | undefined>, default: undefined },
    yRange: { type: Array as unknown as PropType<number[] | undefined>, default: undefined },
    xLabel: { type: String, default: '' },
    yLabel: { type: String, default: '' },
    zLabel: { type: String, default: 'Intensity' },
    hoverTexts: { type: Array as PropType<string[]>, default: () => [] },
    title: { type: String, default: '' },
    height: { type: Number, required: true },
    theme: { type: Object as PropType<Theme | undefined>, default: undefined },
    /** Colour of the selected point; default: the text colour */
    highlightColor: { type: String, default: '' },
    /** The 2D map's plot area: the flat scene lies exactly on it */
    mapArea: { type: Object as PropType<MapArea | null>, default: null },
    /** Shown: false while the 2D map is, when the scene is drawn ahead, flat, out of sight */
    active: { type: Boolean, default: true },
    /** Tilt up from the 2D map when shown */
    animate: { type: Boolean, default: false },
  },
  emits: ['pick', 'rendered', 'moved', 'depth'],
  data() {
    return {
      drawPending: false,
      plotted: false,
      tilting: false,
      renderAfterTilt: false,
      // Shown and not tilted up yet: the next drawing is flat, then tilts
      tiltPending: false,
      /** How far up the scene is drawn now: 0 flat on the map, 1 tilted */
      up: 0,
      renderTimer: null as ReturnType<typeof setTimeout> | null,
    }
  },
  computed: {
    /** The selected point's colour: the text colour, as its ring on the 2D map. */
    markColor(): string {
      return this.highlightColor || this.theme?.textColor || '#262730'
    },
    maxZ(): number {
      let max = 0
      for (const z of this.points.z) if (z > max) max = z
      for (const z of this.highlight.z) if (z > max) max = z
      return max || 1
    },
    /** One line trace of stems, each from the floor to its point and back */
    traces(): Record<string, unknown>[] {
      const { x, y, z, colour, rows } = this.points
      const sx: number[] = []
      const sy: number[] = []
      const sz: number[] = []
      const sc: number[] = []
      const sr: number[] = []
      const st: string[] = []
      for (let i = 0; i < x.length; i++) {
        if (!(z[i] > 0)) continue
        sx.push(x[i], x[i], x[i])
        sy.push(y[i], y[i], y[i])
        sz.push(STEM_FLOOR, z[i], STEM_FLOOR)
        sc.push(colour[i], colour[i], colour[i])
        sr.push(rows[i], rows[i], rows[i])
        const text = this.hoverTexts[rows[i]] ?? ''
        st.push(text, text, text)
      }
      const xLabel = this.xLabel || 'x'
      const yLabel = this.yLabel || 'y'
      const traces: Record<string, unknown>[] = [
        {
          type: 'scatter3d',
          mode: 'lines',
          name: 'points',
          x: sx,
          y: sy,
          z: sz,
          line: {
            width: 2,
            color: sc,
            colorscale: this.colorStops,
            cmin: this.cmin,
            cmax: this.cmax,
            showscale: false,
          },
          customdata: sr,
          hovertext: st,
          hovertemplate: `${xLabel}: %{x}<br>${yLabel}: %{y}<br>%{hovertext}<extra></extra>`,
          connectgaps: false,
          showlegend: false,
        },
        // A dot on top of each stem: easier to point at and click than the line
        {
          type: 'scatter3d',
          mode: 'markers',
          name: 'tops',
          x: sx.filter((_, i) => i % 3 === 1),
          y: sy.filter((_, i) => i % 3 === 1),
          z: sz.filter((_, i) => i % 3 === 1),
          marker: {
            size: 2,
            color: sc.filter((_, i) => i % 3 === 1),
            colorscale: this.colorStops,
            cmin: this.cmin,
            cmax: this.cmax,
            showscale: false,
          },
          customdata: sr.filter((_, i) => i % 3 === 1),
          hovertext: st.filter((_, i) => i % 3 === 1),
          hovertemplate: `${xLabel}: %{x}<br>${yLabel}: %{y}<br>%{hovertext}<extra></extra>`,
          showlegend: false,
        },
      ]
      const hx: number[] = []
      const hy: number[] = []
      const hz: number[] = []
      for (let i = 0; i < this.highlight.x.length; i++) {
        const zi = this.highlight.z[i]
        if (!(zi > 0)) continue
        hx.push(this.highlight.x[i], this.highlight.x[i], this.highlight.x[i])
        hy.push(this.highlight.y[i], this.highlight.y[i], this.highlight.y[i])
        hz.push(STEM_FLOOR, zi, STEM_FLOOR)
      }
      if (hx.length > 0) {
        traces.push({
          type: 'scatter3d',
          mode: 'lines',
          name: 'selected',
          x: hx,
          y: hy,
          z: hz,
          line: { width: 6, color: this.markColor },
          hoverinfo: 'skip',
          showlegend: false,
        })
        // A ring on top of each, as the 2D map rings the selected point
        traces.push({
          type: 'scatter3d',
          mode: 'markers',
          name: 'selected top',
          x: hx.filter((_, i) => i % 3 === 1),
          y: hy.filter((_, i) => i % 3 === 1),
          z: hz.filter((_, i) => i % 3 === 1),
          marker: { size: 7, symbol: 'circle-open', color: this.markColor, line: { width: 3, color: this.markColor } },
          hoverinfo: 'skip',
          showlegend: false,
        })
      }
      return traces
    },
    layout(): Record<string, unknown> {
      const axis = (title: string, range: number[] | undefined) => ({
        title: { text: title },
        ...(range ? { range: [...range].sort((a, b) => a - b), autorange: false } : {}),
      })
      return {
        title: this.title ? { text: `<b>${this.title}</b>` } : undefined,
        paper_bgcolor: this.theme?.backgroundColor,
        plot_bgcolor: this.theme?.secondaryBackgroundColor,
        font: { color: this.theme?.textColor || 'black', family: this.theme?.font || 'Arial' },
        height: this.height,
        margin: { l: 0, r: 0, b: 0, t: this.topMargin },
        showlegend: false,
        scene: {
          xaxis: axis(this.xLabel, this.xRange),
          yaxis: axis(this.yLabel, this.yRange),
          zaxis: { title: { text: this.zLabel }, range: [0, this.maxZ] },
          // As wide as the map: retention time along the long side
          aspectmode: 'manual',
        },
      }
    },
    /** The top margin, as the map's, so the title stays put; and the height left for the scene below it */
    topMargin(): number {
      return this.title ? 60 : 20
    },
    paperHeight(): number {
      return Math.max(1, this.height - this.topMargin)
    },
    renderKey(): string {
      return JSON.stringify([
        this.layout,
        this.points.rows.length,
        this.highlight,
        this.cmin,
        this.cmax,
        this.colorStops,
      ])
    },
  },
  watch: {
    active(active: boolean) {
      if (!active) return
      this.tiltPending = this.animate && !reducedMotion()
      if (this.plotted && !this.renderTimer && !this.drawPending && !this.tilting) {
        if (this.tiltPending) {
          this.tiltPending = false
          void this.tilt(this.flat(), TILTED)
        } else void this.toCamera(TILTED)
      } else this.requestRender()
    },
    // The map moved or was zoomed: lie on it again
    mapArea() {
      if (!this.active) this.requestRender()
    },
    points: {
      handler() {
        this.requestRender()
      },
      deep: false,
    },
    renderKey() {
      this.requestRender()
    },
  },
  mounted() {
    this.requestRender()
  },
  beforeUnmount() {
    if (this.renderTimer) clearTimeout(this.renderTimer)
    const element = document.getElementById(this.plotId)
    if (element && this.plotted) {
      void loadPlotly3D().then((Plotly) => Plotly.purge(element))
    }
  },
  methods: {
    /** Draw the points again: at once when shown, out of sight after a pause. */
    requestRender(): void {
      if (this.tilting) {
        this.renderAfterTilt = true
        return
      }
      if (this.renderTimer) {
        clearTimeout(this.renderTimer)
        this.renderTimer = null
      }
      // Out of sight, drawn once the map has settled; shown, at once
      if (!this.active) {
        this.renderTimer = setTimeout(() => {
          this.renderTimer = null
          this.draw()
        }, HIDDEN_DELAY_MS)
        return
      }
      this.draw()
    },
    /** One drawing per update, in a task of its own (see Plotly3D). */
    draw(): void {
      if (this.drawPending) return
      this.drawPending = true
      setTimeout(() => {
        this.drawPending = false
        void this.renderPlot()
      }, 0)
    },
    async renderPlot(): Promise<void> {
      const Plotly = await loadPlotly3D()
      const element = document.getElementById(this.plotId) as (HTMLElement & { on?: Function }) | null
      if (!element) return
      // Still flat on the map when shown: tilt it up, never jump
      if (this.active && this.up < 1 && this.animate && !reducedMotion()) this.tiltPending = true
      const flat = !this.active || this.tiltPending
      const layout = { ...this.layout, width: element.clientWidth || undefined } as Record<string, unknown>
      layout.scene = {
        ...(layout.scene as object),
        ...this.sceneLayout(flat ? this.flat() : TILTED),
        // A rotation of the user stays across new points and zooms; flat out of sight
        uirevision: flat ? 'flat' : 'scene',
      }
      // The axes' colours, from relayout keys into the layout
      for (const [key, value] of Object.entries(this.axisStyle(flat ? 0 : 1))) {
        const path = key.split('.')
        let node = layout as Record<string, unknown>
        for (const part of path.slice(0, -1)) {
          node[part] = { ...((node[part] as object) ?? {}) }
          node = node[part] as Record<string, unknown>
        }
        node[path[path.length - 1]] = value
      }
      await Plotly.react(
        element,
        this.traces as Plotly.Data[],
        layout as Partial<Plotly.Layout>,
        {
          modeBarButtonsToRemove: ['toImage', 'sendDataToCloud'],
          displaylogo: false,
          responsive: true,
          showTips: false,
        } as Partial<Plotly.Config>,
      )
      if (!this.plotted) {
        this.plotted = true
        ;(element as unknown as Plotly.PlotlyHTMLElement).on('plotly_click', (event: Plotly.PlotMouseEvent) => {
          const row = event.points?.[0]?.customdata
          if (typeof row === 'number') this.$emit('pick', row)
        })
      }
      // How far up it is drawn: 0 flat on the map, 1 tilted
      this.up = flat ? 0 : 1
      this.$emit('depth', this.up)
      this.$emit('rendered')
      if (this.active && this.tiltPending) {
        this.tiltPending = false
        await this.tilt(this.flat(), TILTED)
      }
    },
    /** Straight to a camera, without the tilt */
    async toCamera(camera: SceneCamera): Promise<void> {
      const element = document.getElementById(this.plotId)
      if (!element) return
      const Plotly = await loadPlotly3D()
      await Plotly.relayout(element, this.sceneRelayout(camera) as unknown as Partial<Plotly.Layout>)
      this.up = camera.axes
      this.$emit('depth', camera.axes)
    },
    /** Straight from above with the stems flat, as wide as the plot: the scene drawn as the 2D map */
    flat(): SceneCamera {
      const area = this.mapArea
      const element = document.getElementById(this.plotId)
      const ratio = area?.ratio ?? (element && this.height > 0 ? element.clientWidth / this.height : TILTED.width)
      // Straight from above, from the low-y side, so y runs up the screen as on the map. The box,
      // as wide against its depth as the map's plot area, fills that area: in this camera the box
      // looks FLAT_FIT times as tall as the camera is far.
      return {
        azimuth: -Math.PI / 2,
        elevation: (89.9 * Math.PI) / 180,
        distance: 1 / FLAT_FIT,
        width: ratio,
        height: 0.0001,
        axes: 0,
        domain: area ? { x: area.x, y: area.y.map((v) => Math.min(1, (v * this.height) / this.paperHeight)) } : FULL,
      }
    },
    /** The axes' colours at a strength, as relayout keys */
    axisStyle(strength: number): Record<string, string | boolean> {
      const text = rgbOf(this.theme?.textColor || '#444', [68, 68, 68])
      const paper = rgbOf(this.theme?.backgroundColor || '#fff', [255, 255, 255])
      const style: Record<string, string | boolean> = {}
      for (const axis of ['xaxis', 'yaxis', 'zaxis']) {
        style[`scene.${axis}.tickfont.color`] = mix(paper, text, strength)
        style[`scene.${axis}.title.font.color`] = mix(paper, text, strength)
        style[`scene.${axis}.gridcolor`] = mix(paper, text, 0.2 * strength)
        style[`scene.${axis}.zerolinecolor`] = mix(paper, text, 0.5 * strength)
        // Left out while flat: lines of the box seen edge on
        style[`scene.${axis}.showgrid`] = strength > 0
        style[`scene.${axis}.zeroline`] = strength > 0
      }
      return style
    },
    /** A camera as relayout keys: the view, the box, where it is drawn and its axes */
    sceneRelayout(camera: SceneCamera): Record<string, unknown> {
      const scene = this.sceneLayout(camera)
      return {
        'scene.camera': scene.camera,
        'scene.aspectratio': scene.aspectratio,
        'scene.domain': scene.domain,
        // The axes come in once the map over the scene has faded, as the scene lifts off it
        ...this.axisStyle(Math.max(0, (camera.axes - AXES_FROM) / (1 - AXES_FROM))),
      }
    },
    sceneLayout(camera: SceneCamera): Record<string, unknown> {
      return {
        camera: { eye: eyeOf(camera), up: UP, center: { x: 0, y: 0, z: 0 } },
        aspectratio: { x: camera.width, y: 1, z: camera.height },
        domain: camera.domain,
      }
    },
    /** The camera the scene is seen with now, the user's rotation included */
    currentCamera(): SceneCamera {
      const element = document.getElementById(this.plotId) as unknown as {
        layout?: { scene?: { camera?: { eye?: Vec }; aspectratio?: Vec; domain?: { x: number[]; y: number[] } } }
      } | null
      const scene = element?.layout?.scene
      const camera = cameraOf(
        scene?.camera?.eye ?? TILTED_EYE,
        scene?.aspectratio?.x ?? TILTED.width,
        scene?.aspectratio?.z ?? TILTED.height,
      )
      return scene?.domain ? { ...camera, domain: scene.domain } : camera
    },
    /** Move the camera and the stems' height from one view to the other. */
    async tilt(from: SceneCamera, to: SceneCamera): Promise<void> {
      const element = document.getElementById(this.plotId)
      if (!element || reducedMotion()) return
      // At once, so a drawing asked for meanwhile waits for the tilt
      this.tilting = true
      try {
        const Plotly = await loadPlotly3D()
        await afterPaint()
        const start = performance.now()
        let p = 0
        for (;;) {
          // By the clock, but in at least TILT_STEPS steps where drawing is slow
          p = Math.min(1, (performance.now() - start) / TILT_MS, p + 1 / TILT_STEPS)
          const camera = between(from, to, ease(p))
          await Plotly.relayout(element, this.sceneRelayout(camera) as unknown as Partial<Plotly.Layout>)
          this.up = camera.axes
          this.$emit('depth', camera.axes)
          if (p >= 1) break
          await new Promise((resolve) => requestAnimationFrame(resolve))
        }
      } finally {
        this.tilting = false
        this.$emit('moved')
        if (this.renderAfterTilt) {
          this.renderAfterTilt = false
          this.requestRender()
        }
      }
    },
    /** Lay the scene flat onto the map before the map is shown again. */
    async flatten(): Promise<void> {
      if (!this.plotted) return
      if (reducedMotion()) await this.toCamera(this.flat())
      else await this.tilt(this.currentCamera(), this.flat())
    },
  },
})
</script>

<style scoped>
.heatmap-scene {
  width: 100%;
  box-sizing: border-box;
}
</style>
