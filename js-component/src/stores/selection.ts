/**
 * Generic selection store for cross-component state.
 *
 * Supports any identifier-based selection using dynamic keys.
 * The counter mechanism prevents stale updates from race conditions.
 */

import { defineStore } from 'pinia'

export interface SelectionState {
  // Session identifier for resetting on new session
  id?: number

  // Counter for conflict resolution
  counter?: number

  // Dynamic selection values keyed by identifier name
  [key: string]: unknown
}

export const useSelectionStore = defineStore('selection', {
  state: (): SelectionState => ({
    id: undefined,
    counter: undefined,
  }),

  actions: {
    /**
     * Update a selection value.
     *
     * @param identifier - The identifier name (e.g., 'spectrum', 'mass')
     * @param value - The selected value
     */
    updateSelection(identifier: string, value: unknown) {
      console.log('[SelectionStore] ===== updateSelection =====', {
        timestamp: Date.now(),
        identifier,
        value,
        isPaginationRequest: typeof value === 'object' && value !== null && 'page' in (value as object),
        currentCounter: this.$state.counter,
      })
      this.$patch((state) => {
        state[identifier] = value
        // Increment counter for change detection
        state.counter = (state.counter || 0) + 1
      })
      console.log('[SelectionStore] updateSelection DONE, newCounter:', this.$state.counter)
    },
  },
})
