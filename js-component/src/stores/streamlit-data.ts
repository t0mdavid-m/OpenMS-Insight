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
            // Use column-based parsing for plotData (more efficient for plotting)
            // Use row-based parsing for tableData (needed for Tabulator)
            if (key === 'plotData') {
              const parsed = this.parseArrowTableToColumns(value)
              console.log(`[StreamlitDataStore] Parsed ${key} to columns:`, {
                columns: Object.keys(parsed),
                rowCount: Object.values(parsed)[0]?.length ?? 0,
              })
              this.dataForDrawing[key] = parsed
            } else {
              const parsed = this.parseArrowTable(value)
              console.log(`[StreamlitDataStore] Parsed ${key}:`, { rowCount: parsed.length })
              this.dataForDrawing[key] = parsed
            }
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
     * Used for table data where row-based access is needed.
     *
     * Optimized to use bulk column extraction via toArray() instead of
     * row-by-row random access. This is significantly faster for large tables.
     */
    parseArrowTable(arrowTable: ArrowTable): Record<string, unknown>[] {
      const numRows = arrowTable.table.numRows
      const columnNames = arrowTable.table.schema.fields.map((field) => field.name)

      // Step 1: Bulk extract all columns using toArray() - O(columns) not O(rows × columns)
      const columns: Map<string, unknown[]> = new Map()
      columnNames.forEach((columnName, colIndex) => {
        const column = arrowTable.table.getChildAt(colIndex)
        if (column) {
          // toArray() does vectorized conversion - much faster than row-by-row .get()
          const rawArray = column.toArray()
          // Convert typed array to regular array and handle BigInt
          const values: unknown[] = new Array(rawArray.length)
          for (let i = 0; i < rawArray.length; i++) {
            values[i] = this.parseArrowValue(rawArray[i])
          }
          columns.set(columnName, values)
        }
      })

      // Step 2: Transform to row format (required for Tabulator)
      const rows: Record<string, unknown>[] = new Array(numRows)
      for (let i = 0; i < numRows; i++) {
        const row: Record<string, unknown> = {}
        columnNames.forEach((columnName) => {
          const colData = columns.get(columnName)
          if (colData) {
            row[columnName] = colData[i]
          }
        })
        rows[i] = row
      }

      return rows
    },

    /**
     * Parse Arrow table to column arrays.
     * More efficient for plotting where column-based access is needed.
     * Returns: { columnName: [values...], ... }
     *
     * Optimized to use bulk toArray() extraction instead of row-by-row access.
     */
    parseArrowTableToColumns(arrowTable: ArrowTable): Record<string, unknown[]> {
      const columns: Record<string, unknown[]> = {}
      const columnNames = arrowTable.table.schema.fields.map((field) => field.name)

      columnNames.forEach((columnName, colIndex) => {
        const column = arrowTable.table.getChildAt(colIndex)

        if (column) {
          // toArray() does vectorized conversion - much faster than row-by-row .get()
          const rawArray = column.toArray()
          // Convert typed array to regular array and handle BigInt
          const values: unknown[] = new Array(rawArray.length)
          for (let i = 0; i < rawArray.length; i++) {
            values[i] = this.parseArrowValue(rawArray[i])
          }
          columns[columnName] = values
        } else {
          columns[columnName] = []
        }
      })

      return columns
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
