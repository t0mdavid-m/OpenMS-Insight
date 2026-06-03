/**
 * Tests for Plotly3D's additive, default-off enhancements used by FLASHApp's
 * FLASHQuant feature-trace 3D plot:
 *
 *  1. `seriesColumn` — within each category trace (one trace per CHARGE), the
 *     line must BREAK between consecutive distinct series (isotopes) by an
 *     inserted null/NaN gap, so isotope sub-traces do not connect with a
 *     spurious diagonal. It stays ONE trace per category (legend/color per
 *     category). The break is inserted ONLY between distinct series within the
 *     same category (never before the first series, never at category edges —
 *     those are separate traces). customdata/text stay aligned with x/y/z.
 *
 *  2. `categoryNameTemplate` — the trace legend name is the template with `{}`
 *     replaced by the category value (e.g. `'Charge: {}'` -> `'Charge: 2'`).
 *
 *  Default (neither prop set) reproduces the prior behavior exactly: one
 *  continuous polyline per category, bare category name, no nulls.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('plotly.js-dist-min', () => {
  const newPlot = vi.fn(async (idOrEl: string | HTMLElement) => {
    return typeof idOrEl === 'string' ? document.getElementById(idOrEl) : idOrEl
  })
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

type Trace = {
  name?: string
  x: Array<number | null>
  y: Array<number | null>
  z: Array<number | null>
  customdata: unknown[]
  text: string[]
  line?: { color?: string }
}

// One charge (2) with two isotope series, already sorted Python-side so each
// series is contiguous in RT order (isotope 0: rt 10,11 ; isotope 1: rt 10,11).
const ONE_CHARGE_TWO_ISOTOPES = [
  { mz: 1000.0, rt: 10.0, intensity: 500.0, charge: 2, isotope: 0 },
  { mz: 1000.1, rt: 11.0, intensity: 600.0, charge: 2, isotope: 0 },
  { mz: 1000.5, rt: 10.0, intensity: 400.0, charge: 2, isotope: 1 },
  { mz: 1000.6, rt: 11.0, intensity: 450.0, charge: 2, isotope: 1 },
]

// Two charges, each with two isotopes (contiguous), to check that the break is
// per-series WITHIN a category and that category boundaries do NOT add a null.
const TWO_CHARGES_TWO_ISOTOPES = [
  { mz: 1000.0, rt: 10.0, intensity: 500.0, charge: 2, isotope: 0 },
  { mz: 1000.1, rt: 11.0, intensity: 600.0, charge: 2, isotope: 0 },
  { mz: 1000.5, rt: 10.0, intensity: 400.0, charge: 2, isotope: 1 },
  { mz: 1000.6, rt: 11.0, intensity: 450.0, charge: 2, isotope: 1 },
  { mz: 500.0, rt: 10.0, intensity: 700.0, charge: 3, isotope: 0 },
  { mz: 500.1, rt: 11.0, intensity: 800.0, charge: 3, isotope: 0 },
  { mz: 500.5, rt: 10.0, intensity: 300.0, charge: 3, isotope: 1 },
]

function mountPlot3D(args: Record<string, unknown>, rows: unknown[]) {
  const pinia = createPinia()
  setActivePinia(pinia)
  const dataStore = useStreamlitDataStore()
  // `allDataForDrawing` is a getter over `dataForDrawing` (see store).
  dataStore.dataForDrawing = { plot3dData: rows }

  const wrapper = mount(Plotly3D, {
    props: { args, index: 0 },
    global: { plugins: [pinia] },
    attachTo: document.body,
  })
  return wrapper
}

const BASE_ARGS = {
  componentType: 'Plotly3D' as const,
  xColumn: 'mz',
  yColumn: 'rt',
  zColumn: 'intensity',
  categoryColumn: 'charge',
  traceMode: 'lines' as const,
  stem: false,
}

function getPlotData(wrapper: ReturnType<typeof mountPlot3D>): Trace[] {
  return (wrapper.vm as unknown as { plotData: Trace[] }).plotData
}

describe('Plotly3D seriesColumn sub-trace breaks (FLASHQuant)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('inserts exactly one null break between two isotope series in one charge trace', () => {
    const wrapper = mountPlot3D(
      { ...BASE_ARGS, seriesColumn: 'isotope' },
      ONE_CHARGE_TWO_ISOTOPES,
    )
    const traces = getPlotData(wrapper)

    // Still ONE trace for the single charge.
    expect(traces).toHaveLength(1)
    const t = traces[0]

    // 4 real points + 1 null gap = 5 entries on every aligned array.
    expect(t.z).toHaveLength(5)
    expect(t.x).toHaveLength(5)
    expect(t.y).toHaveLength(5)
    expect(t.customdata).toHaveLength(5)
    expect(t.text).toHaveLength(5)

    // Exactly one break, and it sits between the two series (index 2): the
    // first series' two points, then the null, then the second series' two.
    const nullIdx = t.z.findIndex((v) => v === null)
    expect(t.z.filter((v) => v === null)).toHaveLength(1)
    expect(nullIdx).toBe(2)
    expect(t.x[nullIdx]).toBeNull()
    expect(t.y[nullIdx]).toBeNull()
    expect(t.customdata[nullIdx]).toBeNull()
    expect(t.text[nullIdx]).toBe('')

    // No break before the first series and none trailing the last.
    expect(t.z[0]).not.toBeNull()
    expect(t.z[t.z.length - 1]).not.toBeNull()

    // The real points keep their (already series-contiguous) order/values, so
    // there is NO connecting segment from isotope-0's last point straight to
    // isotope-1's first point (the null sits between them instead).
    expect(t.x.filter((v) => v !== null)).toEqual([1000.0, 1000.1, 1000.5, 1000.6])
    expect(t.z.filter((v) => v !== null)).toEqual([500.0, 600.0, 400.0, 450.0])
  })

  it('breaks per-series within each category but never at category boundaries', () => {
    const wrapper = mountPlot3D(
      { ...BASE_ARGS, seriesColumn: 'isotope' },
      TWO_CHARGES_TWO_ISOTOPES,
    )
    const traces = getPlotData(wrapper)

    // One trace per charge.
    expect(traces).toHaveLength(2)
    const [c2, c3] = traces

    // charge 2: 4 points + 1 break = 5, break between the two isotopes.
    expect(c2.z).toHaveLength(5)
    expect(c2.z.filter((v) => v === null)).toHaveLength(1)
    expect(c2.z.findIndex((v) => v === null)).toBe(2)

    // charge 3: 3 points (2 + 1 isotopes) + 1 break = 4, break after the two
    // isotope-0 points. No leading null carried over from the category change.
    expect(c3.z).toHaveLength(4)
    expect(c3.z.filter((v) => v === null)).toHaveLength(1)
    expect(c3.z.findIndex((v) => v === null)).toBe(2)
    expect(c3.z[0]).not.toBeNull()
  })

  it('default (no seriesColumn) keeps one continuous polyline per category — no nulls', () => {
    const wrapper = mountPlot3D({ ...BASE_ARGS }, ONE_CHARGE_TWO_ISOTOPES)
    const traces = getPlotData(wrapper)

    expect(traces).toHaveLength(1)
    const t = traces[0]
    // 4 points, no break -> the prior (spurious-diagonal) behavior, unchanged.
    expect(t.z).toHaveLength(4)
    expect(t.z.some((v) => v === null)).toBe(false)
    expect(t.x).toEqual([1000.0, 1000.1, 1000.5, 1000.6])
  })

  it('stem mode + seriesColumn still inserts a break and does not crash', () => {
    const wrapper = mountPlot3D(
      { ...BASE_ARGS, seriesColumn: 'isotope', stem: true, stemBaseline: -100000 },
      ONE_CHARGE_TWO_ISOTOPES,
    )
    const traces = getPlotData(wrapper)
    expect(traces).toHaveLength(1)
    const t = traces[0]
    // 4 points * 3 (stem triplet) + 1 break = 13.
    expect(t.z).toHaveLength(13)
    expect(t.z.filter((v) => v === null)).toHaveLength(1)
    // The single break sits between the two series' triplet blocks (after the
    // first series' 2 triplets = 6 entries).
    expect(t.z.findIndex((v) => v === null)).toBe(6)
  })
})

describe('Plotly3D categoryNameTemplate legend label', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('templates the trace name with the category value', () => {
    const wrapper = mountPlot3D(
      { ...BASE_ARGS, seriesColumn: 'isotope', categoryNameTemplate: 'Charge: {}' },
      TWO_CHARGES_TWO_ISOTOPES,
    )
    const traces = getPlotData(wrapper)
    expect(traces.map((t) => t.name)).toEqual(['Charge: 2', 'Charge: 3'])
  })

  it('default (no template) uses the bare category value', () => {
    const wrapper = mountPlot3D({ ...BASE_ARGS }, TWO_CHARGES_TWO_ISOTOPES)
    const traces = getPlotData(wrapper)
    expect(traces.map((t) => t.name)).toEqual(['2', '3'])
  })
})
