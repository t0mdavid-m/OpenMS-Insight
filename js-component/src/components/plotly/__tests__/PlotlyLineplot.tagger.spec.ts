/**
 * Parity regression tests for the tagger-mode LinePlot badge rendering.
 *
 * Finding P1-R2-LP-ANN-001 (charge-badge text color): the per-charge `z=<charge>`
 * badge label must use `font: { size: 15 }` ONLY — no `color`. The oracle
 * (PlotlyLineplotTagger.vue:369-372 / PlotlyLineplotUnified.vue:896-898) sets
 * `font:{size:15}` so Plotly falls back to the theme text color (dark), not a
 * forced white. The previous code forced `color:'white'`, which diverged from the
 * oracle badge label color.
 *
 * Finding P1-R2-LP-TAG-001 (level-0 mass-badge invisible hover): for every
 * highlighted Level-0 mass badge the oracle draws an invisible hover point
 * (marker size 20, opacity 0) carrying `hovertext = String(mass)` (full-precision
 * mass), so hovering the badge reveals the mass (oracle Tagger.vue:406-417,
 * Unified:937-948). The new code drew the badge rect+label via the `mass_label`
 * path but emitted no hover; this test pins that an invisible hover trace is now
 * emitted with the full-precision mass value.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

// jsdom does not implement <canvas>.getContext; the component uses it only to
// measure annotation-label text width. Stub a deterministic context so
// annotationBoxData (which feeds the mass-badge path) computes width without
// throwing — width ~ 8px per character, matching the component's own fallback.
beforeEach(() => {
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

interface PlotlyLineplotVM {
  level: 'deconvolved' | 'annotated'
  taggerChargeAnnotations: AnyRecord[]
  taggerMassBadgeHoverTrace: AnyRecord[]
  traces: AnyRecord[]
  annotationBoxData: Array<{ x: number; visible: boolean; label: string }>
  layout: { annotations?: AnyRecord[] }
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

const TAGGER_ARGS: AnyRecord = {
  componentType: 'PlotlyLineplot',
  mode: 'tagger',
  title: 'Augmented Deconvolved Spectrum',
  titleLevel1: 'Augmented Annotated Spectrum',
  xLabel: 'Monoisotopic Mass',
  xLabelLevel1: 'm/z',
  yLabel: 'Intensity',
  xColumn: 'MonoMass',
  yColumn: 'SumIntensity',
  highlightColumn: 'highlight',
  selectedColumn: 'selected_gold',
  annotationColumn: 'mass_label',
  interactivity: { tagger_mass: 'peak_id' },
  taggerMassButtons: true,
  taggerSegmentsKey: 'plotDataTaggerSegments',
  taggerChargesKey: 'plotDataTaggerCharges',
  taggerLevel1Key: 'plotDataTaggerLevel1',
  xPosScalingFactor: 27.5,
}

describe('PlotlyLineplot tagger charge badge (P1-R2-LP-ANN-001)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('charge-badge label font has size 15 and NO color (theme text color)', () => {
    // Level-1 drill-down: full annotated spectrum + one charge cluster.
    const data: AnyRecord = {
      plotData: {
        MonoMass: [150.0, 250.0],
        SumIntensity: [10, 20],
        peak_id: [0, 1],
        highlight: [true, true],
        selected_gold: [false, false],
        mass_label: ['150.00', '250.00'],
      },
      plotDataTaggerLevel1: {
        x: [500.1, 500.6, 700.2],
        y: [100, 80, 60],
        highlight: [true, true, false],
        selected_gold: [false, false, false],
      },
      plotDataTaggerCharges: {
        mz: [500.1, 500.6],
        intensity: [100, 80],
        charge: [2, 2],
        peak_id: [0, 1],
        cog: [500.3, 500.3],
        charge_label: ['z=2', 'z=2'],
        selected: [false, false],
      },
      _plotConfig: { mode: 'tagger', level: 'annotated' },
    }
    const { wrapper } = mountLineplot(TAGGER_ARGS, data)
    const vm = wrapper.vm as unknown as PlotlyLineplotVM

    expect(vm.level).toBe('annotated')
    const ann = vm.taggerChargeAnnotations
    expect(ann.length).toBeGreaterThan(0)
    for (const a of ann) {
      expect(a.text).toBe('z=2')
      // Parity: font is { size: 15 } only — no color key (=> theme text color).
      expect(a.font).toEqual({ size: 15 })
      expect((a.font as AnyRecord).color).toBeUndefined()
    }
  })
})

describe('PlotlyLineplot level-0 mass-badge hover (P1-R2-LP-TAG-001)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('emits an invisible hover point per visible mass badge with full-precision mass', () => {
    // Level-0 deconvolved spectrum with two highlighted mass badges. The visible
    // label is mass.toFixed(2) but the hover must carry the full-precision mass.
    const data: AnyRecord = {
      plotData: {
        MonoMass: [150.123456, 250.654321, 999.0],
        SumIntensity: [100, 80, 5],
        peak_id: [0, 1, 2],
        highlight: [true, true, false],
        selected_gold: [false, false, false],
        mass_label: ['150.12', '250.65', ''],
      },
      _plotConfig: { mode: 'tagger', level: 'deconvolved' },
    }
    const { wrapper } = mountLineplot(TAGGER_ARGS, data)
    const vm = wrapper.vm as unknown as PlotlyLineplotVM

    expect(vm.level).toBe('deconvolved')

    // The visible mass badges (from the mass_label / annotation path).
    const visibleBoxes = vm.annotationBoxData.filter((b) => b.visible)
    expect(visibleBoxes.length).toBeGreaterThan(0)

    const hoverTraces = vm.taggerMassBadgeHoverTrace
    expect(hoverTraces).toHaveLength(1)
    const trace = hoverTraces[0]

    // Invisible markers (size 20, opacity 0), hover text only.
    expect(trace.mode).toBe('markers')
    expect(trace.hoverinfo).toBe('text')
    expect(trace.marker).toEqual({ size: 20, opacity: 0 })

    const xs = trace.x as number[]
    const texts = trace.text as string[]
    // One hover point per visible badge.
    expect(xs.length).toBe(visibleBoxes.length)
    expect(texts.length).toBe(visibleBoxes.length)

    // Each hover carries the FULL-precision mass (String(mass)), not toFixed(2).
    for (let i = 0; i < xs.length; i++) {
      expect(texts[i]).toBe(String(xs[i]))
    }
    // The full-precision masses are present (not rounded to 2 decimals).
    expect(xs).toContain(150.123456)
    expect(xs).toContain(250.654321)
    // The unhighlighted peak (999.0) must NOT get a badge hover.
    expect(xs).not.toContain(999.0)

    // The hover trace is appended to the plot traces.
    const traces = vm.traces
    const appended = traces.some(
      (t) =>
        t.hoverinfo === 'text' &&
        Array.isArray(t.text) &&
        (t.text as string[]).includes('150.123456'),
    )
    expect(appended).toBe(true)
  })

  it('emits NO mass-badge hover trace in default (non-tagger) mode', () => {
    const data: AnyRecord = {
      plotData: {
        x: [150.5, 250.5],
        y: [100, 80],
        peak_id: [0, 1],
        highlight: [true, true],
        annotation: ['b2', 'b3'],
      },
      _plotConfig: { mode: 'default' },
    }
    const defaultArgs: AnyRecord = {
      componentType: 'PlotlyLineplotUnified',
      mode: 'default',
      title: 'Annotated Spectrum',
      xLabel: 'm/z',
      yLabel: 'Intensity',
      xColumn: 'x',
      yColumn: 'y',
      highlightColumn: 'highlight',
      annotationColumn: 'annotation',
      interactivity: { peak: 'peak_id' },
    }
    const { wrapper } = mountLineplot(defaultArgs, data)
    const vm = wrapper.vm as unknown as PlotlyLineplotVM
    // Default mode: the oracle has no mass-button hover here.
    expect(vm.taggerMassBadgeHoverTrace).toEqual([])
  })
})
