/**
 * Regression tests for categorical-mode click routing in PlotlyHeatmap.
 *
 * Finding P1-HM-INT-001: in categorical mode the heatmap renders N per-category
 * scattergl traces. Plotly's `pointIndex` is PER-TRACE, so the shared click
 * handler in usePlotlyScatter (which previously resolved the clicked point via a
 * flat index into the combined heatmapData) mapped clicks in any category beyond
 * the first to the WRONG global row, pushing wrong interactivity values.
 *
 * The fix attaches per-point `customdata` (a {column: value} record holding the
 * interactivity source values for that point's global row) to each categorical
 * trace, and makes the click handler prefer `pt.customdata` when present, falling
 * back to the flat-index lookup for the single-trace continuous case.
 *
 * These tests assert:
 *  - categorical traces carry the correct per-point customdata (incl. non-first
 *    category points), so a click resolves to the right row's values;
 *  - clicking a non-first-category point pushes that row's interactivity values
 *    to the selection store (the previously-broken path);
 *  - continuous single-trace mode still resolves via the flat index (unchanged).
 */

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

// Capture the plotly_click handler registered by the component so we can drive
// click events directly, and capture the traces passed to newPlot/react so we
// can inspect the per-point customdata the fix attaches.
type ClickHandler = (event: unknown) => void
const registeredClickHandlers: ClickHandler[] = []
let lastTraces: Array<Record<string, unknown>> = []

vi.mock('plotly.js-dist-min', () => {
  // Minimal emitter so document.getElementById(id).on('plotly_click', ...) works
  // the way Plotly wires it after newPlot().
  function attachEmitter(el: HTMLElement) {
    const anyEl = el as unknown as {
      on: (eventName: string, cb: ClickHandler) => void
      removeAllListeners?: (eventName?: string) => void
    }
    anyEl.on = (eventName: string, cb: ClickHandler) => {
      if (eventName === 'plotly_click') registeredClickHandlers.push(cb)
    }
    anyEl.removeAllListeners = () => {}
  }

  const newPlot = vi.fn(
    async (
      idOrEl: string | HTMLElement,
      traces: Array<Record<string, unknown>>,
    ) => {
      lastTraces = traces
      const el =
        typeof idOrEl === 'string' ? document.getElementById(idOrEl) : idOrEl
      if (el) attachEmitter(el as HTMLElement)
      return el
    },
  )

  const react = vi.fn(
    async (
      idOrEl: string | HTMLElement,
      traces: Array<Record<string, unknown>>,
    ) => {
      lastTraces = traces
      return typeof idOrEl === 'string' ? document.getElementById(idOrEl) : idOrEl
    },
  )

  return {
    default: {
      newPlot,
      react,
      relayout: vi.fn(async () => {}),
      restyle: vi.fn(async () => {}),
      downloadImage: vi.fn(),
      Icons: { camera: {} },
    },
  }
})

import PlotlyHeatmap from '../PlotlyHeatmap.vue'
import { useStreamlitDataStore } from '@/stores/streamlit-data'
import { useSelectionStore } from '@/stores/selection'

// Categorical dataset: each row has a distinct interactivity identity
// (scan_idx / mass_idx) so a wrong-row resolution is detectable. Rows are
// interleaved across categories so that, in the combined array, a non-first
// category point does NOT share its per-trace index with its global index.
//
// heatmapData (global index -> row):
//   0: Control   scan_idx=10 mass_idx=100
//   1: Treatment scan_idx=20 mass_idx=200   <- non-first category, global idx 1
//   2: Control   scan_idx=30 mass_idx=300
//   3: Treatment scan_idx=40 mass_idx=400   <- non-first category, global idx 3
//
// Per Plotly, the "Treatment" trace contains points [row1, row3]; clicking its
// SECOND point yields pointIndex=1 which, under the old flat-index lookup, would
// resolve to global row 1 (scan_idx=20) instead of the correct row 3.
const CATEGORICAL_DATA = [
  { rt: 1.0, mz: 100, intensity: 1000, group: 'Control', scan_idx: 10, mass_idx: 100 },
  { rt: 2.0, mz: 200, intensity: 2000, group: 'Treatment', scan_idx: 20, mass_idx: 200 },
  { rt: 3.0, mz: 300, intensity: 3000, group: 'Control', scan_idx: 30, mass_idx: 300 },
  { rt: 4.0, mz: 400, intensity: 4000, group: 'Treatment', scan_idx: 40, mass_idx: 400 },
]

const INTERACTIVITY = { spectrum: 'scan_idx', mass: 'mass_idx' }

function mountHeatmap(args: Record<string, unknown>, heatmapData: unknown[]) {
  const pinia = createPinia()
  setActivePinia(pinia)

  const dataStore = useStreamlitDataStore()
  dataStore.dataForDrawing = { heatmapData }

  const wrapper = mount(PlotlyHeatmap, {
    props: { args, index: 0 },
    global: { plugins: [pinia] },
    attachTo: document.body,
  })

  return { wrapper, selectionStore: useSelectionStore() }
}

describe('PlotlyHeatmap categorical click routing (P1-HM-INT-001)', () => {
  beforeEach(() => {
    registeredClickHandlers.length = 0
    lastTraces = []
    vi.clearAllMocks()
  })

  it('attaches per-point customdata with the correct GLOBAL row identity for non-first categories', () => {
    const args = {
      xColumn: 'rt',
      yColumn: 'mz',
      intensityColumn: 'intensity',
      categoryColumn: 'group',
      interactivity: INTERACTIVITY,
    }
    const { wrapper } = mountHeatmap(args, CATEGORICAL_DATA)

    const traces = (
      wrapper.vm as unknown as {
        buildCategoricalTraces: () => Array<Record<string, unknown>>
      }
    ).buildCategoricalTraces()

    // Two categories -> two traces (order follows first appearance: Control, Treatment)
    expect(traces).toHaveLength(2)
    const treatment = traces.find((t) => t.name === 'Treatment')!
    expect(treatment).toBeTruthy()

    const customdata = treatment.customdata as Array<Record<string, unknown>>
    // Treatment trace holds global rows 1 and 3, in that order.
    expect(customdata).toHaveLength(2)
    expect(customdata[0]).toEqual({ scan_idx: 20, mass_idx: 200 })
    // The SECOND Treatment point (per-trace pointIndex=1) must carry global
    // row 3's identity, NOT global row 1's. This is the core of the bug.
    expect(customdata[1]).toEqual({ scan_idx: 40, mass_idx: 400 })
  })

  it('routes a click on a non-first-category point to the correct row (was broken)', async () => {
    const args = {
      xColumn: 'rt',
      yColumn: 'mz',
      intensityColumn: 'intensity',
      categoryColumn: 'group',
      interactivity: INTERACTIVITY,
    }
    const { wrapper, selectionStore } = mountHeatmap(args, CATEGORICAL_DATA)
    await wrapper.vm.$nextTick()

    // A plotly_click handler should have been registered during render.
    expect(registeredClickHandlers.length).toBeGreaterThan(0)
    const handler = registeredClickHandlers[registeredClickHandlers.length - 1]

    // Find the Treatment trace's customdata as Plotly would supply it.
    const treatment = lastTraces.find((t) => t.name === 'Treatment')!
    const treatmentCustomdata = treatment.customdata as Array<Record<string, unknown>>

    // Simulate Plotly delivering a click on the SECOND Treatment point
    // (per-trace pointIndex = 1). Plotly attaches that point's customdata.
    handler({
      points: [
        {
          curveNumber: 1,
          pointIndex: 1,
          customdata: treatmentCustomdata[1],
        },
      ],
    })

    // Must resolve to global row 3 (scan_idx=40, mass_idx=400), not row 1.
    expect(selectionStore.$state.spectrum).toBe(40)
    expect(selectionStore.$state.mass).toBe(400)
  })

  it('continuous single-trace mode still resolves via flat pointIndex (unchanged)', async () => {
    const continuousData = [
      { rt: 1.0, mz: 100, intensity: 1000, scan_idx: 10, mass_idx: 100 },
      { rt: 2.0, mz: 200, intensity: 2000, scan_idx: 20, mass_idx: 200 },
      { rt: 3.0, mz: 300, intensity: 3000, scan_idx: 30, mass_idx: 300 },
    ]
    const args = {
      xColumn: 'rt',
      yColumn: 'mz',
      intensityColumn: 'intensity',
      interactivity: INTERACTIVITY,
      // no categoryColumn -> single continuous trace, no customdata attached
    }
    const { wrapper, selectionStore } = mountHeatmap(args, continuousData)
    await wrapper.vm.$nextTick()

    // Continuous mode must NOT attach customdata (single combined trace).
    expect(lastTraces).toHaveLength(1)
    expect(lastTraces[0].customdata).toBeUndefined()

    const handler = registeredClickHandlers[registeredClickHandlers.length - 1]
    // Plotly delivers no customdata; only a flat pointIndex into the combined data.
    handler({ points: [{ curveNumber: 0, pointIndex: 2 }] })

    // Flat index 2 -> third row (scan_idx=30, mass_idx=300).
    expect(selectionStore.$state.spectrum).toBe(30)
    expect(selectionStore.$state.mass).toBe(300)
  })
})
