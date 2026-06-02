<template>
  <div class="internal-fragment-map-container" :style="containerStyle">
    <div class="d-flex justify-center">
      <h4>{{ title }}</h4>
    </div>

    <div class="d-flex justify-space-between">
      <!-- Legend -->
      <div class="d-flex justify-start align-center px-4 mb-4">
        <div class="legend-swatch mr-2" :style="{ background: ionColors.by, border: '1px solid white' }"></div>
        <div class="mr-4">by/cz</div>
        <div class="legend-swatch mr-2" :style="{ background: ionColors.bz, border: '1px solid white' }"></div>
        <div class="mr-4">bz</div>
        <div class="legend-swatch mr-2" :style="{ background: ionColors.cy, border: '1px solid white' }"></div>
        <div class="mr-4">cy</div>
      </div>

      <!-- Settings -->
      <div class="d-flex justify-end px-4 mb-4" style="max-width: 97%">
        <v-btn id="internal-frag-settings-button" variant="text" icon="mdi-cog" size="medium"></v-btn>
        <v-menu
          :close-on-content-click="false"
          activator="#internal-frag-settings-button"
          location="bottom"
        >
          <v-card min-width="300">
            <v-list>
              <v-list-item>
                <v-list-item-title>Fragments display style</v-list-item-title>
                <div class="d-flex">
                  <v-switch
                    v-model="fragmentDisplayOverlay"
                    hide-details
                    :label="fragmentDisplayOverlayLabel"
                    class="mr-4"
                  />
                </div>
              </v-list-item>
              <v-list-item>
                <v-list-item-title>Opacity of each fragment (overlay style)</v-list-item-title>
                <div :style="{ background: `rgba(240, 164, 65, ${fragOpacity})` }">
                  <v-slider
                    v-model="fragOpacity"
                    class="align-center ml-4"
                    :max="fragOpacityMax"
                    :min="fragOpacityMin"
                    step="0.01"
                    hide-details
                  >
                    <template #append>
                      <v-text-field
                        v-model.number="fragOpacity"
                        hide-details
                        single-line
                        :min="fragOpacityMin"
                        :max="fragOpacityMax"
                        step="0.01"
                        density="compact"
                        type="number"
                        class="textFieldFontSize"
                      ></v-text-field>
                    </template>
                  </v-slider>
                </div>
              </v-list-item>
              <v-list-item>
                <v-list-item-title>Fragment mass tolerance</v-list-item-title>
                <div class="d-flex justify-space-between">
                  <v-switch
                    v-model="fragmentMassToleranceUnit"
                    true-value="ppm"
                    false-value="Da"
                    hide-details
                    :label="fragmentMassToleranceUnit"
                    class="mr-4"
                  />
                  <v-text-field
                    v-model.number="fragmentMassTolerance"
                    type="number"
                    hide-details="auto"
                    label="mass tolerance"
                  ></v-text-field>
                </div>
              </v-list-item>
            </v-list>
          </v-card>
        </v-menu>
      </div>
    </div>

    <v-sheet class="pa-4 rounded-lg" style="max-width: 97%" :theme="theme?.base ?? 'light'" border>
      <div v-if="sequence.length === 0" class="d-flex justify-center py-8 text-medium-emphasis">
        No internal fragments to display.
      </div>
      <div v-else id="internal-fragment-part">
        <!-- Sequence row -->
        <div class="d-flex sequence-row">
          <div
            v-for="(aa, aaIndex) in sequence"
            :key="`seq-${aa}-${aaIndex}`"
            class="d-flex justify-center align-center fragment-segment sequence-text"
            :style="fragmentStyle"
          >
            {{ aa }}
          </div>
        </div>

        <!-- One block per ion type (DOM order: by, cy, bz — matched to original) -->
        <div
          v-for="block in ionBlocks"
          :key="block.type"
          :style="fragmentTypeContainerStyle"
        >
          <div
            v-for="(frag, fragIndex) in block.fragments"
            :key="`${block.type}-${fragIndex}-${frag.mass}`"
            class="d-flex"
            :style="fragmentTypeOverlayStyle"
          >
            <div
              v-for="(aa, aaIndex) in sequence"
              :key="`${block.type}-${fragIndex}-${aaIndex}`"
              :class="fragmentClasses(aaIndex, frag.start, frag.end, block.type)"
              :style="cellStyle(aaIndex, frag, block)"
              :title="inFragment(aaIndex, frag) ? fragmentTooltip(block.type, frag) : undefined"
            ></div>
          </div>
        </div>
      </div>
    </v-sheet>
  </div>
</template>

<script lang="ts">
import { defineComponent } from 'vue'
import { useStreamlitDataStore } from '@/stores/streamlit-data'
import type { Theme } from 'streamlit-component-lib'

type CombinedFragmentData = { mass: number; start: number; end: number }
type IonType = 'by' | 'cy' | 'bz'
type IonBlock = { type: IonType; fragments: CombinedFragmentData[] }

interface InternalFragmentData {
  sequence: string[]
  fragment_masses_by?: number[]
  start_indices_by?: number[]
  end_indices_by?: number[]
  fragment_masses_bz?: number[]
  start_indices_bz?: number[]
  end_indices_bz?: number[]
  fragment_masses_cy?: number[]
  start_indices_cy?: number[]
  end_indices_cy?: number[]
}

export default defineComponent({
  name: 'InternalFragmentMap',
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
    return { streamlitDataStore }
  },
  data() {
    return {
      fragmentMassTolerance: 10 as number,
      fragmentMassToleranceUnit: 'ppm' as 'ppm' | 'Da',
      fragmentDisplayOverlay: false,
      fragOpacity: 0.2,
      fragOpacityMin: 0.01,
      fragOpacityMax: 1,
      settingsInitialized: false,
    }
  },
  computed: {
    containerStyle(): Record<string, string> {
      return {
        height: `${this.args.height || 400}px`,
        overflowY: 'auto',
      }
    },
    theme(): Theme | undefined {
      return this.streamlitDataStore.theme
    },
    title(): string {
      return (this.args.title as string) ?? 'Internal Fragment Map'
    },
    ionColors(): Record<IonType, string> {
      const fromArgs = (this.args.ionColors as Record<string, string>) ?? {}
      return {
        by: fromArgs.by ?? '#f0a441',
        cy: fromArgs.cy ?? '#12871d',
        bz: fromArgs.bz ?? '#7831cc',
      }
    },
    internalFragmentData(): InternalFragmentData | undefined {
      return this.streamlitDataStore.allDataForDrawing.internalFragmentData as
        | InternalFragmentData
        | undefined
    },
    observedMasses(): number[] {
      return (this.streamlitDataStore.allDataForDrawing.observedMasses as number[]) ?? []
    },
    sequence(): string[] {
      return this.internalFragmentData?.sequence ?? []
    },
    fragmentStyle(): Record<string, string | number> {
      return {
        height: (94 / (this.sequence.length || 1)).toFixed(2) + 'vw',
        '--frag-block-opacity-value': this.fragOpacity,
      }
    },
    fragmentTypeContainerStyle(): Record<string, string> {
      return {
        height: this.fragmentDisplayOverlay ? (this.fragmentStyle.height as string) : 'auto',
      }
    },
    fragmentTypeOverlayStyle(): Record<string, string> {
      return {
        position: this.fragmentDisplayOverlay ? 'absolute' : 'static',
      }
    },
    fragmentDisplayOverlayLabel(): string {
      return this.fragmentDisplayOverlay ? 'Overlay fragments from the same type' : 'Stacked'
    },
    byData(): CombinedFragmentData[] {
      return this.buildFragments('by')
    },
    cyData(): CombinedFragmentData[] {
      return this.buildFragments('cy')
    },
    bzData(): CombinedFragmentData[] {
      return this.buildFragments('bz')
    },
    // DOM order matched to original .vue: by, then cy, then bz.
    ionBlocks(): IonBlock[] {
      return [
        { type: 'by', fragments: this.byData },
        { type: 'cy', fragments: this.cyData },
        { type: 'bz', fragments: this.bzData },
      ]
    },
  },
  watch: {
    internalFragmentData: {
      handler() {
        if (!this.settingsInitialized) {
          const tol = this.args.tolerance as number | undefined
          const unit = this.args.toleranceUnit as 'ppm' | 'Da' | undefined
          if (tol !== undefined) this.fragmentMassTolerance = tol
          if (unit !== undefined) this.fragmentMassToleranceUnit = unit
          this.settingsInitialized = true
        }
      },
      immediate: true,
    },
  },
  methods: {
    /**
     * Build the list of fragments to render for an ion type.
     * If observed masses are provided, keep only fragments matching an observed mass
     * within tolerance (mirrors the original filterMatchingMasses). Otherwise render
     * all theoretical fragments.
     */
    buildFragments(ionType: IonType): CombinedFragmentData[] {
      const data = this.internalFragmentData
      if (!data) return []
      const masses = data[`fragment_masses_${ionType}` as keyof InternalFragmentData] as
        | number[]
        | undefined
      const starts = data[`start_indices_${ionType}` as keyof InternalFragmentData] as
        | number[]
        | undefined
      const ends = data[`end_indices_${ionType}` as keyof InternalFragmentData] as
        | number[]
        | undefined
      if (!masses || !starts || !ends) return []

      // No observed spectrum bound -> render all theoretical fragments.
      if (this.observedMasses.length === 0) {
        const result: CombinedFragmentData[] = []
        for (let i = 0; i < masses.length; i++) {
          result.push({ mass: masses[i], start: starts[i], end: ends[i] })
        }
        return result
      }

      // Observed masses present -> keep only matching fragments (ppm/Da tolerance).
      const result: CombinedFragmentData[] = []
      for (let i = 0; i < masses.length; i++) {
        const theoretical = masses[i]
        for (let o = 0; o < this.observedMasses.length; o++) {
          const diffDa = this.observedMasses[o] - theoretical
          const within =
            this.fragmentMassToleranceUnit === 'ppm'
              ? Math.abs((diffDa / theoretical) * 1e6) <= this.fragmentMassTolerance
              : Math.abs(diffDa) <= this.fragmentMassTolerance
          if (within) {
            result.push({ mass: theoretical, start: starts[i], end: ends[i] })
            break
          }
        }
      }
      return result
    },
    inFragment(sequenceIndex: number, frag: CombinedFragmentData): boolean {
      // Half-open coloring (start, end] — faithful to original fragmentClasses.
      return sequenceIndex > frag.start && sequenceIndex <= frag.end
    },
    fragmentClasses(
      sequenceIndex: number,
      startIndex: number,
      endIndex: number,
      ionType: IonType
    ): Record<string, boolean> {
      const inFrag = sequenceIndex > startIndex && sequenceIndex <= endIndex
      return {
        'fragment-cell': inFrag,
        'not-in-fragment': !inFrag,
        [`${ionType}-fragment`]: inFrag,
      }
    },
    cellStyle(
      sequenceIndex: number,
      frag: CombinedFragmentData,
      block: IonBlock
    ): Record<string, string> {
      const style: Record<string, string> = {
        ...(this.fragmentStyle as Record<string, string>),
        border: '1px solid white',
      }
      if (this.inFragment(sequenceIndex, frag)) {
        style.background = this.ionColors[block.type]
        if (this.fragmentDisplayOverlay) {
          style.opacity = String(this.fragOpacity)
        }
      } else {
        style.background = 'transparent'
      }
      return style
    },
    fragmentTooltip(ionType: IonType, frag: CombinedFragmentData): string {
      return `${ionType}  start: ${frag.start}  end: ${frag.end}  mass: ${frag.mass.toFixed(4)}`
    },
  },
})
</script>

<style scoped lang="css">
.internal-fragment-map-container {
  width: 100%;
}

.sequence-row {
  border-bottom: 1px solid white;
}

.sequence-text {
  font-size: 8px;
}

.fragment-segment {
  aspect-ratio: 1;
}

.fragment-cell {
  aspect-ratio: 1;
}

.not-in-fragment {
  aspect-ratio: 1;
  background: transparent;
}

.legend-swatch {
  width: 10px;
  height: 10px;
}

.textFieldFontSize {
  width: 100px;
}
</style>
