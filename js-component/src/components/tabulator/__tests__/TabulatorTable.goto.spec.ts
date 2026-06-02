/**
 * Regression test for finding P1-R5-TBL-GOTO-001 (server-side go-to doesn't
 * propagate selection downstream).
 *
 * Under server-side pagination (the DEFAULT path), a "go-to" navigates to and
 * visually highlights the target row, but previously NEVER updated the
 * cross-component selection. Downstream linked components (spectrum / mass
 * detail, etc.) therefore did not update to the navigated row.
 *
 * The oracle's go-to propagates selection (performGoTo -> onSelectedRowListener
 * -> onTableClick -> emit('rowSelected') -> cross-component update), and the
 * client-side go-to branch (performGoTo client-side) already updates the
 * selection store. Only the server-side path dropped it.
 *
 * The fix makes `selectPendingTargetRow` (which the paginationState watcher
 * invokes after Python returns _target_row_index) ALSO push the target row's
 * interactivity value(s) into the selection store -- exactly like onRowClick --
 * guarded by skipNextSync so it doesn't redo the (already-applied) visual
 * selection. (Python's server-side go-to also sets this selection
 * authoritatively; this is the client-side parity half of the fix.)
 *
 * These tests assert:
 *  - selectPendingTargetRow pushes the target row's interactivity values into
 *    the selection store (not just a visual highlight);
 *  - it still performs the visual selection (deselect + select + scrollTo);
 *  - normal onRowClick selection still works (unchanged) and routes to the
 *    clicked row's values.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

// Mock Tabulator so mounting the component doesn't spin up a real table (which
// needs a real DOM container + AJAX). The stub provides just enough surface for
// drawTable()/beforeUnmount() to run without throwing. The actual go-to logic is
// driven by replacing wrapper.vm.tabulator with a controlled fake below.
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

const INTERACTIVITY = { spectrum: 'scan_id', mass: 'mass' }

const COLUMN_DEFINITIONS = [
  { field: 'id', title: 'ID' },
  { field: 'scan_id', title: 'Scan' },
  { field: 'mass', title: 'Mass' },
]

// Server-side go-to args: pagination enabled with a paginationIdentifier makes
// isServerSidePagination true, which is the DEFAULT (buggy) path.
const SERVER_SIDE_ARGS = {
  columnDefinitions: COLUMN_DEFINITIONS,
  tableIndexField: 'id',
  interactivity: INTERACTIVITY,
  pagination: true,
  paginationIdentifier: 'goto_table_page',
  pageSize: 100,
  goToFields: ['scan_id'],
}

/**
 * Build a fake Tabulator row exposing the methods selectPendingTargetRow uses.
 */
function makeFakeRow(data: Record<string, unknown>) {
  return {
    _data: data,
    selected: false,
    scrolledTo: false,
    getData() {
      return this._data
    },
    select() {
      this.selected = true
    },
    scrollTo() {
      this.scrolledTo = true
    },
  }
}

/**
 * Install a controlled fake Tabulator onto the component instance, exposing the
 * given active rows via getRows('active'). Returns the deselect spy.
 */
function installFakeTabulator(vm: any, rows: ReturnType<typeof makeFakeRow>[]) {
  const deselectRow = vi.fn()
  vm.tabulator = {
    getRows: (selector?: string) => (selector === 'active' ? rows : rows),
    deselectRow,
  }
  return deselectRow
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

describe('TabulatorTable server-side go-to selection propagation (P1-R5-TBL-GOTO-001)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('isServerSidePagination is the DEFAULT path for these args', () => {
    const { wrapper } = mountTable(SERVER_SIDE_ARGS)
    expect((wrapper.vm as any).isServerSidePagination).toBe(true)
  })

  it('selectPendingTargetRow pushes the target row interactivity values to the selection store', async () => {
    const { wrapper, selectionStore } = mountTable(SERVER_SIDE_ARGS)
    const vm = wrapper.vm as any

    // Active rows on the navigated page (as Python paged them). Target index 2
    // is the row Python resolved via _target_row_index.
    const rows = [
      makeFakeRow({ id: 200, scan_id: 20, mass: 200 }),
      makeFakeRow({ id: 201, scan_id: 21, mass: 201 }),
      makeFakeRow({ id: 202, scan_id: 22, mass: 202 }), // <- target
      makeFakeRow({ id: 203, scan_id: 23, mass: 203 }),
    ]
    const deselectRow = installFakeTabulator(vm, rows)

    // Simulate what the paginationState watcher does after Python returns the
    // navigation hint: it sets pendingTargetRowIndex then calls the method.
    vm.pendingTargetRowIndex = 2
    vm.selectPendingTargetRow()
    await wrapper.vm.$nextTick()

    // Cross-component selection MUST be updated to the TARGET row's values,
    // not just visually highlighted. This is the core of the finding.
    expect(selectionStore.$state.spectrum).toBe(22)
    expect(selectionStore.$state.mass).toBe(202)

    // Visual selection still happens (parity with prior behavior + onRowClick).
    expect(deselectRow).toHaveBeenCalled()
    expect(rows[2].selected).toBe(true)
    expect(rows[2].scrolledTo).toBe(true)
    // Other rows are not selected.
    expect(rows[0].selected).toBe(false)

    // pendingTargetRowIndex is consumed.
    expect(vm.pendingTargetRowIndex).toBeNull()
  })

  it('selectPendingTargetRow with a different target row routes to that row', async () => {
    const { wrapper, selectionStore } = mountTable(SERVER_SIDE_ARGS)
    const vm = wrapper.vm as any

    const rows = [
      makeFakeRow({ id: 300, scan_id: 30, mass: 300 }), // <- target (index 0)
      makeFakeRow({ id: 301, scan_id: 31, mass: 301 }),
    ]
    installFakeTabulator(vm, rows)

    vm.pendingTargetRowIndex = 0
    vm.selectPendingTargetRow()
    await wrapper.vm.$nextTick()

    expect(selectionStore.$state.spectrum).toBe(30)
    expect(selectionStore.$state.mass).toBe(300)
  })

  it('selectPendingTargetRow with null target is a no-op (no selection)', () => {
    const { wrapper, selectionStore } = mountTable(SERVER_SIDE_ARGS)
    const vm = wrapper.vm as any
    installFakeTabulator(vm, [makeFakeRow({ id: 1, scan_id: 1, mass: 1 })])

    vm.pendingTargetRowIndex = null
    vm.selectPendingTargetRow()

    expect(selectionStore.$state.spectrum).toBeUndefined()
    expect(selectionStore.$state.mass).toBeUndefined()
  })

  it('normal onRowClick selection still routes to the clicked row (unchanged)', async () => {
    const { wrapper, selectionStore } = mountTable(SERVER_SIDE_ARGS)
    const vm = wrapper.vm as any

    const deselectRow = vi.fn()
    vm.tabulator = { deselectRow }

    const clickedRow = {
      getData: () => ({ id: 500, scan_id: 50, mass: 500 }),
      getIndex: () => 500,
      select: vi.fn(),
    }

    vm.onRowClick(clickedRow)
    await wrapper.vm.$nextTick()

    expect(selectionStore.$state.spectrum).toBe(50)
    expect(selectionStore.$state.mass).toBe(500)
    expect(clickedRow.select).toHaveBeenCalled()
  })
})
