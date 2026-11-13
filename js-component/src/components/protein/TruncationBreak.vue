<template>
  <!-- Break line marking the residues a proteoform's terminus truncates:
       their protein positions and a zig-zag over `cells` grid cells; the
       C-terminal one (end) runs zig-zag first, positions last -->
  <div :class="['truncated-residues', { 'truncated-residues-end': end }]" :aria-label="text">
    <span class="truncated-label" aria-hidden="true">{{ range }}</span>
    <svg
      class="truncated-break" aria-hidden="true" preserveAspectRatio="none"
      :viewBox="`0 0 ${Math.max(cells, 1) * 20} 8`"
    >
      <polyline
        :points="points" fill="none" stroke="currentColor" stroke-width="1.2"
        vector-effect="non-scaling-stroke"
      />
    </svg>
    <v-tooltip activator="parent" location="bottom" max-width="480">
      <div class="truncated-range">{{ text }}</div>
      <div v-if="mass !== null" class="truncated-mass" :data-testid="`${testid}-mass`">{{ mass }}</div>
      <span class="truncated-sequence" :data-testid="`${testid}-sequence`">{{ residues }}</span>
    </v-tooltip>
  </div>
</template>

<script lang="ts">
import { defineComponent, type PropType } from 'vue'

export default defineComponent({
  name: 'TruncationBreak',
  props: {
    /** Protein positions, e.g. "1–21" */
    range: { type: String, required: true },
    /** Hover text and accessible label, e.g. "21 residues truncated (1–21)" */
    text: { type: String, required: true },
    /** Hover line on the residue mass; null leaves it out */
    mass: { type: String as PropType<string | null>, default: null },
    /** The truncated residues */
    residues: { type: String, required: true },
    /** Grid cells the line spans: sets the zig-zag's tooth count */
    cells: { type: Number, required: true },
    /** C-terminal: zig-zag first, positions on the right */
    end: { type: Boolean, default: false },
    testid: { type: String, required: true },
  },
  computed: {
    /** Two teeth per cell, so the zig-zag keeps its pitch at any width */
    points(): string {
      const n = Math.max(this.cells, 1) * 4
      return Array.from({ length: n + 1 }, (_, i) => `${i * 5},${i % 2 ? 0 : 8}`).join(' ')
    },
  },
})
</script>

<style scoped>
.truncated-residues {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  line-height: 1;
  opacity: var(--v-medium-emphasis-opacity);
  cursor: help;
  aspect-ratio: auto;
  align-self: center;
  min-width: 0;
  overflow: hidden;
  padding: 0 4px;
}

.truncated-residues-end {
  flex-direction: row-reverse;
}

.truncated-label {
  white-space: nowrap;
}

.truncated-break {
  flex: 1;
  min-width: 0;
  height: 8px;
}

.truncated-range {
  font-weight: 600;
}

.truncated-mass {
  font-variant-numeric: tabular-nums;
}

.truncated-sequence {
  font-family: monospace;
  overflow-wrap: anywhere;
}
</style>
