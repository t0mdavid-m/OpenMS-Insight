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

  getters: {
    /**
     * Get selection value for an identifier.
     */
    getSelection:
      (state) =>
      (identifier: string): unknown => {
        return state[identifier]
      },

    /**
     * Get all current selections as a plain object.
     */
    getAllSelections: (state): Record<string, unknown> => {
      const result: Record<string, unknown> = {}
      for (const key in state) {
        if (key !== 'id' && key !== 'counter') {
          result[key] = state[key]
        }
      }
      return result
    },
  },

  actions: {
    /**
     * Update a selection value.
     *
     * @param identifier - The identifier name (e.g., 'spectrum', 'mass')
     * @param value - The selected value
     */
    updateSelection(identifier: string, value: unknown) {
      this.$patch((state) => {
        state[identifier] = value
        // Increment counter for change detection
        state.counter = (state.counter || 0) + 1
      })
    },

    /**
     * Clear a selection.
     */
    clearSelection(identifier: string) {
      this.$patch((state) => {
        state[identifier] = undefined
        state.counter = (state.counter || 0) + 1
      })
    },

    /**
     * Clear all selections.
     */
    clearAllSelections() {
      this.$patch((state) => {
        for (const key in state) {
          if (key !== 'id' && key !== 'counter') {
            state[key] = undefined
          }
        }
        state.counter = (state.counter || 0) + 1
      })
    },
  },
})
