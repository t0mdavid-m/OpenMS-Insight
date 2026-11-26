<template>
  <div class="sequence-coverage-container">
    <v-sheet class="pa-4 rounded-lg help-card" :theme="theme?.base ?? 'light'" border>
      <div class="d-flex align-center mb-2">
        <HelpIcon v-if="args.help" :text="args.help" class="title-help" />
        <h4 v-if="args.title" class="coverage-title">
          {{ args.title }}<span v-if="model?.name" class="coverage-name"> · {{ model.name }}</span>
        </h4>
        <v-spacer />
        <ImageScreenshot
          :element-id="svgId"
          :filename="fileName"
          :format="args.imageFormat"
          :color="theme?.primaryColor ?? 'primary'"
          size="small"
        />
        <FullscreenButton />
      </div>

      <div v-if="!model || model.length === 0" class="coverage-empty">
        {{ args.emptyMessage || 'Nothing matched to this sequence.' }}
      </div>
      <div v-else-if="model.tracks.length === 0" class="coverage-empty">
        {{ args.emptyMessage || 'Nothing matched to this sequence.' }}
      </div>

      <div v-if="model && model.length > 0" :id="svgId" class="coverage-figure">
        <svg
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
              font-size="11"
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
          <!-- legend -->
          <g v-if="args.hasCounts" :transform="`translate(0, ${layout.legendY})`">
            <text :x="0" :y="11" font-size="11" font-weight="600" :fill="textColor">{{ args.countLabel || 'Matches' }}</text>
            <g v-for="(bin, i) in bins" :key="`b${i}`" :transform="`translate(${LEFT + i * SWATCH}, 0)`">
              <rect :x="0" :y="0" :width="SWATCH - 3" :height="12" :fill="bin.color" :stroke="borderColor" stroke-width="0.5" />
              <text :x="(SWATCH - 3) / 2" :y="25" font-size="9" text-anchor="middle" :fill="mutedColor">{{ bin.label }}</text>
            </g>
          </g>
          <text
            v-for="(note, i) in notes"
            :key="`n${i}`"
            :x="0"
            :y="layout.notesY + i * 14 + 10"
            font-size="10"
            :fill="mutedColor"
          >{{ note }}</text>
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
import ImageScreenshot from '@/components/protein/ImageScreenshot.vue'
import { useStreamlitDataStore } from '@/stores/streamlit-data'
import { useSelectionStore } from '@/stores/selection'
import type { CoverageHit, CoverageModel } from '@/types/coverage-data'

const CELL = 12
const LEFT = 150
const LANE = 19
const HIT_HEIGHT = 14
const TRACK_HEADER = 30
const REFERENCE_ROW = 22
const BLOCK_GAP = 14
const SWATCH = 59

let nextId = 0

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

export default defineComponent({
  name: 'SequenceCoverage',
  components: { HelpIcon, FullscreenButton, ImageScreenshot },
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
      CELL,
      LEFT,
      HIT_HEIGHT,
      SWATCH,
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
    model(): CoverageModel | undefined {
      return this.streamlitDataStore.allDataForDrawing?.coverageData as CoverageModel | undefined
    },
    blockSize(): number {
      const size = Number(this.args.blockSize)
      return Number.isFinite(size) && size >= 10 ? size : 50
    },
    interactivity(): Record<string, string> {
      return (this.args.interactivity as Record<string, string>) ?? {}
    },
    clickable(): boolean {
      return Object.keys(this.interactivity).length > 0
    },
    bins(): { label: string; color: string }[] {
      const raw = (this.args.countBins as [number | null, string, string][]) ?? []
      return raw.map(([, label, color]) => ({ label, color }))
    },
    notes(): string[] {
      return (this.args.notes as string[]) ?? []
    },
    fileName(): string {
      const base = this.model?.name || this.args.title || 'sequence-coverage'
      return String(base).replace(/[^\w.-]+/g, '_')
    },
    summary(): string {
      const m = this.model
      if (!m) return ''
      const pct = (m.coverage * 100).toFixed(1)
      return `${m.covered} of ${m.length} positions covered (${pct}%)`
    },
    layout(): { width: number; height: number; blocks: Block[]; legendY: number; notesY: number } {
      const m = this.model
      const size = this.blockSize
      const width = LEFT + size * CELL + 10
      const blocks: Block[] = []
      if (!m || m.length === 0) return { width, height: 0, blocks, legendY: 0, notesY: 0 }
      let y = 34
      for (let b = 0; b * size < m.length; b++) {
        const first = b * size + 1
        const last = Math.min(m.length, first + size - 1)
        const xOf = (position: number) => LEFT + (position - first) * CELL
        const ticks: Tick[] = []
        const tokens: Token[] = []
        for (let p = first; p <= last; p++) {
          if (p === first || p % 5 === 0) ticks.push({ position: p, x: xOf(p) + CELL / 2 })
          const text = m.reference[p - 1] ?? ''
          tokens.push({ position: p, x: xOf(p) + CELL / 2, text, short: shortToken(text) })
        }
        const blockY = y
        y += REFERENCE_ROW
        const tracks: DrawnTrack[] = []
        m.tracks.forEach((track, t) => {
          const trackY = y
          const hits: DrawnHit[] = []
          for (const hit of track.hits) {
            if (hit.end < first || hit.start > last) continue
            const start = Math.max(first, hit.start)
            const end = Math.min(last, hit.end)
            hits.push({
              id: hit.id,
              x: xOf(start) + 0.5,
              y: trackY + hit.lane * LANE + 4,
              width: (end - start + 1) * CELL - 1,
              color: hit.color,
              selected: this.isSelected(hit),
              tooltip: hitTooltip(hit, this.args.countLabel as string, this.args.hasCounts as boolean),
              mods: hit.modifications
                .filter((mod) => mod.position >= first && mod.position <= last)
                .map((mod) => ({
                  position: mod.position,
                  x: xOf(mod.position) + CELL / 2,
                  title: `${mod.position}${mod.label ? `: ${mod.label}` : ''}`,
                })),
              source: hit,
            })
          }
          const pct = (track.coverage * 100).toFixed(1)
          const note = [`${pct}% covered`, track.note].filter((x) => x !== null && x !== undefined && x !== '').join(' · ')
          tracks.push({ index: t, name: track.name, note, y: trackY, hits })
          y += Math.max(TRACK_HEADER, track.lanes * LANE + 6)
        })
        blocks.push({ index: b, y: blockY + 10, ticks, tokens, tracks })
        y += BLOCK_GAP
      }
      const legendY = y
      if (this.args.hasCounts) y += 36
      const notesY = y
      y += this.notes.length * 14
      return { width, height: y + 4, blocks, legendY, notesY }
    },
  },
  watch: {
    layout() {
      this.$nextTick(() => Streamlit.setFrameHeight())
    },
  },
  mounted() {
    this.$nextTick(() => Streamlit.setFrameHeight())
  },
  methods: {
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
  },
})

/** One character for the reference row: a modified code such as [m1A] shows its base. */
function shortToken(text: string): string {
  if (text.length <= 1) return text
  const letters = text.replace(/[^A-Za-z]/g, '')
  return letters ? letters[letters.length - 1] : text[0]
}

function hitTooltip(hit: CoverageHit, countLabel: string | undefined, hasCounts: boolean): string {
  const lines = [`${hit.label || 'Match'} (${hit.start}–${hit.end})`]
  if (hasCounts) lines.push(`${countLabel || 'Matches'}: ${hit.count ?? '–'}`)
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
