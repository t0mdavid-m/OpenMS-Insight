<template>
  <div class="measure-toolbar" :style="cssCustomProperties">
    <button
      type="button"
      class="measure-button"
      :class="{ active: measure.mode }"
      :aria-pressed="measure.mode"
      :title="title"
      @click="measure.toggle()"
    >
      Measure
    </button>
    <span v-if="measure.hint" class="measure-hint">{{ measure.hint }}</span>
    <button
      v-if="measure.measurements.length > 0"
      type="button"
      class="measure-button"
      title="Remove all measurements"
      @click="measure.clear()"
    >
      Clear
    </button>
    <slot />
  </div>
</template>

<script lang="ts">
/**
 * The "Measure" button above a plot, with a hint while measuring and a
 * "Clear" button once there are measurements. State lives in useMeasure().
 */
import { defineComponent, type PropType } from 'vue'
import { useStreamlitDataStore } from '@/stores/streamlit-data'
import type { MeasureState } from '@/composables/useMeasure'

export default defineComponent({
  name: 'MeasureToolbar',
  props: {
    measure: {
      type: Object as PropType<MeasureState>,
      required: true,
    },
    /** Tooltip of the Measure button. */
    title: {
      type: String,
      default: 'Click two points to measure the distance between them',
    },
  },
  setup() {
    return { streamlitDataStore: useStreamlitDataStore() }
  },
  computed: {
    cssCustomProperties(): Record<string, string> {
      const theme = this.streamlitDataStore.theme
      return {
        '--measure-text': theme?.textColor || '#262730',
        '--measure-background': theme?.backgroundColor || 'white',
        '--measure-accent': theme?.primaryColor || '#ff4b4b',
        '--measure-font': theme?.font || 'sans-serif',
      }
    },
  },
})
</script>

<style scoped>
.measure-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 2px 4px 4px;
  font-family: var(--measure-font);
  font-size: 13px;
  color: var(--measure-text);
}

.measure-button {
  font: inherit;
  color: var(--measure-text);
  background: var(--measure-background);
  border: 1px solid color-mix(in srgb, var(--measure-text) 30%, transparent);
  border-radius: 4px;
  padding: 2px 10px;
  cursor: pointer;
}

.measure-button:hover {
  border-color: var(--measure-accent);
}

.measure-button.active {
  color: var(--measure-accent);
  border-color: var(--measure-accent);
  background: color-mix(in srgb, var(--measure-accent) 10%, var(--measure-background));
}

.measure-hint {
  opacity: 0.75;
}
</style>
