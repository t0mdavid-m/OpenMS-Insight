<template>
  <div
    class="heatmap-overview"
    :style="frameStyle"
    title="Overview of the whole map: click or drag to move the zoomed region"
    @pointerdown="onPointerDown"
    @pointermove="onPointerMove"
    @pointerup="onPointerUp"
    @pointercancel="dragging = false"
  >
    <canvas ref="canvas" :width="overview.width" :height="overview.height"></canvas>
    <div class="overview-view" :style="viewStyle"></div>
  </div>
</template>

<script lang="ts">
import { defineComponent, type PropType } from 'vue'
import { colorAt, type ColorStops } from '@/utils/colorscale'
import { decodeCells, viewBox, centeredView, type OverviewData, type OverviewView } from '@/utils/overview'

/**
 * A small picture of the whole heatmap (Heatmap ``overview=True``), shown
 * while the plot is zoomed: the zoomed region is framed, and a click or drag
 * moves the zoom there, keeping its size.
 */
export default defineComponent({
  name: 'HeatmapOverview',
  props: {
    overview: { type: Object as PropType<OverviewData>, required: true },
    /** The zoomed region, in data coordinates. */
    view: { type: Object as PropType<OverviewView>, required: true },
    stops: { type: Array as unknown as PropType<ColorStops>, required: true },
    /** Pixel position of the frame inside the plot's wrapper. */
    left: { type: Number, required: true },
    top: { type: Number, required: true },
    /** Drawn size in pixels (the raster is scaled to it). */
    width: { type: Number, required: true },
    height: { type: Number, required: true },
    background: { type: String, default: '#ffffff' },
    text: { type: String, default: '#262730' },
    accent: { type: String, default: '#1436b8' },
  },
  emits: ['move'],
  data() {
    return {
      dragging: false,
      /** The region while it is dragged, before the plot follows. */
      preview: null as OverviewView | null,
    }
  },
  computed: {
    frameStyle(): Record<string, string> {
      return {
        left: `${this.left}px`,
        top: `${this.top}px`,
        width: `${this.width}px`,
        height: `${this.height}px`,
        background: this.background,
        borderColor: `color-mix(in srgb, ${this.text} 30%, transparent)`,
      }
    },
    viewStyle(): Record<string, string> {
      const box = viewBox(this.overview, this.preview ?? this.view)
      return {
        left: `${box.left * 100}%`,
        top: `${box.top * 100}%`,
        width: `${box.width * 100}%`,
        height: `${box.height * 100}%`,
        borderColor: this.accent,
        // The rest of the map is dimmed, so the zoomed region stands out
        boxShadow: `0 0 0 1px ${this.background}, 0 0 0 999px color-mix(in srgb, ${this.background} 45%, transparent)`,
      }
    },
  },
  watch: {
    overview() {
      this.draw()
    },
    stops() {
      this.draw()
    },
    view() {
      this.preview = null
    },
  },
  mounted() {
    this.draw()
  },
  methods: {
    draw(): void {
      const canvas = this.$refs.canvas as HTMLCanvasElement | undefined
      const context = canvas?.getContext('2d')
      if (!canvas || !context) return
      const { width, height } = this.overview
      const cells = decodeCells(this.overview.cells)
      // One color per cell value; 0 stays empty
      const palette: number[][] = [[0, 0, 0, 0]]
      for (let v = 1; v < 256; v++) {
        const hex = colorAt(this.stops, (v - 1) / 254).replace('#', '')
        palette.push([parseInt(hex.slice(0, 2), 16), parseInt(hex.slice(2, 4), 16), parseInt(hex.slice(4, 6), 16), 255])
      }
      const image = context.createImageData(width, height)
      for (let row = 0; row < height; row++) {
        // Row 0 of the cells is the lowest y, drawn at the bottom
        const y = height - 1 - row
        for (let x = 0; x < width; x++) {
          const color = palette[cells[row * width + x] ?? 0]
          image.data.set(color, (y * width + x) * 4)
        }
      }
      context.putImageData(image, 0, 0)
    },

    /** The point under the pointer, as a fraction of the frame. */
    fraction(event: PointerEvent): [number, number] {
      const rect = (this.$el as HTMLElement).getBoundingClientRect()
      return [(event.clientX - rect.left) / rect.width, (event.clientY - rect.top) / rect.height]
    },

    onPointerDown(event: PointerEvent): void {
      event.preventDefault()
      event.stopPropagation()
      ;(this.$el as HTMLElement).setPointerCapture?.(event.pointerId)
      this.dragging = true
      this.preview = centeredView(this.overview, this.view, ...this.fraction(event))
    },

    onPointerMove(event: PointerEvent): void {
      if (!this.dragging) return
      this.preview = centeredView(this.overview, this.view, ...this.fraction(event))
    },

    onPointerUp(event: PointerEvent): void {
      if (!this.dragging) return
      this.dragging = false
      const view = centeredView(this.overview, this.view, ...this.fraction(event))
      this.preview = view
      this.$emit('move', view)
    },
  },
})
</script>

<style scoped>
.heatmap-overview {
  position: absolute;
  z-index: 2;
  box-sizing: content-box;
  border: 1px solid;
  border-radius: 3px;
  overflow: hidden;
  cursor: crosshair;
  touch-action: none;
  opacity: 0.92;
}
.heatmap-overview canvas {
  display: block;
  width: 100%;
  height: 100%;
}
.overview-view {
  position: absolute;
  box-sizing: border-box;
  border: 1.5px solid;
  pointer-events: none;
  min-width: 3px;
  min-height: 3px;
}
</style>
