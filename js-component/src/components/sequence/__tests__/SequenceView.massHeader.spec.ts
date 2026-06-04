/**
 * Tests for the SequenceView mass-info header (3-seqview-004) and the inbound
 * mass -> fragment-table-row highlight (3-seqview-003) — FLASHApp oracle parity.
 *
 * 3-seqview-004 (mass header): the oracle `preparePrecursorInfo` proteoform branch
 *   renders `massTitle` + three fields (Theoretical / Observed / Δ Mass). Insight
 *   renders this header iff Python supplies an `observed_mass` on sequenceData
 *   (an `observed_mass_column` is configured); a non-positive observed mass shows
 *   the observed + delta fields as "-" (oracle parity). Default-OFF when absent.
 *
 * 3-seqview-003 (inbound highlight): the oracle `updateFragmentTableFromMassSelection`
 *   highlights the fragment-table row matching an EXTERNALLY-selected mass. Insight
 *   listens to a configured `massSelectionIdentifier` and resolves the selection
 *   value back through the SAME interactivity mapping the outbound path publishes,
 *   highlighting locally (no re-publish). Default-OFF when the identifier is unset.
 */

import { beforeEach, describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { createPinia, setActivePinia } from 'pinia'

import SequenceView from '../SequenceView.vue'
import { useSelectionStore } from '@/stores/selection'
import { useStreamlitDataStore } from '@/stores/streamlit-data'
import type { FragmentTableRow } from '@/types/sequence-data'

function mountView(
  args: Record<string, unknown>,
  drawing: Record<string, unknown> = {},
) {
  const pinia = createPinia()
  setActivePinia(pinia)
  const dataStore = useStreamlitDataStore()
  dataStore.dataForDrawing = {
    sequenceData: { sequence: ['P', 'E', 'P', 'T', 'I', 'D', 'E', 'R'] },
    observedMasses: [],
    peakIds: [],
    peakInteractivity: {},
    precursorCharge: 1,
    ...drawing,
  }
  const wrapper = mount(SequenceView, {
    props: { args: { height: 400, deconvolved: true, ...args }, index: 0 },
    global: { plugins: [pinia], stubs: { 'v-tooltip': true, 'v-menu': true } },
  })
  return { wrapper, selectionStore: useSelectionStore(), dataStore }
}

// --------------------------------------------------------------- 3-seqview-004
describe('SequenceView mass-info header (3-seqview-004)', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('hidden by default (no observed_mass supplied) — back-compat byte-unchanged', () => {
    const { wrapper } = mountView(
      {},
      { sequenceData: { sequence: ['P', 'E', 'P'], theoretical_mass: 1000 } },
    )
    const vm = wrapper.vm as any
    expect(vm.showMassHeader).toBe(false)
    expect(vm.massHeaderFields).toEqual([])
    expect(wrapper.find('.mass-info-header').exists()).toBe(false)
  })

  it('shown when observed_mass supplied; renders theoretical / observed / delta', () => {
    const { wrapper } = mountView(
      {},
      {
        sequenceData: {
          sequence: ['P', 'E', 'P'],
          theoretical_mass: 1000.0,
          observed_mass: 1002.5,
          mass_header_title: 'Proteoform',
        },
      },
    )
    const vm = wrapper.vm as any
    expect(vm.showMassHeader).toBe(true)
    expect(vm.massHeaderTitle).toBe('Proteoform')
    expect(vm.massHeaderFields).toEqual([
      'Theoretical mass : 1000.00',
      'Observed mass : 1002.50',
      'Δ Mass (Da) : 2.50',
    ])
    expect(wrapper.find('.mass-info-header').exists()).toBe(true)
  })

  it('non-positive observed mass renders observed + delta as "-" (oracle parity)', () => {
    const { wrapper } = mountView(
      {},
      {
        sequenceData: {
          sequence: ['P', 'E', 'P'],
          theoretical_mass: 1000.0,
          observed_mass: -1,
        },
      },
    )
    const vm = wrapper.vm as any
    expect(vm.showMassHeader).toBe(true) // observed_mass present (even if -1)
    expect(vm.massHeaderFields).toEqual([
      'Theoretical mass : 1000.00',
      'Observed mass : -',
      'Δ Mass (Da) : -',
    ])
  })

  it('uses the supplied mass_header_title (oracle massTitle)', () => {
    const { wrapper } = mountView(
      {},
      {
        sequenceData: {
          sequence: ['P'],
          theoretical_mass: 71.0,
          observed_mass: 71.0,
          mass_header_title: 'Precursor',
        },
      },
    )
    expect((wrapper.vm as any).massHeaderTitle).toBe('Precursor')
  })
})

// --------------------------------------------------------------- 3-seqview-003
describe('SequenceView inbound mass -> fragment-row highlight (3-seqview-003)', () => {
  beforeEach(() => setActivePinia(createPinia()))

  const ROWS: FragmentTableRow[] = [
    { Name: 'b1', IonType: 'b', IonNumber: 1, TheoreticalMass: '0', ObservedMass: 99.9, MassDiffDa: '0', MassDiffPpm: '0', PeakId: 101 },
    { Name: 'y2', IonType: 'y', IonNumber: 2, TheoreticalMass: '0', ObservedMass: 199.9, MassDiffDa: '0', MassDiffPpm: '0', PeakId: 202 },
  ]

  it('highlights the row whose peak interactivity value matches the inbound selection', async () => {
    const { wrapper, selectionStore } = mountView(
      { massSelectionIdentifier: 'mass', interactivity: { mass: 'mass_in_scan' } },
      { peakInteractivity: { '101': { mass_in_scan: 5 }, '202': { mass_in_scan: 9 } } },
    )
    const vm = wrapper.vm as any
    vm.fragmentTableData = [...ROWS]
    await nextTick()
    // External mass selection arrives (per-scan ordinal 9 -> peak 202 -> row 1).
    selectionStore.updateSelection('mass', 9)
    await nextTick()
    expect(vm.selectedFragmentRowIndex).toBe(1)
  })

  it('falls back to matching the raw peak id when no interactivity column is mapped', async () => {
    const { wrapper, selectionStore } = mountView(
      { massSelectionIdentifier: 'mass' }, // no interactivity mapping
    )
    const vm = wrapper.vm as any
    vm.fragmentTableData = [...ROWS]
    await nextTick()
    selectionStore.updateSelection('mass', 101) // raw peak id of row 0
    await nextTick()
    expect(vm.selectedFragmentRowIndex).toBe(0)
  })

  it('inbound highlight can also be driven directly (synchronous handler)', () => {
    // Direct-call variant (no watcher) for a deterministic, tick-free assertion.
    const { wrapper } = mountView(
      { massSelectionIdentifier: 'mass', interactivity: { mass: 'mass_in_scan' } },
      { peakInteractivity: { '101': { mass_in_scan: 5 }, '202': { mass_in_scan: 9 } } },
    )
    const vm = wrapper.vm as any
    vm.fragmentTableData = [...ROWS]
    vm.updateFragmentTableFromMassSelection(9)
    expect(vm.selectedFragmentRowIndex).toBe(1)
  })

  it('clears the highlight when the inbound selection is cleared (null)', async () => {
    const { wrapper, selectionStore } = mountView(
      { massSelectionIdentifier: 'mass', interactivity: { mass: 'mass_in_scan' } },
      { peakInteractivity: { '101': { mass_in_scan: 5 } } },
    )
    const vm = wrapper.vm as any
    vm.fragmentTableData = [...ROWS]
    await nextTick()
    selectionStore.updateSelection('mass', 5)
    await nextTick()
    expect(vm.selectedFragmentRowIndex).toBe(0)
    selectionStore.updateSelection('mass', null)
    await nextTick()
    expect(vm.selectedFragmentRowIndex).toBeUndefined()
  })

  it('no match -> highlight cleared (selection value matches no peak)', () => {
    const { wrapper } = mountView(
      { massSelectionIdentifier: 'mass', interactivity: { mass: 'mass_in_scan' } },
      { peakInteractivity: { '101': { mass_in_scan: 5 } } },
    )
    const vm = wrapper.vm as any
    vm.fragmentTableData = [...ROWS]
    vm.updateFragmentTableFromMassSelection(12345) // no peak has this ordinal
    expect(vm.selectedFragmentRowIndex).toBeUndefined()
  })

  it('re-applies the highlight after the fragment table is rebuilt (row indices shift)', async () => {
    const { wrapper, selectionStore } = mountView(
      { massSelectionIdentifier: 'mass', interactivity: { mass: 'mass_in_scan' } },
      { peakInteractivity: { '202': { mass_in_scan: 9 } } },
    )
    const vm = wrapper.vm as any
    selectionStore.updateSelection('mass', 9)
    await nextTick()
    // Table rebuilt with the matching row now at index 0.
    vm.fragmentTableData = [ROWS[1], ROWS[0]]
    await nextTick()
    // The fragmentTableData watcher re-derives the highlight from the inbound sel.
    expect(vm.selectedFragmentRowIndex).toBe(0)
  })

  // ----- default-OFF / back-compat -----
  it('default-OFF: no massSelectionIdentifier -> external mass selection does NOT highlight', async () => {
    const { wrapper, selectionStore } = mountView(
      { interactivity: { mass: 'mass_in_scan' } }, // no massSelectionIdentifier
      { peakInteractivity: { '101': { mass_in_scan: 5 } } },
    )
    const vm = wrapper.vm as any
    vm.fragmentTableData = [...ROWS]
    await nextTick()
    selectionStore.updateSelection('mass', 5)
    await nextTick()
    expect(vm.selectedFragmentRowIndex).toBeUndefined()
    // The computed listening getter is undefined (no identifier configured).
    expect(vm.selectedInboundMass).toBeUndefined()
  })

  it('does NOT re-publish the selection (local visual only; no feedback loop)', async () => {
    const { wrapper, selectionStore } = mountView(
      { massSelectionIdentifier: 'mass', interactivity: { mass: 'mass_in_scan' } },
      { peakInteractivity: { '101': { mass_in_scan: 5 } } },
    )
    const vm = wrapper.vm as any
    vm.fragmentTableData = [...ROWS]
    await nextTick()
    selectionStore.updateSelection('mass', 5)
    await nextTick()
    const counterAfterExternal = selectionStore.$state.selection_counter
    // Inbound handler ran (row highlighted) but published nothing new.
    expect(vm.selectedFragmentRowIndex).toBe(0)
    expect(selectionStore.$state.selection_counter).toBe(counterAfterExternal)
    expect(selectionStore.$state.mass).toBe(5) // unchanged by the inbound path
  })
})
