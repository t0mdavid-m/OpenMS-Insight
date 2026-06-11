/**
 * Tests for the SequenceView residue-click model — FLASHApp oracle parity.
 *
 * The oracle AminoAcidCell.selectCell() does TWO INDEPENDENT things on ONE
 * residue click ("Both should be supported as is currently the case in FLASHTnT
 * Viewer."):
 *   PATH 1 (aa / sequence-tag selection): publish the residue's aa-position ONLY
 *     for residues with sequence-TAG coverage (coverage > 0) AND only while tags
 *     are shown, TOGGLING (re-click clears). Auto-clears when tags turn off.
 *   PATH 2 (mass / fragment selection): for residues with a matching FRAGMENT
 *     ion, publish that fragment's observed mass as the mass selection.
 *
 * Insight makes both paths generic + config-driven + default-OFF:
 *   - PATH 1 is the `residue_identifier` publication, coverage-gated + toggling
 *     when a `coverage_column` is configured (coverage shown); for callers WITHOUT
 *     coverage it keeps the legacy fragment-gated, non-toggling publication.
 *   - PATH 2 is the new `fragment_mass_identifier` publication (off when unset).
 *
 * These tests assert the selection-store writes for each path, plus default-OFF /
 * back-compat. They split into:
 *   (A) AminoAcidCell — which EVENT fires on a click (the gate predicates);
 *   (B) SequenceView handlers — the store writes (toggle / mass / back-compat).
 */

import { beforeEach, describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

import AminoAcidCell from '../AminoAcidCell.vue'
import SequenceView from '../SequenceView.vue'
import { useSelectionStore } from '@/stores/selection'
import { useStreamlitDataStore } from '@/stores/streamlit-data'
import type { SequenceObject, FragmentTableRow } from '@/types/sequence-data'

function makeSeqObj(overrides: Partial<SequenceObject> = {}): SequenceObject {
  return {
    aminoAcid: 'A',
    coverage: undefined,
    aIon: false,
    bIon: false,
    cIon: false,
    xIon: false,
    yIon: false,
    zIon: false,
    extraTypes: [],
    ...overrides,
  }
}

// --------------------------------------------------------------------------- A
describe('AminoAcidCell.selectCell — two independent paths (oracle parity)', () => {
  beforeEach(() => setActivePinia(createPinia()))

  function mountCell(props: Record<string, unknown>) {
    return mount(AminoAcidCell, {
      props: { index: 3, sequenceLength: 10, ...props },
      global: { stubs: { 'v-tooltip': true, 'v-menu': true } },
    })
  }

  it('PATH 1 fires (tagSelected) for a tag-covered residue while tags shown; PATH 2 does NOT', () => {
    const wrapper = mountCell({
      sequenceObject: makeSeqObj({ coverage: 0.5 }),
      showTags: true,
    })
    ;(wrapper.vm as any).selectCell()
    expect(wrapper.emitted('tagSelected')).toEqual([[3]])
    expect(wrapper.emitted('selected')).toBeUndefined()
  })

  it('PATH 1 does NOT fire for a coverage===0 residue (DoesThisAAHaveSequenceTags is coverage>0)', () => {
    const wrapper = mountCell({
      sequenceObject: makeSeqObj({ coverage: 0 }),
      showTags: true,
    })
    ;(wrapper.vm as any).selectCell()
    expect(wrapper.emitted('tagSelected')).toBeUndefined()
  })

  it('PATH 1 does NOT fire when tags are hidden (showTags=false), even with coverage', () => {
    const wrapper = mountCell({
      sequenceObject: makeSeqObj({ coverage: 0.9 }),
      showTags: false,
    })
    ;(wrapper.vm as any).selectCell()
    expect(wrapper.emitted('tagSelected')).toBeUndefined()
  })

  it('PATH 2 fires (selected) for a matching-fragment residue; PATH 1 does NOT without coverage', () => {
    const wrapper = mountCell({
      sequenceObject: makeSeqObj({ bIon: true }),
      showTags: true,
    })
    ;(wrapper.vm as any).selectCell()
    expect(wrapper.emitted('selected')).toEqual([[3]])
    expect(wrapper.emitted('tagSelected')).toBeUndefined()
  })

  it('BOTH paths fire independently when a residue has coverage AND a matching fragment', () => {
    const wrapper = mountCell({
      sequenceObject: makeSeqObj({ coverage: 0.7, yIon: true }),
      showTags: true,
    })
    ;(wrapper.vm as any).selectCell()
    expect(wrapper.emitted('tagSelected')).toEqual([[3]])
    expect(wrapper.emitted('selected')).toEqual([[3]])
  })

  it('turning showTags off emits clearTagSelection (oracle showTags watch auto-clear)', async () => {
    const wrapper = mountCell({
      sequenceObject: makeSeqObj({ coverage: 0.5 }),
      showTags: true,
    })
    await wrapper.setProps({ showTags: false })
    expect(wrapper.emitted('clearTagSelection')).toBeTruthy()
  })
})

// --------------------------------------------------------------------------- B
describe('SequenceView residue-click handlers — store writes', () => {
  /**
   * Mount SequenceView with given args + seeded drawing data. We drive the
   * handlers directly (like the clearsSelections spec) and inspect the selection
   * store. sequenceObjects / fragmentTableData are set explicitly so the path
   * predicates are deterministic (independent of the fragment matcher).
   */
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

  const COVERED = (cov: number, frag: Partial<SequenceObject> = {}) =>
    makeSeqObj({ coverage: cov, ...frag })

  beforeEach(() => {})

  // ----- PATH 1: coverage-gated toggle -----
  it('PATH 1: tag-covered residue publishes its aa index to residue_identifier', () => {
    const { wrapper, selectionStore } = mountView(
      { residueIdentifier: 'aa' },
      { sequenceData: { sequence: ['P', 'E', 'P'], coverage: [1, 0.5, 0], maxCoverage: 4 } },
    )
    const vm = wrapper.vm as any
    vm.onResidueTagSelected(1)
    expect(selectionStore.$state.aa).toBe(1)
  })

  it('PATH 1: re-clicking the selected residue TOGGLES it off (clears to null)', () => {
    const { wrapper, selectionStore } = mountView(
      { residueIdentifier: 'aa' },
      { sequenceData: { sequence: ['P', 'E', 'P'], coverage: [1, 0.5, 0], maxCoverage: 4 } },
    )
    const vm = wrapper.vm as any
    vm.onResidueTagSelected(1)
    expect(selectionStore.$state.aa).toBe(1)
    vm.onResidueTagSelected(1) // re-click same residue
    expect(selectionStore.$state.aa).toBeNull()
    expect(vm.selectedAAIndex).toBeUndefined()
  })

  it('PATH 1: clicking a different residue moves the selection (no clear)', () => {
    const { wrapper, selectionStore } = mountView(
      { residueIdentifier: 'aa' },
      { sequenceData: { sequence: ['P', 'E', 'P'], coverage: [1, 0.5, 0.2], maxCoverage: 4 } },
    )
    const vm = wrapper.vm as any
    vm.onResidueTagSelected(0)
    vm.onResidueTagSelected(2)
    expect(selectionStore.$state.aa).toBe(2)
  })

  it('PATH 1: showTags-off auto-clear resets the residue selection', () => {
    const { wrapper, selectionStore } = mountView(
      { residueIdentifier: 'aa' },
      { sequenceData: { sequence: ['P', 'E', 'P'], coverage: [1, 0.5, 0], maxCoverage: 4 } },
    )
    const vm = wrapper.vm as any
    vm.onResidueTagSelected(0)
    expect(selectionStore.$state.aa).toBe(0)
    vm.onClearResidueSelection()
    expect(selectionStore.$state.aa).toBeNull()
    expect(vm.selectedAAIndex).toBeUndefined()
  })

  it('coverageShown is the showTags driver: true with maxCoverage>0, false otherwise', () => {
    const on = mountView(
      { residueIdentifier: 'aa' },
      { sequenceData: { sequence: ['P'], coverage: [1], maxCoverage: 3 } },
    )
    expect((on.wrapper.vm as any).coverageShown).toBe(true)
    const off = mountView({ residueIdentifier: 'aa' })
    expect((off.wrapper.vm as any).coverageShown).toBe(false)
  })

  // ----- PATH 2: fragment -> mass publication -----
  it('PATH 2: clicking a matching-fragment residue publishes the fragment peak mass-selection value', () => {
    const { wrapper, selectionStore } = mountView(
      { residueIdentifier: 'aa', fragmentMassIdentifier: 'mass', interactivity: { mass: 'mass_in_scan' } },
      {
        sequenceData: { sequence: ['P', 'E', 'P', 'T'], coverage: [1, 0, 0, 0], maxCoverage: 2 },
        // peak 101 is the matched fragment's peak; its per-scan mass ordinal is 5.
        peakInteractivity: { '101': { mass_in_scan: 5 } },
      },
    )
    const vm = wrapper.vm as any
    // Residue index 0 has a b1 fragment; the matched fragment row carries PeakId 101.
    vm.sequenceObjects[0] = COVERED(1, { bIon: true })
    vm.fragmentTableData = [
      { Name: 'b1', IonType: 'b', IonNumber: 1, TheoreticalMass: '0', ObservedMass: 99.9, MassDiffDa: '0', MassDiffPpm: '0', PeakId: 101 } as FragmentTableRow,
    ]
    vm.onAminoAcidSelected(0)
    // PATH 2 published the per-scan mass ordinal (oracle massIndex) to "mass".
    expect(selectionStore.$state.mass).toBe(5)
  })

  it('PATH 2 falls back to the peak id when fragment_mass_identifier has no interactivity column', () => {
    const { wrapper, selectionStore } = mountView(
      { residueIdentifier: 'aa', fragmentMassIdentifier: 'mass' }, // no interactivity mapping
      {
        sequenceData: { sequence: ['P', 'E'], coverage: [1, 0], maxCoverage: 2 },
        peakInteractivity: {},
      },
    )
    const vm = wrapper.vm as any
    vm.sequenceObjects[0] = COVERED(1, { bIon: true })
    vm.fragmentTableData = [
      { Name: 'b1', IonType: 'b', IonNumber: 1, TheoreticalMass: '0', ObservedMass: 99.9, MassDiffDa: '0', MassDiffPpm: '0', PeakId: 777 } as FragmentTableRow,
    ]
    vm.onAminoAcidSelected(0)
    expect(selectionStore.$state.mass).toBe(777)
  })

  it('PATH 2 OFF (no fragment_mass_identifier): a fragment residue click publishes NO mass selection', () => {
    const { wrapper, selectionStore } = mountView(
      { residueIdentifier: 'aa', interactivity: { mass: 'mass_in_scan' } },
      {
        sequenceData: { sequence: ['P', 'E'], coverage: [1, 0], maxCoverage: 2 },
        peakInteractivity: { '101': { mass_in_scan: 5 } },
      },
    )
    const vm = wrapper.vm as any
    vm.sequenceObjects[0] = COVERED(1, { bIon: true })
    vm.fragmentTableData = [
      { Name: 'b1', IonType: 'b', IonNumber: 1, TheoreticalMass: '0', ObservedMass: 99.9, MassDiffDa: '0', MassDiffPpm: '0', PeakId: 101 } as FragmentTableRow,
    ]
    vm.onAminoAcidSelected(0)
    expect(selectionStore.$state.mass).toBeUndefined()
  })

  it('PATH 1 + PATH 2 fire INDEPENDENTLY on a residue that has both coverage and a fragment', () => {
    const { wrapper, selectionStore } = mountView(
      { residueIdentifier: 'aa', fragmentMassIdentifier: 'mass', interactivity: { mass: 'mass_in_scan' } },
      {
        sequenceData: { sequence: ['P', 'E'], coverage: [1, 0], maxCoverage: 2 },
        peakInteractivity: { '101': { mass_in_scan: 9 } },
      },
    )
    const vm = wrapper.vm as any
    vm.sequenceObjects[0] = COVERED(1, { bIon: true })
    vm.fragmentTableData = [
      { Name: 'b1', IonType: 'b', IonNumber: 1, TheoreticalMass: '0', ObservedMass: 99.9, MassDiffDa: '0', MassDiffPpm: '0', PeakId: 101 } as FragmentTableRow,
    ]
    // Both emits happen on one click; simulate the two handlers the cell triggers.
    vm.onResidueTagSelected(0)
    vm.onAminoAcidSelected(0)
    expect(selectionStore.$state.aa).toBe(0) // PATH 1
    expect(selectionStore.$state.mass).toBe(9) // PATH 2
  })

  // ----- back-compat (no coverage configured) -----
  it('back-compat: WITHOUT coverage, a fragment residue click publishes residue_identifier (legacy, non-toggle)', () => {
    const { wrapper, selectionStore } = mountView(
      { residueIdentifier: 'aa' }, // no coverage, no fragmentMassIdentifier
    )
    const vm = wrapper.vm as any
    vm.sequenceObjects[2] = makeSeqObj({ aminoAcid: 'P', bIon: true }) // no coverage
    vm.fragmentTableData = []
    vm.onAminoAcidSelected(2)
    // Legacy path: aa published as the index, highlight set, no toggle semantics.
    expect(selectionStore.$state.aa).toBe(2)
    expect(vm.selectedAAIndex).toBe(2)
    // Re-clicking the same residue does NOT clear (legacy non-toggle).
    vm.onAminoAcidSelected(2)
    expect(selectionStore.$state.aa).toBe(2)
  })

  it('back-compat: a plain SequenceView (no residue/mass identifiers) writes NOTHING on a residue click', () => {
    const { wrapper, selectionStore } = mountView({})
    const vm = wrapper.vm as any
    vm.sequenceObjects[1] = makeSeqObj({ bIon: true })
    vm.fragmentTableData = []
    const before = JSON.stringify(selectionStore.$state)
    vm.onAminoAcidSelected(1)
    // No identifiers configured -> no cross-component selection published.
    expect(selectionStore.$state.aa).toBeUndefined()
    expect(selectionStore.$state.mass).toBeUndefined()
    // Only the local highlight changed (selectedAAIndex), store selections intact.
    expect(JSON.stringify({ ...selectionStore.$state })).toBe(before)
  })
})
