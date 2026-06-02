<template>
  <div
    :id="id"
    class="d-flex justify-center align-center rounded-lg protein-terminal"
    :style="proteinTerminalCellStyles"
    @click.stop
  >
    <!-- N / C letter, struck through when this terminus is truncated -->
    <div :class="['terminal-text', { truncated: truncated }]">
      {{ proteinTerminalText }}
    </div>
    <!-- Undetermined terminus marker (oracle parity): a red "??" overlay shown
         when the terminus position could not be determined. -->
    <div v-if="!determined" class="undetermined">??</div>
    <v-tooltip activator="parent">
      <div>{{ proteinTerminal }}</div>
      <div v-if="truncated">Truncated</div>
      <div v-if="!determined">Undetermined terminus</div>
    </v-tooltip>
  </div>
</template>

<script lang="ts">
import { defineComponent, type PropType } from 'vue'
import { useStreamlitDataStore } from '@/stores/streamlit-data'
import type { Theme } from 'streamlit-component-lib'

/**
 * Generic N/C protein-terminal cell.
 *
 * Display-only port of the oracle ProteinTerminalCell
 * (FLASHApp openms-streamlit-vue-component). Renders the terminal letter and,
 * for parity with the oracle:
 *   - strikes the letter through when the terminus is `truncated`;
 *   - overlays a red "??" when the terminus is not `determined`
 *     (truncated / undetermined N/C terminals).
 *
 * The oracle's variable-modification menu is intentionally omitted here (the
 * Insight SequenceView is display-only for modifications), keeping the public
 * surface minimal and generic. Both flags default off, so when a caller does
 * not supply proteoform terminal info the cell renders a plain terminal letter
 * (no visual change vs. the previous plain terminal div).
 */
export default defineComponent({
  name: 'ProteinTerminalCell',
  props: {
    /** Which terminus this cell represents. */
    proteinTerminal: {
      type: String as PropType<'N-term' | 'C-term'>,
      required: true,
    },
    /** Residue index this terminal abuts (informational only). */
    index: {
      type: Number,
      required: true,
    },
    /** Whether this terminus is truncated (strike-through styling). */
    truncated: {
      type: Boolean,
      default: false,
    },
    /** Whether this terminus position is determined; false -> "??" overlay. */
    determined: {
      type: Boolean,
      default: true,
    },
    fontSize: {
      type: Number,
      default: 12,
    },
  },
  setup() {
    const streamlitData = useStreamlitDataStore()
    return { streamlitData }
  },
  computed: {
    id(): string {
      return `terminal-${this.proteinTerminal}-${this.index}`
    },
    theme(): Theme | undefined {
      return this.streamlitData.theme
    },
    proteinTerminalText(): string {
      // 'N-term' -> 'N', 'C-term' -> 'C'
      return this.proteinTerminal.charAt(0)
    },
    proteinTerminalCellStyles(): Record<string, string> {
      return {
        '--protein-terminal-cell-color': this.theme?.textColor ?? '#000',
        '--protein-terminal-cell-hover-color': this.theme?.textColor ?? '#000',
        '--protein-terminal-cell-hover-bg-color':
          this.theme?.backgroundColor ?? '#fff',
        '--amino-acid-font-size': `${this.fontSize}px`,
      }
    },
  },
})
</script>

<style scoped>
.protein-terminal {
  font-weight: bold;
  background-color: rgba(128, 128, 128, 0.2);
  border-radius: 4px;
  aspect-ratio: 1;
  position: relative;
  cursor: default;
}

.protein-terminal:hover {
  background-color: var(--protein-terminal-cell-hover-bg-color);
  color: var(--protein-terminal-cell-hover-color);
}

/* Red "??" overlay for an undetermined terminus (oracle parity). */
.undetermined {
  position: absolute;
  top: -20%;
  font-size: 0.7em;
  font-weight: 1000;
  color: red;
  z-index: 1100;
}

.terminal-text {
  font-weight: 1000;
  font-size: var(--amino-acid-font-size, 12px);
}

/* Struck-through, dimmed letter for a truncated terminus (oracle parity). */
.terminal-text.truncated {
  color: rgba(128, 128, 128, 0.4);
  text-decoration: line-through;
}
</style>
