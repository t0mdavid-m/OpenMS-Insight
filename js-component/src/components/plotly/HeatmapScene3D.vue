<template>
  <div :id="plotId" class="heatmap-scene" data-own-size :style="{ minHeight: `${height}px` }"></div>
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
}
const UP: Vec = { x: 0, y: 0, z: 1 }
function cameraOf(eye: Vec, width: number, height: number): SceneCamera {
  const distance = Math.hypot(eye.x, eye.y, eye.z) || 1
  return {
    azimuth: Math.atan2(eye.y, eye.x),
    elevation: Math.asin(Math.max(-1, Math.min(1, eye.z / distance))),
    distance,
    width,
    height,
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
/** Distance of the camera above a flat scene, so it fills the plot as the 2D map does */
const FLAT_EYE = 0.62
/** Length of the tilt between the map and the scene, in ms */
const TILT_MS = 900
const TILT_STEPS = 30

const ease = (t: number) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2)
/** From one camera to the other: round the centre the short way, the box's shape along */
function between(a: SceneCamera, b: SceneCamera, t: number): SceneCamera {
  let turn = b.azimuth - a.azimuth
  if (turn > Math.PI) turn -= 2 * Math.PI
  if (turn < -Math.PI) turn += 2 * Math.PI
  const lerp = (u: number, v: number) => u + (v - u) * t
  return {
    azimuth: a.azimuth + turn * t,
    elevation: lerp(a.elevation, b.elevation),
    distance: lerp(a.distance, b.distance),
    width: lerp(a.width, b.width),
    height: lerp(a.height, b.height),
  }
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
    /** Tilt up from the 2D map when first drawn */
    animate: { type: Boolean, default: false },
  },
  emits: ['pick', 'rendered'],
  data() {
    return {
      drawPending: false,
      plotted: false,
      tilting: false,
      renderAfterTilt: false,
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
        font: { color: this.theme?.textColor, family: this.theme?.font },
        height: this.height,
        margin: { l: 0, r: 0, b: 0, t: this.title ? 50 : 10 },
        showlegend: false,
        scene: {
          xaxis: axis(this.xLabel, this.xRange),
          yaxis: axis(this.yLabel, this.yRange),
          zaxis: { title: { text: this.zLabel }, range: [0, this.maxZ] },
          // As wide as the map: retention time along the long side
          aspectmode: 'manual',
          aspectratio: { x: TILTED.width, y: 1, z: TILTED.height },
          camera: { eye: TILTED_EYE, up: UP },
          // A rotation of the user stays across new points and zooms
          uirevision: 'scene',
        },
      }
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
    const element = document.getElementById(this.plotId)
    if (element && this.plotted) {
      void loadPlotly3D().then((Plotly) => Plotly.purge(element))
    }
  },
  methods: {
    /** One drawing per update, in a task of its own (see Plotly3D). */
    requestRender(): void {
      if (this.tilting) {
        this.renderAfterTilt = true
        return
      }
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
      const tiltUp = this.animate && !this.plotted && !reducedMotion()
      const layout = { ...this.layout, width: element.clientWidth || undefined } as Record<string, unknown>
      if (tiltUp) layout.scene = { ...(layout.scene as object), ...this.sceneLayout(this.flat()) }
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
      this.$emit('rendered')
      if (tiltUp) await this.tilt(this.flat(), TILTED)
    },
    /** Straight from above with the stems flat, as wide as the plot: the scene drawn as the 2D map */
    flat(): SceneCamera {
      const element = document.getElementById(this.plotId)
      const ratio = element && this.height > 0 ? element.clientWidth / this.height : TILTED.width
      const width = Math.min(4, Math.max(1, ratio))
      // Seen from just short of straight above, from the low-y side: y runs up the screen as on the map
      return {
        azimuth: -Math.PI / 2,
        elevation: (89.5 * Math.PI) / 180,
        distance: FLAT_EYE * width,
        width,
        height: 0.01,
      }
    },
    sceneLayout(camera: SceneCamera): Record<string, unknown> {
      return {
        camera: { eye: eyeOf(camera), up: UP, center: { x: 0, y: 0, z: 0 } },
        aspectratio: { x: camera.width, y: 1, z: camera.height },
      }
    },
    /** The camera the scene is seen with now, the user's rotation included */
    currentCamera(): SceneCamera {
      const element = document.getElementById(this.plotId) as unknown as {
        layout?: { scene?: { camera?: { eye?: Vec }; aspectratio?: Vec } }
      } | null
      const scene = element?.layout?.scene
      return cameraOf(
        scene?.camera?.eye ?? TILTED_EYE,
        scene?.aspectratio?.x ?? TILTED.width,
        scene?.aspectratio?.z ?? TILTED.height,
      )
    },
    /** Move the camera and the stems' height from one view to the other. */
    async tilt(from: SceneCamera, to: SceneCamera): Promise<void> {
      const element = document.getElementById(this.plotId)
      if (!element || reducedMotion()) return
      const Plotly = await loadPlotly3D()
      this.tilting = true
      try {
        const start = performance.now()
        let p = 0
        for (;;) {
          // By the clock, but in at least TILT_STEPS steps where drawing is slow
          p = Math.min(1, (performance.now() - start) / TILT_MS, p + 1 / TILT_STEPS)
          const camera = between(from, to, ease(p))
          const scene = this.sceneLayout(camera)
          await Plotly.relayout(element, {
            'scene.camera': scene.camera,
            'scene.aspectratio': scene.aspectratio,
          } as unknown as Partial<Plotly.Layout>)
          if (p >= 1) break
          await new Promise((resolve) => requestAnimationFrame(resolve))
        }
      } finally {
        this.tilting = false
        if (this.renderAfterTilt) {
          this.renderAfterTilt = false
          this.requestRender()
        }
      }
    },
    /** Lay the scene flat onto the map before the map is shown again. */
    async flatten(): Promise<void> {
      if (!this.plotted) return
      await this.tilt(this.currentCamera(), this.flat())
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
