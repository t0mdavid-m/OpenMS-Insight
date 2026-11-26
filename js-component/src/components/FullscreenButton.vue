<template>
  <v-btn
    v-if="available"
    variant="text"
    icon
    size="small"
    :title="fullscreen ? 'Exit full screen (Esc)' : 'Full screen'"
    :aria-pressed="fullscreen"
    @click="toggle"
  >
    <v-icon>{{ fullscreen ? 'mdi-fullscreen-exit' : 'mdi-fullscreen' }}</v-icon>
  </v-btn>
</template>

<script lang="ts">
import { defineComponent } from 'vue'
import { fullscreen, fullscreenAvailable, toggleFullscreen } from '@/utils/fullscreen'

/** The full screen switch for views without the plot toolbar. */
export default defineComponent({
  name: 'FullscreenButton',
  setup() {
    return { fullscreen, available: fullscreenAvailable(), toggle: toggleFullscreen }
  },
})
</script>
