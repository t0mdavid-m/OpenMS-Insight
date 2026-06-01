<template>
  <div class="internal-fragment-map">
    <div v-if="title" class="d-flex justify-center">
      <h4>{{ title }}</h4>
    </div>
    <!-- Legend -->
    <div class="d-flex justify-start align-center legend">
      <div class="legend-swatch by-fragment"></div>
      <div class="legend-label">by/cz</div>
      <div class="legend-swatch bz-fragment"></div>
      <div class="legend-label">bz</div>
      <div class="legend-swatch cy-fragment"></div>
      <div class="legend-label">cy</div>
    </div>

    <div v-if="sequence.length > 0" class="fragment-sheet">
      <!-- Sequence row -->
      <div class="sequence-row">
        <div
          v-for="(aa, aaIndex) in sequence"
          :key="`aa-${aaIndex}`"
          class="fragment-segment sequence-text"
          :style="cellStyle"
        >
          {{ aa }}
        </div>
      </div>

      <!-- One stacked row group per fragment type (by, cy, bz) -->
      <div v-for="group in fragmentGroups" :key="group.type" class="fragment-type-stack">
        <div
          v-for="(frag, fragIndex) in group.fragments"
          :key="`${group.type}-${fragIndex}`"
          class="fragment-row"
        >
          <div
            v-for="(aa, aaIndex) in sequence"
            :key="`${group.type}-${fragIndex}-${aaIndex}`"
            :class="segmentClass(aaIndex, frag.start, frag.end, group.cssClass)"
            :style="cellStyle"
          ></div>
        </div>
      </div>
    </div>
    <div v-else class="no-data">No sequence selected</div>
  </div>
</template>

<script lang="ts">
import { defineComponent, type PropType } from 'vue'
import { Streamlit } from 'streamlit-component-lib'
import { useStreamlitDataStore } from '@/stores/streamlit-data'
import type { InternalFragmentMapComponentArgs } from '@/types/component'

type Frag = { mass: number; start: number; end: number }

/**
 * InternalFragmentMap — colored internal-fragment blocks over a sequence.
 *
 * Consumes a self-contained payload from Python:
 *   {
 *     sequence: string[],
 *     observedMasses: number[],
 *     tolerancePpm: number,
 *     colors: { by, cy, bz },
 *     fragment_masses_by/cy/bz: number[],
 *     start_indices_by/cy/bz: number[],
 *     end_indices_by/cy/bz: number[],
 *   }
 * For each ion-pair type it keeps the theoretical internal fragments whose mass
 * matches an observed mass within tolerance, and draws one stacked row per
 * matched fragment with its [start, end) residue span colored. Mirrors the
 * original InternalFragmentMap.vue rendering (per-type by/cy/bz stacks).
 */
export default defineComponent({
  name: 'InternalFragmentMap',
  props: {
    args: {
      type: Object as PropType<InternalFragmentMapComponentArgs>,
      required: true,
    },
    index: {
      type: Number,
      required: true,
    },
  },
  setup() {
    const streamlitData = useStreamlitDataStore()
    return { streamlitData }
  },
  computed: {
    payload(): Record<string, unknown> {
      return (
        (this.streamlitData.allDataForDrawing?.internalFragmentData as Record<
          string,
          unknown
        >) || {}
      )
    },
    title(): string {
      return this.args.title || ''
    },
    sequence(): string[] {
      const seq = this.payload.sequence
      return Array.isArray(seq) ? (seq as string[]) : []
    },
    observedMasses(): number[] {
      const obs = this.payload.observedMasses
      return Array.isArray(obs) ? (obs as number[]) : []
    },
    tolerancePpm(): number {
      return (this.payload.tolerancePpm as number) ?? this.args.tolerancePpm ?? 10
    },
    cellStyle(): Record<string, string> {
      // Square cells sized so the sequence spans the available width.
      const len = this.sequence.length || 1
      return {
        height: (94 / len).toFixed(2) + 'vw',
        maxHeight: '24px',
      }
    },
    /**
     * Match theoretical internal fragments against observed masses per type.
     */
    fragmentGroups(): Array<{ type: string; cssClass: string; fragments: Frag[] }> {
      return [
        { type: 'by', cssClass: 'by-fragment', fragments: this.matchType('by') },
        { type: 'cy', cssClass: 'cy-fragment', fragments: this.matchType('cy') },
        { type: 'bz', cssClass: 'bz-fragment', fragments: this.matchType('bz') },
      ]
    },
  },
  watch: {
    payload: {
      handler() {
        this.$nextTick(() => Streamlit.setFrameHeight())
      },
      deep: true,
    },
  },
  mounted() {
    this.$nextTick(() => Streamlit.setFrameHeight())
  },
  methods: {
    /**
     * Keep fragments of a type whose theoretical mass matches any observed
     * mass within tolerancePpm. Same comparison as the original
     * filterMatchingMasses (ppm on (observed - theoretical) / theoretical).
     */
    matchType(type: string): Frag[] {
      const masses = (this.payload[`fragment_masses_${type}`] as number[]) || []
      const starts = (this.payload[`start_indices_${type}`] as number[]) || []
      const ends = (this.payload[`end_indices_${type}`] as number[]) || []
      const observed = this.observedMasses
      const tol = this.tolerancePpm

      const out: Frag[] = []
      for (let i = 0; i < masses.length; i++) {
        const theoretical = masses[i]
        for (let o = 0; o < observed.length; o++) {
          const ppm = ((observed[o] - theoretical) / theoretical) * 1e6
          if (Math.abs(ppm) <= tol) {
            out.push({ mass: theoretical, start: starts[i], end: ends[i] })
            break
          }
        }
      }
      return out
    },
    segmentClass(
      sequenceIndex: number,
      startIndex: number,
      endIndex: number,
      className: string
    ): Record<string, boolean> {
      // Same span test as the original: (start, end] inclusive of end bound.
      const inFragment = sequenceIndex > startIndex && sequenceIndex <= endIndex
      return {
        [className]: inFragment,
        'not-in-fragment': !inFragment,
      }
    },
  },
})
</script>

<style scoped>
.internal-fragment-map {
  width: 100%;
  box-sizing: border-box;
  padding: 8px;
}
.legend {
  margin-bottom: 12px;
  gap: 4px;
}
.legend-swatch {
  width: 14px;
  height: 10px;
  margin-right: 4px;
  border: 1px solid #fff;
}
.legend-label {
  margin-right: 16px;
  font-size: 12px;
}
.fragment-sheet {
  border: 1px solid #ccc;
  border-radius: 8px;
  padding: 8px;
  max-width: 97%;
}
.sequence-row {
  display: flex;
  border-bottom: 1px solid #fff;
}
.fragment-type-stack {
  margin-top: 2px;
}
.fragment-row {
  display: flex;
}
.fragment-segment {
  flex: 1 1 0;
  aspect-ratio: 1;
  display: flex;
  align-items: center;
  justify-content: center;
}
.sequence-text {
  font-size: 8px;
}
.by-fragment {
  flex: 1 1 0;
  aspect-ratio: 1;
  background: #f0a441;
  border: 1px solid #fff;
}
.cy-fragment {
  flex: 1 1 0;
  aspect-ratio: 1;
  background: #12871d;
  border: 1px solid #fff;
}
.bz-fragment {
  flex: 1 1 0;
  aspect-ratio: 1;
  background: #7831cc;
  border: 1px solid #fff;
}
.not-in-fragment {
  flex: 1 1 0;
  aspect-ratio: 1;
  background: transparent;
  border: 1px solid transparent;
}
.no-data {
  padding: 16px;
  text-align: center;
  color: #888;
}
</style>
