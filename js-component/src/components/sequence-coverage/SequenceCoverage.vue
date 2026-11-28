<template>
  <div ref="container" class="sequence-coverage-container">
    <v-sheet class="pa-4 rounded-lg help-card" :theme="theme?.base ?? 'light'" border>
      <div class="d-flex align-center mb-2">
        <HelpIcon v-if="args.help" :text="args.help" class="title-help" />
        <h4 v-if="args.title" class="coverage-title">
          {{ args.title }}<span v-if="model?.name" class="coverage-name"> · {{ model.name }}</span>
        </h4>
        <v-spacer />
        <!-- Toolbar, as in the sequence view -->
        <v-btn :id="`${svgId}-download`" variant="text" icon size="small" :disabled="!hasMap">
          <v-icon>mdi-download</v-icon>
          <v-tooltip activator="parent" location="bottom">Download</v-tooltip>
        </v-btn>
        <v-menu :activator="`#${svgId}-download`" location="bottom">
          <v-card min-width="240">
            <v-list density="compact">
              <v-list-item
                v-for="item in downloads"
                :key="item.id"
                :prepend-icon="item.icon"
                :title="item.title"
                :subtitle="item.subtitle"
                @click="download(item.id)"
              />
            </v-list>
          </v-card>
        </v-menu>
        <FullscreenButton />
        <v-btn :id="`${svgId}-settings`" variant="text" icon size="small">
          <v-icon>mdi-cog</v-icon>
          <v-tooltip activator="parent" location="bottom">Settings</v-tooltip>
        </v-btn>
        <v-menu :close-on-content-click="false" :activator="`#${svgId}-settings`" location="bottom">
          <v-card min-width="300">
            <v-list>
              <v-list-item>
                <v-list-item-title>Positions per line</v-list-item-title>
                <v-checkbox
                  v-model="fitWidth"
                  label="Fit to the width"
                  hide-details
                  density="comfortable"
                ></v-checkbox>
                <v-slider
                  :model-value="layout.size"
                  :ticks="{ 10: '10', 50: '50', 100: '100', 150: '150', 200: '200' }"
                  :min="10"
                  :max="200"
                  step="10"
                  show-ticks="always"
                  tick-size="4"
                  thumb-label
                  @update:model-value="setPositions"
                ></v-slider>
              </v-list-item>
              <v-list-item v-for="setting in appSettings" :key="setting.identifier">
                <v-list-item-title>{{ setting.label }}</v-list-item-title>
                <v-btn-toggle
                  v-if="setting.kind === 'choice'"
                  :model-value="optionIndex(setting)"
                  mandatory
                  density="compact"
                  class="mt-1 setting-choice"
                  @update:model-value="(i: number) => chooseOption(setting, i)"
                >
                  <v-btn v-for="(option, i) in setting.options" :key="i" :value="i" size="small">{{ option.label }}</v-btn>
                </v-btn-toggle>
                <v-slider
                  v-else-if="setting.kind === 'range'"
                  :model-value="Number(settingValue(setting))"
                  :min="setting.min"
                  :max="setting.max"
                  :step="setting.step"
                  thumb-label
                  hide-details
                  @end="(value: number) => writeSetting(setting, value)"
                ></v-slider>
                <v-checkbox
                  v-else
                  :model-value="!!settingValue(setting)"
                  hide-details
                  density="comfortable"
                  @update:model-value="(value: boolean | null) => writeSetting(setting, !!value)"
                ></v-checkbox>
              </v-list-item>
            </v-list>
          </v-card>
        </v-menu>
      </div>

      <div v-if="!hasMap" class="coverage-empty">
        {{ args.emptyMessage || 'Nothing matched to this sequence.' }}
      </div>

      <div v-if="model && model.length > 0" ref="figure" class="coverage-figure">
        <svg
          :id="svgId"
          :width="layout.width"
          :height="layout.height"
          :viewBox="`0 0 ${layout.width} ${layout.height}`"
          xmlns="http://www.w3.org/2000/svg"
          font-family="sans-serif"
          role="img"
          :aria-label="summary"
        >
          <text :x="0" :y="14" font-size="12" font-weight="600" :fill="textColor">{{ summary }}</text>
          <g v-for="block in layout.blocks" :key="block.index">
            <!-- reference row -->
            <text
              v-for="tick in block.ticks"
              :key="`t${tick.position}`"
              :x="tick.x"
              :y="block.y"
              font-size="9"
              text-anchor="middle"
              :fill="mutedColor"
            >{{ tick.position }}</text>
            <text
              v-for="token in block.tokens"
              :key="`r${token.position}`"
              :x="token.x"
              :y="block.y + 14"
              :font-size="layout.tokenFont"
              font-family="monospace"
              text-anchor="middle"
              :fill="textColor"
            >{{ token.short }}<title>{{ token.position }}: {{ token.text }}</title></text>
            <!-- tracks -->
            <g v-for="track in block.tracks" :key="`k${track.index}`">
              <text :x="0" :y="track.y + 11" font-size="11" font-weight="600" :fill="textColor">{{ track.name }}</text>
              <text :x="0" :y="track.y + 24" font-size="10" :fill="mutedColor">{{ track.note }}</text>
              <g
                v-for="hit in track.hits"
                :key="`h${hit.id}`"
                :class="{ clickable: clickable }"
                @click="select(hit.source)"
              >
                <rect
                  :x="hit.x"
                  :y="hit.y"
                  :width="hit.width"
                  :height="HIT_HEIGHT"
                  rx="2"
                  :fill="hit.color"
                  :stroke="hit.selected ? selectedColor : borderColor"
                  :stroke-width="hit.selected ? 2 : 0.75"
                ><title>{{ hit.tooltip }}</title></rect>
                <circle
                  v-for="mod in hit.mods"
                  :key="`m${mod.position}`"
                  :cx="mod.x"
                  :cy="hit.y + HIT_HEIGHT / 2"
                  r="3"
                  :fill="args.modificationColor || '#00a6a6'"
                  stroke="#ffffff"
                  stroke-width="0.75"
                ><title>{{ mod.title }}</title></circle>
              </g>
            </g>
          </g>
          <!-- legend, wrapped to the width -->
          <g v-if="args.hasCounts" :transform="`translate(0, ${layout.legendY})`">
            <text :x="0" :y="11" font-size="11" font-weight="600" :fill="textColor">{{ args.countLabel || 'Matches' }}</text>
            <g v-for="swatch in layout.swatches" :key="`b${swatch.index}`" :transform="`translate(${swatch.x}, ${swatch.y})`">
              <rect :x="0" :y="0" :width="SWATCH - 3" :height="12" :fill="swatch.color" :stroke="borderColor" stroke-width="0.5" />
              <text :x="(SWATCH - 3) / 2" :y="25" font-size="9" text-anchor="middle" :fill="mutedColor">{{ swatch.label }}</text>
            </g>
          </g>
          <!-- notes, wrapped to the width -->
          <text
            v-for="(line, i) in layout.noteLines"
            :key="`n${i}`"
            :x="0"
            :y="layout.notesY + i * NOTE_LINE + 10"
            font-size="10"
            :fill="mutedColor"
          >{{ line }}</text>
        </svg>
      </div>
    </v-sheet>
  </div>
</template>

<script lang="ts">
import { defineComponent } from 'vue'
import { Streamlit, type Theme } from 'streamlit-component-lib'
import HelpIcon from '@/components/common/HelpIcon.vue'
import FullscreenButton from '@/components/FullscreenButton.vue'
import { useStreamlitDataStore } from '@/stores/streamlit-data'
import { useSelectionStore } from '@/stores/selection'
import type { CoverageHit, CoverageModel } from '@/types/coverage-data'
import type { SettingArgs } from '@/utils/settings'
import { imageFileName, imageFormatOf, saveImage, type ImageFormat } from '@/utils/imageExport'
import { EXPORT_MARGIN, coverageHtml, coverageTsv, rasterize, standaloneSvg, textUrl } from '@/utils/coverageExport'

/** Narrowest and widest cell of one position; the map fills its width between them. */
const MIN_CELL = 12
const MAX_CELL = 28
const LANE = 19
const HIT_HEIGHT = 14
const TRACK_HEADER = 30
const REFERENCE_ROW = 22
const BLOCK_GAP = 14
const SWATCH = 59
const NOTE_LINE = 14
const LABEL_GAP = 14
const RIGHT = 6

let nextId = 0
let measureContext: CanvasRenderingContext2D | null = null

/** Width of `text` in `font`, for the label column and the wrapping notes. */
function textWidth(text: string, font: string): number {
  if (!measureContext) measureContext = document.createElement('canvas').getContext('2d')
  if (!measureContext) return text.length * 7
  measureContext.font = font
  return measureContext.measureText(text).width
}

/** Words of `text` in lines no wider than `width`. */
function wrap(text: string, width: number, font: string): string[] {
  const lines: string[] = []
  let line = ''
  for (const word of text.split(/\s+/).filter(Boolean)) {
    const next = line ? `${line} ${word}` : word
    if (line && textWidth(next, font) > width) {
      lines.push(line)
      line = word
    } else {
      line = next
    }
  }
  if (line) lines.push(line)
  return lines
}

interface Tick { position: number; x: number }
interface Token { position: number; x: number; text: string; short: string }
interface DrawnHit {
  id: number
  x: number
  y: number
  width: number
  color: string
  selected: boolean
  tooltip: string
  mods: { position: number; x: number; title: string }[]
  source: CoverageHit
}
interface DrawnTrack { index: number; name: string; note: string; y: number; hits: DrawnHit[] }
interface Block { index: number; y: number; ticks: Tick[]; tokens: Token[]; tracks: DrawnTrack[] }
interface Swatch { index: number; x: number; y: number; label: string; color: string }
interface Layout {
  width: number
  height: number
  size: number
  tokenFont: number
  blocks: Block[]
  swatches: Swatch[]
  legendY: number
  notesY: number
  noteLines: string[]
}
interface DownloadItem { id: string; icon: string; title: string; subtitle: string }

export default defineComponent({
  name: 'SequenceCoverage',
  components: { HelpIcon, FullscreenButton },
  props: {
    args: { type: Object, required: true },
    index: { type: Number, required: true },
  },
  setup() {
    const streamlitDataStore = useStreamlitDataStore()
    const selectionStore = useSelectionStore()
    return { streamlitDataStore, selectionStore }
  },
  data() {
    return {
      svgId: `sequence-coverage-${nextId++}`,
      HIT_HEIGHT,
      SWATCH,
      NOTE_LINE,
      /** Width the map may take, measured from the card */
      availableWidth: 0,
      /** Positions per line: fitted to the width, or the user's number */
      fitWidth: true,
      positions: 50,
      settingsInitialized: false,
      resizeObserver: null as ResizeObserver | null,
    }
  },
  computed: {
    theme(): Theme | undefined {
      return this.streamlitDataStore.theme
    },
    textColor(): string {
      return this.theme?.textColor ?? '#1f2933'
    },
    mutedColor(): string {
      return this.theme?.base === 'dark' ? '#a0a7b4' : '#5f6b7a'
    },
    borderColor(): string {
      return this.theme?.base === 'dark' ? '#8a93a3' : '#9aa3ae'
    },
    selectedColor(): string {
      return this.theme?.primaryColor ?? '#3157e9'
    },
    backgroundColor(): string {
      return this.theme?.backgroundColor ?? (this.theme?.base === 'dark' ? '#0e1117' : '#ffffff')
    },
    model(): CoverageModel | undefined {
      return this.streamlitDataStore.allDataForDrawing?.coverageData as CoverageModel | undefined
    },
    hasMap(): boolean {
      return !!this.model && this.model.length > 0 && this.model.tracks.length > 0
    },
    interactivity(): Record<string, string> {
      return (this.args.interactivity as Record<string, string>) ?? {}
    },
    clickable(): boolean {
      return Object.keys(this.interactivity).length > 0
    },
    appSettings(): SettingArgs[] {
      return (this.args.toolbarSettings as SettingArgs[] | undefined) ?? []
    },
    bins(): { label: string; color: string }[] {
      const raw = (this.args.countBins as [number | null, string, string][]) ?? []
      return raw.map(([, label, color]) => ({ label, color }))
    },
    notes(): string[] {
      return (this.args.notes as string[]) ?? []
    },
    countLabel(): string {
      return (this.args.countLabel as string) || 'Matches'
    },
    fileName(): string {
      const base = this.model?.name || this.args.title || 'sequence-coverage'
      return String(base).replace(/[^\w.-]+/g, '_').replace(/^_+|_+$/g, '')
    },
    pageTitle(): string {
      return [this.args.title, this.model?.name].filter(Boolean).join(' · ') || 'Sequence coverage'
    },
    imageFormat(): ImageFormat {
      return imageFormatOf(this.args.imageFormat)
    },
    downloads(): DownloadItem[] {
      const formats: ImageFormat[] = this.imageFormat === 'svg' ? ['svg', 'png'] : [this.imageFormat, 'svg']
      const items: DownloadItem[] = formats.map((format) => ({
        id: format,
        icon: 'mdi-image-outline',
        title: `Image (${format.toUpperCase()})`,
        subtitle: format === 'svg' ? 'Scales without loss' : 'For slides and documents',
      }))
      items.push({ id: 'html', icon: 'mdi-web', title: 'Web page (HTML)', subtitle: 'The map with its tooltips, opens anywhere' })
      items.push({ id: 'tsv', icon: 'mdi-table', title: 'Table (TSV)', subtitle: 'Every match drawn, per track' })
      return items
    },
    summary(): string {
      const m = this.model
      if (!m) return ''
      const pct = (m.coverage * 100).toFixed(1)
      return `${m.covered} of ${m.length} positions covered (${pct}%)`
    },
    trackNotes(): string[] {
      return (this.model?.tracks ?? []).map((track) => {
        const pct = (track.coverage * 100).toFixed(1)
        return [`${pct}% covered`, track.note].filter((x) => x !== null && x !== undefined && x !== '').join(' · ')
      })
    },
    /** The label column: as wide as the widest track name or note. */
    labelWidth(): number {
      const widths = [40]
      for (const track of this.model?.tracks ?? []) widths.push(textWidth(track.name, '600 11px sans-serif'))
      for (const note of this.trackNotes) widths.push(textWidth(note, '10px sans-serif'))
      if (this.args.hasCounts) widths.push(textWidth(this.countLabel, '600 11px sans-serif'))
      const width = Math.ceil(Math.max(...widths)) + LABEL_GAP
      // A long name must not squeeze the sequence out of a narrow frame
      const frame = this.availableWidth || 800
      return Math.min(width, Math.max(80, Math.floor(frame * 0.4)))
    },
    layout(): Layout {
      const m = this.model
      const frame = Math.max(this.availableWidth || 800, 200)
      const left = this.labelWidth
      const room = Math.max(frame - left - RIGHT, MIN_CELL * 10)
      let size: number
      if (this.fitWidth) {
        size = Math.max(10, Math.min(200, Math.floor(room / MIN_CELL / 10) * 10))
        if (m && m.length > 0 && m.length < size) size = m.length
      } else {
        size = this.positions
      }
      const cell = Math.max(MIN_CELL, Math.min(MAX_CELL, room / size))
      const tokenFont = Math.round(Math.max(11, Math.min(15, cell * 0.8)))
      const lineWidth = left + size * cell + RIGHT
      const width = Math.max(lineWidth, Math.min(frame, lineWidth))
      const empty: Layout = { width, height: 0, size, tokenFont, blocks: [], swatches: [], legendY: 0, notesY: 0, noteLines: [] }
      if (!m || m.length === 0) return empty
      const blocks: Block[] = []
      let y = 34
      for (let b = 0; b * size < m.length; b++) {
        const first = b * size + 1
        const last = Math.min(m.length, first + size - 1)
        const xOf = (position: number) => left + (position - first) * cell
        const ticks: Tick[] = []
        const tokens: Token[] = []
        // Ticks every 5 positions, every 10 when the cells are too narrow for the numbers
        const every = cell * 5 >= 24 ? 5 : 10
        for (let p = first; p <= last; p++) {
          if (p === first || p % every === 0) ticks.push({ position: p, x: xOf(p) + cell / 2 })
          const text = m.reference[p - 1] ?? ''
          tokens.push({ position: p, x: xOf(p) + cell / 2, text, short: shortToken(text) })
        }
        const blockY = y
        y += REFERENCE_ROW
        const tracks: DrawnTrack[] = []
        m.tracks.forEach((track, t) => {
          const trackY = y
          const hits: DrawnHit[] = []
          // Lanes are packed per line, so a line holds only the rows its own matches need
          const shown = track.hits
            .filter((hit) => hit.end >= first && hit.start <= last)
            .map((hit) => ({ hit, start: Math.max(first, hit.start), end: Math.min(last, hit.end) }))
            .sort((a, b) => a.start - b.start || b.end - a.end || a.hit.lane - b.hit.lane)
          const ends: number[] = []
          for (const { hit, start, end } of shown) {
            let lane = ends.findIndex((laneEnd) => laneEnd < start)
            if (lane < 0) lane = ends.push(end) - 1
            else ends[lane] = end
            hits.push({
              id: hit.id,
              x: xOf(start) + 0.5,
              y: trackY + lane * LANE + 4,
              width: (end - start + 1) * cell - 1,
              color: hit.color,
              selected: this.isSelected(hit),
              tooltip: hitTooltip(hit, this.countLabel, this.args.hasCounts as boolean),
              mods: hit.modifications
                .filter((mod) => mod.position >= first && mod.position <= last)
                .map((mod) => ({
                  position: mod.position,
                  x: xOf(mod.position) + cell / 2,
                  title: `${mod.position}${mod.label ? `: ${mod.label}` : ''}`,
                })),
              source: hit,
            })
          }
          tracks.push({ index: t, name: track.name, note: this.trackNotes[t], y: trackY, hits })
          y += Math.max(TRACK_HEADER, Math.max(1, ends.length) * LANE + 6)
        })
        blocks.push({ index: b, y: blockY + 10, ticks, tokens, tracks })
        y += BLOCK_GAP
      }
      // Legend: as many swatches per row as fit beside its title
      const legendY = y
      const swatches: Swatch[] = []
      if (this.args.hasCounts) {
        const perRow = Math.max(1, Math.floor((width - left) / SWATCH))
        this.bins.forEach((bin, i) => {
          swatches.push({
            index: i,
            x: left + (i % perRow) * SWATCH,
            y: Math.floor(i / perRow) * 32,
            label: bin.label,
            color: bin.color,
          })
        })
        y += Math.ceil(this.bins.length / perRow) * 32 + 4
      }
      const notesY = y
      const noteLines = this.notes.flatMap((note) => wrap(note, width - RIGHT, '10px sans-serif'))
      y += noteLines.length * NOTE_LINE
      return { width, height: y + 4, size, tokenFont, blocks, swatches, legendY, notesY, noteLines }
    },
  },
  watch: {
    layout() {
      this.$nextTick(() => Streamlit.setFrameHeight())
    },
    args: {
      immediate: true,
      handler() {
        if (this.settingsInitialized) return
        const size = Number(this.args.blockSize)
        if (this.args.blockSize !== null && this.args.blockSize !== undefined && Number.isFinite(size)) {
          this.fitWidth = false
          this.positions = Math.max(10, Math.min(200, size))
        }
        this.settingsInitialized = true
      },
    },
  },
  mounted() {
    const container = this.$refs.container as HTMLElement | undefined
    if (container && typeof ResizeObserver !== 'undefined') {
      this.resizeObserver = new ResizeObserver(() => this.measure())
      this.resizeObserver.observe(container)
    }
    this.measure()
    this.$nextTick(() => Streamlit.setFrameHeight())
  },
  beforeUnmount() {
    this.resizeObserver?.disconnect()
  },
  methods: {
    measure() {
      const container = this.$refs.container as HTMLElement | undefined
      if (!container) return
      // The card's padding (pa-4) and border
      const width = Math.floor(container.clientWidth - 34)
      if (width > 0 && width !== this.availableWidth) this.availableWidth = width
    },
    setPositions(value: number) {
      this.positions = Number(value)
      this.fitWidth = false
    },
    settingValue(setting: SettingArgs): unknown {
      const value = (this.selectionStore.$state as Record<string, unknown>)[setting.identifier]
      return value === undefined || value === null ? setting.default : value
    },
    optionIndex(setting: SettingArgs): number {
      const current = JSON.stringify(this.settingValue(setting))
      const i = (setting.options ?? []).findIndex((o) => JSON.stringify(o.value) === current)
      return i < 0 ? 0 : i
    },
    chooseOption(setting: SettingArgs, index: number) {
      const option = (setting.options ?? [])[index]
      if (option) this.writeSetting(setting, option.value)
    },
    writeSetting(setting: SettingArgs, value: unknown) {
      if (JSON.stringify(value) === JSON.stringify(this.settingValue(setting))) return
      this.selectionStore.updateSelection(setting.identifier, value)
    },
    isSelected(hit: CoverageHit): boolean {
      const identifiers = Object.keys(this.interactivity)
      if (identifiers.length === 0) return false
      return identifiers.every((id) => {
        const value = (this.selectionStore.$state as Record<string, unknown>)[id]
        return value !== undefined && value !== null && value === hit.values[id]
      })
    },
    select(hit: CoverageHit) {
      for (const identifier of Object.keys(this.interactivity)) {
        this.selectionStore.updateSelection(identifier, hit.values[identifier])
      }
    },
    async download(kind: string) {
      const model = this.model
      if (!model) return
      if (kind === 'tsv') {
        const tsv = coverageTsv(model, this.args.hasCounts ? this.countLabel : null)
        saveUrl(textUrl(tsv, 'text/tab-separated-values'), `${this.fileName}.tsv`)
        return
      }
      const svg = document.getElementById(this.svgId) as SVGSVGElement | null
      if (!svg) return
      const svgText = standaloneSvg(svg, this.layout.width, this.layout.height, this.backgroundColor)
      if (kind === 'html') {
        const html = coverageHtml(svgText, this.pageTitle, this.backgroundColor, this.textColor)
        saveUrl(textUrl(html, 'text/html'), `${this.fileName}.html`)
      } else if (kind === 'svg') {
        saveUrl(textUrl(svgText, 'image/svg+xml'), imageFileName(this.fileName, 'svg'))
      } else {
        const image = await rasterize(
          svgText,
          this.layout.width + 2 * EXPORT_MARGIN,
          this.layout.height + 2 * EXPORT_MARGIN,
          kind as Exclude<ImageFormat, 'svg'>)
        saveImage(image.url, imageFileName(this.fileName, image.format))
      }
    },
  },
})

/** Save a blob URL, then let it go. */
function saveUrl(url: string, filename: string): void {
  saveImage(url, filename)
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

/** One character for the reference row: a modified code such as [m1A] shows its base. */
function shortToken(text: string): string {
  if (text.length <= 1) return text
  const letters = text.replace(/[^A-Za-z]/g, '')
  return letters ? letters[letters.length - 1] : text[0]
}

function hitTooltip(hit: CoverageHit, countLabel: string, hasCounts: boolean): string {
  const lines = [`${hit.label || 'Match'} (${hit.start}–${hit.end})`]
  if (hasCounts) lines.push(`${countLabel}: ${hit.count ?? '–'}`)
  for (const mod of hit.modifications) lines.push(`${mod.position}${mod.label ? `: ${mod.label}` : ''}`)
  return lines.join('\n')
}
</script>

<style scoped>
.sequence-coverage-container {
  width: 100%;
}
.coverage-title {
  margin: 0;
}
.coverage-name {
  font-weight: 400;
  opacity: 0.75;
}
.coverage-figure {
  overflow-x: auto;
}
.coverage-empty {
  opacity: 0.7;
  padding: 8px 0;
}
.clickable {
  cursor: pointer;
}
.title-help {
  margin-right: 6px;
}
</style>
