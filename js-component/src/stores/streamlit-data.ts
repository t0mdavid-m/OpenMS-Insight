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

      // Extract selection store data before processing
      const pythonState = newData.args.selection_store as Record<string, unknown> | undefined
      const newHash = newData.args.hash as string | undefined
      const dataChanged = newData.args.dataChanged as boolean | undefined

      // Clean up before re-assignment
      delete newData.args.selection_store
      delete newData.args.hash
      delete newData.args.dataChanged

      // IMPORTANT: Update data FIRST, before selection store
      // This ensures that when selection watchers fire, the correct data is already in place
      console.log('[StreamlitDataStore] updateRenderData:', {
        dataChanged,
        oldHash: this.hash?.substring(0, 8),
        newHash: newHash?.substring(0, 8),
        pythonStateSpectrum: pythonState?.spectrum,
        pythonStatePeak: pythonState?.peak,
      })

      // Only process data if Python says it changed (optimization to avoid re-parsing same data)
      if (dataChanged && newHash) {
        // Store render data
        this.renderData = newData

        // Parse Arrow tables to native JS objects BEFORE updating hash
        // This ensures watchers see the new data when they fire on hash change
        // IMPORTANT: Merge new data instead of replacing, so multiple components
        // can each contribute their data (tableData, heatmapData, plotData, etc.)
        const data = newData.args as StreamlitData
        Object.entries(data).forEach(([key, value]) => {
          if (value instanceof ArrowTable) {
            const parsed = this.parseArrowTable(value)
            console.log(`[StreamlitDataStore] Parsed ${key}:`, { rowCount: parsed.length })
            this.dataForDrawing[key] = parsed
          } else {
            this.dataForDrawing[key] = value
          }
        })

        // Update hash AFTER data is parsed - this triggers watchers that depend on hash
        this.hash = newHash
      } else if (!dataChanged) {
        // Data unchanged - Python only sent hash and state, keep cached data
        console.log('[StreamlitDataStore] Data unchanged, using cached data')
        // Update components config without changing data
        if (newData.args.components) {
          if (!this.renderData) {
            this.renderData = newData
          } else {
            this.renderData.args.components = newData.args.components
          }
        }
      }

      // Update selection store AFTER data is updated
      // This ensures watchers see the correct data when they fire
      if (pythonState) {
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
