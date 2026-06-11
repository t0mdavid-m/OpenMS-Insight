/**
 * Tests for the selection store's idempotence guard in updateSelection().
 *
 * Regression guard for the table-sort infinite loop: updateSelection MUST NOT
 * bump the counters when called with a value deep-equal to the current one.
 * Otherwise App.vue's counter watcher re-fires setComponentValue on every render
 * (the echo), which ping-pongs setComponentValue <-> st.rerun forever and hangs
 * the app on a column sort. This mirrors Python's StateManager.set_selection,
 * which is a no-op on an unchanged value.
 */

import { beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

import { useSelectionStore } from '../selection'

describe('selection store updateSelection idempotence', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('does not bump counters when the pagination value is unchanged (deep-equal)', () => {
    const store = useSelectionStore()
    const pagination = {
      page: 1,
      page_size: 100,
      sort_column: 'Score',
      sort_dir: 'desc',
    }

    store.updateSelection('table_page', pagination)
    const paginationCounter = store.pagination_counter
    const legacyCounter = store.counter

    // Re-set a DEEP-EQUAL value (new object, identical contents): must be a no-op.
    store.updateSelection('table_page', { ...pagination })

    expect(store.pagination_counter).toBe(paginationCounter)
    expect(store.counter).toBe(legacyCounter)
  })

  it('bumps the pagination counter when the sort actually changes', () => {
    const store = useSelectionStore()
    store.updateSelection('table_page', {
      page: 1,
      sort_column: 'Score',
      sort_dir: 'desc',
    })
    const before = store.pagination_counter ?? 0

    // Toggle sort direction -> real change -> must bump.
    store.updateSelection('table_page', {
      page: 1,
      sort_column: 'Score',
      sort_dir: 'asc',
    })

    expect(store.pagination_counter ?? 0).toBeGreaterThan(before)
  })

  it('is a no-op for an unchanged non-pagination selection but bumps on change', () => {
    const store = useSelectionStore()

    store.updateSelection('protein', 1)
    const before = store.selection_counter ?? 0

    // Same value -> no counter bump.
    store.updateSelection('protein', 1)
    expect(store.selection_counter ?? 0).toBe(before)

    // New value -> bump.
    store.updateSelection('protein', 2)
    expect(store.selection_counter ?? 0).toBeGreaterThan(before)
  })
})
