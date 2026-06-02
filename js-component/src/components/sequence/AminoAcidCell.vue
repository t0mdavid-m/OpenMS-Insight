<template>
  <div
    :id="id"
    class="d-flex justify-center align-center rounded-lg"
    :class="[
      aminoAcidCellClass,
      { highlighted: isHighlighted },
      { 'regex-highlighted': isRegexHighlighted },
      { truncated: isTruncated },
      { 'fixed-mod': fixedModification },
    ]"
    :style="cellStyles"
    @click="selectCell"
    @contextmenu.prevent="toggleMenuOpen"
  >
    <!-- Fragment ion markers (N-terminal: a, b, c) -->
    <div v-if="showFragments && sequenceObject.aIon" class="frag-marker-container frag-marker-a">
      <svg viewBox="0 0 10 10">
        <path stroke="green" d="M7, 1 L9, 3 L9, 7 L9, 3 L7, 1 z" stroke-width="1.5" />
      </svg>
    </div>
    <div v-if="showFragments && sequenceObject.bIon" class="frag-marker-container frag-marker-b">
      <svg viewBox="0 0 10 10">
        <path stroke="blue" d="M10, 0 V5 M10, 0 H5 z" stroke-width="3" />
      </svg>
    </div>
    <div v-if="showFragments && sequenceObject.cIon" class="frag-marker-container frag-marker-c">
      <svg viewBox="0 0 10 10">
        <path stroke="red" d="M4, 1 L9, 3 L9, 7 L9, 3 L4, 1 z" stroke-width="1.5" />
      </svg>
    </div>

    <!-- Fragment ion markers (C-terminal: x, y, z) -->
    <div v-if="showFragments && sequenceObject.xIon" class="frag-marker-container frag-marker-x">
      <svg viewBox="0 0 10 10">
        <path stroke="green" d="M1, 3 L1, 7 L3, 9 L1, 7 L1, 3 z" stroke-width="1.5" />
      </svg>
    </div>
    <div v-if="showFragments && sequenceObject.yIon" class="frag-marker-container frag-marker-y">
      <svg viewBox="0 0 10 10">
        <path stroke="blue" d="M0, 10 V5 M0, 10 H5 z" stroke-width="3" />
      </svg>
    </div>
    <div v-if="showFragments && sequenceObject.zIon" class="frag-marker-container frag-marker-z">
      <svg viewBox="0 0 10 10">
        <path stroke="red" d="M1, 3 L1, 7 L6, 9 L1, 7 L1, 3 z" stroke-width="1.5" />
      </svg>
    </div>

    <!-- Tag-span bracket markers (P0) -->
    <div v-if="showTags && sequenceObject.tagStart" class="rounded-lg tag-marker tag-start"></div>
    <div v-if="showTags && sequenceObject.tagEnd" class="rounded-lg tag-marker tag-end"></div>

    <!-- Ambiguous-modification spanning region markers (P0). Also driven by the
         per-residue fixed-mod `modification` value (existing behavior) and the
         interactive variable modification. -->
    <div v-if="showModifications && (sequenceObject.modStart || isPointModification)" class="rounded-lg mod-marker mod-start"></div>
    <div v-if="showModifications && (sequenceObject.modEnd || isPointModification)" class="rounded-lg mod-marker mod-end"></div>
    <div v-if="showModifications && sequenceObject.modStart && !sequenceObject.modEnd" class="mod-marker mod-start-cont"></div>
    <div v-if="showModifications && !sequenceObject.modStart && sequenceObject.modEnd" class="mod-marker mod-end-cont"></div>
    <div v-if="showModifications && sequenceObject.modCenter" class="mod-marker mod-center-cont"></div>

    <!-- Modification mass badge + tooltip (Possible Modifications) -->
    <div v-if="showModifications && (sequenceObject.modEnd || isPointModification)" class="rounded-lg mod-mass">
      {{ modMassDisplay }}
      <v-tooltip activator="parent" class="foreground">
        {{ `Modification Mass: ${modMassDisplay} Da` }}
        <template v-if="sequenceObject.modLabels">
          <br />
          {{ `Possible Modifications: ${sequenceObject.modLabels}` }}
        </template>
      </v-tooltip>
    </div>

    <!-- Modification mass with fragment ion border coloring (span end) -->
    <div v-if="showFragments && showModifications && (sequenceObject.modEnd || isPointModification) && sequenceObject.aIon && !sequenceObject.bIon" class="rounded-lg mod-mass-a">{{ modMassDisplay }}</div>
    <div v-if="showFragments && showModifications && (sequenceObject.modEnd || isPointModification) && sequenceObject.bIon" class="rounded-lg mod-mass-b">{{ modMassDisplay }}</div>
    <div v-if="showFragments && showModifications && (sequenceObject.modEnd || isPointModification) && sequenceObject.cIon && !sequenceObject.bIon" class="rounded-lg mod-mass-c">{{ modMassDisplay }}</div>

    <!-- Extra fragment type indicator -->
    <div v-if="showModifications && hasExtraFragTypes" class="frag-marker-extra-type">
      <svg viewBox="0 0 10 10">
        <circle cx="5" cy="5" r="0.5" class="extra-frag-circle" stroke-width="0.3" fill="gold" />
      </svg>
    </div>

    <!-- Amino acid letter -->
    <div class="aa-text">{{ aminoAcid }}</div>

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

    <!-- Tooltip -->
    <v-tooltip activator="parent">
      <div>Position: {{ index + 1 }}</div>
      <div v-if="prefix !== undefined">Prefix: {{ prefix }}</div>
      <div v-if="suffix !== undefined">Suffix: {{ suffix }}</div>
      <div v-if="hasExtraFragTypes">{{ sequenceObject.extraTypes.join(', ') }}</div>
    </v-tooltip>
  </div>
</template>

<script lang="ts">
import { defineComponent, type PropType } from 'vue'
import { useStreamlitDataStore } from '@/stores/streamlit-data'
import type { SequenceObject } from '@/types/sequence-data'
import type { Theme } from 'streamlit-component-lib'
import { potentialModificationMap, type KnownModification, modificationMassMap } from './modification'

export default defineComponent({
  name: 'AminoAcidCell',
  props: {
    sequenceObject: {
      type: Object as PropType<SequenceObject>,
      required: true,
    },
    index: {
      type: Number,
      required: true,
    },
    sequenceLength: {
      type: Number,
      required: true,
    },
    fixedModification: {
      type: Boolean,
      default: false,
    },
    showFragments: {
      type: Boolean,
      default: true,
    },
    /** Whether ambiguous/variable modification markers are shown (P0/P1) */
    showModifications: {
      type: Boolean,
      default: true,
    },
    /** Whether tag-span bracket markers are shown (P0) */
    showTags: {
      type: Boolean,
      default: false,
    },
    fontSize: {
      type: Number,
      default: 12,
    },
    isHighlighted: {
      type: Boolean,
      default: false,
    },
    /** Whether this residue is regex-highlighted (P1) */
    isRegexHighlighted: {
      type: Boolean,
      default: false,
    },
    /** Per-residue fixed-mod mass shift (existing behavior); null = none */
    modification: {
      type: Number as PropType<number | null>,
      default: null,
    },
    /**
     * Whether coverage coloring is active for the grid. When false, no coverage
     * shading is applied (the residue uses the plain theme background), matching
     * FLASHApp's behavior of only shading when sequence tags are shown. (EXTEND)
     */
    showCoverage: {
      type: Boolean,
      default: false,
    },
    /** Disable the right-click variable-modification context menu (TnT path) */
    disableVariableModificationSelection: {
      type: Boolean,
      default: true,
    },
    /** Current interactive variable modification mass for this residue (0 = none) */
    variableMod: {
      type: Number as PropType<number | undefined>,
      default: undefined,
    },
  },
  // 'residueSelected' (existing) for the tag cross-link; 'residueSelectionCleared'
  // when the Tags toggle is turned off (parity with FLASHApp clearing
  // selectedAApos); 'update-modification' (index, mass) for interactive
  // variable modifications.
  emits: ['selected', 'residueSelected', 'residueSelectionCleared', 'update-modification'],
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
      return `aa-${this.aminoAcid}-${this.index}`
    },
    theme(): Theme | undefined {
      return this.streamlitData.theme
    },
    aminoAcid(): string {
      return this.sequenceObject.aminoAcid
    },
    prefix(): number | undefined {
      return this.index + 1
    },
    suffix(): number | undefined {
      return this.sequenceLength - this.index
    },
    hasExtraFragTypes(): boolean {
      return this.sequenceObject.extraTypes.length > 0
    },
    hasMatchingFragments(): boolean {
      return (
        this.sequenceObject.aIon ||
        this.sequenceObject.bIon ||
        this.sequenceObject.cIon ||
        this.sequenceObject.xIon ||
        this.sequenceObject.yIon ||
        this.sequenceObject.zIon
      )
    },
    /** Whether this residue is a truncated proteoform flank (P0) */
    isTruncated(): boolean {
      return this.sequenceObject.truncated === true
    },
    modificationsForSelect(): string[] {
      return ['None', 'Custom', ...this.potentialModifications]
    },
    potentialModifications(): KnownModification[] {
      return potentialModificationMap[this.aminoAcid] ?? []
    },
    /**
     * Whether a POINT modification badge/marker should show on this single
     * residue: either a per-residue fixed-mod value (existing behavior) or an
     * interactive variable modification selected on it. (DISTINCT from the
     * spanning ambiguous mod-range markers, which use modStart/modEnd/modCenter.)
     */
    isPointModification(): boolean {
      if (this.modification !== null) return true
      if (this.selectedModification !== undefined) return true
      return this.variableMod !== undefined && this.variableMod !== 0
    },
    /**
     * Whether this residue is covered by at least one sequence tag (coverage > 0),
     * mirroring FLASHApp's AminoAcidCell.DoesThisAAHaveSequenceTags. Only covered
     * residues are clickable for the Tag-Table cross-link. (EXTEND)
     */
    hasSequenceTags(): boolean {
      return this.coverage > 0
    },
    aminoAcidCellClass(): Record<string, boolean> {
      return {
        'sequence-amino-acid': !this.fixedModification,
        'sequence-amino-acid-highlighted': this.fixedModification,
      }
    },
    /**
     * Normalized per-residue coverage in [0, 1], or -1 when no coverage data is
     * present for this residue (mirrors FLASHApp's AminoAcidCell.coverage). (EXTEND)
     */
    coverage(): number {
      return this.sequenceObject.coverage !== undefined ? this.sequenceObject.coverage : -1
    },
    /**
     * Coverage-driven background color, computed exactly like FLASHApp's
     * AminoAcidCell.aminoAcidCellStyles:
     *   - coverage < 0           -> no shading (use theme secondaryBackgroundColor)
     *   - showCoverage === false -> alpha 0 (transparent overlay over theme bg)
     *   - alpha !== 0            -> remap [eps,1] -> [0.1,1] via alpha*0.9 + 0.1
     * Result is rgba(228, 87, 46, alpha) — the FLASHApp coverage scale color.
     */
    coverageBgColor(): string | undefined {
      let alpha = this.coverage
      if (alpha < 0) {
        return undefined
      }
      if (!this.showCoverage) {
        alpha = 0
      } else if (alpha !== 0) {
        alpha = alpha * 0.9 + 0.1
      }
      return `rgba(228, 87, 46, ${alpha})`
    },
    cellStyles(): Record<string, string> {
      const isDark = this.theme?.base === 'dark'
      const bgColor =
        this.coverageBgColor ?? (this.theme?.secondaryBackgroundColor ?? '#f0f0f0')
      return {
        '--amino-acid-cell-color': this.theme?.textColor ?? '#000',
        '--amino-acid-cell-bg-color': bgColor,
        '--amino-acid-cell-hover-color': this.theme?.textColor ?? '#000',
        '--amino-acid-cell-hover-bg-color': this.theme?.backgroundColor ?? '#fff',
        '--amino-acid-font-size': `${this.fontSize}px`,
        '--mod-mass-bg-color': isDark ? '#e0e0e0' : '#fff',
        '--mod-mass-text-color': '#000',
        '--mod-mass-border-color': isDark ? '#666' : '#a79c91',
        '--mod-marker-dot-color': isDark ? 'rgba(150, 150, 220, 0.8)' : '#676a9c',
        '--mod-marker-bg-color': isDark ? 'rgba(180, 180, 220, 0.3)' : '#e5e5f7',
        '--extra-frag-stroke': isDark ? 'rgba(255, 255, 255, 0.5)' : 'black',
        position: 'relative',
      }
    },
    /**
     * Mass badge text. An interactive variable / custom modification takes
     * precedence; otherwise the spanning mod-range badge (modMass) or the
     * per-residue fixed-mod value is shown.
     */
    modMassDisplay(): string {
      if (this.selectedModification !== undefined) {
        return formatSigned(modificationMassMap[this.selectedModification])
      }
      if (this.variableMod !== undefined && this.variableMod !== 0) {
        return formatSigned(this.variableMod)
      }
      if (this.sequenceObject.modMass) {
        return this.sequenceObject.modMass
      }
      if (this.modification !== null) {
        return formatSigned(this.modification)
      }
      return ''
    },
  },
  watch: {
    selectedModification() {
      // Reflect selection into the badge immediately (parity with legacy).
      if (this.selectedModification !== undefined && modificationMassMap[this.selectedModification] !== undefined) {
        this.sequenceObject.modMass = formatSigned(modificationMassMap[this.selectedModification])
      }
    },
    // Clear the residue selection when the Tags toggle is turned off (P2, parity
    // with FLASHApp AminoAcidCell ~372-376). The parent owns the selection state.
    showTags(newValue: boolean) {
      if (!newValue) {
        this.$emit('residueSelectionCleared')
      }
    },
  },
  methods: {
    selectCell(): void {
      // Residue -> Tag-Table cross-link (EXTEND): clicking a residue COVERED by
      // sequence tags (coverage > 0) emits its index for the parent to toggle the
      // residue-position selection, mirroring FLASHApp AminoAcidCell.selectCell.
      // Gated on the Tags toggle (P2): the residue selection is only active when
      // sequence tags are visible (parity with FLASHApp ~386).
      if (this.hasSequenceTags && this.showTags) {
        this.$emit('residueSelected', this.index)
      }
      // Fragment selection (existing behavior) is independent of coverage.
      if (this.hasMatchingFragments) {
        this.$emit('selected', this.index)
      }
    },
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

/** Format a mass shift with an explicit sign (e.g. "+57.02", "-0.98"). */
function formatSigned(mass: number): string {
  return mass.toLocaleString('en-US', { signDisplay: 'always', maximumFractionDigits: 2 })
}
</script>

<style scoped>
.foreground {
  position: relative;
  z-index: 1000;
}

.sequence-amino-acid-highlighted,
.sequence-amino-acid.highlighted {
  background-color: #f3a712;
  color: #000000;
  outline: 3px solid #29335c;
  font-weight: bold;
}

/* Regex highlighting (P1) */
.sequence-amino-acid.regex-highlighted {
  background-color: #e3f2fd !important;
  color: #1565c0 !important;
  outline: 2px solid #1976d2 !important;
  font-weight: bold;
}

/* When both highlighted and regex-highlighted, prioritize normal highlighting */
.sequence-amino-acid.highlighted.regex-highlighted {
  background-color: #f3a712 !important;
  color: #000000 !important;
  outline: 3px solid #29335c !important;
}

/* Truncated proteoform flank (P0) */
.sequence-amino-acid.truncated .aa-text {
  color: rgba(128, 128, 128, 0.3);
  outline: rgba(128, 128, 128, 0.3);
  text-decoration: line-through !important;
}

.sequence-amino-acid {
  background-color: var(--amino-acid-cell-bg-color);
  color: var(--amino-acid-cell-color);
  cursor: pointer;
  aspect-ratio: 1;
}

.sequence-amino-acid:hover {
  background-color: var(--amino-acid-cell-hover-bg-color);
  color: var(--amino-acid-cell-hover-color);
}

.sequence-amino-acid-highlighted {
  background-color: var(--amino-acid-cell-bg-color);
  color: #f3a712;
}

.sequence-amino-acid-highlighted:hover {
  background-color: var(--amino-acid-cell-hover-bg-color);
}

.fixed-mod {
  color: #f3a712;
}

/* Fragment marker base container */
.frag-marker-container {
  width: 100%;
  height: 100%;
  position: absolute;
  z-index: 1000;
}

.frag-marker-a {
  top: -28%;
  left: 15%;
}

.frag-marker-b {
  top: -8%;
  left: 13%;
}

.frag-marker-c {
  top: -28%;
  left: 15%;
}

.frag-marker-x {
  bottom: -32%;
  left: -10%;
}

.frag-marker-y {
  bottom: -8%;
  left: -10%;
}

.frag-marker-z {
  bottom: -32%;
  left: -10%;
}

.frag-marker-extra-type {
  width: 100%;
  height: 100%;
  position: absolute;
  top: -30%;
  z-index: 1000;
}

.aa-text {
  position: absolute;
  font-size: var(--amino-acid-font-size, 12px);
  font-weight: 500;
}

/* Tag-span bracket markers (P0) */
.tag-marker {
  position: absolute;
  top: -7.5%;
  left: -7.5%;
  width: 115%;
  height: 115%;
  display: flex;
  align-items: center;
  justify-content: right;
  border: 0.3em solid black;
  z-index: 1100;
}

.tag-start {
  clip-path: inset(0 50% 0 0);
}

.tag-end {
  clip-path: inset(0 0 0 50%);
}

/* Modification marker with dotted pattern background (like FLASHApp) */
.mod-marker {
  position: absolute;
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: right;
  background-image: radial-gradient(var(--mod-marker-dot-color, #676a9c) 0.5px, transparent 0.5px),
    radial-gradient(#444cf7 0.5px, var(--mod-marker-bg-color, #e5e5f7) 0.5px);
  background-size: 15px 15px;
  background-position: 0 0, 10px 10px;
  background-repeat: repeat;
}

.mod-start {
  clip-path: inset(0 50% 0 0);
}

.mod-end {
  clip-path: inset(0 0 0 50%);
}

.mod-start-cont {
  clip-path: inset(0 0 0 50%);
}

.mod-end-cont {
  clip-path: inset(0 50% 0 0);
}

.mod-center-cont {
  width: 125%;
}

/* Modification mass badge */
.mod-mass {
  background-color: var(--mod-mass-bg-color, white);
  color: var(--mod-mass-text-color, inherit);
  display: inline-block;
  position: absolute;
  top: -15%;
  right: -25%;
  display: flex;
  align-items: center;
  justify-content: right;
  border: 0.1em solid var(--mod-mass-border-color, #a79c91);
  font-size: 0.7em;
  padding: 0em 0.2em;
  z-index: 1100;
}

/* Extra fragment circle stroke */
.extra-frag-circle {
  stroke: var(--extra-frag-stroke, black);
}

/* Modification mass with fragment ion colored borders */
.mod-mass-a {
  display: inline-block;
  position: absolute;
  top: -15%;
  right: -25%;
  display: flex;
  align-items: center;
  border-top: 0.2em solid green;
  border-right: 0.2em solid green;
  border-bottom: 0.2em solid green;
  border-radius: 0.5rem;
  padding: 0em 0.2em;
  z-index: 1200;
  font-size: 0.7em;
  color: rgba(0, 0, 0, 0);
}

.mod-mass-b {
  display: inline-block;
  position: absolute;
  top: -15%;
  right: -25%;
  display: flex;
  align-items: center;
  border-top: 0.2em solid blue;
  border-right: 0.2em solid blue;
  border-bottom: 0.2em solid blue;
  border-radius: 0.5rem;
  z-index: 1200;
  padding: 0em 0.2em;
  font-size: 0.7em;
  color: rgba(0, 0, 0, 0);
}

.mod-mass-c {
  display: inline-block;
  position: absolute;
  top: -15%;
  right: -25%;
  display: flex;
  align-items: center;
  border-top: 0.2em solid red;
  border-right: 0.2em solid red;
  border-bottom: 0.2em solid red;
  border-radius: 0.5rem;
  z-index: 1200;
  font-size: 0.7em;
  padding: 0em 0.2em;
  color: rgba(0, 0, 0, 0);
}
</style>
