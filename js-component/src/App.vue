<template>
  <div v-if="componentArgs !== undefined">
    <component
      :is="currentComponent"
      :args="componentArgs"
      :index="0"
    />
  </div>
  <div v-else class="d-flex w-100" style="height: 200px">
    <v-alert
      class="h-50 ma-8"
      icon="mdi-application-variable-outline"
      title="Loading..."
      type="info"
      density="compact"
    >
      <v-progress-linear indeterminate></v-progress-linear>
    </v-alert>
  </div>
</template>

<script lang="ts">
import { defineComponent, watch, toRaw, type Component } from 'vue'
import { useStreamlitDataStore } from './stores/streamlit-data'
import { useSelectionStore } from '@/stores/selection'
import { Streamlit, type RenderData } from 'streamlit-component-lib'
import type { ComponentArgs, ComponentLayout } from './types/component'
import TabulatorTable from './components/tabulator/TabulatorTable.vue'
import PlotlyLineplot from './components/plotly/PlotlyLineplot.vue'
import PlotlyHeatmap from './components/plotly/PlotlyHeatmap.vue'

export default defineComponent({
  name: 'App',
  components: {
    TabulatorTable,
    PlotlyLineplot,
    PlotlyHeatmap,
  },
  setup() {
    const streamlitDataStore = useStreamlitDataStore()
    const selectionStore = useSelectionStore()

    // Watch selection store counter and send state back to Python
    // We watch counter (a primitive) instead of deep-watching the entire state.
    // This avoids creating a spread object on every reactivity check.
    // Counter increments on every selection change, so this captures all updates.
    let lastSentCounter: number | undefined = undefined
    let lastSentHash: string | undefined = undefined

    const sendStateToStreamlit = () => {
      const currentCounter = selectionStore.$state.counter
      const currentHash = streamlitDataStore.hash || null

      // Avoid duplicate sends for same counter+hash combination
      if (currentCounter === lastSentCounter && currentHash === lastSentHash) return
      lastSentCounter = currentCounter
      lastSentHash = currentHash ?? undefined

      // Deep clone to remove Vue reactivity proxies before sending to Streamlit
      // This prevents "Proxy object could not be cloned" errors
      const plainState = JSON.parse(JSON.stringify(selectionStore.$state))
      // Echo back Vue's current data hash so Python knows if Vue has the data
      // This enables bidirectional hash confirmation for cache optimization
      plainState._vueDataHash = currentHash
      Streamlit.setComponentValue(plainState)
    }

    // Watch both counter and hash to ensure Python always knows Vue's state
    watch(() => selectionStore.$state.counter, sendStateToStreamlit, { immediate: true })
    watch(() => streamlitDataStore.hash, sendStateToStreamlit)

    // Watch for height changes and update frame height
    watch(
      () => streamlitDataStore.allDataForDrawing?.height,
      (newHeight) => {
        if (newHeight && typeof newHeight === 'number') {
          Streamlit.setFrameHeight(newHeight)
        }
      },
      { immediate: true }
    )

    return { streamlitDataStore, selectionStore }
  },
  data() {
    return {
      resizeObserver: undefined as ResizeObserver | undefined,
    }
  },
  computed: {
    /**
     * Get the component args from the first (and only) component in the layout.
     * Python sends: components: [[{componentArgs: {...}}]]
     */
    componentArgs(): ComponentArgs | undefined {
      const components = this.streamlitDataStore.args?.components
      if (components && components.length > 0 && components[0].length > 0) {
        return components[0][0].componentArgs
      }
      return undefined
    },

    /**
     * Get the Vue component based on componentType.
     */
    currentComponent(): Component | null {
      const componentType = this.componentArgs?.componentType
      switch (componentType) {
        case 'TabulatorTable':
          return TabulatorTable
        case 'PlotlyLineplotUnified':
        case 'PlotlyLineplot':
          return PlotlyLineplot
        case 'PlotlyHeatmap':
          return PlotlyHeatmap
        default:
          console.warn(`Unknown component type: ${componentType}`)
          return null
      }
    },
  },
  created() {
    Streamlit.setComponentReady()
    // Set initial frame height - will be updated when data arrives
    Streamlit.setFrameHeight(400)
    Streamlit.events.addEventListener(Streamlit.RENDER_EVENT, this.updateStreamlitData)
  },
  mounted() {
    // Use ResizeObserver to update frame height only when size actually changes
    // This replaces polling (setInterval every 500ms) with event-driven updates
    this.resizeObserver = new ResizeObserver(() => {
      Streamlit.setFrameHeight()
    })
    this.resizeObserver.observe(this.$el as HTMLElement)
  },
  unmounted() {
    Streamlit.events.removeEventListener(Streamlit.RENDER_EVENT, this.updateStreamlitData)
    if (this.resizeObserver) {
      this.resizeObserver.disconnect()
    }
  },
  updated() {
    Streamlit.setFrameHeight()
  },
  methods: {
    async updateStreamlitData(event: Event): Promise<void> {
      this.streamlitDataStore.updateRenderData((event as CustomEvent<RenderData>).detail)
    },
  },
})
</script>

<style>
body {
  margin: 0;
  font-family: 'Source Sans Pro', sans-serif;
}

.tabulator-tooltip {
  background: #fff;
  color: #000;
}
</style>
