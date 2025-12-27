/**
 * Shared composable for Plotly scatter-based components (Heatmap, VolcanoPlot).
 *
 * Provides common functionality:
 * - Resize observer for responsive behavior
 * - Plotly config with SVG export
 * - Click event handling with selection store integration
 * - Theme-aware layout styling
 * - Streamlit frame height updates
 */

import { ref, computed, type Ref, type ComputedRef } from 'vue'
import Plotly from 'plotly.js-dist-min'
import { Streamlit, type Theme } from 'streamlit-component-lib'
import { useStreamlitDataStore } from '@/stores/streamlit-data'
import { useSelectionStore } from '@/stores/selection'

export interface PlotlyScatterOptions {
  /** Unique ID for the plot container */
  id: ComputedRef<string>
  /** Interactivity mapping: identifier -> column name */
  interactivity: ComputedRef<Record<string, string>>
  /** Function to get data array for click handling */
  getData: () => Record<string, unknown>[]
  /** Optional title for SVG export filename */
  title?: ComputedRef<string | undefined>
  /** Width threshold for "narrow" mode (default 600) */
  narrowThreshold?: number
}

export interface PlotlyScatterReturn {
  /** Current plot width in pixels */
  plotWidth: Ref<number>
  /** Whether the plot is in narrow mode */
  isNarrowPlot: ComputedRef<boolean>
  /** Streamlit theme */
  theme: ComputedRef<Theme | undefined>
  /** Theme-aware base layout properties */
  themeLayout: ComputedRef<Partial<Plotly.Layout>>
  /** Set up resize observer - call in mounted() */
  setupResizeObserver: () => void
  /** Clean up resize observer - call in beforeUnmount() */
  cleanupResizeObserver: () => void
  /** Get Plotly config with SVG export and scroll zoom */
  getPlotConfig: (additionalButtons?: Plotly.ModeBarButton[]) => Partial<Plotly.Config>
  /** Set up click handler for interactivity - call after Plotly.newPlot() */
  setupClickHandler: () => void
  /** Update Streamlit frame height - call after render */
  updateFrameHeight: () => void
  /** Selection store for direct access if needed */
  selectionStore: ReturnType<typeof useSelectionStore>
}

export function usePlotlyScatter(options: PlotlyScatterOptions): PlotlyScatterReturn {
  const { id, interactivity, getData, title, narrowThreshold = 600 } = options

  const streamlitDataStore = useStreamlitDataStore()
  const selectionStore = useSelectionStore()

  // Reactive state
  const plotWidth = ref(800)
  const resizeObserver = ref<ResizeObserver | null>(null)

  // Computed properties
  const isNarrowPlot = computed(() => plotWidth.value < narrowThreshold)

  const theme = computed(() => streamlitDataStore.theme)

  const themeLayout = computed<Partial<Plotly.Layout>>(() => ({
    paper_bgcolor: theme.value?.backgroundColor || 'white',
    plot_bgcolor: theme.value?.secondaryBackgroundColor || '#f5f5f5',
    font: {
      color: theme.value?.textColor || 'black',
      family: theme.value?.font || 'Arial',
    },
  }))

  // Methods
  function setupResizeObserver(): void {
    const plotElement = document.getElementById(id.value)
    if (plotElement && window.ResizeObserver) {
      resizeObserver.value = new ResizeObserver((entries) => {
        for (const entry of entries) {
          const newWidth = entry.contentRect.width
          if (Math.abs(newWidth - plotWidth.value) > 10) {
            plotWidth.value = newWidth
          }
        }
      })
      resizeObserver.value.observe(plotElement)
    }
  }

  function cleanupResizeObserver(): void {
    if (resizeObserver.value) {
      resizeObserver.value.disconnect()
      resizeObserver.value = null
    }
  }

  function getPlotConfig(additionalButtons?: Plotly.ModeBarButton[]): Partial<Plotly.Config> {
    const buttons: Plotly.ModeBarButton[] = [
      {
        title: 'Download as SVG',
        name: 'toImageSvg',
        icon: Plotly.Icons.camera,
        click: (plotlyElement: unknown) => {
          Plotly.downloadImage(plotlyElement as Plotly.PlotlyHTMLElement, {
            filename: title?.value || 'plot',
            height: 400,
            width: 1200,
            format: 'svg',
          })
        },
      },
      ...(additionalButtons || []),
    ]

    return {
      modeBarButtonsToRemove: ['toImage', 'sendDataToCloud'] as Plotly.ModeBarDefaultButtons[],
      modeBarButtonsToAdd: buttons,
      scrollZoom: true,
      responsive: true,
    }
  }

  function setupClickHandler(): void {
    const plotElement = document.getElementById(id.value) as Plotly.PlotlyHTMLElement | null
    if (!plotElement) return

    plotElement.on('plotly_click', (eventData: Plotly.PlotMouseEvent) => {
      const interactivityMap = interactivity.value
      if (!interactivityMap || Object.keys(interactivityMap).length === 0) {
        return
      }

      if (eventData.points && eventData.points.length > 0) {
        const pointIndex = eventData.points[0].pointIndex
        const data = getData()
        const pointData = data[pointIndex]

        if (pointData) {
          // Update selection store for each interactivity mapping
          for (const [identifier, column] of Object.entries(interactivityMap)) {
            const value = pointData[column]
            if (value !== undefined) {
              selectionStore.updateSelection(identifier, value)
            }
          }
        }
      }
    })
  }

  function updateFrameHeight(): void {
    Streamlit.setFrameHeight()
  }

  return {
    plotWidth,
    isNarrowPlot,
    theme,
    themeLayout,
    setupResizeObserver,
    cleanupResizeObserver,
    getPlotConfig,
    setupClickHandler,
    updateFrameHeight,
    selectionStore,
  }
}
