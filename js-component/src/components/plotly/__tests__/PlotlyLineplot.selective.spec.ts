/**
 * Vitest for the SELECTIVE-HIGHLIGHT (FLASHApp parity) modebar toggle behavior in
 * the default-mode LinePlot (PlotlyLineplot.vue).
 *
 * Reproduces the oracle PlotlyLineplotUnified.vue interaction model:
 *  - "Hide/Show Deconvolved Peaks" (annotated spectrum only) toggles between the
 *    SELECTIVE highlight (the selected mass's peaks, baked into highlight_mask) and
 *    that set PLUS every signal peak (ALL-SIGNAL set), CLIENT-SIDE (no round-trip).
 *  - "Hide/Show Annotations" toggles the z=N charge labels.
 *  - Defaults: selective only (deconvolvedPeaksHighlightMode OFF), labels visible.
 *  - Both buttons carry the EXACT dynamic oracle titles, swapping with state.
 *  - When the selective path is NOT active, no toggle buttons + the base mask is
 *    used verbatim (existing default behavior unchanged).
 */

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

beforeEach(() => {
  // jsdom lacks <canvas>.getContext; the descriptor/annotation path measures text.
  HTMLCanvasElement.prototype.getContext = vi.fn(() => ({
    font: '',
    measureText: (t: string) => ({ width: t.length * 8 }),
  })) as unknown as HTMLCanvasElement['getContext']
})

vi.mock('plotly.js-dist-min', () => {
  const newPlot = vi.fn(async () => undefined)
  return {
    default: {
      newPlot,
      react: vi.fn(async () => undefined),
      relayout: vi.fn(async () => {}),
      restyle: vi.fn(async () => {}),
      downloadImage: vi.fn(),
      Icons: { camera: {} },
    },
  }
})

import PlotlyLineplot from '../PlotlyLineplot.vue'
import { useStreamlitDataStore } from '@/stores/streamlit-data'

type AnyRecord = Record<string, unknown>

interface SelectiveVM {
  annotationsVisible: boolean
  deconvolvedPeaksHighlightMode: boolean
  selectiveHighlightEnabled: boolean
  deconvPeaksToggleEnabled: boolean
  effectiveHighlightMask: boolean[] | undefined
  descriptorAnnotationBoxes: Array<{ visible: boolean; text: string }>
  buildSelectiveHighlightButtons(): Array<{ name: string; title: string }>
  toggleAnnotations(): void
  toggleDeconvolvedPeaksHighlight(): void
  traces: Array<AnyRecord>
}

function mountLineplot(args: AnyRecord, data: AnyRecord) {
  const pinia = createPinia()
  setActivePinia(pinia)
  const dataStore = useStreamlitDataStore()
  dataStore.dataForDrawing = data
  const wrapper = mount(PlotlyLineplot, {
    props: { args, index: 0 },
    global: { plugins: [pinia] },
    attachTo: document.body,
  })
  return { wrapper, dataStore }
}

// Annotated-spectrum args: m/z x-axis, selective-highlight active, deconv toggle on.
const ANNOTATED_ARGS: AnyRecord = {
  componentType: 'PlotlyLineplotUnified',
  mode: 'default',
  title: 'Annotated Spectrum',
  xLabel: 'm/z',
  yLabel: 'Intensity',
  xColumn: 'mz',
  yColumn: 'intensity',
  interactivity: { peak: 'peak_id' },
  selectiveHighlightEnabled: true,
  deconvPeaksToggle: true,
}

// Base frame for an annotated spectrum: 5 m/z peaks. The SELECTIVE set (the
// selected mass's peaks) is baked into highlight_mask by Python — here peaks 0,1,2
// belong to the selected mass. The ALL-SIGNAL set covers every signal peak (0..4).
function annotatedData(extra: AnyRecord = {}): AnyRecord {
  return {
    plotData: {
      mz: [75.0, 75.1, 50.0, 125.0, 175.0],
      intensity: [3, 1, 2, 4, 6],
      peak_id: [0, 1, 2, 3, 4],
      // selective set (selected mass = peaks 0,1,2)
      _dynamic_highlight: [true, true, true, false, false],
      _dynamic_annotation: ['', '', '', '', ''],
    },
    _plotConfig: {
      xColumn: 'mz',
      yColumn: 'intensity',
      highlightColumn: '_dynamic_highlight',
      annotationColumn: '_dynamic_annotation',
      interactivityColumns: { peak_id: 'peak_id' },
    },
    // z=N charge labels for the selected mass (generic descriptors).
    peakAnnotations: [
      { x: 75.02, text: 'z=12', color: '#E4572E', group: 'charge' },
      { x: 50.0, text: 'z=13', color: '#E4572E', group: 'charge' },
    ],
    selectiveHighlight: {
      idColumn: 'peak_id',
      allSignalKeys: [0, 1, 2, 3, 4],
      annotationsVisible: true,
      deconvolvedPeaksHighlightMode: false,
      deconvPeaksToggle: true,
    },
    ...extra,
  }
}

function countHighlighted(mask: boolean[] | undefined): number {
  if (!mask) return -1
  return mask.filter(Boolean).length
}

describe('PlotlyLineplot selective highlight — defaults', () => {
  beforeEach(() => vi.clearAllMocks())

  it('default: selective only (toggle OFF), z=N labels visible', () => {
    const { wrapper } = mountLineplot(ANNOTATED_ARGS, annotatedData())
    const vm = wrapper.vm as unknown as SelectiveVM
    expect(vm.selectiveHighlightEnabled).toBe(true)
    expect(vm.deconvPeaksToggleEnabled).toBe(true)
    // Defaults match the oracle.
    expect(vm.annotationsVisible).toBe(true)
    expect(vm.deconvolvedPeaksHighlightMode).toBe(false)
    // Effective mask == the SELECTIVE set only (peaks 0,1,2).
    expect(vm.effectiveHighlightMask).toEqual([true, true, true, false, false])
    // z=N labels are visible (both descriptors present).
    const labels = vm.descriptorAnnotationBoxes.filter((b) => b.visible)
    expect(labels.map((b) => b.text).sort()).toEqual(['z=12', 'z=13'])
  })
})

describe('PlotlyLineplot selective highlight — "Show Deconvolved Peaks" toggle', () => {
  beforeEach(() => vi.clearAllMocks())

  it('toggling ON highlights ALL signal peaks (cumulative with selective)', async () => {
    const { wrapper } = mountLineplot(ANNOTATED_ARGS, annotatedData())
    const vm = wrapper.vm as unknown as SelectiveVM

    // Before: only the 3 selective peaks are highlighted.
    expect(countHighlighted(vm.effectiveHighlightMask)).toBe(3)

    // Toggle ON => the all-signal set (all 5 peaks) is highlighted, client-side.
    vm.toggleDeconvolvedPeaksHighlight()
    await wrapper.vm.$nextTick()
    expect(vm.deconvolvedPeaksHighlightMode).toBe(true)
    expect(vm.effectiveHighlightMask).toEqual([true, true, true, true, true])

    // Toggle OFF => back to the selective-only set.
    vm.toggleDeconvolvedPeaksHighlight()
    await wrapper.vm.$nextTick()
    expect(countHighlighted(vm.effectiveHighlightMask)).toBe(3)
  })

  it('button title swaps with state: Show <-> Hide Deconvolved Peaks', async () => {
    const { wrapper } = mountLineplot(ANNOTATED_ARGS, annotatedData())
    const vm = wrapper.vm as unknown as SelectiveVM

    let buttons = vm.buildSelectiveHighlightButtons()
    const deconvBtn = () =>
      vm.buildSelectiveHighlightButtons().find((b) => b.name === 'toggleDeconvolvedPeaks')
    // Annotated spectrum => BOTH buttons present, in oracle order.
    expect(buttons.map((b) => b.name)).toEqual([
      'toggleAnnotations',
      'toggleDeconvolvedPeaks',
    ])
    // Default OFF => "Show Deconvolved Peaks".
    expect(deconvBtn()?.title).toBe('Show Deconvolved Peaks')

    vm.toggleDeconvolvedPeaksHighlight()
    await wrapper.vm.$nextTick()
    // ON => "Hide Deconvolved Peaks".
    expect(deconvBtn()?.title).toBe('Hide Deconvolved Peaks')
  })
})

describe('PlotlyLineplot selective highlight — "Hide Annotations" toggle', () => {
  beforeEach(() => vi.clearAllMocks())

  it('toggling hides/shows the z=N charge labels; title swaps', async () => {
    const { wrapper } = mountLineplot(ANNOTATED_ARGS, annotatedData())
    const vm = wrapper.vm as unknown as SelectiveVM

    const annBtn = () =>
      vm.buildSelectiveHighlightButtons().find((b) => b.name === 'toggleAnnotations')

    // Default visible => labels shown, button says "Hide Annotations".
    expect(vm.descriptorAnnotationBoxes.filter((b) => b.visible).length).toBe(2)
    expect(annBtn()?.title).toBe('Hide Annotations')

    // Toggle OFF => labels hidden entirely, button says "Show Annotations".
    vm.toggleAnnotations()
    await wrapper.vm.$nextTick()
    expect(vm.annotationsVisible).toBe(false)
    expect(vm.descriptorAnnotationBoxes.length).toBe(0)
    expect(annBtn()?.title).toBe('Show Annotations')

    // Toggle back ON => labels return.
    vm.toggleAnnotations()
    await wrapper.vm.$nextTick()
    expect(vm.descriptorAnnotationBoxes.filter((b) => b.visible).length).toBe(2)
  })
})

describe('PlotlyLineplot selective highlight — deconvolved spectrum (no deconv button)', () => {
  beforeEach(() => vi.clearAllMocks())

  it('deconv spectrum: only the annotations toggle, NO deconvolved-peaks button', () => {
    // Deconvolved spectrum: MonoMass x-axis, selective active, deconv toggle OFF.
    const args: AnyRecord = {
      ...ANNOTATED_ARGS,
      componentType: 'PlotlyLineplotUnified',
      xLabel: 'MonoMass',
      xColumn: 'mass',
      deconvPeaksToggle: false,
    }
    const data: AnyRecord = {
      plotData: {
        mass: [150.0, 250.0, 350.0],
        intensity: [1000, 2000, 1500],
        peak_id: [0, 1, 2],
        _dynamic_highlight: [false, true, false],
        _dynamic_annotation: ['', '', ''],
      },
      _plotConfig: {
        xColumn: 'mass',
        yColumn: 'intensity',
        highlightColumn: '_dynamic_highlight',
        annotationColumn: '_dynamic_annotation',
        interactivityColumns: { peak_id: 'peak_id' },
      },
      // Deconv spectrum: NO charge labels (oracle), no all-signal set.
      selectiveHighlight: {
        idColumn: 'peak_id',
        allSignalKeys: null,
        deconvPeaksToggle: false,
      },
    }
    const { wrapper } = mountLineplot(args, data)
    const vm = wrapper.vm as unknown as SelectiveVM

    expect(vm.deconvPeaksToggleEnabled).toBe(false)
    const buttons = vm.buildSelectiveHighlightButtons()
    expect(buttons.map((b) => b.name)).toEqual(['toggleAnnotations'])
    // Selective highlight still works (the selected mass row only).
    expect(vm.effectiveHighlightMask).toEqual([false, true, false])
  })
})

describe('PlotlyLineplot selective highlight — default OFF (no regression)', () => {
  beforeEach(() => vi.clearAllMocks())

  it('without selectiveHighlightEnabled: NO toggle buttons, base mask used', () => {
    const args: AnyRecord = {
      componentType: 'PlotlyLineplotUnified',
      mode: 'default',
      title: 'Plain Spectrum',
      xLabel: 'm/z',
      xColumn: 'mz',
      yColumn: 'intensity',
      highlightColumn: 'is_signal',
      interactivity: { peak: 'peak_id' },
      // selectiveHighlightEnabled intentionally absent.
    }
    const data: AnyRecord = {
      plotData: {
        mz: [100, 200, 300],
        intensity: [10, 20, 30],
        peak_id: [0, 1, 2],
        is_signal: [true, false, true],
      },
      _plotConfig: {
        xColumn: 'mz',
        yColumn: 'intensity',
        highlightColumn: 'is_signal',
        interactivityColumns: { peak_id: 'peak_id' },
      },
    }
    const { wrapper } = mountLineplot(args, data)
    const vm = wrapper.vm as unknown as SelectiveVM

    expect(vm.selectiveHighlightEnabled).toBe(false)
    // No toggle buttons added.
    expect(vm.buildSelectiveHighlightButtons()).toEqual([])
    // effectiveHighlightMask is undefined => traces() falls back to the base mask.
    expect(vm.effectiveHighlightMask).toBeUndefined()
  })
})
