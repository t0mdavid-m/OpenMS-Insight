<template>
  <div
    class="d-flex justify-center align-center rounded-lg"
    :class="proteinTerminalCellClasses"
    :style="proteinTerminalCellStyles"
    @click.stop
    @contextmenu.prevent="toggleMenuOpen"
  >
    <div :class="['terminal-text', { truncated: truncated }]">
      {{ proteinTerminalText }}
    </div>
    <!-- Undetermined-terminus marker (red "??") -->
    <div v-if="!determined" class="undetermined">??</div>

    <!-- Variable / custom modification context menu (Deconv path only) -->
    <v-menu
      v-model="menuOpen"
      activator="parent"
      location="end"
      :open-on-click="false"
      :close-on-content-click="false"
      width="200px"
    >
      <v-list>
        <v-list-item>
          <v-select
            v-model="selectedModification"
            :clearable="true"
            label="Modification"
            density="compact"
            :items="modificationsForSelect"
            @update:model-value="updateSelectedModification"
            @click:clear="selectedModification = undefined"
          >
          </v-select>
        </v-list-item>
        <v-list-item v-if="customSelected">
          <v-form @submit.prevent>
            <v-text-field v-model="customModMass" hide-details label="Monoisotopic mass in Da" type="number" />
            <v-btn type="submit" :block="true" class="mt-2" @click="updateCustomModification">Submit</v-btn>
          </v-form>
        </v-list-item>
      </v-list>
    </v-menu>
    <v-tooltip activator="parent">
      {{ proteinTerminalText }}
    </v-tooltip>
  </div>
</template>

<script lang="ts">
import { defineComponent, type PropType } from 'vue'
import { useStreamlitDataStore } from '@/stores/streamlit-data'
import type { Theme } from 'streamlit-component-lib'
import { potentialModificationMap, type KnownModification, modificationMassMap } from './modification'

export default defineComponent({
  name: 'ProteinTerminalCell',
  props: {
    proteinTerminal: {
      type: String as PropType<'N-term' | 'C-term'>,
      required: true,
    },
    index: {
      type: Number,
      required: true,
    },
    truncated: {
      type: Boolean,
      default: false,
    },
    determined: {
      type: Boolean,
      default: true,
    },
    disableVariableModificationSelection: {
      type: Boolean,
      default: false,
    },
    fontSize: {
      type: Number,
      default: 12,
    },
    /** Current variable modification mass for this terminal (0 / undefined = none) */
    variableMod: {
      type: Number as PropType<number | undefined>,
      default: undefined,
    },
  },
  // (index, mass): parent records the variable modification for this terminal.
  emits: ['update-modification'],
  setup() {
    const streamlitData = useStreamlitDataStore()
    return { streamlitData }
  },
  data() {
    return {
      menuOpen: false,
      selectedModification: undefined as KnownModification | undefined,
      customSelected: false,
      customModMass: '0' as string,
    }
  },
  computed: {
    id(): string {
      return `${this.proteinTerminal}${this.index}`
    },
    theme(): Theme | undefined {
      return this.streamlitData.theme
    },
    proteinTerminalText(): string {
      return this.proteinTerminal.charAt(0)
    },
    hasVariableModification(): boolean {
      return this.variableMod !== undefined && this.variableMod !== 0
    },
    modificationsForSelect(): string[] {
      return ['None', 'Custom', ...this.potentialModifications]
    },
    proteinTerminalCellStyles(): Record<string, string> {
      return {
        '--protein-terminal-cell-color': this.theme?.textColor ?? '#fff',
        '--protein-terminal-cell-hover-color': '#fff',
        '--protein-terminal-cell-hover-bg-color': this.theme?.secondaryBackgroundColor ?? '#000',
        '--amino-acid-font-size': `${this.fontSize}px`,
      }
    },
    proteinTerminalCellClasses(): Record<string, boolean> {
      return {
        'protein-terminal': this.selectedModification === undefined && !this.hasVariableModification,
        'protein-terminal-modified': this.selectedModification !== undefined || this.hasVariableModification,
      }
    },
    potentialModifications(): KnownModification[] {
      return potentialModificationMap[this.proteinTerminal] ?? []
    },
  },
  methods: {
    toggleMenuOpen(): void {
      if (this.disableVariableModificationSelection) {
        return
      }
      this.menuOpen = !this.menuOpen
    },
    updateSelectedModification(modification: 'None' | 'Custom' | KnownModification) {
      if (modification === 'None') {
        this.selectedModification = undefined
      } else if (modification === 'Custom') {
        this.customSelected = true
        return
      } else {
        this.selectedModification = modification as KnownModification
      }
      this.toggleMenuOpen()
      this.customSelected = false
      this.$emit(
        'update-modification',
        this.index,
        this.selectedModification ? modificationMassMap[this.selectedModification] : 0,
      )
    },
    updateCustomModification() {
      this.$emit('update-modification', this.index, parseFloat(this.customModMass))
      this.toggleMenuOpen()
    },
  },
})
</script>

<style scoped>
.undetermined {
  position: relative;
  top: -20%;
  font-size: 0.7em;
  font-weight: 1000;
  color: red;
  z-index: 1100;
}

.protein-terminal:hover {
  background-color: var(--protein-terminal-cell-hover-bg-color);
  color: var(--protein-terminal-cell-hover-color);
}

.terminal-text {
  font-weight: 1000;
  font-size: var(--amino-acid-font-size, 12px);
}

.terminal-text.truncated {
  color: rgba(128, 128, 128, 0.4);
  outline: rgba(128, 128, 128, 0.4);
}

.protein-terminal-modified {
  background-color: #9c1e1e;
  color: var(--amino-acid-cell-color);
}

.protein-terminal-modified:hover {
  background-color: #ff1e1e;
}
</style>
