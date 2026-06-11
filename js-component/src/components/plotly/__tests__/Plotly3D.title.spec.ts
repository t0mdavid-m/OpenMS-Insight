/**
 * Vitest for Plotly3D's DYNAMIC TITLE (FLASHApp parity, default-off).
 *
 * When `titleSelection` maps the scan + mass selection identifiers, the title is
 * computed REACTIVELY from the selection store, exactly like the oracle
 * Plotly3Dplot.vue `title` computed:
 *   '' when the scan selection is unset,
 *   'Precursor signals' when the scan is set but the mass is unset,
 *   'Mass signals' when both are set.
 * When `titleSelection` is absent, the static `args.title` is used unchanged.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('plotly.js-dist-min', () => {
  const newPlot = vi.fn(async (idOrEl: string | HTMLElement) =>
    typeof idOrEl === 'string' ? document.getElementById(idOrEl) : idOrEl,
  )
  return {
    default: {
      newPlot,
      react: vi.fn(async () => null),
      relayout: vi.fn(async () => {}),
      restyle: vi.fn(async () => {}),
      downloadImage: vi.fn(),
      Icons: { camera: {} },
    },
  }
})

import Plotly3D from '../plot3d/Plotly3D.vue'
import { useStreamlitDataStore } from '@/stores/streamlit-data'
import { useSelectionStore } from '@/stores/selection'

type AnyRecord = Record<string, unknown>

interface Plot3DTitleVM {
  displayTitle: string | undefined
  layout: { title?: { text: string } }
}

const ROWS = [
  { mass: 1000.0, charge: 2, intensity: 500.0, series: 'Signal', scan: 100, mass_index: 0 },
]

function mountPlot3D(args: AnyRecord) {
  const pinia = createPinia()
  setActivePinia(pinia)
  const dataStore = useStreamlitDataStore()
  dataStore.dataForDrawing = { plot3dData: ROWS }
  const selectionStore = useSelectionStore()
  const wrapper = mount(Plotly3D, {
    props: { args, index: 0 },
    global: { plugins: [pinia] },
    attachTo: document.body,
  })
  return { wrapper, selectionStore }
}

const TITLE_ARGS: AnyRecord = {
  componentType: 'Plotly3D',
  xColumn: 'mass',
  yColumn: 'charge',
  zColumn: 'intensity',
  categoryColumn: 'series',
  traceMode: 'lines',
  stem: false,
  title: 'Precursor Signals',
  titleSelection: { scan: 'spectrum', mass: 'mass' },
}

describe('Plotly3D dynamic title (FLASHApp parity)', () => {
  beforeEach(() => vi.clearAllMocks())

  it("'' when the scan selection is unset", () => {
    const { wrapper } = mountPlot3D(TITLE_ARGS)
    const vm = wrapper.vm as unknown as Plot3DTitleVM
    expect(vm.displayTitle).toBe('')
    // Empty title => layout omits the title block entirely.
    expect(vm.layout.title).toBeUndefined()
  })

  it("'Precursor signals' when scan set but mass unset", async () => {
    const { wrapper, selectionStore } = mountPlot3D(TITLE_ARGS)
    selectionStore.$patch({ spectrum: 100 })
    await wrapper.vm.$nextTick()
    const vm = wrapper.vm as unknown as Plot3DTitleVM
    expect(vm.displayTitle).toBe('Precursor signals')
    expect(vm.layout.title?.text).toBe('<b>Precursor signals</b>')
  })

  it("'Mass signals' when both scan and mass are set", async () => {
    const { wrapper, selectionStore } = mountPlot3D(TITLE_ARGS)
    selectionStore.$patch({ spectrum: 100, mass: 5 })
    await wrapper.vm.$nextTick()
    const vm = wrapper.vm as unknown as Plot3DTitleVM
    expect(vm.displayTitle).toBe('Mass signals')
    expect(vm.layout.title?.text).toBe('<b>Mass signals</b>')
  })

  it('transitions reactively as the selection changes', async () => {
    const { wrapper, selectionStore } = mountPlot3D(TITLE_ARGS)
    const vm = wrapper.vm as unknown as Plot3DTitleVM
    expect(vm.displayTitle).toBe('')
    selectionStore.$patch({ spectrum: 100 })
    await wrapper.vm.$nextTick()
    expect(vm.displayTitle).toBe('Precursor signals')
    selectionStore.$patch({ mass: 7 })
    await wrapper.vm.$nextTick()
    expect(vm.displayTitle).toBe('Mass signals')
    // Clearing the mass falls back to 'Precursor signals'.
    selectionStore.$patch({ mass: null })
    await wrapper.vm.$nextTick()
    expect(vm.displayTitle).toBe('Precursor signals')
  })

  it('without titleSelection: static title used unchanged (default off)', () => {
    const args: AnyRecord = { ...TITLE_ARGS }
    delete args.titleSelection
    const { wrapper, selectionStore } = mountPlot3D(args)
    selectionStore.$patch({ spectrum: 100, mass: 5 })
    const vm = wrapper.vm as unknown as Plot3DTitleVM
    // Static title regardless of selection.
    expect(vm.displayTitle).toBe('Precursor Signals')
    expect(vm.layout.title?.text).toBe('<b>Precursor Signals</b>')
  })
})
