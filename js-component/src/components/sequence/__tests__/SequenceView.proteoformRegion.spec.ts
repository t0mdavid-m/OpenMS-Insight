/**
 * Tests for the SequenceView proteoform-REGION fragment handling — FLASHApp
 * oracle parity (round-17 findings 3-seqview-009 + 3-seqview-010).
 *
 * The oracle (FLASHApp src/parse/tnt.py getFragmentDataFromSeq) computes the
 * theoretical fragment grid on the DETERMINED PROTEOFORM SUB-region
 * (sequence[start_index:end_index+1]) and the oracle SequenceView.vue maps each
 * fragment index back to its grid residue with an OFFSET
 * (aaIndex = theoIndex + sequence_start). It ALSO suppresses ALL prefix (a/b/c)
 * ions when the N-terminus is undetermined (sequence_start_reported < 0) and ALL
 * suffix (x/y/z) ions when the C-terminus is undetermined
 * (sequence_end_reported < 0) — SequenceView.vue:803-807.
 *
 * Insight reproduces this generically: Python slices the grid when proteoform
 * columns are configured and sends `proteoform_fragments` + `fragment_grid_offset`
 * (+ the reported `proteoform_start`/`proteoform_end`, negative => undetermined).
 * The Vue side then offsets the grid mapping and suppresses the undetermined
 * families. Non-proteoform / whole-protein callers (no flag, offset 0, both
 * termini determined) are byte-unchanged.
 *
 * These tests drive `matchFragments` directly with a sub-region grid + observed
 * masses and inspect which grid residues get marked + which fragment rows appear.
 */

import { beforeEach, describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

import SequenceView from '../SequenceView.vue'
import { useStreamlitDataStore } from '@/stores/streamlit-data'

// Theoretical neutral fragment masses for the PROTEOFORM SUB-region "PEPTIDEK"
// (== oracle getFragmentMassesWithSeq("PEPTIDEK"), charge 0). Only the few used
// below are needed; values are exact pyOpenMS / oracle masses.
const PEPTIDEK_B1 = 97.05276422329999 // P  prefix b-ion (b1)
const PEPTIDEK_B2 = 226.0953584466 // PE prefix b-ion (b2)
const PEPTIDEK_Y1 = 146.10552844660003 // K  suffix y-ion (y1)
const PEPTIDEK_Y8 = 927.4549330734999 // whole-region suffix y-ion (y8, intact)

function subRegionGridPEPTIDEK(): Record<string, number[][]> {
  // Per-position single-mass lists for b and y over the 8-residue sub-region.
  // Only b1/b2/y1/y8 carry the exact values we match on; the rest are filler
  // (unmatched against the observed masses we supply).
  const b = [
    [PEPTIDEK_B1],
    [PEPTIDEK_B2],
    [300.0],
    [400.0],
    [500.0],
    [600.0],
    [700.0],
    [800.0],
  ]
  const y = [
    [PEPTIDEK_Y1],
    [250.0],
    [350.0],
    [450.0],
    [550.0],
    [650.0],
    [750.0],
    [PEPTIDEK_Y8],
  ]
  const empty = Array.from({ length: 8 }, () => [] as number[])
  return {
    fragment_masses_a: empty.map((p) => [...p]),
    fragment_masses_b: b,
    fragment_masses_c: empty.map((p) => [...p]),
    fragment_masses_x: empty.map((p) => [...p]),
    fragment_masses_y: y,
    fragment_masses_z: empty.map((p) => [...p]),
  }
}

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
  return { wrapper, dataStore }
}

// The full protein MKPEPTIDEK (10 residues); proteoform PEPTIDEK is residues
// 2..9 (0-based) => fragment_grid_offset 2, proteoformEnd 9.
const FULL_SEQ = ['M', 'K', 'P', 'E', 'P', 'T', 'I', 'D', 'E', 'K']

describe('SequenceView proteoform-region fragment grid offset (3-seqview-009)', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('exposes proteoformFragments / fragmentGridOffset / suffix-end from sequenceData', () => {
    const { wrapper } = mountView(
      {},
      {
        sequenceData: {
          sequence: FULL_SEQ,
          proteoform_fragments: true,
          fragment_grid_offset: 2,
          proteoform_start: 2,
          proteoform_end: 9,
          ...subRegionGridPEPTIDEK(),
        },
      },
    )
    const vm = wrapper.vm as any
    expect(vm.proteoformFragments).toBe(true)
    expect(vm.fragmentGridOffset).toBe(2)
    expect(vm.fragmentGridSuffixEnd).toBe(9)
  })

  it('a PREFIX (b) ion marks grid residue ionNumber-1 + offset (oracle aaIndex = theoIndex + sequence_start)', () => {
    const { wrapper } = mountView(
      {},
      {
        sequenceData: {
          sequence: FULL_SEQ,
          proteoform_fragments: true,
          fragment_grid_offset: 2,
          proteoform_start: 2,
          proteoform_end: 9,
          ...subRegionGridPEPTIDEK(),
        },
        // observed = sub-region b1 (the oracle 97.05 @ grid 2 example) + b2.
        observedMasses: [PEPTIDEK_B1, PEPTIDEK_B2],
      },
    )
    const vm = wrapper.vm as any
    // b1 -> grid residue 0 + 2 = 2 (the proteoform's first residue P).
    expect(vm.sequenceObjects[2].bIon).toBe(true)
    // b2 -> grid residue 1 + 2 = 3.
    expect(vm.sequenceObjects[3].bIon).toBe(true)
    // The BUGGY full-sequence mapping would have marked grid 0/1 (M/K) — assert NOT.
    expect(vm.sequenceObjects[0].bIon).toBe(false)
    expect(vm.sequenceObjects[1].bIon).toBe(false)
    // The fragment table reports the ion NUMBER relative to the sub-region (b1/b2)
    // with the correct sub-region theoretical mass.
    const b1 = vm.fragmentTableData.find((r: any) => r.Name === 'b1')
    expect(b1).toBeTruthy()
    expect(Number(b1.TheoreticalMass)).toBeCloseTo(PEPTIDEK_B1, 3)
  })

  it('a SUFFIX (y) ion marks grid residue sequence_end - ionNumber + 1 (offset-aware)', () => {
    const { wrapper } = mountView(
      {},
      {
        sequenceData: {
          sequence: FULL_SEQ,
          proteoform_fragments: true,
          fragment_grid_offset: 2,
          proteoform_start: 2,
          proteoform_end: 9,
          ...subRegionGridPEPTIDEK(),
        },
        // y1 (K, sub-region ion 1) + y8 (intact proteoform).
        observedMasses: [PEPTIDEK_Y1, PEPTIDEK_Y8],
      },
    )
    const vm = wrapper.vm as any
    // y1 -> grid residue sequence_end(9) - 1 + 1 = 9 (the proteoform's last residue).
    expect(vm.sequenceObjects[9].yIon).toBe(true)
    // y8 (intact) -> grid residue 9 - 8 + 1 = 2 (the proteoform's first residue).
    expect(vm.sequenceObjects[2].yIon).toBe(true)
    const y8 = vm.fragmentTableData.find((r: any) => r.Name === 'y8')
    expect(y8).toBeTruthy()
  })

  it('round-trip: a fragment-row click maps back to the same offset grid residue', () => {
    const { wrapper } = mountView(
      {},
      {
        sequenceData: {
          sequence: FULL_SEQ,
          proteoform_fragments: true,
          fragment_grid_offset: 2,
          proteoform_start: 2,
          proteoform_end: 9,
          ...subRegionGridPEPTIDEK(),
        },
        observedMasses: [PEPTIDEK_B1],
      },
    )
    const vm = wrapper.vm as any
    vm.onFragmentTableRowClick(new Event('click'), {
      item: { IonType: 'b', IonNumber: 1 },
    } as any)
    // b1 click highlights grid residue 2 (offset), not 0.
    expect(vm.selectedAAIndex).toBe(2)
  })
})

describe('SequenceView undetermined-terminus fragment suppression (3-seqview-010)', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('undetermined N (proteoform_start < 0): NO prefix (a/b/c) ions matched/marked', () => {
    const { wrapper } = mountView(
      {},
      {
        sequenceData: {
          sequence: FULL_SEQ,
          proteoform_fragments: true,
          fragment_grid_offset: 0, // clamped start
          proteoform_start: -1, // UNDETERMINED N
          proteoform_end: 9,
          ...subRegionGridPEPTIDEK(),
        },
        // Supply BOTH a prefix (b1) and a suffix (y1) observed mass.
        observedMasses: [PEPTIDEK_B1, PEPTIDEK_Y1],
      },
    )
    const vm = wrapper.vm as any
    // Prefix ions suppressed -> no b row, no b marker anywhere.
    expect(vm.fragmentTableData.some((r: any) => r.IonType.startsWith('b'))).toBe(false)
    expect(vm.sequenceObjects.some((o: any) => o.bIon)).toBe(false)
    // Suffix ions still matched (C-terminus determined).
    expect(vm.fragmentTableData.some((r: any) => r.Name === 'y1')).toBe(true)
  })

  it('undetermined C (proteoform_end < 0): NO suffix (x/y/z) ions matched/marked', () => {
    const { wrapper } = mountView(
      {},
      {
        sequenceData: {
          sequence: FULL_SEQ,
          proteoform_fragments: true,
          fragment_grid_offset: 2,
          proteoform_start: 2,
          proteoform_end: -1, // UNDETERMINED C
          ...subRegionGridPEPTIDEK(),
        },
        observedMasses: [PEPTIDEK_B1, PEPTIDEK_Y1],
      },
    )
    const vm = wrapper.vm as any
    // Suffix ions suppressed -> no y row, no y/x/z markers.
    expect(vm.fragmentTableData.some((r: any) => r.IonType.startsWith('y'))).toBe(false)
    expect(vm.sequenceObjects.some((o: any) => o.yIon || o.xIon || o.zIon)).toBe(false)
    // Prefix ions still matched (N-terminus determined).
    expect(vm.fragmentTableData.some((r: any) => r.Name === 'b1')).toBe(true)
  })
})

describe('SequenceView whole-protein / non-proteoform back-compat (byte-unchanged mapping)', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('non-proteoform (no flag): full-length grid mapping unchanged (b -> ionNumber-1, y -> L-ionNumber)', () => {
    // Full sequence PEPTIDER (8 residues), grid computed on the FULL sequence.
    const seq = ['P', 'E', 'P', 'T', 'I', 'D', 'E', 'R']
    const { wrapper } = mountView(
      {},
      {
        sequenceData: {
          sequence: seq,
          // NO proteoform_fragments flag -> offset 0, suffix end = L-1.
          fragment_masses_b: [
            [PEPTIDEK_B1], // P b1
            [200], [300], [400], [500], [600], [700], [800],
          ],
          fragment_masses_y: [
            [100], [200], [300], [400], [500], [600], [700],
            [PEPTIDEK_Y8],
          ],
          fragment_masses_a: Array.from({ length: 8 }, () => []),
          fragment_masses_c: Array.from({ length: 8 }, () => []),
          fragment_masses_x: Array.from({ length: 8 }, () => []),
          fragment_masses_z: Array.from({ length: 8 }, () => []),
        },
        observedMasses: [PEPTIDEK_B1, PEPTIDEK_Y8],
      },
    )
    const vm = wrapper.vm as any
    expect(vm.proteoformFragments).toBe(false)
    expect(vm.fragmentGridOffset).toBe(0)
    expect(vm.fragmentGridSuffixEnd).toBe(7) // L-1
    // b1 -> grid 0 (no offset); y8 -> grid 7 - 8 + 1 = 0 (== L - 8).
    expect(vm.sequenceObjects[0].bIon).toBe(true)
    expect(vm.sequenceObjects[0].yIon).toBe(true)
  })

  it('whole-protein proteoform (flag set, offset 0, both determined): mapping == full-length', () => {
    const seq = ['P', 'E', 'P', 'T', 'I', 'D', 'E', 'R']
    const { wrapper } = mountView(
      {},
      {
        sequenceData: {
          sequence: seq,
          proteoform_fragments: true,
          fragment_grid_offset: 0, // whole protein
          proteoform_start: 0,
          proteoform_end: 7,
          fragment_masses_b: [
            [PEPTIDEK_B1], [200], [300], [400], [500], [600], [700], [800],
          ],
          fragment_masses_y: Array.from({ length: 8 }, () => []),
          fragment_masses_a: Array.from({ length: 8 }, () => []),
          fragment_masses_c: Array.from({ length: 8 }, () => []),
          fragment_masses_x: Array.from({ length: 8 }, () => []),
          fragment_masses_z: Array.from({ length: 8 }, () => []),
        },
        observedMasses: [PEPTIDEK_B1],
      },
    )
    const vm = wrapper.vm as any
    // offset 0 -> b1 still maps to grid 0 (byte-identical to full-length).
    expect(vm.sequenceObjects[0].bIon).toBe(true)
    // Both termini determined -> no suppression.
    expect(vm.fragmentTableData.some((r: any) => r.Name === 'b1')).toBe(true)
  })
})
