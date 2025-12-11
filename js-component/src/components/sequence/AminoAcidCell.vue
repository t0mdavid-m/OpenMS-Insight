<template>
  <div
    :id="id"
    class="d-flex justify-center align-center rounded-lg amino-acid-cell"
    :class="{ highlighted: isHighlighted, 'fixed-mod': fixedModification }"
    :style="cellStyles"
    @click="selectCell"
  >
    <!-- Fragment ion markers -->
    <div v-if="showFragments && sequenceObject.aIon" class="frag-marker-container frag-a">
      <svg viewBox="0 0 10 10">
        <path stroke="green" d="M7, 1 L9, 3 L9, 7 L9, 3 L7, 1 z" stroke-width="1.5" />
      </svg>
    </div>
    <div v-if="showFragments && sequenceObject.bIon" class="frag-marker-container frag-b">
      <svg viewBox="0 0 10 10">
        <path stroke="blue" d="M10, 0 V5 M10, 0 H5 z" stroke-width="3" />
      </svg>
    </div>
    <div v-if="showFragments && sequenceObject.cIon" class="frag-marker-container frag-c">
      <svg viewBox="0 0 10 10">
        <path stroke="red" d="M4, 1 L9, 3 L9, 7 L9, 3 L4, 1 z" stroke-width="1.5" />
      </svg>
    </div>
    <div v-if="showFragments && sequenceObject.xIon" class="frag-marker-container frag-x">
      <svg viewBox="0 0 10 10">
        <path stroke="green" d="M1, 3 L1, 7 L3, 9 L1, 7 L1, 3 z" stroke-width="1.5" />
      </svg>
    </div>
    <div v-if="showFragments && sequenceObject.yIon" class="frag-marker-container frag-y">
      <svg viewBox="0 0 10 10">
        <path stroke="blue" d="M0, 10 V5 M0, 10 H5 z" stroke-width="3" />
      </svg>
    </div>
    <div v-if="showFragments && sequenceObject.zIon" class="frag-marker-container frag-z">
      <svg viewBox="0 0 10 10">
        <path stroke="red" d="M1, 3 L1, 7 L6, 9 L1, 7 L1, 3 z" stroke-width="1.5" />
      </svg>
    </div>

    <!-- Extra fragment type indicator -->
    <div v-if="hasExtraFragTypes" class="frag-marker-extra">
      <svg viewBox="0 0 10 10">
        <circle cx="5" cy="5" r="0.5" stroke="black" stroke-width="0.3" fill="gold" />
      </svg>
    </div>

    <!-- Amino acid letter -->
    <div class="aa-text">{{ aminoAcid }}</div>

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
    fontSize: {
      type: Number,
      default: 12,
    },
    isHighlighted: {
      type: Boolean,
      default: false,
    },
  },
  emits: ['selected'],
  setup() {
    const streamlitData = useStreamlitDataStore()
    return { streamlitData }
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
    cellStyles(): Record<string, string> {
      return {
        '--aa-cell-color': this.theme?.textColor ?? '#000',
        '--aa-cell-bg-color': this.theme?.secondaryBackgroundColor ?? '#f0f0f0',
        '--aa-cell-hover-bg-color': this.theme?.backgroundColor ?? '#fff',
        '--aa-font-size': `${this.fontSize}px`,
        position: 'relative',
      }
    },
  },
  methods: {
    selectCell(): void {
      if (this.hasMatchingFragments) {
        this.$emit('selected', this.index)
      }
    },
  },
})
</script>

<style scoped>
.amino-acid-cell {
  background-color: var(--aa-cell-bg-color);
  color: var(--aa-cell-color);
  cursor: pointer;
  aspect-ratio: 1;
}

.amino-acid-cell:hover {
  background-color: var(--aa-cell-hover-bg-color);
}

.amino-acid-cell.highlighted {
  background-color: #f3a712;
  color: #000;
  outline: 3px solid #29335c;
  font-weight: bold;
}

.amino-acid-cell.fixed-mod {
  color: #f3a712;
}

.aa-text {
  position: absolute;
  font-size: var(--aa-font-size, 12px);
  font-weight: 500;
}

.frag-marker-container {
  width: 100%;
  height: 100%;
  position: absolute;
  z-index: 10;
}

.frag-a {
  top: -28%;
  left: 15%;
}

.frag-b {
  top: -8%;
  left: 13%;
}

.frag-c {
  top: -28%;
  left: 15%;
}

.frag-x {
  bottom: -32%;
  left: -10%;
}

.frag-y {
  bottom: -8%;
  left: -10%;
}

.frag-z {
  bottom: -32%;
  left: -10%;
}

.frag-marker-extra {
  width: 100%;
  height: 100%;
  position: absolute;
  top: -30%;
  z-index: 10;
}
</style>
