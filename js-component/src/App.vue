<template>
  <div
    v-if="componentArgs !== undefined"
    class="insight-root"
    :class="{ 'view-fullscreen': fullscreen }"
    :style="fullscreenStyle"
  >
    <HelpIcon
      v-if="componentArgs.help && !helpInCard && helpState.claimed === 0"
      :text="componentArgs.help"
      floating
    />
    <component
      :is="currentComponent"
      :args="shownArgs"
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
import { defineAsyncComponent, defineComponent, provide, watch, toRaw, type Component } from 'vue'
import { HELP_KEY, createHelpState } from './composables/useHelp'
import { useTheme } from 'vuetify'
import { stateValues, useStreamlitDataStore } from './stores/streamlit-data'
import { useSelectionStore } from '@/stores/selection'
import { Streamlit, type RenderData } from 'streamlit-component-lib'
import type { ComponentArgs, ComponentLayout } from './types/component'
import { applyAppTheme } from './utils/appTheme'
import { fullscreen, resizePlots, screenHeight } from './utils/fullscreen'
import HelpIcon from './components/common/HelpIcon.vue'

// Height of the view with its data, measured; sent along with the next state
let reportedFrameHeight = 0
// Each view is its own chunk, so a page with several views does not load and
// run Plotly in every table's frame
const TabulatorTable = defineAsyncComponent(() => import('./components/tabulator/TabulatorTable.vue'))
const PlotlyLineplot = defineAsyncComponent(() => import('./components/plotly/PlotlyLineplot.vue'))
const PlotlyHeatmap = defineAsyncComponent(() => import('./components/plotly/PlotlyHeatmap.vue'))
const PlotlyClusteredHeatmap = defineAsyncComponent(() => import('./components/plotly/PlotlyClusteredHeatmap.vue'))
const PlotlyMirrorPlot = defineAsyncComponent(() => import('./components/plotly/PlotlyMirrorPlot.vue'))
const PlotlyVolcano = defineAsyncComponent(() => import('./components/plotly/PlotlyVolcano.vue'))
const PlotlyPca = defineAsyncComponent(() => import('./components/plotly/PlotlyPca.vue'))
const PlotlySeries = defineAsyncComponent(() => import('./components/plotly/PlotlySeries.vue'))
const Plotly3D = defineAsyncComponent(() => import('./components/plotly/Plotly3D.vue'))
const PlotlyDeconvolvedSpectrum = defineAsyncComponent(() => import('./components/plotly/PlotlyDeconvolvedSpectrum.vue'))
const SequenceView = defineAsyncComponent(() => import('./components/sequence/SequenceView.vue'))
const ProteinSequenceView = defineAsyncComponent(() => import('./components/protein/ProteinSequenceView.vue'))
const ProteinStructureView = defineAsyncComponent(() => import('./components/protein/ProteinStructureView.vue'))
const SequenceCoverage = defineAsyncComponent(() => import('./components/sequence-coverage/SequenceCoverage.vue'))

export default defineComponent({
  name: 'App',
  components: {
    HelpIcon,
    TabulatorTable,
    PlotlyLineplot,
    PlotlyHeatmap,
    PlotlyClusteredHeatmap,
    PlotlyMirrorPlot,
    PlotlyVolcano,
    PlotlyPca,
    PlotlySeries,
    Plotly3D,
    PlotlyDeconvolvedSpectrum,
    SequenceView,
    ProteinSequenceView,
    ProteinStructureView,
    SequenceCoverage,
  },
  setup() {
    const streamlitDataStore = useStreamlitDataStore()
    const selectionStore = useSelectionStore()

    // A toolbar or table title that draws the help icon in its own row claims
    // it; the icon floats in the corner only while no view has claimed it
    const helpState = createHelpState()
    provide(HELP_KEY, helpState)
    watch(
      () => {
        const c = streamlitDataStore.args?.components
        const a = c && c.length > 0 && c[0].length > 0 ? c[0][0].componentArgs : undefined
        const inCard = ['SequenceView', 'ProteinSequenceView', 'SequenceCoverage'].includes(String(a?.componentType))
        return a?.help && !inCard ? String(a.help) : ''
      },
      (text) => { helpState.text = text },
      { immediate: true },
    )

    // Checkboxes, switches and buttons take the app's primary colour
    const vuetifyTheme = useTheme()
    watch(
      () => streamlitDataStore.theme?.primaryColor,
      (primary) => {
        if (!primary) return
        for (const name of ['light', 'dark']) {
          const t = vuetifyTheme.themes.value[name]
          if (t) t.colors.primary = primary
        }
      },
      { immediate: true },
    )

    // Watch selection store counter and send state back to Python
    // We watch counter (a primitive) instead of deep-watching the entire state.
    // This avoids creating a spread object on every reactivity check.
    // Counter increments on every selection change, so this captures all updates.
    let lastSentCounter: number | undefined = undefined
    let lastSentHash: string | undefined = undefined
    let lastSentAnnotationsHash: string | undefined = undefined
    let lastSentRequestedData = false
    let dataRequests = 0

    // Debounce utility for selection state updates
    // This prevents rapid clicks from overwhelming Streamlit with reruns
    let sendStateTimeout: ReturnType<typeof setTimeout> | null = null
    const DEBOUNCE_MS = 100 // 100ms debounce window

    const sendStateToStreamlit = () => {
      // Before its first render the view holds nothing Python does not know,
      // and each value sent would cost the page a rerun. A request for data is
      // the exception: a view whose first data never arrived (its message was
      // dropped when a rerun started) has not rendered, and without the request
      // Python would keep sending only the hash and the view would stay on
      // "Loading..."
      if (streamlitDataStore.renderData === null && !streamlitDataStore.requestData) return
      const currentCounter = selectionStore.$state.counter
      const currentHash = streamlitDataStore.hash || null
      const currentAnnotations = streamlitDataStore.annotations
      // Hash annotations to detect changes (use peak_id array as proxy for full content)
      const annotationsHash = currentAnnotations
        ? JSON.stringify(currentAnnotations.peak_id)
        : undefined

      // Avoid duplicate sends for same counter+hash+annotations combination
      const event = streamlitDataStore.event
      if (event === null && currentCounter === lastSentCounter && currentHash === lastSentHash && annotationsHash === lastSentAnnotationsHash) {
        console.log('[App] sendStateToStreamlit: SKIPPED (duplicate)', {
          timestamp: Date.now(),
          counter: currentCounter,
        })
        return
      }
      // A new data hash alone is nothing new for Python, which sent that data.
      // After a data request it is: Streamlit keeps returning the last value
      // sent, so a value still carrying the request would ask on every run.
      const reportsNothingNew =
        annotationsHash === lastSentAnnotationsHash &&
        !streamlitDataStore.requestData &&
        !lastSentRequestedData
      lastSentCounter = currentCounter
      lastSentHash = currentHash ?? undefined
      lastSentAnnotationsHash = annotationsHash

      // Deep clone to remove Vue reactivity proxies before sending to Streamlit
      // This prevents "Proxy object could not be cloned" errors
      const plainState = JSON.parse(JSON.stringify(selectionStore.$state))

      // The selection values are exactly what Python just sent (its counter
      // moved because Python's did, a view wrote back a value it already had, or
      // new data arrived): sending them back would only rerun the script, once
      // per component on the page.
      if (event === null && reportsNothingNew && stateValues(plainState) === streamlitDataStore.lastPythonState) {
        console.log('[App] sendStateToStreamlit: SKIPPED (state is Python\'s)', {
          timestamp: Date.now(),
          counter: currentCounter,
        })
        return
      }

      // Find pagination identifier and value for logging
      const paginationIdentifier = Object.keys(plainState).find(k =>
        typeof plainState[k] === 'object' && plainState[k]?.page !== undefined
      )
      const paginationValue = paginationIdentifier ? plainState[paginationIdentifier] : undefined

      console.log('[App] ===== sendStateToStreamlit =====', {
        timestamp: Date.now(),
        counter: currentCounter,
        hash: currentHash?.substring(0, 8),
        paginationIdentifier,
        paginationValue,
        requestData: streamlitDataStore.requestData,
      })

      // Echo back Vue's current data hash so Python knows if Vue has the data
      // This enables bidirectional hash confirmation for cache optimization
      plainState._vueDataHash = currentHash
      // Include annotations from components like SequenceView
      if (currentAnnotations) {
        plainState._annotations = JSON.parse(JSON.stringify(currentAnnotations))
      }
      // Signal Python if we need data (cache miss after page navigation)
      lastSentRequestedData = streamlitDataStore.requestData
      if (streamlitDataStore.requestData) {
        // A new value per request, so Python can tell it from the kept one
        plainState._requestData = ++dataRequests
        streamlitDataStore.clearRequestData()
      }
      if (event !== null) {
        plainState._event = JSON.parse(JSON.stringify(event))
        streamlitDataStore.event = null
      }
      // The view's last height, so Python reserves it when the view is drawn again
      if (reportedFrameHeight > 0) plainState._frameHeight = reportedFrameHeight
      Streamlit.setComponentValue(plainState)
      console.log('[App] setComponentValue CALLED')
    }

    // Debounced version for selection changes - batches rapid clicks. A change
    // after a quiet period is sent at once (a single click should not wait for
    // the window); changes following it within the window are batched.
    let lastDebouncedSend = 0
    const debouncedSendState = () => {
      if (sendStateTimeout) {
        clearTimeout(sendStateTimeout)
      } else if (Date.now() - lastDebouncedSend >= DEBOUNCE_MS) {
        lastDebouncedSend = Date.now()
        sendStateToStreamlit()
        return
      }
      sendStateTimeout = setTimeout(() => {
        lastDebouncedSend = Date.now()
        sendStateToStreamlit()
        sendStateTimeout = null
      }, DEBOUNCE_MS)
    }

    // Flush any pending debounced state (used before immediate sends)
    const flushPendingState = () => {
      if (sendStateTimeout) {
        clearTimeout(sendStateTimeout)
        sendStateTimeout = null
      }
    }

    // Watch counter, hash, annotations, and requestData to ensure Python always knows Vue's state
    // Counter changes (selection updates) are debounced to prevent rapid click cascades
    watch(() => selectionStore.$state.counter, (newVal, oldVal) => {
      // On first load (immediate: true), send immediately
      if (oldVal === undefined) {
        sendStateToStreamlit()
      } else {
        // Debounce subsequent selection changes to batch rapid clicks
        debouncedSendState()
      }
    }, { immediate: true })
    // Hash and annotation changes are sent immediately (data sync, not user interaction)
    watch(() => streamlitDataStore.hash, () => sendStateToStreamlit())
    watch(() => streamlitDataStore.annotations, () => sendStateToStreamlit(), { deep: true })
    // RequestData needs immediate response - flush any pending debounced state first
    watch(() => streamlitDataStore.requestData, (newVal) => {
      if (newVal) {
        flushPendingState()
        sendStateToStreamlit()
      }
    })

    // A view's action goes out at once, with any pending selection
    watch(() => streamlitDataStore.event, (newVal) => {
      if (newVal !== null) {
        flushPendingState()
        sendStateToStreamlit()
      }
    })

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

    return { streamlitDataStore, selectionStore, helpState, fullscreen, screenHeight }
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

    /** The arguments the view is drawn with: in full screen, as tall as the screen. */
    shownArgs(): ComponentArgs | undefined {
      const args = this.componentArgs
      if (!args || !this.fullscreen) return args
      const height = this.screenHeight - 16
      const sized: Record<string, unknown> = { ...args, height }
      // The structure viewer sizes its canvas apart from its controls
      if ('viewerHeight' in args || args.componentType === 'ProteinStructureView') sized.viewerHeight = height - 160
      return sized as unknown as ComponentArgs
    },
    /** In full screen the view sits on the app's background and scrolls if taller. */
    fullscreenStyle(): Record<string, string> | undefined {
      if (!this.fullscreen) return undefined
      return {
        background: this.streamlitDataStore.theme?.backgroundColor || '#ffffff',
        height: '100vh',
        overflow: 'auto',
      }
    },
    /**
     * Views drawn on a card show their help icon in the card's corner.
     */
    helpInCard(): boolean {
      return ['SequenceView', 'ProteinSequenceView', 'SequenceCoverage'].includes(String(this.componentArgs?.componentType))
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
        case 'PlotlyClusteredHeatmap':
          return PlotlyClusteredHeatmap
        case 'PlotlyMirrorPlot':
          return PlotlyMirrorPlot
        case 'PlotlyVolcano':
          return PlotlyVolcano
        case 'PlotlyPca':
          return PlotlyPca
        case 'PlotlySeries':
          return PlotlySeries
        case 'Plotly3D':
          return Plotly3D
        case 'PlotlyDeconvolvedSpectrum':
          return PlotlyDeconvolvedSpectrum
        case 'SequenceView':
          return SequenceView
        case 'ProteinSequenceView':
          return ProteinSequenceView
        case 'ProteinStructureView':
          return ProteinStructureView
        case 'SequenceCoverage':
          return SequenceCoverage
        default:
          console.warn(`Unknown component type: ${componentType}`)
          return null
      }
    },
  },
  watch: {
    // Plots keep the height they were drawn with until they redraw: resize them now
    'shownArgs.height'(height: number | undefined, previous: number | undefined) {
      if (typeof height === 'number' && typeof previous === 'number' && height !== previous) {
        this.$nextTick(() => resizePlots(height - previous))
      }
    },
  },
  created() {
    Streamlit.setComponentReady()
    // No height of its own here: the frame starts at the height Python gave the
    // view and keeps it until the view has its data (see mounted)
    Streamlit.events.addEventListener(Streamlit.RENDER_EVENT, this.updateStreamlitData)
  },
  mounted() {
    // Use ResizeObserver to update frame height only when size actually changes
    // This replaces polling (setInterval every 500ms) with event-driven updates
    // Until the data arrives the view shows a placeholder, whose height is not
    // the view's: measured, the frame shrank to it and grew again with the data,
    // and everything below jumped twice. It keeps Python's height until then.
    // Measured on the view, not the document: while a table lays out new rows
    // the document is briefly taller than the view, and the frame grew to that.
    this.resizeObserver = new ResizeObserver(() => {
      if (this.streamlitDataStore.hash) this.reportViewHeight()
    })
    this.resizeObserver.observe(this.$el as HTMLElement)
    // The data may leave the size as it was, so no resize follows: measure once
    this.$watch(
      () => !!this.streamlitDataStore.hash,
      (hasData: boolean) => {
        if (hasData) this.$nextTick(() => this.reportViewHeight())
      },
      { immediate: true }
    )
  },
  unmounted() {
    Streamlit.events.removeEventListener(Streamlit.RENDER_EVENT, this.updateStreamlitData)
    if (this.resizeObserver) {
      this.resizeObserver.disconnect()
    }
  },
  // Removed: updated() hook that called Streamlit.setFrameHeight()
  // This was redundant - height is now set explicitly by components
  // and via the watch on allDataForDrawing.height
  methods: {
    /**
     * Give the frame the view's height, once the view has drawn.
     *
     * A view's code is loaded on demand: when its data comes before its code,
     * the view takes no space yet and measures 0. Reported, that hid the frame
     * until the code arrived (on a slow connection seconds later), so every
     * plot of a page vanished and came back. The frame keeps its height then.
     */
    reportViewHeight(): void {
      const height = this.viewHeight()
      if (height <= 0) return
      reportedFrameHeight = height
      Streamlit.setFrameHeight(height)
    },
    /** Bottom of the view in the document, its last element's margin included. */
    viewHeight(): number {
      const root = this.$el as HTMLElement
      const last = root.lastElementChild as HTMLElement | null
      const margin = last ? parseFloat(getComputedStyle(last).marginBottom) || 0 : 0
      return Math.ceil(root.getBoundingClientRect().bottom + window.scrollY + margin)
    },
    async updateStreamlitData(event: Event): Promise<void> {
      const detail = (event as CustomEvent<RenderData>).detail
      // The app's fonts and primary colour, so the frame matches the page around it
      applyAppTheme(detail.theme)
      this.streamlitDataStore.updateRenderData(detail)
    },
  },
})
</script>

<style>
body {
  margin: 0;
}

.insight-root {
  position: relative;
}
/* The app's text font (set from the theme by applyThemeFonts), also for
   Vuetify's typography classes, which name Roboto */
html,
html body,
html body :is(.text-h1, .text-h2, .text-h3, .text-h4, .text-h5, .text-h6, .text-subtitle-1, .text-subtitle-2,
  .text-body-1, .text-body-2, .text-button, .text-caption, .text-overline) {
  font-family: var(--insight-font, 'Source Sans Pro', sans-serif);
}

/* The selected table row in the app's primary colour, over the row's own background */
html[data-insight-themed] .tabulator-row.tabulator-selected {
  background-color: color-mix(in srgb, var(--insight-primary) 24%, transparent);
}
html[data-insight-themed] .tabulator-row.tabulator-selected:hover {
  background-color: color-mix(in srgb, var(--insight-primary) 36%, transparent);
}

/* Numbers in tables and on axes line up, whatever numerals the font draws by default */
html {
  font-variant-numeric: lining-nums tabular-nums;
}

.tabulator-tooltip {
  background: #fff;
  color: #000;
}
</style>
