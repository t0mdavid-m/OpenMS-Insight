<template>
  <div class="sequence-view-container" :style="containerStyle">
    <v-sheet class="pa-4 rounded-lg" :theme="theme?.base ?? 'light'" border>
      <!-- Header title -->
      <div class="d-flex justify-center mb-2">
        <h4>Sequence View</h4>
      </div>

      <!-- Precursor / Proteoform mass header (P1) -->
      <div v-if="massData.length !== 0" class="d-flex justify-space-evenly align-center flex-wrap mb-2">
        <h3 class="mr-2">{{ massTitle }}</h3>
        <v-divider :vertical="true"></v-divider>
        <template v-for="(item, mIndex) in massData" :key="mIndex">
          <span class="px-2">{{ item }}</span>
          <v-divider :vertical="true"></v-divider>
        </template>
      </div>

      <!-- Toolbar -->
      <div class="d-flex justify-end px-4 mb-4">
        <SequenceViewInformation />

        <v-btn variant="text" icon size="small" :disabled="sequence.length === 0" @click="copySequence">
          <v-icon>mdi-content-copy</v-icon>
          <v-tooltip activator="parent" location="bottom">Copy sequence to clipboard</v-tooltip>
        </v-btn>

        <!-- Change sequence dialog (Deconv / non-TnT path) (P1) -->
        <v-btn
          v-if="shouldShowSequenceChangeButton"
          variant="text"
          icon
          size="small"
          @click="openSequenceDialog"
        >
          <v-icon>mdi-dna</v-icon>
          <v-tooltip activator="parent" location="bottom">Change sequence</v-tooltip>
        </v-btn>

        <!-- Regex highlight toggle (P1) -->
        <v-btn variant="text" icon size="small" :disabled="sequence.length === 0" @click="toggleRegexHighlight">
          <v-icon>mdi-magnify</v-icon>
          <v-tooltip activator="parent" location="bottom">
            {{ showRegexHighlight ? 'Hide regex highlighting' : 'Show regex highlighting' }}
          </v-tooltip>
        </v-btn>

        <v-btn id="settings-btn" variant="text" icon size="small">
          <v-icon>mdi-cog</v-icon>
        </v-btn>
        <v-menu :close-on-content-click="false" activator="#settings-btn" location="bottom">
          <v-card min-width="300">
            <v-list>
              <v-list-item>
                <v-list-item-title># amino acids per row</v-list-item-title>
                <v-slider
                  v-model="rowWidth"
                  :ticks="{ 20: '20', 25: '25', 30: '30', 35: '35', 40: '40' }"
                  :min="20"
                  :max="40"
                  step="5"
                  show-ticks="always"
                  tick-size="4"
                ></v-slider>
              </v-list-item>
              <v-list-item>
                <v-list-item-title>Font Size</v-list-item-title>
                <v-slider
                  v-model="fontSize"
                  :ticks="{ 8: '8', 10: '10', 12: '12', 14: '14', 16: '16' }"
                  :min="8"
                  :max="16"
                  step="2"
                  show-ticks="always"
                  tick-size="4"
                ></v-slider>
              </v-list-item>
              <v-list-item>
                <v-list-item-title>Visibility</v-list-item-title>
                <div class="d-flex justify-space-evenly flex-wrap">
                  <v-checkbox
                    v-for="visibilityOption in visibilityOptions"
                    :key="visibilityOption.text"
                    v-model="visibilityOption.selected"
                    :label="visibilityOption.text"
                    hide-details
                    density="comfortable"
                  ></v-checkbox>
                </div>
              </v-list-item>
              <v-list-item>
                <v-list-item-title>Fragment ion types</v-list-item-title>
                <div class="d-flex justify-space-evenly">
                  <v-checkbox
                    v-for="ion in ionTypes"
                    :key="ion.text"
                    v-model="ion.selected"
                    :label="ion.text"
                    :disabled="!showFragments"
                    hide-details
                    density="comfortable"
                  ></v-checkbox>
                </div>
                <div class="d-flex justify-space-evenly">
                  <v-checkbox
                    v-for="(_, extra) in ionTypesExtra"
                    :key="extra"
                    v-model="ionTypesExtra[extra as ExtraFragmentType]"
                    :label="extra"
                    :disabled="!showFragments"
                    hide-details
                    density="comfortable"
                  ></v-checkbox>
                </div>
              </v-list-item>
              <v-list-item>
                <v-list-item-title>Fragment mass tolerance</v-list-item-title>
                <div class="d-flex align-center ga-2">
                  <v-text-field
                    v-model.number="fragmentMassTolerance"
                    type="number"
                    hide-details="auto"
                    :disabled="!showFragments"
                    density="compact"
                    style="max-width: 100px"
                  ></v-text-field>
                  <v-btn-toggle v-model="toleranceIsPpm" mandatory density="compact" :disabled="!showFragments">
                    <v-btn :value="true" size="small">ppm</v-btn>
                    <v-btn :value="false" size="small">Da</v-btn>
                  </v-btn-toggle>
                </div>
              </v-list-item>
              <v-list-item v-if="hasExternalAnnotations">
                <v-list-item-title>Use search engine annotations</v-list-item-title>
                <v-checkbox
                  v-model="useExternalAnnotations"
                  :disabled="!showFragments"
                  hide-details
                  density="comfortable"
                ></v-checkbox>
                <v-list-item-subtitle class="text-caption">
                  {{ externalAnnotations.length }} annotations from idXML
                </v-list-item-subtitle>
              </v-list-item>
            </v-list>
          </v-card>
        </v-menu>
      </div>

      <!-- Regex highlighting input (P1) -->
      <div v-if="showRegexHighlight" class="pb-4 px-4">
        <v-card variant="outlined" class="pa-3">
          <v-row align="center">
            <v-col cols="12" md="8">
              <v-text-field
                v-model="regexPattern"
                label="Regex pattern for highlighting"
                placeholder="e.g., A+, [KR], M.*L"
                :error-messages="regexError"
                hide-details="auto"
                density="compact"
                @input="onRegexInput"
              >
                <template #prepend-inner>
                  <v-icon>mdi-regex</v-icon>
                </template>
              </v-text-field>
            </v-col>
            <v-col cols="12" md="4">
              <div v-if="regexHighlightedIndices.size > 0" class="text-caption text-medium-emphasis">
                {{ regexHighlightedIndices.size }} cells highlighted
              </div>
              <div v-else-if="regexPattern && !regexError" class="text-caption text-medium-emphasis">
                No matches found
              </div>
            </v-col>
          </v-row>
        </v-card>
      </div>

      <!-- Sequence grid (+ coverage scale legend) -->
      <div class="sequence-and-scale">
      <div class="px-2 pb-4 sequence-grid-area" :class="gridClasses" style="width: 100%; max-width: 100%">
        <template v-for="(aaObj, aaIndex) in sequenceObjects" :key="aaIndex">
          <!-- Row number (left). Protein-absolute when truncations are shown,
               otherwise cleaved (determined-span-relative) numbering (P2). -->
          <div
            v-if="(showTruncations && aaIndex !== 0 && aaIndex % rowWidth === 0) || (!showTruncations && (aaIndex - sequenceStart) !== 0 && (aaIndex - sequenceStart) % rowWidth === 0 && aaIndex < sequenceEnd && aaIndex > sequenceStart)"
            class="d-flex justify-center align-center row-number"
          >
            {{ showTruncations ? aaIndex + 1 : aaIndex - sequenceStart + 1 }}
          </div>

          <!-- N-terminal marker -->
          <ProteinTerminalCell
            v-if="aaIndex === 0"
            protein-terminal="N-term"
            :truncated="nTruncation"
            :index="-1"
            :determined="nDetermined"
            :disable-variable-modification-selection="disableVariableModifications"
            :variable-mod="variableModifications[-1]"
            :font-size="fontSize"
            @update-modification="onUpdateModification"
          />

          <!-- Amino acid cell. With truncations hidden, only the determined span
               is rendered (P0/P2). -->
          <AminoAcidCell
            v-if="showTruncations || (sequenceStart <= aaIndex && sequenceEnd >= aaIndex)"
            :sequence-object="aaObj"
            :index="aaIndex"
            :sequence-length="sequence.length"
            :fixed-modification="isFixedModification(aaObj.aminoAcid)"
            :show-fragments="showFragments"
            :show-modifications="showModifications"
            :show-tags="showTags"
            :show-coverage="showCoverage"
            :font-size="fontSize"
            :is-highlighted="selectedAAIndex === aaIndex || selectedResidueIndex === aaIndex"
            :is-regex-highlighted="regexHighlightedIndices.has(aaIndex)"
            :modification="modifications[aaIndex] ?? null"
            :disable-variable-modification-selection="disableVariableModifications"
            :variable-mod="variableModifications[aaIndex]"
            @selected="onAminoAcidSelected"
            @residue-selected="onResidueSelected"
            @residue-selection-cleared="onResidueSelectionCleared"
            @update-modification="onUpdateModification"
          />

          <!-- Row number (right) -->
          <div
            v-if="(showTruncations && aaIndex % rowWidth === rowWidth - 1 && aaIndex !== sequence.length - 1) || (!showTruncations && (aaIndex - sequenceStart) % rowWidth === rowWidth - 1 && aaIndex < sequenceEnd && aaIndex > sequenceStart)"
            class="d-flex justify-center align-center row-number"
          >
            {{ showTruncations ? aaIndex + 1 : aaIndex - sequenceStart + 1 }}
          </div>

          <!-- C-terminal marker -->
          <ProteinTerminalCell
            v-if="aaIndex === sequence.length - 1"
            protein-terminal="C-term"
            :truncated="cTruncation"
            :index="sequence.length"
            :determined="cDetermined"
            :disable-variable-modification-selection="disableVariableModifications"
            :variable-mod="variableModifications[sequence.length]"
            :font-size="fontSize"
            @update-modification="onUpdateModification"
          />
        </template>
      </div>

      <!-- Coverage scale legend (EXTEND): shown when coverage data is present and
           tags are visible (P2: gate on showTags). -->
      <div v-if="showCoverageScale" class="scale-container" title="Sequence Tag Coverage">
        <div class="scale-text">{{ maxCoverage + 'x' }}</div>
        <div class="scale"></div>
        <div class="scale-text">1x</div>
      </div>
      </div>

      <!-- Fragment table -->
      <div v-if="showFragments && fragmentTableData.length > 0" class="mt-4">
        <v-divider class="mb-4"></v-divider>
        <div class="d-flex justify-space-between align-center mb-2">
          <h5>Matching Fragments ({{ fragmentTableData.length }})</h5>
          <span class="text-caption">Residue cleavage: {{ residueCleavagePercentage.toFixed(1) }}%</span>
        </div>
        <v-data-table
          :headers="fragmentTableHeaders"
          :items="fragmentTableData"
          :items-per-page="10"
          density="compact"
          class="elevation-1"
          :row-props="getRowProps"
          @click:row="onFragmentTableRowClick"
        ></v-data-table>
      </div>
    </v-sheet>

    <!-- Copy snackbar -->
    <v-snackbar v-model="copySnackbar" :timeout="2000" location="bottom">
      {{ copySnackbarText }}
    </v-snackbar>

    <!-- Custom sequence input dialog (Deconv / non-TnT path) (P1) -->
    <v-dialog v-model="sequenceDialog" max-width="600" persistent>
      <v-card>
        <v-card-title class="text-h6">Enter Custom Sequence</v-card-title>
        <v-card-text>
          <v-textarea
            v-model="customSequenceInput"
            label="Protein Sequence"
            placeholder="Enter amino acid sequence (e.g., MKFLVNVALVF...)"
            :error-messages="sequenceInputError"
            rows="6"
            auto-grow
            counter
            hint="Enter single-letter amino acid codes only"
            persistent-hint
          >
            <template #prepend-inner>
              <v-icon>mdi-dna</v-icon>
            </template>
          </v-textarea>
        </v-card-text>
        <v-card-actions>
          <v-spacer></v-spacer>
          <v-btn variant="text" @click="closeSequenceDialog">Cancel</v-btn>
          <v-btn color="primary" variant="elevated" @click="submitCustomSequence">Apply Sequence</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<script lang="ts">
import { defineComponent } from 'vue'
import { useStreamlitDataStore } from '@/stores/streamlit-data'
import { useSelectionStore } from '@/stores/selection'
import type { Theme } from 'streamlit-component-lib'
import type { SequenceData, SequenceObject, FragmentTableRow, ExternalAnnotation, SequenceViewSettings, ModRange, TagSpan } from '@/types/sequence-data'
import { UNDETERMINED_TERMINUS } from '@/types/sequence-data'
import AminoAcidCell from './AminoAcidCell.vue'
import ProteinTerminalCell from './ProteinTerminalCell.vue'
import SequenceViewInformation from './SequenceViewInformation.vue'
import { extraFragmentTypeObject, type ExtraFragmentType } from './modification'

// Proton mass for m/z calculations
const PROTON_MASS = 1.007276

// Superscript characters for charge display
const SUPERSCRIPT_DIGITS: Record<string, string> = {
  '0': '⁰', '1': '¹', '2': '²', '3': '³', '4': '⁴',
  '5': '⁵', '6': '⁶', '7': '⁷', '8': '⁸', '9': '⁹'
}

function toSuperscript(n: number): string {
  return String(n).split('').map(d => SUPERSCRIPT_DIGITS[d] || d).join('')
}

export default defineComponent({
  name: 'SequenceView',
  components: {
    AminoAcidCell,
    ProteinTerminalCell,
    SequenceViewInformation,
  },
  props: {
    args: {
      type: Object,
      required: true,
    },
    index: {
      type: Number,
      required: true,
    },
  },
  setup() {
    const streamlitDataStore = useStreamlitDataStore()
    const selectionStore = useSelectionStore()
    return { streamlitDataStore, selectionStore }
  },
  data() {
    return {
      rowWidth: 35,
      fontSize: 12,
      autoZoomApplied: false,
      // Visibility toggles. Fragments/Modifications always present; Tags and
      // Truncations are pushed once on the TnT path (computed_mass present). (P2)
      visibilityOptions: [
        { text: 'Fragments', selected: true },
        { text: 'Modifications', selected: true },
      ] as { text: string; selected: boolean }[],
      ionTypes: [
        { text: 'a', selected: false },
        { text: 'b', selected: true },
        { text: 'c', selected: false },
        { text: 'x', selected: false },
        { text: 'y', selected: true },
        { text: 'z', selected: false },
      ],
      ionTypesExtra: {
        'water loss': false,
        'ammonium loss': false,
        'proton loss/addition': false,
      } as Record<ExtraFragmentType, boolean>,
      fragmentMassTolerance: 10,
      toleranceIsPpm: true,
      // Track if settings have been initialized from Python defaults.
      // Once initialized, user adjustments persist across filter changes.
      settingsInitialized: false,
      useExternalAnnotations: true,
      sequenceObjects: [] as SequenceObject[],
      fragmentTableData: [] as FragmentTableRow[],
      selectedAAIndex: undefined as number | undefined,
      // 0-based grid index of the residue toggled for the Tag-Table cross-link
      // (EXTEND). undefined => no residue selected. Used for highlighting and
      // toggle detection; the value PUBLISHED to the store is protein-absolute.
      selectedResidueIndex: undefined as number | undefined,
      selectedFragmentRowIndex: undefined as number | undefined,
      copySnackbar: false,
      copySnackbarText: '',
      // Precursor / Proteoform mass header (P1)
      massData: [] as string[],
      massTitle: '' as string,
      // Regex highlighting (P1)
      showRegexHighlight: false,
      regexPattern: '' as string,
      regexError: '' as string,
      regexHighlightedIndices: new Set<number>(),
      // Custom-sequence change dialog (P1)
      sequenceDialog: false,
      customSequenceInput: '' as string,
      sequenceInputError: '' as string,
      // Interactive variable modifications keyed by grid index (Deconv path).
      // Index -1 = N-terminal, sequence.length = C-terminal. (P1)
      variableModifications: {} as Record<number, number>,
    }
  },
  computed: {
    containerStyle(): Record<string, string> {
      return {
        height: `${this.args.height || 400}px`,
        overflowY: 'auto'
      }
    },
    theme(): Theme | undefined {
      return this.streamlitDataStore.theme
    },
    sequenceData(): SequenceData | undefined {
      return this.streamlitDataStore.allDataForDrawing.sequenceData as SequenceData | undefined
    },
    observedMasses(): number[] {
      return (this.streamlitDataStore.allDataForDrawing.observedMasses as number[]) ?? []
    },
    /** Peak IDs corresponding to observed masses (for interactivity linking) */
    peakIds(): number[] | undefined {
      return this.streamlitDataStore.allDataForDrawing.peakIds as number[] | undefined
    },
    precursorMass(): number {
      return (this.streamlitDataStore.allDataForDrawing.precursorMass as number) ?? 0
    },
    /** Interactivity mapping from component args */
    interactivity(): Record<string, string> {
      return (this.args.interactivity as Record<string, string>) ?? {}
    },
    /** Whether data is deconvolved (neutral masses) or not (m/z values) */
    deconvolved(): boolean {
      return (this.args.deconvolved as boolean) ?? true
    },
    /** Maximum charge state to consider for fragment matching */
    maxCharge(): number {
      return (this.streamlitDataStore.allDataForDrawing?.precursorCharge as number) ?? 1
    },
    sequence(): string[] {
      return this.sequenceData?.sequence ?? []
    },
    modifications(): (number | null)[] {
      return this.sequenceData?.modifications ?? []
    },
    theoreticalMass(): number {
      return this.sequenceData?.theoretical_mass ?? 0
    },
    fixedModificationSites(): string[] {
      return this.sequenceData?.fixed_modifications ?? []
    },
    /** Observed/deconvolved proteoform mass (Da), undefined when absent (P1) */
    computedMass(): number | undefined {
      return this.sequenceData?.computed_mass
    },
    /** TnT path when a proteoform (computed) mass is present (P1) */
    displayTnT(): boolean {
      return this.computedMass !== undefined
    },
    /**
     * Whether the right-click variable-modification context menu is disabled.
     * Disabled on the TnT path, otherwise driven by the Python flag
     * `disableVariableModifications` (default True). (P1)
     */
    disableVariableModifications(): boolean {
      if (this.displayTnT) {
        return true
      }
      return (this.args.disableVariableModifications as boolean) ?? true
    },
    shouldShowSequenceChangeButton(): boolean {
      return !this.displayTnT
    },
    /** Whether the Fragments visibility toggle is on */
    showFragments(): boolean {
      return this.visibilityOptions.find((o) => o.text === 'Fragments')?.selected ?? true
    },
    /** Whether the Modifications visibility toggle is on */
    showModifications(): boolean {
      return this.visibilityOptions.find((o) => o.text === 'Modifications')?.selected ?? true
    },
    /** Tags visibility (TnT path only). Gates coverage shading + tag markers. (P2) */
    showTags(): boolean {
      if (!this.displayTnT) {
        return false
      }
      return this.visibilityOptions.find((o) => o.text === 'Tags')?.selected ?? false
    },
    /** Truncations visibility (TnT path only). Gates truncated flank rendering. (P2) */
    showTruncations(): boolean {
      if (!this.displayTnT) {
        return false
      }
      return this.visibilityOptions.find((o) => o.text === 'Truncations')?.selected ?? false
    },
    /**
     * Raw (possibly-sentinel) reported proteoform start. UNDETERMINED_TERMINUS
     * (-2) means the N-terminus is open/undetermined. Absent => 0. (P0)
     */
    sequenceStartReported(): number {
      return this.sequenceData?.proteoform_start ?? 0
    },
    /** Effective determined-region start (clamped, sentinel -> 0). (P0) */
    sequenceStart(): number {
      return this.sequenceStartReported < 0 ? 0 : this.sequenceStartReported
    },
    /** Whether an N-terminal truncation flank exists. (P0) */
    nTruncation(): boolean {
      return this.sequenceStart > 0
    },
    /** Whether the N-terminus is determined (not the open sentinel). (P0) */
    nDetermined(): boolean {
      return this.sequenceStartReported >= 0
    },
    /**
     * Raw (possibly-sentinel) reported proteoform end. UNDETERMINED_TERMINUS
     * (-2) means the C-terminus is open/undetermined. Absent => last residue. (P0)
     */
    sequenceEndReported(): number {
      return this.sequenceData?.proteoform_end ?? this.sequence.length - 1
    },
    /** Effective determined-region end (clamped, sentinel -> last residue). (P0) */
    sequenceEnd(): number {
      return this.sequenceEndReported < 0 ? this.sequence.length - 1 : this.sequenceEndReported
    },
    /** Whether a C-terminal truncation flank exists. (P0) */
    cTruncation(): boolean {
      return this.sequenceEnd < this.sequence.length - 1
    },
    /** Whether the C-terminus is determined (not the open sentinel). (P0) */
    cDetermined(): boolean {
      return this.sequenceEndReported >= 0
    },
    /** Ambiguous modification ranges (spanning dotted regions). (P0) */
    modRanges(): ModRange[] {
      return this.sequenceData?.mod_ranges ?? []
    },
    /**
     * The interactivity identifier (if any) mapped to the special sentinel column
     * "tag_span". When configured, the incoming selection value (a TagSpan
     * {start, end, nTerminal}) drives the per-residue tag-start/tag-end brackets,
     * mirroring FLASHApp's selectionStore.selectedTag + updateTagPosition. (P0)
     */
    tagSpanIdentifier(): string | undefined {
      for (const [identifier, column] of Object.entries(this.interactivity)) {
        if (column === 'tag_span') {
          return identifier
        }
      }
      return undefined
    },
    /** Currently-selected tag span from the store (via the tag_span sentinel). (P0) */
    selectedTag(): TagSpan | undefined {
      const identifier = this.tagSpanIdentifier
      if (identifier === undefined) {
        return undefined
      }
      const value = this.selectionStore.$state[identifier]
      if (value && typeof value === 'object' && 'start' in value && 'end' in value) {
        return value as TagSpan
      }
      return undefined
    },
    /** Per-residue normalized coverage (EXTEND). Empty when unavailable. */
    coverage(): number[] {
      return this.sequenceData?.coverage ?? []
    },
    /**
     * Offset from a residue's 0-based grid index to its PROTEIN-ABSOLUTE 0-based
     * position (EXTEND). Defaults to 0 (displayed sequence == full protein /
     * starts at protein position 0). Drives the residue-click Tag-Table cross-link.
     */
    sequenceOffset(): number {
      return this.sequenceData?.sequence_offset ?? 0
    },
    /**
     * The interactivity identifier (if any) mapped to the special sentinel column
     * "residue_position" (EXTEND). When configured, clicking a covered residue
     * sets this selection to the clicked residue's protein-absolute position
     * (toggle off when re-clicking the same residue), mirroring FLASHApp's
     * selectionStore.selectedAApos used by the Tag-Table range filter.
     */
    residuePositionIdentifier(): string | undefined {
      for (const [identifier, column] of Object.entries(this.interactivity)) {
        if (column === 'residue_position') {
          return identifier
        }
      }
      return undefined
    },
    /** Raw maximum coverage (EXTEND). -1 when unavailable. */
    maxCoverage(): number {
      return this.sequenceData?.maxCoverage ?? -1
    },
    /**
     * Whether per-residue coverage coloring is active (EXTEND). On the TnT path
     * coverage shading is gated on the Tags visibility toggle (P2, parity with
     * FLASHApp). On the non-TnT path it stays active whenever coverage data is
     * present (preserves existing behavior).
     */
    showCoverage(): boolean {
      if (this.coverage.length === 0) {
        return false
      }
      if (this.displayTnT) {
        return this.showTags
      }
      return true
    },
    /** Whether to show the coverage scale legend (EXTEND). */
    showCoverageScale(): boolean {
      return this.showCoverage && this.maxCoverage > 0
    },
    /** FLASHApp-style settings (tolerance / ion_types), if provided (EXTEND). */
    settings(): SequenceViewSettings | undefined {
      return this.streamlitDataStore.allDataForDrawing.settings as
        | SequenceViewSettings
        | undefined
    },
    /** External annotations from search engine if available */
    externalAnnotations(): ExternalAnnotation[] {
      return this.sequenceData?.external_annotations ?? []
    },
    /** Whether external annotations are available */
    hasExternalAnnotations(): boolean {
      return this.externalAnnotations.length > 0
    },
    /** Default tolerance from search parameters */
    defaultTolerance(): number {
      return this.sequenceData?.fragment_tolerance ?? 10
    },
    /** Default tolerance type from search parameters */
    defaultToleranceIsPpm(): boolean {
      return this.sequenceData?.fragment_tolerance_ppm ?? true
    },
    gridClasses(): Record<string, boolean> {
      return {
        'sequence-grid': true,
        [`grid-width-${this.rowWidth}`]: true,
      }
    },
    residueCleavagePercentage(): number {
      if (this.sequenceObjects.length <= 1) return 0

      let explainedCleavage = 0
      for (let i = 0; i < this.sequenceObjects.length - 1; i++) {
        const preAA = this.sequenceObjects[i]
        const postAA = this.sequenceObjects[i + 1]
        if (preAA.aIon || preAA.bIon || preAA.cIon || postAA.xIon || postAA.yIon || postAA.zIon) {
          explainedCleavage++
        }
      }
      // Denominator = determined-span length (P2, parity with FLASHApp ~567),
      // not the full sequence length. Falls back to full length when no
      // proteoform bounds are reported.
      const denom = this.sequenceEnd - this.sequenceStart
      if (denom <= 0) {
        return 0
      }
      return (explainedCleavage / denom) * 100
    },
    fragmentTableHeaders() {
      const headers = [
        { title: 'Name', key: 'Name', sortable: true },
        { title: 'Ion Type', key: 'IonType', sortable: true },
        { title: 'Ion #', key: 'IonNumber', sortable: true },
      ]
      // Add Charge column for non-deconvolved data
      if (!this.deconvolved) {
        headers.push({ title: 'z', key: 'Charge', sortable: true })
      }
      headers.push(
        { title: this.deconvolved ? 'Theo. Mass' : 'Theo. m/z', key: 'TheoreticalMass', sortable: true },
        { title: this.deconvolved ? 'Obs. Mass' : 'Obs. m/z', key: 'ObservedMass', sortable: true },
        { title: 'Δ Da', key: 'MassDiffDa', sortable: true },
        { title: 'Δ ppm', key: 'MassDiffPpm', sortable: true },
      )
      return headers
    },
  },
  watch: {
    sequenceData: {
      handler(newData, oldData) {
        // Reset auto-zoom flag when sequence changes
        const newSeq = newData?.sequence?.join('') ?? ''
        const oldSeq = oldData?.sequence?.join('') ?? ''
        if (newSeq !== oldSeq) {
          this.autoZoomApplied = false
          // New proteoform/sequence: clear any residue toggle so the highlight
          // and published residue-position selection don't carry across (EXTEND).
          if (this.selectedResidueIndex !== undefined) {
            this.selectedResidueIndex = undefined
            const identifier = this.residuePositionIdentifier
            if (identifier !== undefined) {
              this.selectionStore.updateSelection(identifier, undefined)
            }
          }
          // Clear interactive variable modifications on sequence change (P1).
          this.variableModifications = {}
        }

        // Ensure Tags/Truncations visibility options exist on the TnT path (P2).
        if (this.displayTnT && !this.visibilityOptions.some((o) => o.text === 'Tags')) {
          this.visibilityOptions.push({ text: 'Truncations', selected: true })
          this.visibilityOptions.push({ text: 'Tags', selected: true })
        }

        this.initializeSequenceObjects()
        this.prepareAmbiguousModifications()
        this.updateTagPosition()
        this.preparePrecursorInfo()

        // Apply auto-zoom for short sequences
        this.applyAutoZoom()

        // Initialize settings from Python defaults ONLY on first load.
        // Once initialized, user adjustments persist across filter changes.
        if (!this.settingsInitialized) {
          if (this.sequenceData?.fragment_tolerance !== undefined) {
            this.fragmentMassTolerance = this.sequenceData.fragment_tolerance
          }
          if (this.sequenceData?.fragment_tolerance_ppm !== undefined) {
            this.toleranceIsPpm = this.sequenceData.fragment_tolerance_ppm
          }
          // FLASHApp-style settings (TnT) take precedence when present:
          // ion_types drive the default selected fragment ion types, and
          // tolerance (ppm) overrides the fragment mass tolerance. (EXTEND)
          if (this.settings?.ion_types !== undefined) {
            for (const ion of this.ionTypes) {
              ion.selected = this.settings.ion_types.includes(ion.text)
            }
          }
          if (this.settings?.tolerance !== undefined) {
            this.fragmentMassTolerance = this.settings.tolerance
            this.toleranceIsPpm = true
          }
          if (this.sequenceData?.neutral_losses !== undefined) {
            this.ionTypesExtra['water loss'] = this.sequenceData.neutral_losses
            this.ionTypesExtra['ammonium loss'] = this.sequenceData.neutral_losses
          }
          if (this.sequenceData?.proton_loss_addition !== undefined) {
            this.ionTypesExtra['proton loss/addition'] = this.sequenceData.proton_loss_addition
          }
          this.settingsInitialized = true
        }
        this.matchFragments()
      },
      immediate: true,
      deep: true,
    },
    observedMasses: {
      handler() {
        this.matchFragments()
        // Refresh the precursor mass header (observed mass travels with peaks).
        this.preparePrecursorInfo()
      },
      deep: true,
    },
    ionTypes: {
      handler() {
        this.resetFragmentMarkers()
        this.matchFragments()
      },
      deep: true,
    },
    ionTypesExtra: {
      handler() {
        this.resetFragmentMarkers()
        this.matchFragments()
      },
      deep: true,
    },
    fragmentMassTolerance() {
      this.resetFragmentMarkers()
      this.matchFragments()
    },
    toleranceIsPpm() {
      this.resetFragmentMarkers()
      this.matchFragments()
    },
    useExternalAnnotations() {
      this.resetFragmentMarkers()
      this.matchFragments()
    },
    // Re-paint the tag-span brackets when the incoming selection changes (P0).
    selectedTag: {
      handler() {
        this.updateTagPosition()
      },
      deep: true,
    },
    // Re-match fragments and refresh the mass header when an interactive
    // variable modification is added/removed (P1).
    variableModifications: {
      handler() {
        this.resetFragmentMarkers()
        this.matchFragments()
        this.preparePrecursorInfo()
      },
      deep: true,
    },
  },
  methods: {
    initializeSequenceObjects(): void {
      this.sequenceObjects = []
      const coverage = this.coverage
      const start = this.sequenceStart
      const end = this.sequenceEnd
      this.sequence.forEach((aa, index) => {
        // A residue is a truncated flank when outside the determined span (P0).
        const truncated = index < start || index > end
        this.sequenceObjects.push({
          aminoAcid: aa,
          // Per-residue coverage for coverage coloring (EXTEND). undefined when
          // no coverage data is present -> AminoAcidCell renders no shading.
          coverage: coverage[index],
          truncated,
          tagStart: false,
          tagEnd: false,
          modStart: false,
          modCenter: false,
          modEnd: false,
          modMass: '',
          modLabels: '',
          aIon: false,
          bIon: false,
          cIon: false,
          xIon: false,
          yIon: false,
          zIon: false,
          extraTypes: [],
        })
      })
    },
    /**
     * Ambiguous modification ranges -> per-residue modStart/modCenter/modEnd
     * markers + mass badge + possible-mod labels (P0). Mirrors FLASHApp's
     * prepareAmbigiousModifications. DISTINCT from per-residue fixed mods.
     */
    prepareAmbiguousModifications(): void {
      for (const modification of this.modRanges) {
        const start = modification.start
        const end = modification.end
        const massDisplay = modification.mass_diff.toLocaleString('en-US', {
          signDisplay: 'always',
          maximumFractionDigits: 2,
        })
        for (let index = start; index <= end; index++) {
          if (index < 0 || index >= this.sequenceObjects.length) {
            continue
          }
          if (index === start) {
            this.sequenceObjects[index].modStart = true
          }
          if (index === end) {
            this.sequenceObjects[index].modEnd = true
            this.sequenceObjects[index].modMass = massDisplay
            this.sequenceObjects[index].modLabels = modification.labels
          }
          if (index !== start && index !== end) {
            this.sequenceObjects[index].modCenter = true
          }
        }
      }
    },
    /**
     * Selected tag span -> per-residue tag-start/tag-end bracket markers (P0).
     * Mirrors FLASHApp's updateTagPosition. The tag span is delivered via the
     * optional `tag_span` interactivity sentinel and carries protein-absolute
     * indices; subtract sequenceOffset to map onto grid indices.
     */
    updateTagPosition(): void {
      if (this.sequenceObjects.length !== this.sequence.length) {
        this.initializeSequenceObjects()
      }
      const tag = this.selectedTag
      const offset = this.sequenceOffset
      for (let index = 0; index < this.sequenceObjects.length; index++) {
        this.sequenceObjects[index].tagStart = tag !== undefined && tag.start - offset === index
        this.sequenceObjects[index].tagEnd = tag !== undefined && tag.end - offset === index
      }
    },
    /**
     * Apply auto-zoom for short sequences.
     * If the sequence fits on one line at minimum rowWidth (20),
     * set rowWidth to minimum and fontSize to maximum for maximum zoom.
     * Only applies once per sequence to avoid overriding user preferences.
     */
    applyAutoZoom(): void {
      if (this.autoZoomApplied) return

      const minRowWidth = 20
      const maxFontSize = 16

      // If sequence fits on one line at minimum row width, apply max zoom
      // (minimum AAs per row = maximum zoom level)
      if (this.sequence.length > 0 && this.sequence.length <= minRowWidth) {
        this.rowWidth = minRowWidth
        this.fontSize = maxFontSize
      }

      this.autoZoomApplied = true
    },
    resetFragmentMarkers(): void {
      for (const obj of this.sequenceObjects) {
        obj.aIon = false
        obj.bIon = false
        obj.cIon = false
        obj.xIon = false
        obj.yIon = false
        obj.zIon = false
        obj.extraTypes = []
      }
    },
    /** Total mass shift from interactive variable modifications (P1). */
    totalVariableModMass(): number {
      return Object.values(this.variableModifications).reduce(
        (sum, mass) => sum + (mass || 0),
        0,
      )
    },
    /**
     * Build the Precursor / Proteoform mass header (P1). On the TnT path
     * (computed_mass present) the title is "Proteoform" and rows show theoretical
     * protein mass, observed proteoform mass and Δ Mass. Otherwise the title is
     * "Precursor" and rows show theoretical (+ variable mods), observed precursor
     * and Δ Mass. Empty when there is nothing to show.
     */
    preparePrecursorInfo(): void {
      if (this.sequence.length === 0) {
        this.massData = []
        return
      }

      if (this.computedMass !== undefined) {
        this.massTitle = 'Proteoform'
        let proteoformMass = '-'
        let deltaMass = '-'
        if (this.computedMass > 0) {
          proteoformMass = this.computedMass.toFixed(2)
          deltaMass = Math.abs(this.theoreticalMass - this.computedMass).toFixed(2)
        }
        this.massData = [
          `Theoretical protein mass : ${this.theoreticalMass.toFixed(2)}`,
          `Observed proteoform mass : ${proteoformMass}`,
          `Δ Mass (Da) : ${deltaMass}`,
        ]
        return
      }

      // Precursor path: requires an observed precursor mass to be meaningful.
      const observedMass = this.precursorMass
      if (!observedMass || observedMass === 0) {
        this.massData = []
        return
      }
      const theoreticalMass = this.theoreticalMass + this.totalVariableModMass()
      const deltaMassDa = Math.abs(theoreticalMass - observedMass)
      this.massTitle = 'Precursor'
      this.massData = [
        `Theoretical mass : ${theoreticalMass.toFixed(2)}`,
        `Observed mass : ${observedMass.toFixed(2)}`,
        `Δ Mass (Da) : ${deltaMassDa.toFixed(2)}`,
      ]
    },
    /**
     * Record an interactive variable / custom modification on a residue or
     * terminal (P1). Index -1 = N-terminal, sequence.length = C-terminal.
     */
    onUpdateModification(index: number, mass: number): void {
      this.variableModifications = { ...this.variableModifications, [index]: mass }
    },
    getFragmentMasses(ionType: string): number[][] {
      if (!this.sequenceData) return []
      const key = `fragment_masses_${ionType}` as keyof SequenceData
      return (this.sequenceData[key] as number[][]) ?? []
    },
    /** Check if mass difference is within tolerance */
    isWithinTolerance(massDiffDa: number, theoreticalValue: number): boolean {
      if (this.toleranceIsPpm) {
        const massDiffPpm = Math.abs((massDiffDa / theoreticalValue) * 1e6)
        return massDiffPpm <= this.fragmentMassTolerance
      } else {
        return Math.abs(massDiffDa) <= this.fragmentMassTolerance
      }
    },
    /**
     * Mark amino acid position with matched ion (P0). Fragments are matched over
     * the DETERMINED region [sequenceStart..sequenceEnd]; prefix ion i (1-based
     * ionNumber) lands at grid index sequenceStart + (ionNumber-1), suffix ion j
     * at sequenceEnd - (ionNumber-1). With no truncation (start=0, end=last) this
     * reduces to the legacy bare placement (ionNumber-1 / length-ionNumber).
     */
    markAminoAcidPosition(ionType: string, ionNumber: number, typeName: string): void {
      const isPrefixIon = ['a', 'b', 'c'].includes(ionType)
      const aaIndex = isPrefixIon
        ? this.sequenceStart + (ionNumber - 1)
        : this.sequenceEnd - (ionNumber - 1)

      if (aaIndex >= 0 && aaIndex < this.sequenceObjects.length) {
        const aaObj = this.sequenceObjects[aaIndex]
        const ionKey = `${ionType}Ion` as keyof SequenceObject
        ;(aaObj[ionKey] as boolean) = true

        if (typeName) {
          aaObj.extraTypes.push(`${ionType}${typeName}`)
        }
      }
    },
    /** Use external annotations from search engine */
    matchFragmentsExternal(): FragmentTableRow[] {
      const matchingFragments: FragmentTableRow[] = []

      for (const ann of this.externalAnnotations) {
        // Find closest observed peak and track its index for PeakId lookup
        let bestObserved: number | null = null
        let bestObservedIndex = -1
        let bestDiff = Infinity

        for (let obsIdx = 0; obsIdx < this.observedMasses.length; obsIdx++) {
          const observedValue = this.observedMasses[obsIdx]
          const diff = Math.abs(observedValue - ann.mz)
          if (diff < bestDiff) {
            bestDiff = diff
            bestObserved = observedValue
            bestObservedIndex = obsIdx
          }
        }

        if (bestObserved === null) continue

        const massDiffDa = bestObserved - ann.mz
        const massDiffPpm = (massDiffDa / ann.mz) * 1e6

        // Check if within tolerance
        if (!this.isWithinTolerance(massDiffDa, ann.mz)) continue

        // Parse ion number from annotation (e.g., "b5" -> 5)
        let ionNumber = 0
        const numMatch = ann.annotation.match(/[a-z](\d+)/i)
        if (numMatch) {
          ionNumber = parseInt(numMatch[1], 10)
        }

        const fragmentRow: FragmentTableRow = {
          Name: ann.annotation,
          IonType: ann.ion_type,
          IonNumber: ionNumber,
          TheoreticalMass: ann.mz.toFixed(3),
          ObservedMass: bestObserved,
          MassDiffDa: massDiffDa.toFixed(3),
          MassDiffPpm: massDiffPpm.toFixed(3),
        }

        if (ann.charge > 1) {
          fragmentRow.Charge = ann.charge
        }

        // Add PeakId for interactivity linking
        if (this.peakIds && bestObservedIndex >= 0 && this.peakIds[bestObservedIndex] !== undefined) {
          fragmentRow.PeakId = this.peakIds[bestObservedIndex]
        }

        matchingFragments.push(fragmentRow)

        // Mark amino acid position
        if (ionNumber > 0 && ann.ion_type !== 'unknown') {
          this.markAminoAcidPosition(ann.ion_type, ionNumber, '')
        }
      }

      return matchingFragments
    },
    /** Match fragments using theoretical masses */
    matchFragmentsTheoretical(): FragmentTableRow[] {
      const matchingFragments: FragmentTableRow[] = []
      // Fragments are computed (in Python) over the DETERMINED region
      // [sequenceStart..sequenceEnd]; theoIndex 0 corresponds to grid index
      // sequenceStart (prefix) / sequenceEnd (suffix). (P0)
      const sequenceStart = this.sequenceStart
      const sequenceEnd = this.sequenceEnd

      // Get active extra fragment types
      const extraFragments = Object.entries(extraFragmentTypeObject)
        .filter(
          ([type]) => this.ionTypesExtra[type as ExtraFragmentType] || type === 'default'
        )
        .map(([_, fragments]) => fragments)
        .flat()

      // Determine charge states to check
      const chargeStates = this.deconvolved ? [1] : Array.from({ length: this.maxCharge }, (_, i) => i + 1)

      const variableModsActive = Object.values(this.variableModifications).some(
        (m) => m !== undefined && m !== 0,
      )

      // Process each selected ion type
      for (const ionType of this.ionTypes.filter((t) => t.selected)) {
        const isPrefix = ['a', 'b', 'c'].includes(ionType.text)
        // On the TnT path, don't match prefix (a/b/c) ions when the N-terminus is
        // undetermined, nor suffix (x/y/z) ions when the C-terminus is
        // undetermined (parity with FLASHApp ~804-807).
        if (isPrefix && !this.nDetermined) {
          continue
        }
        if (!isPrefix && !this.cDetermined) {
          continue
        }
        const theoreticalFrags = this.getFragmentMasses(ionType.text)

        for (let theoIndex = 0; theoIndex < theoreticalFrags.length; theoIndex++) {
          // Per-position variable-modification mass shift (P1). Variable mods
          // are keyed by PROTEIN-ABSOLUTE grid index. For prefix ions
          // (b{theoIndex+1} covers determined residues at grid indices
          // sequenceStart..sequenceStart+theoIndex) add mods at grid index
          // <= sequenceStart+theoIndex; for suffix ions (covers grid indices
          // sequenceEnd-theoIndex..sequenceEnd) add mods at grid index
          // >= sequenceEnd-theoIndex.
          let varMassShift = 0
          if (variableModsActive) {
            for (const [varIndexStr, varMass] of Object.entries(this.variableModifications)) {
              if (!varMass) continue
              const varIndex = parseInt(varIndexStr, 10)
              if (isPrefix) {
                if (varIndex <= sequenceStart + theoIndex) {
                  varMassShift += varMass
                }
              } else if (varIndex >= sequenceEnd - theoIndex) {
                varMassShift += varMass
              }
            }
          }

          for (const baseTheoreticalMass of theoreticalFrags[theoIndex]) {
            const theoreticalMass = baseTheoreticalMass + varMassShift
            // Try each extra fragment type
            for (const { typeName, typeMass } of extraFragments) {
              const adjustedNeutralMass = theoreticalMass + typeMass

              // Try each charge state
              for (const charge of chargeStates) {
                // Calculate theoretical m/z (or use neutral mass for deconvolved)
                const theoreticalValue = this.deconvolved
                  ? adjustedNeutralMass
                  : (adjustedNeutralMass + charge * PROTON_MASS) / charge

                // Match against observed masses/m/z values (track index for PeakId lookup)
                for (let obsIdx = 0; obsIdx < this.observedMasses.length; obsIdx++) {
                  const observedValue = this.observedMasses[obsIdx]
                  const massDiffDa = observedValue - theoreticalValue

                  if (this.isWithinTolerance(massDiffDa, theoreticalValue)) {
                    const massDiffPpm = (massDiffDa / theoreticalValue) * 1e6

                    // Found a match - report all matches (multiple charge states)
                    // Include neutral loss/addition in name (e.g., "y5-H2O²⁺")
                    const baseIonName = `${ionType.text}${theoIndex + 1}${typeName}`
                    const ionName = this.deconvolved
                      ? baseIonName
                      : `${baseIonName}${toSuperscript(charge)}⁺`

                    const fragmentRow: FragmentTableRow = {
                      Name: ionName,
                      IonType: `${ionType.text}${typeName}`,
                      IonNumber: theoIndex + 1,
                      TheoreticalMass: theoreticalValue.toFixed(3),
                      ObservedMass: observedValue,
                      MassDiffDa: massDiffDa.toFixed(3),
                      MassDiffPpm: massDiffPpm.toFixed(3),
                    }

                    // Add charge for non-deconvolved data
                    if (!this.deconvolved) {
                      fragmentRow.Charge = charge
                    }

                    // Add PeakId for interactivity linking
                    if (this.peakIds && this.peakIds[obsIdx] !== undefined) {
                      fragmentRow.PeakId = this.peakIds[obsIdx]
                    }

                    matchingFragments.push(fragmentRow)

                    // Mark the amino acid position
                    this.markAminoAcidPosition(ionType.text, theoIndex + 1, typeName)
                  }
                }
              }
            }
          }
        }
      }

      return matchingFragments
    },
    matchFragments(): void {
      if (this.sequence.length === 0 || this.observedMasses.length === 0) {
        this.fragmentTableData = []
        // Clear annotations when no data
        this.streamlitDataStore.setAnnotations(null)
        return
      }

      // Use external annotations if available and enabled
      if (this.useExternalAnnotations && this.hasExternalAnnotations) {
        this.fragmentTableData = this.matchFragmentsExternal()
      } else {
        this.fragmentTableData = this.matchFragmentsTheoretical()
      }

      // Convert fragment table data to annotations for cross-component sharing
      // This enables LinePlot to display fragment annotations
      const peakIds: number[] = []
      const highlightColors: string[] = []
      const annotations: string[] = []

      for (const row of this.fragmentTableData) {
        if (row.PeakId !== undefined) {
          peakIds.push(row.PeakId)
          // Color based on ion type (a/b/c = red-ish, x/y/z = blue-ish)
          const ionType = row.IonType.charAt(0).toLowerCase()
          const color = ['a', 'b', 'c'].includes(ionType) ? '#E4572E' : '#1f77b4'
          highlightColors.push(color)
          annotations.push(row.Name)
        }
      }

      // Update store with annotations (triggers rerun in Python via state change)
      // Also increment selection counter to ensure state is sent reliably
      const prevAnnotations = this.streamlitDataStore.annotations
      const prevPeakIds = prevAnnotations?.peak_id ?? []
      const annotationsChanged = peakIds.length !== prevPeakIds.length ||
        peakIds.some((id, i) => id !== prevPeakIds[i])

      if (peakIds.length > 0) {
        this.streamlitDataStore.setAnnotations({
          peak_id: peakIds,
          highlight_color: highlightColors,
          annotation: annotations,
        })
      } else {
        this.streamlitDataStore.setAnnotations(null)
      }

      // Force counter increment when annotations change to ensure state is sent
      if (annotationsChanged) {
        this.selectionStore.$patch({ counter: (this.selectionStore.$state.counter || 0) + 1 })
      }
    },
    isFixedModification(aminoAcid: string): boolean {
      return this.fixedModificationSites.includes(aminoAcid)
    },
    /**
     * Residue -> Tag-Table cross-link (EXTEND). Toggle the residue-position
     * selection for the clicked covered residue, mirroring FLASHApp's
     * AminoAcidCell.selectCell + selectionStore.selectedAApos:
     *   - clicking a new residue sets the selection to its PROTEIN-ABSOLUTE
     *     0-based position (grid index + sequenceOffset),
     *   - clicking the already-selected residue clears it (toggle off).
     * No-op when no interactivity identifier maps to "residue_position".
     */
    onResidueSelected(aaIndex: number): void {
      const identifier = this.residuePositionIdentifier
      if (identifier === undefined) {
        return
      }
      if (this.selectedResidueIndex === aaIndex) {
        // Toggle off: clear both the highlight and the published selection.
        this.selectedResidueIndex = undefined
        this.selectionStore.updateSelection(identifier, undefined)
      } else {
        this.selectedResidueIndex = aaIndex
        // Publish the PROTEIN-ABSOLUTE position so it matches tag StartPos/EndPos.
        this.selectionStore.updateSelection(identifier, aaIndex + this.sequenceOffset)
      }
    },
    /**
     * Clear the residue-position selection when the Tags toggle is turned off
     * (P2, parity with FLASHApp). Clears both the highlight and the published
     * selection. No-op when nothing is selected. Idempotent across the many
     * cells that emit this on the same toggle.
     */
    onResidueSelectionCleared(): void {
      if (this.selectedResidueIndex === undefined) {
        return
      }
      this.selectedResidueIndex = undefined
      const identifier = this.residuePositionIdentifier
      if (identifier !== undefined) {
        this.selectionStore.updateSelection(identifier, undefined)
      }
    },
    onAminoAcidSelected(aaIndex: number): void {
      this.selectedAAIndex = aaIndex

      // Find corresponding fragment in table
      const aaObj = this.sequenceObjects[aaIndex]
      let ionName = ''

      // Ion numbers are relative to the DETERMINED region: prefix ion # is
      // (gridIndex - sequenceStart + 1), suffix ion # is (sequenceEnd - gridIndex + 1).
      // With no truncation this matches the legacy bare placement. (P0)
      if (aaObj.bIon) ionName = `b${aaIndex - this.sequenceStart + 1}`
      else if (aaObj.aIon) ionName = `a${aaIndex - this.sequenceStart + 1}`
      else if (aaObj.cIon) ionName = `c${aaIndex - this.sequenceStart + 1}`
      else if (aaObj.yIon) ionName = `y${this.sequenceEnd - aaIndex + 1}`
      else if (aaObj.xIon) ionName = `x${this.sequenceEnd - aaIndex + 1}`
      else if (aaObj.zIon) ionName = `z${this.sequenceEnd - aaIndex + 1}`

      if (ionName) {
        const rowIndex = this.fragmentTableData.findIndex((row) => row.Name === ionName)
        if (rowIndex >= 0) {
          this.selectedFragmentRowIndex = rowIndex
        }
      }
    },
    onFragmentTableRowClick(_event: Event, { item }: { item: FragmentTableRow }): void {
      // Find the amino acid index from the fragment
      const ionType = item.IonType.charAt(0)
      const ionNumber = item.IonNumber
      const isPrefixIon = ['a', 'b', 'c'].includes(ionType)

      // Map ion number back to its grid index over the DETERMINED region (P0).
      const aaIndex = isPrefixIon
        ? this.sequenceStart + (ionNumber - 1)
        : this.sequenceEnd - (ionNumber - 1)
      if (aaIndex >= 0 && aaIndex < this.sequenceObjects.length) {
        this.selectedAAIndex = aaIndex
      }

      // Handle interactivity: update selection for each mapped identifier.
      // Skip the sentinel columns (residue_position, tag_span, sequence_out) which
      // are driven by other interactions, not the fragment-table peak click.
      if (item.PeakId !== undefined && Object.keys(this.interactivity).length > 0) {
        for (const [identifier, columnName] of Object.entries(this.interactivity)) {
          if (columnName === 'residue_position' || columnName === 'tag_span' || columnName === 'sequence_out') {
            continue
          }
          this.selectionStore.updateSelection(identifier, item.PeakId)
        }
      }
    },
    getRowProps({ index }: { index: number }) {
      return {
        class: index === this.selectedFragmentRowIndex ? 'bg-amber-lighten-4' : '',
      }
    },
    async copySequence(): Promise<void> {
      try {
        if (this.sequence.length === 0) {
          return
        }
        // Copy only the displayed/determined span (P2, parity with FLASHApp ~1138).
        const sequenceStr = this.sequence.slice(this.sequenceStart, this.sequenceEnd + 1).join('')
        await navigator.clipboard.writeText(sequenceStr)
        this.copySnackbarText = 'Sequence copied to clipboard!'
        this.copySnackbar = true
      } catch (error) {
        this.copySnackbarText = 'Failed to copy sequence'
        this.copySnackbar = true
        console.error('Copy failed:', error)
      }
    },
    // ---- Regex highlight (P1) ----
    toggleRegexHighlight(): void {
      this.showRegexHighlight = !this.showRegexHighlight
      if (!this.showRegexHighlight) {
        this.regexPattern = ''
        this.regexError = ''
        this.regexHighlightedIndices = new Set<number>()
      }
    },
    onRegexInput(): void {
      this.regexError = ''
      const indices = new Set<number>()
      if (!this.regexPattern) {
        this.regexHighlightedIndices = indices
        return
      }
      try {
        const regex = new RegExp(this.regexPattern, 'gi')
        const sequenceString = this.sequence.join('')
        let match: RegExpExecArray | null
        while ((match = regex.exec(sequenceString)) !== null) {
          for (let i = match.index; i < match.index + match[0].length; i++) {
            indices.add(i)
          }
          if (match[0].length === 0) {
            break
          }
        }
        this.regexHighlightedIndices = indices
      } catch (error) {
        this.regexError = 'Invalid regex pattern'
        this.regexHighlightedIndices = new Set<number>()
        console.warn('Regex error:', error)
      }
    },
    // ---- Custom-sequence change dialog (P1) ----
    openSequenceDialog(): void {
      this.customSequenceInput = ''
      this.sequenceInputError = ''
      this.sequenceDialog = true
    },
    closeSequenceDialog(): void {
      this.sequenceDialog = false
      this.customSequenceInput = ''
      this.sequenceInputError = ''
    },
    /**
     * Emit a user-entered sequence via the optional `sequence_out` interactivity
     * sentinel so the Deconv viewer can rebuild on it (parity with FLASHApp
     * updateSequenceOut). No-op when no identifier maps to `sequence_out`.
     */
    submitCustomSequence(): void {
      const sequence = this.customSequenceInput.toUpperCase()
      for (const [identifier, columnName] of Object.entries(this.interactivity)) {
        if (columnName === 'sequence_out') {
          this.selectionStore.updateSelection(identifier, sequence)
        }
      }
      this.sequenceDialog = false
      this.customSequenceInput = ''
      this.sequenceInputError = ''
    },
  },
})
</script>

<style scoped>
.sequence-view-container {
  width: 100%;
}

.sequence-grid {
  display: grid;
  grid-template-rows: auto;
  gap: 4px;
}

.grid-width-20 {
  grid-template-columns: repeat(22, 1fr);
}

.grid-width-25 {
  grid-template-columns: repeat(27, 1fr);
}

.grid-width-30 {
  grid-template-columns: repeat(32, 1fr);
}

.grid-width-35 {
  grid-template-columns: repeat(37, 1fr);
}

.grid-width-40 {
  grid-template-columns: repeat(42, 1fr);
}

.row-number {
  font-size: 10px;
  opacity: 0.6;
}

/* Coverage scale legend layout (EXTEND), mirrors FLASHApp SequenceView. */
.sequence-and-scale {
  display: flex;
  align-items: center;
}

.sequence-grid-area {
  flex-grow: 1;
}

.scale-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  margin-left: 8px;
}

.scale {
  width: 60px;
  height: 100px;
  background: linear-gradient(
    to top,
    rgba(228, 87, 46, 0.1),
    rgba(228, 87, 46, 0.2) 10%,
    rgba(228, 87, 46, 0.4) 20%,
    rgba(228, 87, 46, 0.6) 40%,
    rgba(228, 87, 46, 0.8) 70%,
    rgba(228, 87, 46, 1) 100%
  );
}

.scale-text {
  text-align: center;
  font-size: 14pt;
  font-weight: bold;
}

.terminal-cell {
  font-weight: bold;
  font-size: 12px;
  background-color: rgba(128, 128, 128, 0.2);
  border-radius: 4px;
  aspect-ratio: 1;
}
</style>
