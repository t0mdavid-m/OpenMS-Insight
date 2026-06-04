<template>
  <div class="sequence-view-container" :style="containerStyle">
    <v-sheet class="pa-4 rounded-lg" :theme="theme?.base ?? 'light'" border>
      <!-- Header with mass information -->
      <div class="d-flex justify-center mb-2">
        <h4>Sequence View</h4>
      </div>

      <!-- Mass-info header (oracle preparePrecursorInfo; 3-seqview-004). Gated on
           an observed mass supplied by Python (observed_mass_column); hidden
           otherwise so existing callers are byte-unchanged. -->
      <div v-if="showMassHeader" class="d-flex justify-space-evenly align-center mb-2 mass-info-header">
        <h3>{{ massHeaderTitle }}</h3>
        <v-divider :vertical="true"></v-divider>
        <template v-for="(field, fieldIndex) in massHeaderFields" :key="fieldIndex">
          <span>{{ field }}</span>
          <v-divider :vertical="true"></v-divider>
        </template>
      </div>

      <!-- Toolbar -->
      <div class="d-flex justify-end px-4 mb-4">
        <v-btn variant="text" icon size="small" :disabled="sequence.length === 0" @click="copySequence">
          <v-icon>mdi-content-copy</v-icon>
          <v-tooltip activator="parent" location="bottom">Copy sequence to clipboard</v-tooltip>
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
                <v-list-item-title>Show Fragments</v-list-item-title>
                <v-checkbox v-model="showFragments" hide-details density="comfortable"></v-checkbox>
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

      <!-- Sequence grid (+ optional per-residue coverage scale legend) -->
      <div class="sequence-and-scale">
      <div class="px-2 pb-4 sequence-grid-part" :class="gridClasses" style="width: 100%; max-width: 100%">
        <template v-for="(aaObj, aaIndex) in sequenceObjects" :key="aaIndex">
          <!-- Row number (left) -->
          <div
            v-if="aaIndex !== 0 && aaIndex % rowWidth === 0"
            class="d-flex justify-center align-center row-number"
          >
            {{ aaIndex + 1 }}
          </div>

          <!-- N-terminal marker -->
          <ProteinTerminalCell
            v-if="aaIndex === 0"
            protein-terminal="N-term"
            :index="-1"
            :truncated="nTruncation"
            :determined="nDetermined"
            :font-size="fontSize"
          />

          <!-- Amino acid cell -->
          <AminoAcidCell
            :sequence-object="aaObj"
            :index="aaIndex"
            :sequence-length="sequence.length"
            :fixed-modification="isFixedModification(aaObj.aminoAcid)"
            :show-fragments="showFragments"
            :show-tags="coverageShown"
            :font-size="fontSize"
            :is-highlighted="selectedAAIndex === aaIndex"
            :modification="modifications[aaIndex] ?? null"
            @selected="onAminoAcidSelected"
            @tag-selected="onResidueTagSelected"
            @clear-tag-selection="onClearResidueSelection"
          />

          <!-- Row number (right) -->
          <div
            v-if="aaIndex % rowWidth === rowWidth - 1 && aaIndex !== sequence.length - 1"
            class="d-flex justify-center align-center row-number"
          >
            {{ aaIndex + 1 }}
          </div>

          <!-- C-terminal marker -->
          <ProteinTerminalCell
            v-if="aaIndex === sequence.length - 1"
            protein-terminal="C-term"
            :index="sequence.length"
            :truncated="cTruncation"
            :determined="cDetermined"
            :font-size="fontSize"
          />
        </template>
      </div>
      <!-- Per-residue coverage scale legend (oracle parity). Gated on a real
           coverage range (maxCoverage > 0); hidden when no coverage supplied. -->
      <div v-if="maxCoverage > 0" class="scale-container" title="Sequence Coverage">
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

      <!-- Internal fragment map (display-only, gated by Python args) -->
      <InternalFragmentMap
        v-if="internalFragments && internalData"
        class="mt-4"
        :sequence="sequence"
        :internal-data="internalData"
        :observed-masses="observedMasses"
        :tolerance="sequenceData?.internal_fragment_tolerance ?? 10"
        :tolerance-is-ppm="sequenceData?.internal_fragment_tolerance_ppm ?? true"
      />
    </v-sheet>

    <!-- Copy snackbar -->
    <v-snackbar v-model="copySnackbar" :timeout="2000" location="bottom">
      {{ copySnackbarText }}
    </v-snackbar>
  </div>
</template>

<script lang="ts">
import { defineComponent } from 'vue'
import { useStreamlitDataStore } from '@/stores/streamlit-data'
import { useSelectionStore } from '@/stores/selection'
import type { Theme } from 'streamlit-component-lib'
import type {
  SequenceData,
  SequenceObject,
  FragmentTableRow,
  ExternalAnnotation,
  InternalFragmentData,
} from '@/types/sequence-data'
import AminoAcidCell from './AminoAcidCell.vue'
import InternalFragmentMap from './InternalFragmentMap.vue'
import ProteinTerminalCell from './ProteinTerminalCell.vue'
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
    InternalFragmentMap,
    ProteinTerminalCell,
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
      showFragments: true,
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
      selectedFragmentRowIndex: undefined as number | undefined,
      copySnackbar: false,
      copySnackbarText: '',
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
    /** Per-peak interactivity column values, keyed by peak id ({col: value}). */
    peakInteractivity(): Record<string, Record<string, unknown>> {
      const v = this.streamlitDataStore.allDataForDrawing.peakInteractivity
      return (v as Record<string, Record<string, unknown>>) ?? {}
    },
    precursorMass(): number {
      return (this.streamlitDataStore.allDataForDrawing.precursorMass as number) ?? 0
    },
    /** Interactivity mapping from component args */
    interactivity(): Record<string, string> {
      return (this.args.interactivity as Record<string, string>) ?? {}
    },
    /** Identifier emitted when a residue is clicked (0-based residue index). */
    residueIdentifier(): string | undefined {
      return this.args.residueIdentifier as string | undefined
    },
    /**
     * Identifier the matched fragment's mass selection is published to on a
     * residue click (PATH 2). Maps the oracle `updateMassTableFromFragmentMass`
     * -> `updateSelectedMass(massIndex)`: when set, clicking a residue with a
     * matching fragment publishes that fragment peak's mass-selection value
     * (resolved via the `interactivity` column of the same name when present,
     * else the peak id). Undefined -> PATH 2 off (back-compatible).
     */
    fragmentMassIdentifier(): string | undefined {
      return this.args.fragmentMassIdentifier as string | undefined
    },
    /**
     * Whether the per-residue coverage / sequence-tag layer is active (real
     * coverage range supplied). This is Insight's analog of the oracle
     * `showTags`: PATH 1 (coverage-gated aa toggle) is only live when coverage is
     * shown. When OFF, the residue click keeps its legacy fragment-gated
     * `residueIdentifier` publication (back-compat for callers without coverage).
     */
    coverageShown(): boolean {
      return this.maxCoverage > 0
    },
    /** Whether data is deconvolved (neutral masses) or not (m/z values) */
    deconvolved(): boolean {
      return (this.args.deconvolved as boolean) ?? true
    },
    /** Whether to render the internal-fragment map below the terminal map. */
    internalFragments(): boolean {
      return this.args.internalFragments === true
    },
    /**
     * Internal-fragment payload assembled from the sequenceData arrays.
     * Returns undefined unless Python attached the internal arrays.
     */
    internalData(): InternalFragmentData | undefined {
      const data = this.sequenceData
      if (!data?.internal_fragments) return undefined
      return {
        fragment_masses_by: data.fragment_masses_by ?? [],
        start_indices_by: data.start_indices_by ?? [],
        end_indices_by: data.end_indices_by ?? [],
        fragment_masses_bz: data.fragment_masses_bz ?? [],
        start_indices_bz: data.start_indices_bz ?? [],
        end_indices_bz: data.end_indices_bz ?? [],
        fragment_masses_cy: data.fragment_masses_cy ?? [],
        start_indices_cy: data.start_indices_cy ?? [],
        end_indices_cy: data.end_indices_cy ?? [],
      }
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
    /**
     * Per-residue coverage (normalised to [0,1]), one entry per residue.
     * Empty when no coverage was supplied by Python.
     */
    coverage(): number[] {
      return this.sequenceData?.coverage ?? []
    },
    /**
     * Raw maximum coverage count (for the scale legend label, e.g. "5x").
     * -1 when no coverage was supplied -> the scale legend is hidden.
     */
    maxCoverage(): number {
      return this.sequenceData?.maxCoverage ?? -1
    },
    /**
     * Reported proteoform start (0-based). A negative value marks an
     * UNDETERMINED N-terminus (oracle convention). Undefined -> 0 (full,
     * determined N-terminus; back-compatible).
     */
    proteoformStartReported(): number {
      return this.sequenceData?.proteoform_start ?? 0
    },
    /** Clamped proteoform start (negative -> 0). */
    proteoformStart(): number {
      return this.proteoformStartReported < 0 ? 0 : this.proteoformStartReported
    },
    /**
     * Reported proteoform end (0-based). A negative value marks an UNDETERMINED
     * C-terminus. Undefined -> last residue (full, determined C-terminus).
     */
    proteoformEndReported(): number {
      return this.sequenceData?.proteoform_end ?? this.sequence.length - 1
    },
    /** Clamped proteoform end (negative -> last residue). */
    proteoformEnd(): number {
      return this.proteoformEndReported < 0
        ? this.sequence.length - 1
        : this.proteoformEndReported
    },
    /** N-terminus is truncated when the proteoform starts after residue 0. */
    nTruncation(): boolean {
      return this.proteoformStart > 0
    },
    /** N-terminus is determined unless the reported start is negative. */
    nDetermined(): boolean {
      return this.proteoformStartReported >= 0
    },
    /** C-terminus is truncated when the proteoform ends before the last residue. */
    cTruncation(): boolean {
      return this.proteoformEnd < this.sequence.length - 1
    },
    /** C-terminus is determined unless the reported end is negative. */
    cDetermined(): boolean {
      return this.proteoformEndReported >= 0
    },
    theoreticalMass(): number {
      return this.sequenceData?.theoretical_mass ?? 0
    },
    /**
     * Per-row OBSERVED mass for the mass-info header. Undefined when Python did
     * not attach `observed_mass` (no `observed_mass_column` configured) -> the
     * header is hidden (back-compatible).
     */
    observedMass(): number | undefined {
      return this.sequenceData?.observed_mass
    },
    /** Title shown to the left of the mass-info header (oracle massTitle). */
    massHeaderTitle(): string {
      return this.sequenceData?.mass_header_title ?? 'Proteoform'
    },
    /**
     * Whether the mass-info header is shown (3-seqview-004). Gated on Python
     * having supplied an observed mass; off otherwise so existing callers render
     * byte-unchanged.
     */
    showMassHeader(): boolean {
      return this.observedMass !== undefined
    },
    /**
     * The three mass-info header fields, mirroring the oracle
     * `preparePrecursorInfo` proteoform branch: Theoretical mass / Observed mass /
     * Δ Mass (Da). A non-positive observed mass renders observed + delta as "-"
     * (oracle parity for `computedMass <= 0`).
     */
    massHeaderFields(): string[] {
      if (this.observedMass === undefined) return []
      const theo = this.theoreticalMass
      let observedStr = '-'
      let deltaStr = '-'
      if (this.observedMass > 0) {
        observedStr = this.observedMass.toFixed(2)
        deltaStr = Math.abs(theo - this.observedMass).toFixed(2)
      }
      return [
        `Theoretical mass : ${theo.toFixed(2)}`,
        `Observed mass : ${observedStr}`,
        `Δ Mass (Da) : ${deltaStr}`,
      ]
    },
    /**
     * Identifier the component LISTENS to for the inbound mass -> fragment-row
     * highlight (3-seqview-003). Undefined -> inbound highlight off
     * (back-compatible).
     */
    massSelectionIdentifier(): string | undefined {
      return this.args.massSelectionIdentifier as string | undefined
    },
    /**
     * The currently-selected inbound mass value (from the selection store at the
     * configured identifier), or undefined when no inbound identifier is set /
     * nothing is selected. Drives `updateFragmentTableFromMassSelection`.
     */
    selectedInboundMass(): unknown {
      if (!this.massSelectionIdentifier) return undefined
      return this.selectionStore.$state[this.massSelectionIdentifier]
    },
    fixedModificationSites(): string[] {
      return this.sequenceData?.fixed_modifications ?? []
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
      return (explainedCleavage / (this.sequence.length - 1)) * 100
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
          // Oracle SequenceView.vue sequence watch (~632): clear the residue
          // (aa-position) selection when the sequence changes. Scoped to PATH-1
          // callers (residueIdentifier configured) so non-coverage callers are
          // unaffected.
          if (this.residueIdentifier) {
            this.selectedAAIndex = undefined
            this.selectionStore.updateSelection(this.residueIdentifier, null)
          }
        }

        this.initializeSequenceObjects()

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
    /**
     * INBOUND mass selection (3-seqview-003): when the externally-published mass
     * selection changes, re-highlight the matching fragment-table row. Gated on a
     * configured `massSelectionIdentifier` (the computed returns undefined and the
     * watcher no-ops otherwise -> back-compatible).
     */
    selectedInboundMass(newValue: unknown) {
      this.updateFragmentTableFromMassSelection(newValue)
    },
    /**
     * Re-apply the inbound highlight after the fragment table is rebuilt (a new
     * sequence/scan shifts row indices). No-op when the inbound identifier is
     * unset. The outbound paths set `selectedFragmentRowIndex` directly, so only
     * re-derive from the inbound selection when one is configured.
     */
    fragmentTableData() {
      if (this.massSelectionIdentifier) {
        this.updateFragmentTableFromMassSelection(this.selectedInboundMass)
      }
    },
  },
  methods: {
    initializeSequenceObjects(): void {
      this.sequenceObjects = []
      const coverage = this.coverage
      this.sequence.forEach((aa, index) => {
        this.sequenceObjects.push({
          aminoAcid: aa,
          // Per-residue coverage (already normalised to [0,1] in Python). Left
          // undefined when no coverage was supplied -> no gradient.
          coverage: coverage[index],
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
    /** Mark amino acid position with matched ion */
    markAminoAcidPosition(ionType: string, ionNumber: number, typeName: string): void {
      const sequenceLength = this.sequence.length
      const isPrefixIon = ['a', 'b', 'c'].includes(ionType)
      const aaIndex = isPrefixIon ? ionNumber - 1 : sequenceLength - ionNumber

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
      const sequenceLength = this.sequence.length

      // Get active extra fragment types
      const extraFragments = Object.entries(extraFragmentTypeObject)
        .filter(
          ([type]) => this.ionTypesExtra[type as ExtraFragmentType] || type === 'default'
        )
        .map(([_, fragments]) => fragments)
        .flat()

      // Determine charge states to check
      const chargeStates = this.deconvolved ? [1] : Array.from({ length: this.maxCharge }, (_, i) => i + 1)

      // Process each selected ion type
      for (const ionType of this.ionTypes.filter((t) => t.selected)) {
        const theoreticalFrags = this.getFragmentMasses(ionType.text)

        for (let theoIndex = 0; theoIndex < theoreticalFrags.length; theoIndex++) {
          for (const theoreticalMass of theoreticalFrags[theoIndex]) {
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
     * PATH 2 (mass / fragment selection): a residue with a matching FRAGMENT ion
     * was clicked. Reproduces the oracle `aminoAcidSelected` ->
     * `updateMassTableFromFragmentMass` -> `updateSelectedMass`: find the matched
     * fragment table row, highlight it, and publish that fragment peak's
     * mass-selection value to `fragmentMassIdentifier`.
     *
     * Back-compat: when coverage (PATH 1) is NOT shown, this also keeps the legacy
     * fragment-gated `residueIdentifier` publication so existing callers (no
     * coverage configured) behave exactly as before. When coverage IS shown the
     * aa-position publication is owned by PATH 1 (`onResidueTagSelected`).
     */
    onAminoAcidSelected(aaIndex: number): void {
      // Legacy highlight-on-fragment-click only when coverage (PATH 1) is OFF.
      // When coverage is shown the gold highlight follows the PATH-1 toggle
      // (oracle: aminoAcidSelected does NOT touch selectedAApos), so a
      // fragment-only residue click does not move the highlight.
      if (!this.coverageShown) {
        this.selectedAAIndex = aaIndex
      }

      // Find corresponding fragment in table
      const aaObj = this.sequenceObjects[aaIndex]
      let ionName = ''

      if (aaObj.bIon) ionName = `b${aaIndex + 1}`
      else if (aaObj.aIon) ionName = `a${aaIndex + 1}`
      else if (aaObj.cIon) ionName = `c${aaIndex + 1}`
      else if (aaObj.yIon) ionName = `y${this.sequence.length - aaIndex}`
      else if (aaObj.xIon) ionName = `x${this.sequence.length - aaIndex}`
      else if (aaObj.zIon) ionName = `z${this.sequence.length - aaIndex}`

      if (ionName) {
        const rowIndex = this.fragmentTableData.findIndex((row) => row.Name === ionName)
        if (rowIndex >= 0) {
          this.selectedFragmentRowIndex = rowIndex
          // PATH 2: publish ONLY the mass selection (oracle
          // updateMassTableFromFragmentMass -> updateSelectedMass updates just the
          // mass), gated on fragmentMassIdentifier (default-OFF).
          if (this.fragmentMassIdentifier) {
            this.publishFragmentMassSelection(this.fragmentTableData[rowIndex], [
              this.fragmentMassIdentifier,
            ])
          }
        }
      }

      // Legacy PATH 1 (back-compat only): emit the residue position (0-based) as a
      // cross-component selection. Only when coverage is NOT shown — otherwise the
      // coverage-gated toggle path (onResidueTagSelected) owns this identifier.
      if (this.residueIdentifier && !this.coverageShown) {
        this.selectionStore.updateSelection(this.residueIdentifier, aaIndex)
      }
    },
    /**
     * PATH 1 (aa / sequence-tag selection): a residue with sequence-tag coverage
     * was clicked while tags are shown. Reproduces the oracle TOGGLE on
     * `selectedAApos` (re-clicking the currently-selected residue clears it) and
     * publishes the residue index to `residueIdentifier`.
     */
    onResidueTagSelected(aaIndex: number): void {
      if (!this.residueIdentifier) return
      if (this.selectedAAIndex === aaIndex) {
        // Toggle off (oracle updateSelectedAA(undefined) -> store unset sentinel).
        // The gold highlight follows selectedAAIndex (oracle selectedAApos).
        this.selectedAAIndex = undefined
        this.selectionStore.updateSelection(this.residueIdentifier, null)
      } else {
        this.selectedAAIndex = aaIndex
        this.selectionStore.updateSelection(this.residueIdentifier, aaIndex)
      }
    },
    /**
     * showTags-off auto-clear (oracle AminoAcidCell watch + SequenceView sequence
     * watch): clear the residue (aa-position) selection. Wired only when PATH 1 is
     * configured (a residueIdentifier exists).
     */
    onClearResidueSelection(): void {
      if (!this.residueIdentifier) return
      this.selectedAAIndex = undefined
      this.selectionStore.updateSelection(this.residueIdentifier, null)
    },
    /**
     * Publish the interactivity selection(s) for a matched fragment row's peak —
     * shared by PATH 2 (residue click) and the fragment-table row click. Emits the
     * MAPPED column's value for the peak when available (e.g. a per-scan mass
     * ordinal = the oracle massIndex), falling back to the global peak id.
     *
     * @param item the matched fragment row (carrying PeakId).
     * @param identifiers restrict to these identifiers (PATH 2 publishes only
     *   `fragmentMassIdentifier`); omitted -> all configured interactivity.
     */
    publishFragmentMassSelection(
      item: FragmentTableRow,
      identifiers?: string[],
    ): void {
      if (item.PeakId === undefined) return
      const values = this.peakInteractivity[item.PeakId as unknown as string]
      // Resolve one identifier's value: the mapped interactivity column's value
      // for this peak when present, else the global peak id.
      const resolve = (identifier: string): unknown => {
        const columnName = this.interactivity[identifier]
        if (columnName && values && columnName in values) {
          return values[columnName]
        }
        return item.PeakId
      }
      // Restricted set (PATH 2): publish exactly the requested identifiers (even
      // those without an interactivity column -> peak-id fallback, so PATH 2 always
      // publishes). Unrestricted (fragment-row click): publish every configured
      // interactivity identifier.
      const ids = identifiers ?? Object.keys(this.interactivity)
      for (const identifier of ids) {
        this.selectionStore.updateSelection(identifier, resolve(identifier))
      }
    },
    onFragmentTableRowClick(_event: Event, { item }: { item: FragmentTableRow }): void {
      // Find the amino acid index from the fragment
      const ionType = item.IonType.charAt(0)
      const ionNumber = item.IonNumber
      const isPrefixIon = ['a', 'b', 'c'].includes(ionType)

      const aaIndex = isPrefixIon ? ionNumber - 1 : this.sequence.length - ionNumber
      if (aaIndex >= 0 && aaIndex < this.sequenceObjects.length) {
        this.selectedAAIndex = aaIndex
      }

      // Handle interactivity: update selection for each mapped identifier
      // (publishes the per-peak mapped value, falling back to the peak id).
      this.publishFragmentMassSelection(item)
    },
    getRowProps({ index }: { index: number }) {
      return {
        class: index === this.selectedFragmentRowIndex ? 'bg-amber-lighten-4' : '',
      }
    },
    /**
     * INBOUND mass -> fragment-row highlight (3-seqview-003). Reproduces the
     * oracle `updateFragmentTableFromMassSelection`: when the shared mass
     * selection changes EXTERNALLY (e.g. a mass-table / spectrum click elsewhere
     * publishes to `massSelectionIdentifier`), highlight the fragment-table row
     * whose matched peak corresponds to that selection. Local visual only — it
     * does NOT re-publish any selection (so no cross-component feedback loop).
     *
     * The published selection value is the interactivity-mapped value of a peak
     * (e.g. a per-scan mass ordinal), the SAME value `publishFragmentMassSelection`
     * emits outbound. We therefore resolve it back through the same mapping: the
     * matching fragment row is the one whose `PeakId`'s interactivity value (or the
     * raw peak id when no column is mapped) equals the selection. Default-OFF: a
     * null/undefined selection or no configured identifier clears the highlight
     * iff it was set by this path.
     */
    updateFragmentTableFromMassSelection(selectionValue: unknown): void {
      if (!this.massSelectionIdentifier) return
      if (selectionValue === undefined || selectionValue === null) {
        this.selectedFragmentRowIndex = undefined
        return
      }
      // Column the inbound identifier maps to (e.g. "mass_in_scan"); when absent
      // the selection value is the raw peak id (matches the outbound fallback).
      const columnName = this.interactivity[this.massSelectionIdentifier]
      const rowIndex = this.fragmentTableData.findIndex((row) => {
        if (row.PeakId === undefined) return false
        let peakValue: unknown = row.PeakId
        if (columnName) {
          const values = this.peakInteractivity[row.PeakId as unknown as string]
          if (values && columnName in values) {
            peakValue = values[columnName]
          }
        }
        // Loose compare so numeric ids that arrive as strings still match.
        // eslint-disable-next-line eqeqeq
        return peakValue == selectionValue
      })
      this.selectedFragmentRowIndex = rowIndex >= 0 ? rowIndex : undefined
    },
    async copySequence(): Promise<void> {
      try {
        const sequenceStr = this.sequence.join('')
        await navigator.clipboard.writeText(sequenceStr)
        this.copySnackbarText = 'Sequence copied to clipboard!'
        this.copySnackbar = true
      } catch (error) {
        this.copySnackbarText = 'Failed to copy sequence'
        this.copySnackbar = true
        console.error('Copy failed:', error)
      }
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

/* Coverage scale legend layout (oracle parity). The sequence grid grows to fill
   the row; the scale legend sits to its right. When no coverage is supplied the
   scale-container is not rendered (v-if), so this collapses to the grid alone. */
.sequence-and-scale {
  display: flex;
  align-items: center;
}

.sequence-grid-part {
  flex-grow: 1;
}

.scale-container {
  display: flex;
  flex-direction: column;
  align-items: center;
}

/* Vertical gradient legend: faint (1x) at the bottom -> full coverage at top,
   using the same E4572E (228,87,46) base color as the per-residue gradient. */
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
</style>
