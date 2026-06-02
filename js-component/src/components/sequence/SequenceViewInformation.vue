<template>
  <v-btn id="info-button" variant="text" size="small" icon>
    <v-icon>mdi-information</v-icon>
    <v-tooltip activator="parent" location="bottom">Sequence View legend</v-tooltip>
  </v-btn>
  <v-dialog v-model="dialog" activator="#info-button" width="auto" :theme="theme?.base ?? 'light'">
    <v-card>
      <v-card-title>Sequence View legend</v-card-title>
      <v-divider></v-divider>
      <v-card-text>
        <div class="text-h6 d-flex justify-center">Legend for Sequence Map</div>
        <div class="d-flex justify-center">
          <div class="sequence-grid pa-6" style="width: 150px; max-width: 100%">
            <AminoAcidCell
              :index="0"
              :sequence-object="aaSequenceObject"
              :sequence-length="2"
              :show-modifications="true"
              @selected.stop
            />
          </div>
        </div>
        Fragment ion types
        <v-row>
          <div class="d-flex flex-wrap">
            <v-checkbox v-model="aIon" label="a" hide-details density="comfortable"></v-checkbox>
            <v-checkbox v-model="bIon" label="b" hide-details density="comfortable"></v-checkbox>
            <v-checkbox v-model="cIon" label="c" hide-details density="comfortable"></v-checkbox>
            <v-checkbox v-model="xIon" label="x" hide-details density="comfortable"></v-checkbox>
            <v-checkbox v-model="yIon" label="y" hide-details density="comfortable"></v-checkbox>
            <v-checkbox v-model="zIon" label="z" hide-details density="comfortable"></v-checkbox>
            <v-checkbox v-model="waterLoss" label="water loss" hide-details density="comfortable"></v-checkbox>
            <v-checkbox v-model="ammoniumLoss" label="ammonium loss" hide-details density="comfortable"></v-checkbox>
            <v-checkbox v-model="proton" label="proton loss/addition" hide-details density="comfortable"></v-checkbox>
          </div>
        </v-row>
        Modifications
        <div class="d-flex flex-wrap align-center">
          <v-checkbox v-model="variableMod" label="Modifications" hide-details density="comfortable"></v-checkbox>
          <div class="text-subtitle-2 d-flex justify-end align-end ml-2">
            * Click checkboxes to see the styles
          </div>
        </div>
        <v-list density="compact">
          <v-list-item-title>Interaction tips</v-list-item-title>
          <v-list-item>Left click: highlights corresponding entries in the Fragment Table</v-list-item>
          <v-list-item>Right click: opens the variable modification menu (custom modification available)</v-list-item>
        </v-list>
      </v-card-text>
      <v-card-actions>
        <v-btn color="primary" :block="true" @click="dialog = false">Close</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script lang="ts">
import { defineComponent } from 'vue'
import { useStreamlitDataStore } from '@/stores/streamlit-data'
import type { Theme } from 'streamlit-component-lib'
import AminoAcidCell from './AminoAcidCell.vue'
import type { SequenceObject } from '@/types/sequence-data'

export default defineComponent({
  name: 'SequenceViewInformation',
  components: { AminoAcidCell },
  setup() {
    const streamlitDataStore = useStreamlitDataStore()
    return { streamlitDataStore }
  },
  data() {
    return {
      dialog: false,
      aIon: true,
      bIon: false,
      cIon: false,
      xIon: true,
      yIon: true,
      zIon: false,
      variableMod: false,
      waterLoss: false,
      ammoniumLoss: false,
      proton: false,
    }
  },
  computed: {
    theme(): Theme | undefined {
      return this.streamlitDataStore.theme
    },
    aaSequenceObject(): SequenceObject {
      return {
        aminoAcid: 'AA',
        truncated: false,
        aIon: this.aIon,
        bIon: this.bIon,
        cIon: this.cIon,
        xIon: this.xIon,
        yIon: this.yIon,
        zIon: this.zIon,
        modStart: this.variableMod,
        modEnd: this.variableMod,
        modMass: '+134.99',
        extraTypes: this.extraFragTypes(),
      }
    },
  },
  methods: {
    extraFragTypes(): string[] {
      let ionType = ''
      if (this.aIon) ionType = 'a'
      else if (this.bIon) ionType = 'b'
      else if (this.cIon) ionType = 'c'
      else if (this.xIon) ionType = 'x'
      else if (this.yIon) ionType = 'y'
      else if (this.zIon) ionType = 'z'
      else return []

      const extraTypes: string[] = []
      if (this.waterLoss) extraTypes.push(`${ionType}-H2O`)
      if (this.ammoniumLoss) extraTypes.push(`${ionType}-NH3`)
      if (this.proton) {
        extraTypes.push(`${ionType}-H`)
        extraTypes.push(`${ionType}+H`)
      }
      return extraTypes
    },
  },
})
</script>

<style scoped>
.sequence-grid {
  display: grid;
  grid-template-rows: auto;
  gap: 4px;
}

.sequence-grid > div {
  aspect-ratio: 1;
}
</style>
