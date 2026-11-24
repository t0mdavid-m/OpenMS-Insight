<template>
  <form class="goto-form" @submit.prevent="submit">
    <div v-for="axis in axes" :key="axis.name" class="goto-row">
      <span class="goto-label" :title="axis.label">{{ axis.label }}</span>
      <input
        v-model="inputs[axis.name].low"
        class="goto-input"
        type="text"
        inputmode="decimal"
        :aria-label="`${axis.label} from`"
        @input="error = ''"
      />
      <span class="goto-to">to</span>
      <input
        v-model="inputs[axis.name].high"
        class="goto-input"
        type="text"
        inputmode="decimal"
        :aria-label="`${axis.label} to`"
        @input="error = ''"
      />
    </div>
    <div class="goto-footer">
      <span v-if="error" class="goto-error" role="alert">{{ error }}</span>
      <span v-else class="goto-hint">Empty fields keep that axis</span>
      <button type="submit" class="goto-apply">Go</button>
    </div>
  </form>
</template>

<script lang="ts">
/**
 * The Go to tool's form: two fields per axis, filled with the range in view,
 * and Go (or Enter) to show the typed ranges (utils/goToRange.ts).
 */
import { defineComponent, type PropType } from 'vue'
import { formatBound, goToRelayout, type GoToAxis, type GoToInput } from '@/utils/goToRange'

function inputsFor(axes: GoToAxis[]): Record<string, GoToInput> {
  const inputs: Record<string, GoToInput> = {}
  for (const axis of axes) {
    const low = Math.min(axis.low, axis.high)
    const high = Math.max(axis.low, axis.high)
    inputs[axis.name] = { low: formatBound(low, low, high), high: formatBound(high, low, high) }
  }
  return inputs
}

export default defineComponent({
  name: 'GoToForm',
  props: {
    axes: { type: Array as PropType<GoToAxis[]>, required: true },
    apply: { type: Function as PropType<(update: Record<string, number>) => void>, required: true },
  },
  data() {
    return { inputs: inputsFor(this.axes), error: '' }
  },
  watch: {
    /** The view changed while the form is open (a zoom): start from it again. */
    axes(next: GoToAxis[]) {
      this.inputs = inputsFor(next)
      this.error = ''
    },
  },
  mounted() {
    const first = this.$el.querySelector('input') as HTMLInputElement | null
    first?.focus()
    first?.select()
  },
  methods: {
    submit(): void {
      const result = goToRelayout(this.axes, this.inputs)
      if ('error' in result) {
        this.error = result.error
        return
      }
      this.apply(result.update)
    },
  },
})
</script>

<style scoped>
.goto-form {
  display: flex;
  flex-direction: column;
  gap: 5px;
  padding: 4px 9px 7px;
}
.goto-row {
  display: flex;
  align-items: center;
  gap: 6px;
}
.goto-label {
  width: 96px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.goto-to {
  color: var(--tb-muted);
}
.goto-input {
  width: 78px;
  height: 24px;
  padding: 0 6px;
  border: 1px solid var(--tb-border);
  border-radius: 6px;
  background: var(--tb-background);
  color: var(--tb-text);
  font: inherit;
  font-variant-numeric: tabular-nums;
}
.goto-input:focus-visible {
  outline: 2px solid var(--tb-accent);
  outline-offset: 0;
}
.goto-footer {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 2px;
}
.goto-hint,
.goto-error {
  flex: 1;
  font-size: 11px;
  color: var(--tb-muted);
  white-space: normal;
}
.goto-error {
  color: #d62728;
}
.goto-apply {
  height: 24px;
  padding: 0 14px;
  border: none;
  border-radius: 999px;
  background: var(--tb-accent);
  color: #ffffff;
  font: inherit;
  font-weight: 600;
  cursor: pointer;
}
</style>
