/**
 * Tests for the generic "clear dependent selections on click" mechanism
 * (FLASHApp oracle parity: TabulatorProteinTable.updateSelectedProtein clears
 * selectedAA + selectedTag + tagData on EVERY protein-row click).
 *
 * The generic capability: a Table configured with `clearsSelections: string[]`
 * resets each listed selection identifier to the store's "unset" sentinel (null)
 * whenever a row is clicked, IN ADDITION to writing its own `interactivity`
 * selections. This propagates (App.vue -> StateManager.update_from_vue, which
 * treats null as no-selection) so dependent components see no `aa`/`tag` on the
 * next render.
 *
 * These tests assert (against the selection store, exactly like the click path):
 *  - default OFF (no clearsSelections) => onRowClick writes ONLY this table's own
 *    interactivity selections; nothing else is touched;
 *  - ON (clearsSelections=["aa","tag"]) => onRowClick writes the interactivity
 *    selections AND resets aa/tag to null;
 *  - an identifier this table itself sets via interactivity is NEVER clobbered to
 *    null even if also listed in clearsSelections.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

// Mock Tabulator so mounting doesn't spin up a real table (needs a real DOM
// container + AJAX). onRowClick only uses the row object + selection store, so a
// minimal stub for deselectRow() is all that's needed here.
vi.mock('tabulator-tables', () => {
  class TabulatorFullStub {
    constructor(_selector: unknown, _options: unknown) {}
    on() {}
    off() {}
    destroy() {}
    getSelectedRows() {
      return []
    }
    getRows() {
      return []
    }
    deselectRow() {}
    selectRow() {}
    scrollToRow() {}
    redraw() {}
    setData() {}
    clearAlert() {}
  }
  return { TabulatorFull: TabulatorFullStub }
})

import TabulatorTable from '../TabulatorTable.vue'
import { useSelectionStore } from '@/stores/selection'

const COLUMN_DEFINITIONS = [
  { field: 'id', title: 'ID' },
  { field: 'scan_id', title: 'Scan' },
]

// Protein table: clicking a row sets {protein, scan} (mirrors FLASHApp's protein
// table interactivity). pagination/paginationIdentifier present => the DEFAULT
// server-side path, matching real usage.
const BASE_ARGS = {
  columnDefinitions: COLUMN_DEFINITIONS,
  tableIndexField: 'id',
  interactivity: { protein: 'id', scan: 'scan_id' },
  pagination: true,
  paginationIdentifier: 'protein_table_page',
  pageSize: 100,
}

function mountTable(args: Record<string, unknown>) {
  const pinia = createPinia()
  setActivePinia(pinia)
  const wrapper = mount(TabulatorTable, {
    props: { args },
    global: { plugins: [pinia] },
    attachTo: document.body,
  })
  return { wrapper, selectionStore: useSelectionStore() }
}

/** A fake clicked row exposing exactly what onRowClick uses. */
function makeClickedRow(data: Record<string, unknown>) {
  return {
    getData: () => data,
    getIndex: () => data.id,
    select: vi.fn(),
  }
}

describe('TabulatorTable clearsSelections (clear dependent selections on click)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('default OFF: onRowClick writes only this table\'s interactivity selections', async () => {
    const { wrapper, selectionStore } = mountTable(BASE_ARGS)
    const vm = wrapper.vm as any
    vm.tabulator = { deselectRow: vi.fn() }

    // Pre-seed a dependent selection that would normally come from another
    // component (e.g. SequenceView publishing `aa`). With clearsSelections OFF it
    // must remain untouched after a protein click.
    selectionStore.updateSelection('aa', 7)
    selectionStore.updateSelection('tag', { sequence: 'ABC' })

    vm.onRowClick(makeClickedRow({ id: 42, scan_id: 5 }))
    await wrapper.vm.$nextTick()

    // Own interactivity selections written.
    expect(selectionStore.$state.protein).toBe(42)
    expect(selectionStore.$state.scan).toBe(5)
    // Dependent selections NOT touched (default behavior unchanged).
    expect(selectionStore.$state.aa).toBe(7)
    expect(selectionStore.$state.tag).toEqual({ sequence: 'ABC' })
  })

  it('ON: onRowClick writes interactivity selections AND resets clearsSelections to null', async () => {
    const { wrapper, selectionStore } = mountTable({
      ...BASE_ARGS,
      clearsSelections: ['aa', 'tag'],
    })
    const vm = wrapper.vm as any
    vm.tabulator = { deselectRow: vi.fn() }

    // Stale dependent selections from a previous proteoform.
    selectionStore.updateSelection('aa', 7)
    selectionStore.updateSelection('tag', { sequence: 'ABC', selectedAA: 1 })

    vm.onRowClick(makeClickedRow({ id: 99, scan_id: 12 }))
    await wrapper.vm.$nextTick()

    // Own interactivity selections written to the clicked row's values.
    expect(selectionStore.$state.protein).toBe(99)
    expect(selectionStore.$state.scan).toBe(12)
    // Dependent selections RESET to the "unset" sentinel (null) so downstream
    // components treat them as no-selection.
    expect(selectionStore.$state.aa).toBeNull()
    expect(selectionStore.$state.tag).toBeNull()
  })

  it('never clobbers an identifier this table itself sets via interactivity', async () => {
    // `scan` is BOTH a clearsSelections entry AND an interactivity selection this
    // table sets. The interactivity write must win (scan must NOT be nulled).
    const { wrapper, selectionStore } = mountTable({
      ...BASE_ARGS,
      clearsSelections: ['aa', 'scan'],
    })
    const vm = wrapper.vm as any
    vm.tabulator = { deselectRow: vi.fn() }

    selectionStore.updateSelection('aa', 3)

    vm.onRowClick(makeClickedRow({ id: 1, scan_id: 88 }))
    await wrapper.vm.$nextTick()

    expect(selectionStore.$state.protein).toBe(1)
    // scan is set by interactivity and listed in clearsSelections -> interactivity wins.
    expect(selectionStore.$state.scan).toBe(88)
    // aa (a pure dependent) is reset.
    expect(selectionStore.$state.aa).toBeNull()
  })
})
