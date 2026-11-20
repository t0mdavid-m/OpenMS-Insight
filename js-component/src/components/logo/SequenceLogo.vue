<template>
  <div class="logo-root" :style="{ color: textColor }">
    <PlotToolbar :plot-id="id" :tools="toolbarTools" :stepper="args.stepper" />
    <div v-if="args.title" class="logo-title">{{ args.title }}</div>
    <div :id="id" ref="box" class="logo-box">
      <svg
        v-if="width > 0"
        ref="svg"
        xmlns="http://www.w3.org/2000/svg"
        :width="width"
        :height="svgHeight"
        :viewBox="`0 0 ${width} ${svgHeight}`"
        :font-family="FONT"
        role="img"
        :aria-label="args.title || 'Sequence logo'"
      >
        <!-- Highlighted position (its identifier holds it) -->
        <rect
          v-for="column in highlighted"
          :key="`hl-${column}`"
          :x="xOf(column)"
          :y="MARGIN.top"
          :width="columnWidth"
          :height="plotHeight"
          class="logo-highlight"
        />
        <!-- Y axis -->
        <line :x1="MARGIN.left" :x2="MARGIN.left" :y1="MARGIN.top" :y2="MARGIN.top + plotHeight" stroke="currentColor" stroke-opacity="0.6" />
        <g v-for="tick in yTicks" :key="`y-${tick}`">
          <line :x1="MARGIN.left - 4" :x2="MARGIN.left" :y1="yOf(tick)" :y2="yOf(tick)" stroke="currentColor" stroke-opacity="0.6" />
          <text :x="MARGIN.left - 7" :y="yOf(tick) + 4" text-anchor="end" font-size="11" fill="currentColor">{{ tickText(tick) }}</text>
        </g>
        <text
          :transform="`translate(13, ${MARGIN.top + plotHeight / 2}) rotate(-90)`"
          text-anchor="middle"
          font-size="12"
          fill="currentColor"
        >{{ args.yLabel }}</text>
        <!-- X axis -->
        <line
          :x1="MARGIN.left"
          :x2="MARGIN.left + plotWidth"
          :y1="MARGIN.top + plotHeight"
          :y2="MARGIN.top + plotHeight"
          stroke="currentColor"
          stroke-opacity="0.6"
        />
        <text
          v-for="column in length"
          :key="`x-${column}`"
          :x="xOf(column - 1) + columnWidth / 2"
          :y="MARGIN.top + plotHeight + 17"
          text-anchor="middle"
          font-size="12"
          fill="currentColor"
        >{{ labelOf(column - 1) }}</text>
        <!-- Letters: a nested SVG per letter, the glyph stretched to fill it -->
        <svg
          v-for="letter in letters"
          :key="`${letter.position}-${letter.residue}`"
          :x="letter.x"
          :y="letter.y"
          :width="letter.width"
          :height="letter.height"
          viewBox="0 0 100 100"
          preserveAspectRatio="none"
          class="logo-letter"
          :class="{ clickable }"
          :opacity="letter.dimmed ? 0.3 : 1"
          :data-residue="letter.residue"
          :data-position="letter.position"
          @click="pick(letter)"
        >
          <title>{{ letter.tip }}</title>
          <rect x="0" y="0" width="100" height="100" fill="transparent" />
          <text
            x="2"
            y="100"
            textLength="96"
            lengthAdjust="spacingAndGlyphs"
            :font-size="GLYPH_SIZE"
            font-weight="700"
            :fill="letter.color"
          >{{ letter.residue }}</text>
        </svg>
      </svg>
      <div v-if="width > 0 && letters.length === 0" class="logo-empty">No sequences to show.</div>
    </div>
  </div>
</template>

<script lang="ts">
import { defineComponent, type PropType } from 'vue'
import { Streamlit, type Theme } from 'streamlit-component-lib'
import PlotToolbar from '@/components/plotly/PlotToolbar.vue'
import { useStreamlitDataStore } from '@/stores/streamlit-data'
import { useSelectionStore } from '@/stores/selection'
import { ICONS, TOOLBAR_HEIGHT, type PlotTool } from '@/utils/plotTools'
import { RASTER_SCALE, convertRaster, downloadTitle, imageFileName, imageFormatOf, saveImage } from '@/utils/imageExport'
import type { SequenceLogoComponentArgs } from '@/types/component'

interface LogoRow {
  position: number
  label: string
  residue: string
  count: number
  frequency: number
  height: number
}

interface Letter extends LogoRow {
  x: number
  y: number
  width: number
  height: number
  color: string
  dimmed: boolean
  tip: string
}

// Bold sans-serif capitals are about 0.716 em tall: this size makes one 100 units high
const GLYPH_SIZE = 139.5
const FONT = 'Arial, Helvetica, sans-serif'
const MARGIN = { top: 8, right: 8, bottom: 26, left: 52 }

export default defineComponent({
  name: 'SequenceLogo',
  components: { PlotToolbar },
  props: {
    args: { type: Object as PropType<SequenceLogoComponentArgs>, required: true },
    index: { type: Number, required: true },
  },
  setup() {
    return { streamlitDataStore: useStreamlitDataStore(), selectionStore: useSelectionStore(), GLYPH_SIZE, FONT, MARGIN }
  },
  data() {
    return { width: 0, observer: null as ResizeObserver | null, frameObserver: null as ResizeObserver | null }
  },
  computed: {
    id(): string {
      return `logo-${this.index}`
    },
    theme(): Theme | undefined {
      return this.streamlitDataStore.theme
    },
    textColor(): string {
      return this.theme?.textColor || '#262730'
    },
    rows(): LogoRow[] {
      const data = this.streamlitDataStore.allDataForDrawing?.logoData
      return Array.isArray(data) ? (data as LogoRow[]) : []
    },
    length(): number {
      const fromRows = this.rows.reduce((n, r) => Math.max(n, Number(r.position) + 1), 0)
      return Math.max(this.args.length || 0, fromRows, 1)
    },
    svgHeight(): number {
      const titleHeight = this.args.title ? 24 : 0
      return Math.max((this.args.height || 300) - TOOLBAR_HEIGHT - titleHeight - 8, 120)
    },
    plotWidth(): number {
      return Math.max(this.width - MARGIN.left - MARGIN.right, 10)
    },
    plotHeight(): number {
      return this.svgHeight - MARGIN.top - MARGIN.bottom
    },
    columnWidth(): number {
      return this.plotWidth / this.length
    },
    // The axis's height, or the tallest stack where one is taller
    yMax(): number {
      const totals = new Map<number, number>()
      for (const row of this.rows) totals.set(row.position, (totals.get(row.position) || 0) + row.height)
      const tallest = Math.max(0, ...totals.values())
      const axis = this.args.yMax || 1
      return tallest > axis ? Math.ceil(tallest * 2) / 2 : axis
    },
    yTicks(): number[] {
      const step = this.args.units === 'probability' ? 0.25 : this.yMax > 3 ? 1 : 0.5
      const ticks: number[] = []
      for (let t = 0; t <= this.yMax + 1e-9; t += step) ticks.push(Math.round(t * 100) / 100)
      return ticks
    },
    clickable(): boolean {
      return Object.keys(this.args.interactivity || {}).length > 0
    },
    // Identifier -> field of the clicks, and what the state holds for each
    picked(): { field: string; value: unknown }[] {
      return Object.entries(this.args.interactivity || {})
        .map(([identifier, field]) => ({ field, value: this.selectionStore.$state[identifier] }))
        .filter((p) => p.value !== null && p.value !== undefined)
    },
    highlighted(): number[] {
      const columns = new Set<number>()
      for (const { field, value } of this.picked) {
        for (let c = 0; c < this.length; c++) {
          if ((field === 'position' && Number(value) === c) || (field === 'label' && String(value) === this.labelOf(c))) {
            columns.add(c)
          }
        }
      }
      return [...columns]
    },
    pickedResidue(): string | null {
      const entry = this.picked.find((p) => p.field === 'residue')
      return entry ? String(entry.value) : null
    },
    letters(): Letter[] {
      const stacks = new Map<number, number>()
      const colors = this.args.colors || {}
      const unit = this.args.units === 'probability' ? '' : ' bits'
      return this.rows.map((row) => {
        const position = Number(row.position)
        const below = stacks.get(position) || 0
        stacks.set(position, below + row.height)
        const height = (row.height / this.yMax) * this.plotHeight
        const pad = Math.min(2, this.columnWidth * 0.06)
        const value = row.height.toFixed(2)
        return {
          ...row,
          position,
          x: this.xOf(position) + pad,
          y: this.yOf(below + row.height),
          width: Math.max(this.columnWidth - 2 * pad, 1),
          height: Math.max(height, 0),
          color: colors[row.residue] || '#616161',
          dimmed: this.pickedResidue !== null && this.pickedResidue !== row.residue,
          tip: `${row.label}: ${row.residue}, ${(row.frequency * 100).toFixed(1)} % (${formatCount(row.count)})${
            unit ? `, ${value}${unit}` : ''
          }`,
        }
      })
    },
    toolbarTools(): PlotTool[] {
      const format = imageFormatOf(this.args.imageFormat)
      return [{ id: 'download', group: 'export', icon: ICONS.download, label: downloadTitle(format), run: () => this.download() }]
    },
  },
  mounted() {
    const box = this.$refs.box as HTMLElement
    this.width = box.clientWidth
    this.observer = new ResizeObserver(() => {
      this.width = box.clientWidth
    })
    this.observer.observe(box)
    // The frame follows the view's height (the app's own observer may watch
    // the loading placeholder this view replaced)
    this.frameObserver = new ResizeObserver(() => Streamlit.setFrameHeight())
    this.frameObserver.observe(this.$el as HTMLElement)
  },
  beforeUnmount() {
    this.observer?.disconnect()
    this.frameObserver?.disconnect()
  },
  methods: {
    xOf(column: number): number {
      return MARGIN.left + column * this.columnWidth
    },
    yOf(value: number): number {
      return MARGIN.top + this.plotHeight * (1 - value / this.yMax)
    },
    labelOf(column: number): string {
      const labels = this.args.positionLabels
      if (labels && column < labels.length) return labels[column]
      return String((this.args.firstPosition ?? 1) + column)
    },
    tickText(tick: number): string {
      return Number.isInteger(tick) ? String(tick) : tick.toFixed(2).replace(/0$/, '')
    },
    pick(letter: Letter): void {
      for (const [identifier, field] of Object.entries(this.args.interactivity || {})) {
        const value = field === 'position' ? letter.position : field === 'label' ? letter.label : letter.residue
        this.selectionStore.updateSelection(identifier, value)
      }
    },
    async download(): Promise<void> {
      const svg = this.$refs.svg as SVGSVGElement | undefined
      if (!svg) return
      const format = imageFormatOf(this.args.imageFormat)
      const copy = svg.cloneNode(true) as SVGSVGElement
      copy.querySelectorAll('title').forEach((t) => t.remove())
      copy.setAttribute('color', this.textColor)
      copy.setAttribute('style', `color: ${this.textColor}`)
      const text = new XMLSerializer().serializeToString(copy)
      const name = (this.args.title || 'sequence-logo').replace(/[^\w.-]+/g, '_')
      const svgUrl = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(text)}`
      if (format === 'svg') {
        saveImage(svgUrl, imageFileName(name, 'svg'))
        return
      }
      const image = new Image()
      image.src = svgUrl
      await image.decode()
      const canvas = document.createElement('canvas')
      canvas.width = this.width * RASTER_SCALE
      canvas.height = this.svgHeight * RASTER_SCALE
      const context = canvas.getContext('2d')
      if (!context) return
      context.scale(RASTER_SCALE, RASTER_SCALE)
      context.drawImage(image, 0, 0, this.width, this.svgHeight)
      const result = await convertRaster(canvas.toDataURL('image/png'), format)
      saveImage(result.url, imageFileName(name, result.format))
    },
  },
})

function formatCount(count: number): string {
  return Number.isInteger(count) ? String(count) : count.toFixed(2)
}
</script>

<style scoped>
.logo-root {
  padding: 0 8px 8px 8px;
  box-sizing: border-box;
  width: 100%;
}
.logo-title {
  text-align: center;
  font-weight: 600;
  font-size: 14px;
  height: 24px;
  line-height: 24px;
}
.logo-box {
  position: relative;
  width: 100%;
}
.logo-letter.clickable {
  cursor: pointer;
}
.logo-letter:hover {
  filter: brightness(1.25);
}
.logo-highlight {
  fill: #ff7501;
  fill-opacity: 0.14;
}
.logo-empty {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  opacity: 0.6;
}
</style>
