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

export default defineComponent({
  name: 'App',
  components: {
    TabulatorTable,
    PlotlyLineplot,
  },
  setup() {
    const streamlitDataStore = useStreamlitDataStore()
    const selectionStore = useSelectionStore()

    // Watch selection store and send changes back to Python
    watch(
      () => ({ ...selectionStore.$state }),
      (newState) => {
        Streamlit.setComponentValue(newState)
      },
      { deep: true, immediate: true }
    )

    return { streamlitDataStore, selectionStore }
  },
  data() {
    return {
      timer: undefined as NodeJS.Timer | undefined,
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
        default:
          console.warn(`Unknown component type: ${componentType}`)
          return null
      }
    },
  },
  created() {
    Streamlit.setComponentReady()
    Streamlit.setFrameHeight(400)
    Streamlit.events.addEventListener(Streamlit.RENDER_EVENT, this.updateStreamlitData)
  },
  mounted() {
    // Periodically update frame height
    this.timer = setInterval(() => {
      Streamlit.setFrameHeight()
    }, 500)
  },
  unmounted() {
    Streamlit.events.removeEventListener(Streamlit.RENDER_EVENT, this.updateStreamlitData)
    clearInterval(this.timer)
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
