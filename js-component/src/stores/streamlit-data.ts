/**
 * Store for Streamlit render data.
 *
 * Handles receiving data from Python, parsing Arrow tables, and storing
 * component configuration and data.
 */

import { defineStore } from 'pinia'
import type { RenderData, Theme } from 'streamlit-component-lib'
import { ArrowTable } from 'streamlit-component-lib'
import { Vector } from 'apache-arrow'
import { useSelectionStore } from '@/stores/selection'
import type { ComponentLayout, StreamlitData } from '@/types/component'

export const useStreamlitDataStore = defineStore('streamlit-data', {
  state: () => ({
    renderData: null as RenderData | null,
    dataForDrawing: {} as Record<string, unknown>,
    hash: '' as string,
  }),

  getters: {
    args: (state): StreamlitData | undefined => state.renderData?.args,

    components(): ComponentLayout[][] | undefined {
      return this.args?.components
    },

    allDataForDrawing: (state) => state.dataForDrawing,

    theme: (state): Theme | undefined => state.renderData?.theme,
  },

  actions: {
    updateRenderData(newData: RenderData) {
      const selectionStore = useSelectionStore()

      // Update selection store from Python state with counter-based conflict resolution
      if (newData.args.selection_store) {
        const pythonState = newData.args.selection_store as Record<string, unknown>
        const pythonCounter = (pythonState.counter as number) || 0
        const vueCounter = (selectionStore.$state.counter as number) || 0

        selectionStore.$patch((state) => {
          // Clear state if different session
          if (pythonState.id !== state.id) {
            for (const key in state) {
              (state as Record<string, unknown>)[key] = undefined
            }
            Object.assign(state, pythonState)
          } else if (pythonCounter >= vueCounter) {
            // Only accept Python's state if it's at least as recent as ours
            Object.assign(state, pythonState)
          } else {
            // Vue has newer state, only accept new keys from Python
            for (const key in pythonState) {
              if (!(key in state) || state[key] === undefined) {
                (state as Record<string, unknown>)[key] = pythonState[key]
              }
            }
          }
        })
      }

      // Skip re-processing if data hash hasn't changed
      if (this.hash === newData.args.hash) {
        return
      }
      this.hash = newData.args.hash

      // Clean up before re-assignment
      delete newData.args.selection_store
      delete newData.args.hash

      // Reset data
      this.dataForDrawing = {}
      this.renderData = newData

      // Parse Arrow tables to native JS objects
      const data = newData.args as StreamlitData
      Object.entries(data).forEach(([key, value]) => {
        if (value instanceof ArrowTable) {
          this.dataForDrawing[key] = this.parseArrowTable(value)
        } else {
          this.dataForDrawing[key] = value
        }
      })
    },

    /**
     * Parse Arrow table to array of row objects.
     */
    parseArrowTable(arrowTable: ArrowTable): Record<string, unknown>[] {
      const rows: Record<string, unknown>[] = []
      const columnNames = arrowTable.table.schema.fields.map((field) => field.name)

      for (let i = 0; i < arrowTable.table.numRows; i++) {
        const row: Record<string, unknown> = {}
        columnNames.forEach((columnName, colIndex) => {
          const rawValue = arrowTable.table.getChildAt(colIndex)?.get(i)
          row[columnName] = this.parseArrowValue(rawValue)
        })
        rows.push(row)
      }

      return rows
    },

    /**
     * Convert Arrow value to native JS type.
     */
    parseArrowValue(value: unknown): unknown {
      // Arrow stores integers as bigint
      if (typeof value === 'bigint') {
        return Number(value)
      }
      // Arrays are stored as vectors
      if (value instanceof Vector) {
        const result: unknown[] = []
        for (let i = 0; i < value.length; i++) {
          result.push(this.parseArrowValue(value.get(i)))
        }
        return result
      }
      return value
    },
  },
})
