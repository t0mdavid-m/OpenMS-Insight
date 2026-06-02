<template>
  <div class="d-flex justify-center">
    <h4>Internal Fragment Map</h4>
  </div>
  <div class="d-flex justify-space-between">
    <div class="d-flex justify-start align-center px-4 mb-4">
      <div class="by-fragment-legend mr-2" style="border: 1px solid white"></div>
      <div class="mr-4">by/cz</div>
      <div class="bz-fragment-legend mr-2" style="border: 1px solid white"></div>
      <div class="mr-4">bz</div>
      <div class="cy-fragment-legend mr-2" style="border: 1px solid white"></div>
      <div class="mr-4">cy</div>
    </div>
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
                  :label="`${fragmentDisplayOverlayLabels}`"
                  class="mr-4"
                />
              </div>
            </v-list-item>
            <v-list-item>
              <v-list-item-title
                >Opacity of each fragment (If overlay display style)</v-list-item-title
              >
              <div :style="{ background: `rgba(240, 164, 65, ${fragOpacity})` }">
                <v-slider
                  v-model="fragOpacity"
                  class="align-center ml-4"
                  :max="fragOpacityMax"
                  :min="fragOpacityMin"
                  hide-details
                >
                  <template #append>
                    <v-text-field
                      v-model="fragOpacity"
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
                  :label="`${fragmentMassToleranceUnit}`"
                  class="mr-4"
                />
                <v-text-field
                  v-model="fragmentMassTolerance"
                  type="number"
                  hide-details="auto"
                  label="mass tolerance"
                  @change="updateMassTolerance"
                ></v-text-field>
              </div>
            </v-list-item>
          </v-list>
        </v-card>
      </v-menu>
    </div>
  </div>
  <v-sheet class="pa-4 rounded-lg" style="max-width: 97%" :theme="theme?.base ?? 'light'" border>
    <div id="internal-fragment-part">
      <div
        class="d-flex"
        style="border-bottom: white; border-bottom-width: 1px; border-bottom-style: solid"
      >
        <div
          v-for="(aa, aaIndex) in sequence"
          :key="`${aa}-${aaIndex}`"
          class="d-flex justify-center align-center fragment-segment sequence-text"
          :style="fragmentStyle"
        >
          {{ aa }}
        </div>
      </div>
      <div :style="fragmentTypeContainerStyle">
        <div
          v-for="(fragmentData, fragIndex) in byData"
          :key="`by-${fragIndex}-${fragmentData.mass}`"
          class="d-flex"
          :style="fragmentTypeOverlayStyle"
        >
          <div
            v-for="(aa, aaIndex) in sequence"
            :key="`${aa}-${aaIndex}`"
            :class="fragmentClasses(aaIndex, fragmentData.start, fragmentData.end, 'by-fragment')"
            style="border: 1px solid white"
            :style="fragmentStyle"
          ></div>
        </div>
      </div>
      <div :style="fragmentTypeContainerStyle">
        <div
          v-for="(fragmentData, fragIndex) in cyData"
          :key="`cy-${fragIndex}-${fragmentData.mass}`"
          class="d-flex"
          :style="fragmentTypeOverlayStyle"
        >
          <div
            v-for="(aa, aaIndex) in sequence"
            :key="`${aa}-${aaIndex}`"
            :class="fragmentClasses(aaIndex, fragmentData.start, fragmentData.end, 'cy-fragment')"
            style="border: 1px solid white"
            :style="fragmentStyle"
          ></div>
        </div>
      </div>
      <div :style="fragmentTypeContainerStyle">
        <div
          v-for="(fragmentData, fragIndex) in bzData"
          :key="`bz-${fragIndex}-${fragmentData.mass}`"
          class="d-flex"
          :style="fragmentTypeOverlayStyle"
        >
          <div
            v-for="(aa, aaIndex) in sequence"
            :key="`${aa}-${aaIndex}`"
            :class="fragmentClasses(aaIndex, fragmentData.start, fragmentData.end, 'bz-fragment')"
            style="border: 1px solid white"
            :style="fragmentStyle"
          ></div>
        </div>
      </div>
    </div>
  </v-sheet>
</template>

<script lang="ts">
import { defineComponent, type PropType, type StyleValue } from 'vue'
import { useStreamlitDataStore } from '@/stores/streamlit-data'
import type { Theme } from 'streamlit-component-lib'
import type { InternalFragmentData } from '@/types/sequence-data'

type CombinedFragmentData = { mass: number; start: number; end: number }

export default defineComponent({
  name: 'InternalFragmentMap',
  props: {
    /** Single-letter residue codes for the (sliced) sequence. */
    sequence: {
      type: Array as PropType<string[]>,
      required: true,
    },
    /** Enumerated theoretical internal fragments (Python-computed). */
    internalData: {
      type: Object as PropType<InternalFragmentData>,
      required: true,
    },
    /** Observed (deconvolved neutral) masses for the selected scan. */
    observedMasses: {
      type: Array as PropType<number[]>,
      default: () => [],
    },
    /** Default match tolerance value. */
    tolerance: {
      type: Number,
      default: 10,
    },
    /** Default match tolerance unit (ppm if true). */
    toleranceIsPpm: {
      type: Boolean,
      default: true,
    },
  },
  setup() {
    const streamlitData = useStreamlitDataStore()
    return { streamlitData }
  },
  data() {
    return {
      // Seeded from props; the Da toggle exists for parity but the matcher is
      // ppm-only (mirrors the oracle filterMatchingMasses).
      fragmentMassTolerance: this.tolerance as number,
      fragmentMassToleranceUnit: (this.toleranceIsPpm ? 'ppm' : 'Da') as 'ppm' | 'Da',
      fragmentDisplayOverlay: false,
      fragOpacity: 0.2,
      fragOpacityMin: 0.01,
      fragOpacityMax: 1,
    }
  },
  computed: {
    theme(): Theme | undefined {
      return this.streamlitData.theme
    },
    fragmentStyle(): StyleValue {
      return {
        height: (94 / (this.sequence?.length ?? 1)).toFixed(2) + 'vw',
        '--frag-block-opacity-value': this.fragOpacity,
      } as StyleValue
    },
    fragmentTypeContainerStyle(): StyleValue {
      return {
        height: this.fragmentDisplayOverlay
          ? (94 / (this.sequence?.length ?? 1)).toFixed(2) + 'vw'
          : 'auto',
      }
    },
    fragmentTypeOverlayStyle(): StyleValue {
      return {
        position: this.fragmentDisplayOverlay ? 'absolute' : 'static',
      }
    },
    fragmentDisplayOverlayLabels(): string {
      return this.fragmentDisplayOverlay ? 'Overlay fragments from the same type' : 'Stacked'
    },
    byData(): CombinedFragmentData[] {
      return this.matchFamily('by')
    },
    cyData(): CombinedFragmentData[] {
      return this.matchFamily('cy')
    },
    bzData(): CombinedFragmentData[] {
      return this.matchFamily('bz')
    },
  },
  methods: {
    updateMassTolerance(event: Event) {
      this.fragmentMassTolerance = Number.parseInt((event.target as HTMLInputElement).value)
    },
    matchFamily(family: 'by' | 'cy' | 'bz'): CombinedFragmentData[] {
      // Eligibility gate: no observed masses (e.g. MS1 / no selection) => no bars.
      if (this.observedMasses.length === 0) return []

      const masses = this.internalData[`fragment_masses_${family}`]
      const starts = this.internalData[`start_indices_${family}`]
      const ends = this.internalData[`end_indices_${family}`]
      if (!masses || !starts || !ends) return []

      const combined: CombinedFragmentData[] = []
      this.filterMatchingMasses(this.observedMasses, masses, starts, ends, combined)
      return combined
    },
    fragmentClasses(
      sequenceIndex: number,
      startIndex: number,
      endIndex: number,
      className: string
    ) {
      const inFragment = sequenceIndex > startIndex && sequenceIndex <= endIndex
      let thisClassName = className
      if (this.fragmentDisplayOverlay) thisClassName += '-overlayed'
      return {
        [thisClassName]: inFragment,
        'not-in-fragment': !inFragment,
      }
    },
    filterMatchingMasses(
      observedMassses: number[],
      fragmentMasses: number[],
      startIndices: number[],
      endIndices: number[],
      target: CombinedFragmentData[]
    ) {
      for (let i = 0, frag_size = fragmentMasses.length; i < frag_size; i++) {
        const theoretical_mass = fragmentMasses[i]

        for (let obsIndex = 0, obsSize = observedMassses.length; obsIndex < obsSize; ++obsIndex) {
          const massDiffDa = observedMassses[obsIndex] - theoretical_mass
          const massDiffPpm = (massDiffDa / theoretical_mass) * 1e6
          if (Math.abs(massDiffPpm) > this.fragmentMassTolerance) {
            // if mass difference is larger than tolerance, ignore
            continue
          }
          // if valid push
          target.push({
            mass: theoretical_mass,
            start: startIndices[i],
            end: endIndices[i],
          })
          break
        }
      }
    },
  },
})
</script>

<style scoped lang="css">
.sequence-text {
  font-size: 8px;
}

.fragment-segment {
  aspect-ratio: 1;
}

.by-fragment {
  aspect-ratio: 1;
  background: #f0a441;
}

.by-fragment-overlayed {
  aspect-ratio: 1;
  background: #f0a441;
  opacity: var(--frag-block-opacity-value);
}

.by-fragment-legend {
  aspect-ratio: 1;
  background: #f0a441;
  height: 10px;
}

.cy-fragment {
  aspect-ratio: 1;
  background: #12871d;
}

.cy-fragment-overlayed {
  aspect-ratio: 1;
  background: #12871d;
  opacity: var(--frag-block-opacity-value);
}

.cy-fragment-legend {
  aspect-ratio: 1;
  background: #12871d;
  height: 10px;
}

.bz-fragment {
  aspect-ratio: 1;
  background: #7831cc;
}

.bz-fragment-overlayed {
  aspect-ratio: 1;
  background: #7831cc;
  opacity: var(--frag-block-opacity-value);
}

.bz-fragment-legend {
  aspect-ratio: 1;
  background: #7831cc;
  height: 10px;
}

.not-in-fragment {
  background: transparent;
  aspect-ratio: 1;
}

.v-input.textFieldFontSize {
  width: 100px;
}
</style>
