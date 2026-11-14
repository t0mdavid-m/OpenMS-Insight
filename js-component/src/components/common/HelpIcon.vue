<template>
  <span class="insight-help" :class="{ floating }" tabindex="0" aria-label="About this view">
    <v-icon icon="mdi-information-outline" size="16" />
    <v-tooltip activator="parent" location="bottom start" max-width="360" open-on-focus>
      <span class="insight-help-text">{{ text }}</span>
    </v-tooltip>
  </span>
</template>

<script lang="ts">
import { defineComponent } from 'vue'

/**
 * An info icon whose tooltip explains the view (the component's `help`
 * argument). Floating: in the view's top left corner, over the plot's margin.
 */
export default defineComponent({
  name: 'HelpIcon',
  props: {
    text: { type: String, required: true },
    floating: { type: Boolean, default: false },
  },
})
</script>

<style scoped>
.insight-help {
  display: inline-flex;
  align-items: center;
  cursor: help;
  opacity: 0.6;
  color: var(--insight-text, currentColor);
}
.insight-help:hover,
.insight-help:focus {
  opacity: 1;
  outline: none;
}
.insight-help.floating {
  position: absolute;
  top: 10px;
  left: 6px;
  z-index: 5;
}
.insight-help-text {
  white-space: pre-line;
}
</style>
