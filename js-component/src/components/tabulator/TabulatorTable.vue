<template>
  <div style="padding: 8px; width: 98%">
    <div class="d-flex">
      <div style="width: 100%; display: grid; grid-template-columns: 1fr 1fr 1fr">
        <div class="d-flex justify-start" style="grid-column: 1 / span 1">
          <div style="position: relative; display: inline-block">
            <v-btn variant="text" size="small" icon="mdi-download" @click="downloadTable" />
            <v-btn variant="text" size="small" icon="mdi-filter" @click="openFilterDialog" />
            <div v-if="activeFilterCount > 0" class="filter-badge">
              {{ activeFilterCount }}
            </div>
          </div>
          <v-btn
            v-if="args.goToFields && args.goToFields.length > 0"
            variant="text"
            size="small"
            icon="mdi-arrow-right-bold"
            @click="toggleGoTo"
            color="default"
          />
        </div>
        <div class="d-flex justify-center" style="grid-column: 2 / span 1">
          <h4>{{ args.title ?? '' }}</h4>
        </div>
        <div class="d-flex justify-end" style="grid-column: 3 / span 1"></div>
      </div>
    </div>

    <!-- Go To interface -->
    <div
      v-if="args.goToFields && args.goToFields.length > 0 && showGoTo"
      ref="goToInterface"
      style="
        padding: 8px;
        margin-bottom: 8px;
        background-color: #f5f5f5;
        border-radius: 4px;
        border: 1px solid #e0e0e0;
      "
    >
      <div style="display: flex; gap: 8px; align-items: center; height: 32px">
        <span style="font-size: 14px; font-weight: 500; color: #333">Go to:</span>
        <select
          v-model="selectedGoToField"
          style="
            font-size: 12px;
            padding: 4px 8px;
            border: 1px solid #ccc;
            border-radius: 3px;
            background: white;
            height: 24px;
          "
        >
          <option v-for="field in args.goToFields" :key="field" :value="field">
            {{ getGoToFieldLabel(field) }}
          </option>
        </select>
        <input
          v-model="goToInputValue"
          @keyup.enter="performGoTo"
          :placeholder="getGoToPlaceholder()"
          style="
            width: 200px;
            font-size: 12px;
            padding: 4px 8px;
            border: 1px solid #ccc;
            border-radius: 3px;
            height: 24px;
          "
        />
        <button
          @click="performGoTo"
          :disabled="!goToInputValue.trim()"
          style="
            font-size: 12px;
            padding: 4px 12px;
            border: 1px solid #ccc;
            border-radius: 3px;
            cursor: pointer;
            height: 24px;
          "
          :style="{
            opacity: !goToInputValue.trim() ? 0.5 : 1,
            cursor: !goToInputValue.trim() ? 'not-allowed' : 'pointer',
          }"
        >
          Go
        </button>
      </div>
    </div>

    <div :id="id" :class="tableClasses"></div>
  </div>
</template>

<script lang="ts">
import { defineComponent, type PropType } from 'vue'
import { TabulatorFull as Tabulator, type ColumnDefinition, type Options } from 'tabulator-tables'
import { useStreamlitDataStore } from '@/stores/streamlit-data'
import { useSelectionStore } from '@/stores/selection'
import type { TableComponentArgs } from '@/types/component'

export default defineComponent({
  name: 'TabulatorTable',
  props: {
    args: {
      type: Object as PropType<TableComponentArgs>,
      required: true,
    },
    index: {
      type: Number,
      required: true,
    },
  },
  emits: ['rowSelected'],
  setup() {
    const streamlitDataStore = useStreamlitDataStore()
    const selectionStore = useSelectionStore()
    return { streamlitDataStore, selectionStore }
  },
  data() {
    return {
      tabulator: undefined as Tabulator | undefined,
      selectedColumns: [] as string[],
      filterValues: {} as Record<
        string,
        {
          categorical?: string[]
          numeric?: { min: number; max: number }
          text?: string
        }
      >,
      filterTypes: {} as Record<string, 'categorical' | 'numeric' | 'text'>,
      columnAnalysis: {} as Record<
        string,
        {
          uniqueValues: (string | number)[]
          minValue?: number
          maxValue?: number
          dataType: 'categorical' | 'numeric' | 'text'
        }
      >,
      teleportDialog: false,
      teleportBackdrop: null as HTMLElement | null,
      teleportContainer: null as HTMLElement | null,
      parentDocument: null as Document | null,
      showGoTo: false,
      selectedGoToField: '',
      goToInputValue: '',
    }
  },
  computed: {
    id(): string {
      return `table-${this.index}`
    },
    tableClasses(): Record<string, boolean> {
      return {
        'table-dark': this.streamlitDataStore.theme?.base === 'dark',
        'table-light': this.streamlitDataStore.theme?.base === 'light',
        'table-bordered': true,
        'table-sm': true,
      }
    },
    tableData(): Record<string, unknown>[] {
      const data = this.streamlitDataStore.allDataForDrawing?.tableData
      return Array.isArray(data) ? data : []
    },
    columnNames(): { field: string; title: string }[] {
      return (this.args.columnDefinitions || [])
        .map((col) => ({
          field: col.field || '',
          title: (col.title as string) || col.field || '',
        }))
        .filter((col) => col.field !== '')
    },
    activeFilterCount(): number {
      let count = 0
      for (const columnField of this.selectedColumns) {
        const filterValue = this.filterValues[columnField]
        if (!filterValue) continue

        const filterType = this.filterTypes[columnField]
        let hasActiveFilter = false

        switch (filterType) {
          case 'categorical':
            hasActiveFilter = !!(filterValue.categorical && filterValue.categorical.length > 0)
            break
          case 'numeric':
            if (filterValue.numeric) {
              const dataMin = this.getMinValue(columnField)
              const dataMax = this.getMaxValue(columnField)
              hasActiveFilter =
                filterValue.numeric.min !== dataMin || filterValue.numeric.max !== dataMax
            }
            break
          case 'text':
            hasActiveFilter = !!(filterValue.text && filterValue.text.trim() !== '')
            break
        }

        if (hasActiveFilter) count++
      }
      return count
    },
    preparedTableData(): Record<string, unknown>[] {
      const indexField = this.args.tableIndexField || 'id'
      const columns = [
        ...(this.args.columnDefinitions || []).map((col) => col.field),
        indexField,
      ]

      if (this.tableData.length > 0) {
        const result: Record<string, unknown>[] = []
        this.tableData.forEach((row, index) => {
          const filteredRow: Record<string, unknown> = {}
          columns.forEach((column) => {
            if (column !== undefined) {
              filteredRow[column] = row[column]
            }
          })
          if (this.tableData[0][indexField] === undefined) {
            result.push({ ...filteredRow, [indexField]: index })
          } else {
            result.push({ ...filteredRow })
          }
        })
        return result
      }
      return this.tableData
    },
  },
  watch: {
    tableData() {
      this.updateTableData()
    },
    selectedColumns: {
      handler(newColumns: string[]) {
        newColumns.forEach((columnField) => {
          this.initializeFilterValue(columnField)
        })
      },
      immediate: true,
    },
    // Watch selection store to update table selection when state changes
    'selectionStore.$state': {
      handler() {
        this.syncSelectionFromStore()
      },
      deep: true,
    },
  },
  mounted() {
    this.drawTable()
    this.initializeTeleport()
    this.initializeGoTo()
  },
  beforeUnmount() {
    this.cleanupTeleport()
  },
  methods: {
    drawTable(): void {
      const indexField = this.args.tableIndexField || 'id'
      const baseHeight = this.args.title ? 320 : 310
      const goToHeight = this.showGoTo ? 58 : 0
      const tableMaxHeight = baseHeight - goToHeight

      this.tabulator = new Tabulator(`#${this.id}`, {
        index: indexField,
        data: this.preparedTableData,
        minHeight: 50,
        maxHeight: Math.max(tableMaxHeight, 50),
        responsiveLayout: 'collapse',
        layout: this.args.tableLayoutParam || 'fitDataFill',
        selectable: 1,
        columnDefaults: {
          title: '',
          hozAlign: 'right',
        },
        columns: (this.args.columnDefinitions || []).map((col) => {
          const colDef = { ...col }
          if (colDef.headerTooltip === undefined) {
            colDef.headerTooltip = true
          }
          return colDef
        }),
        initialSort: this.args.initialSort,
      })

      this.tabulator.on('tableBuilt', () => {
        this.selectDefaultRow()
        this.applyFilters()
      })

      // Use Tabulator's rowClick event for reliable row selection handling
      this.tabulator.on('rowClick', (e: Event, row: any) => {
        this.onRowClick(row)
      })
    },

    /**
     * Update table data efficiently using Tabulator's setData() method.
     * This preserves table state (filters, scroll position) instead of recreating the table.
     */
    updateTableData(): void {
      if (!this.tabulator) {
        // First render - create the table
        this.drawTable()
        return
      }

      // Use Tabulator's setData for efficient updates
      // This preserves filters, sorting, and other table state
      this.tabulator.setData(this.preparedTableData)

      // Clear column analysis cache since data changed
      this.columnAnalysis = {}

      // Re-sync selection from store after data update
      this.$nextTick(() => {
        this.syncSelectionFromStore()
      })
    },

    syncSelectionFromStore(): void {
      // Sync table selection with selection store
      if (!this.tabulator) return

      const interactivity = this.args.interactivity || {}

      for (const [identifier, column] of Object.entries(interactivity)) {
        const selectedValue = this.selectionStore.$state[identifier]
        if (selectedValue !== undefined && selectedValue !== null) {
          // Check if the currently selected row already matches
          const currentlySelected = this.tabulator.getSelectedRows()[0]
          if (currentlySelected) {
            const currentData = currentlySelected.getData()
            if (currentData[column as string] === selectedValue) {
              // Already selected the correct row
              return
            }
          }

          // Find and select the row with this value
          const rowIndex = this.preparedTableData.findIndex(
            (row) => row[column as string] === selectedValue
          )
          if (rowIndex >= 0) {
            const indexField = this.args.tableIndexField || 'id'
            const rowId = this.preparedTableData[rowIndex][indexField]
            const row = this.tabulator.getRow(rowId)
            if (row) {
              this.tabulator.deselectRow()
              row.select()
            }
          }
          break
        }
      }
    },

    selectDefaultRow(): void {
      // First, try to select based on current selection state
      const interactivity = this.args.interactivity || {}
      let selectedFromState = false

      // Check if we have a selection in the store that matches our interactivity
      for (const [identifier, column] of Object.entries(interactivity)) {
        const selectedValue = this.selectionStore.$state[identifier]
        if (selectedValue !== undefined && selectedValue !== null) {
          // Find the row with this value in the column
          const rowIndex = this.preparedTableData.findIndex(
            (row) => row[column as string] === selectedValue
          )
          if (rowIndex >= 0) {
            const indexField = this.args.tableIndexField || 'id'
            const rowId = this.preparedTableData[rowIndex][indexField]
            const row = this.tabulator?.getRow(rowId)
            if (row) {
              row.select()
              this.tabulator?.scrollToRow(rowId, 'center', false)
              selectedFromState = true
              break
            }
          }
        }
      }

      // If no selection from state, use default row
      if (!selectedFromState) {
        const defaultRow = this.args.defaultRow ?? 0
        if (defaultRow >= 0) {
          const visibleRows = this.tabulator?.getRows('active')
          if (visibleRows && visibleRows.length > 0 && defaultRow < visibleRows.length) {
            visibleRows[defaultRow].select()
            this.onTableClick()
          }
        }
      }
    },

    onRowClick(row: any): void {
      // Get the row data directly from Tabulator's row object
      const rowData = row.getData()
      const rowIndex = row.getIndex()

      this.$emit('rowSelected', rowIndex)

      // Update selection store using the interactivity mapping
      const interactivity = this.args.interactivity || {}

      if (rowData) {
        for (const [identifier, column] of Object.entries(interactivity)) {
          const value = rowData[column as string]
          this.selectionStore.updateSelection(identifier, value)
        }
      }
    },

    onTableClick(): void {
      // Legacy method - now handled by onRowClick via Tabulator's rowClick event
      const selectedRow = this.tabulator?.getSelectedRows()[0]?.getIndex()
      if (selectedRow !== undefined) {
        const rowData = this.preparedTableData.find(
          (row) => row[this.args.tableIndexField || 'id'] === selectedRow
        )
        if (rowData) {
          const interactivity = this.args.interactivity || {}
          for (const [identifier, column] of Object.entries(interactivity)) {
            const value = rowData[column as string]
            this.selectionStore.updateSelection(identifier, value)
          }
        }
      }
    },

    downloadTable(): void {
      if (this.tabulator) {
        this.tabulator.download('csv', `${this.args.title || 'table'}.csv`)
      }
    },

    // Filter methods
    openFilterDialog(): void {
      if (this.canUseTeleport()) {
        this.openTeleportDialog()
      }
    },

    toggleColumnSelection(columnField: string): void {
      const index = this.selectedColumns.indexOf(columnField)
      if (index > -1) {
        this.selectedColumns.splice(index, 1)
        this.cleanupFilterForColumn(columnField)
      } else {
        this.selectedColumns.push(columnField)
        this.$nextTick(() => {
          this.initializeFilterValue(columnField)
        })
      }
    },

    analyzeColumn(
      columnField: string
    ): {
      uniqueValues: (string | number)[]
      minValue?: number
      maxValue?: number
      dataType: 'categorical' | 'numeric' | 'text'
    } {
      if (this.columnAnalysis[columnField]) {
        return this.columnAnalysis[columnField]
      }

      const column = (this.args.columnDefinitions || []).find((col) => col.field === columnField)
      const values = this.preparedTableData
        .map((row) => row[columnField])
        .filter((v) => v != null && v !== '')

      const uniqueValues = [...new Set(values)]
      const sorter = column?.sorter

      let dataType: 'categorical' | 'numeric' | 'text'
      let minValue: number | undefined
      let maxValue: number | undefined

      if (sorter === 'number') {
        const numericValues = values.filter(
          (v) => typeof v === 'number' || !isNaN(Number(v))
        )
        if (numericValues.length > 0) {
          const numbers = numericValues.map((v) => Number(v))
          minValue = Math.min(...numbers)
          maxValue = Math.max(...numbers)
          dataType = uniqueValues.length <= 10 ? 'categorical' : 'numeric'
        } else {
          dataType = 'text'
        }
      } else {
        dataType = uniqueValues.length <= 50 ? 'categorical' : 'text'
      }

      const analysis = {
        uniqueValues: uniqueValues.slice(0, 100).map((v) =>
          typeof v === 'string' || typeof v === 'number' ? v : String(v)
        ) as (string | number)[],
        minValue,
        maxValue,
        dataType,
      }

      this.columnAnalysis[columnField] = analysis
      this.filterTypes[columnField] = dataType

      return analysis
    },

    getFilterType(columnField: string): 'categorical' | 'numeric' | 'text' {
      if (!this.filterTypes[columnField]) {
        this.analyzeColumn(columnField)
      }
      return this.filterTypes[columnField]
    },

    getUniqueValues(columnField: string): string[] {
      const analysis = this.analyzeColumn(columnField)
      return analysis.uniqueValues.map((v) => String(v)).sort()
    },

    getMinValue(columnField: string): number {
      const analysis = this.analyzeColumn(columnField)
      return analysis.minValue ?? 0
    },

    getMaxValue(columnField: string): number {
      const analysis = this.analyzeColumn(columnField)
      return analysis.maxValue ?? 100
    },

    initializeFilterValue(columnField: string): void {
      if (!this.filterValues[columnField]) {
        const filterType = this.getFilterType(columnField)
        const newFilterValue: {
          categorical?: string[]
          numeric?: { min: number; max: number }
          text?: string
        } = {}

        switch (filterType) {
          case 'categorical':
            newFilterValue.categorical = []
            break
          case 'numeric':
            newFilterValue.numeric = {
              min: this.getMinValue(columnField),
              max: this.getMaxValue(columnField),
            }
            break
          case 'text':
            newFilterValue.text = ''
            break
        }

        this.filterValues[columnField] = newFilterValue
      }
    },

    applyFilters(): void {
      if (!this.tabulator) return

      this.tabulator.clearFilter(true)

      this.selectedColumns.forEach((columnField) => {
        const filterValue = this.filterValues[columnField]
        const filterType = this.filterTypes[columnField]

        if (!filterValue) return

        switch (filterType) {
          case 'categorical':
            if (filterValue.categorical?.length) {
              const column = (this.args.columnDefinitions || []).find(
                (col) => col.field === columnField
              )
              const isNumericColumn = column?.sorter === 'number'

              const filterValues = isNumericColumn
                ? filterValue.categorical.map((v) => {
                    const num = Number(v)
                    return isNaN(num) ? v : num
                  })
                : filterValue.categorical

              this.tabulator?.addFilter(columnField, 'in', filterValues)
            }
            break
          case 'numeric':
            if (filterValue.numeric) {
              this.tabulator?.addFilter(columnField, '>=', filterValue.numeric.min)
              this.tabulator?.addFilter(columnField, '<=', filterValue.numeric.max)
            }
            break
          case 'text':
            if (filterValue.text) {
              this.tabulator?.addFilter(columnField, 'regex', filterValue.text)
            }
            break
        }
      })
    },

    cleanupFilterForColumn(columnField: string): void {
      delete this.filterValues[columnField]
      delete this.filterTypes[columnField]
      delete this.columnAnalysis[columnField]
      this.applyFilters()
    },

    // Teleport functionality for filter dialog
    canUseTeleport(): boolean {
      try {
        return !!(window.parent && window.parent.document && window.parent !== window)
      } catch {
        return false
      }
    },

    initializeTeleport(): void {
      if (this.canUseTeleport()) {
        this.parentDocument = window.parent.document
      }
    },

    openTeleportDialog(): void {
      if (!this.parentDocument || this.teleportDialog) return

      this.teleportDialog = true
      this.createTeleportBackdrop()
      this.createTeleportContainer()
      this.renderFilterDialog()
    },

    createTeleportBackdrop(): void {
      if (!this.parentDocument) return

      this.teleportBackdrop = this.parentDocument.createElement('div')
      this.teleportBackdrop.style.cssText = `
        position: fixed;
        top: 0;
        left: 0;
        width: 100vw;
        height: 100vh;
        background-color: rgba(0, 0, 0, 0.5);
        z-index: 9999;
        display: flex;
        align-items: center;
        justify-content: center;
      `

      this.teleportBackdrop.addEventListener('click', (e) => {
        if (e.target === this.teleportBackdrop) {
          this.closeTeleportDialog()
        }
      })

      this.parentDocument.body.appendChild(this.teleportBackdrop)
    },

    createTeleportContainer(): void {
      if (!this.parentDocument || !this.teleportBackdrop) return

      this.teleportContainer = this.parentDocument.createElement('div')
      this.teleportContainer.style.cssText = `
        background: white;
        border-radius: 8px;
        max-width: 90vw;
        max-height: 90vh;
        width: 800px;
        box-shadow: 0 4px 16px rgba(0, 0, 0, 0.2);
        display: flex;
        flex-direction: column;
        overflow: hidden;
      `

      this.teleportBackdrop.appendChild(this.teleportContainer)
    },

    renderFilterDialog(): void {
      if (!this.teleportContainer || !this.parentDocument) return

      // Header
      const header = this.parentDocument.createElement('div')
      header.style.cssText = `
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 16px 24px;
        border-bottom: 1px solid #e0e0e0;
        background: white;
      `

      const title = this.parentDocument.createElement('span')
      title.textContent = 'Filter Options'
      title.style.cssText = 'font-size: 20px; font-weight: 500; color: #333;'

      const closeBtn = this.parentDocument.createElement('button')
      closeBtn.innerHTML = '×'
      closeBtn.style.cssText = `
        background: none;
        border: none;
        font-size: 24px;
        cursor: pointer;
        color: #666;
        padding: 4px 8px;
        border-radius: 4px;
      `
      closeBtn.addEventListener('click', () => this.closeTeleportDialog())

      header.appendChild(title)
      header.appendChild(closeBtn)

      // Content
      const content = this.parentDocument.createElement('div')
      content.style.cssText = `
        padding: 24px;
        overflow-y: auto;
        flex: 1;
        min-height: 0;
      `

      this.renderColumnSelection(content)
      this.renderFilterControls(content)

      // Footer
      const footer = this.parentDocument.createElement('div')
      footer.style.cssText = `
        padding: 16px 24px;
        border-top: 1px solid #e0e0e0;
        display: flex;
        justify-content: flex-end;
        background: white;
      `

      const closeFooterBtn = this.parentDocument.createElement('button')
      closeFooterBtn.textContent = 'Close'
      closeFooterBtn.style.cssText = `
        background: #1976d2;
        color: white;
        border: none;
        padding: 8px 16px;
        border-radius: 4px;
        cursor: pointer;
        font-size: 14px;
      `
      closeFooterBtn.addEventListener('click', () => this.closeTeleportDialog())

      footer.appendChild(closeFooterBtn)

      this.teleportContainer.appendChild(header)
      this.teleportContainer.appendChild(content)
      this.teleportContainer.appendChild(footer)
    },

    renderColumnSelection(content: HTMLElement): void {
      if (!this.parentDocument) return

      const columnSection = this.parentDocument.createElement('div')
      columnSection.style.cssText = `
        background-color: white;
        border-radius: 4px;
        border: 1px solid #e0e0e0;
        padding: 16px;
        margin-bottom: 24px;
      `

      const columnTitle = this.parentDocument.createElement('h6')
      columnTitle.textContent = 'Select Columns:'
      columnTitle.style.cssText =
        'color: #333; margin: 0 0 12px 0; font-size: 16px; font-weight: 500;'

      const chipsContainer = this.parentDocument.createElement('div')
      chipsContainer.style.cssText = 'display: flex; flex-wrap: wrap; gap: 8px;'

      this.columnNames.forEach((column) => {
        if (!this.parentDocument) return
        const chip = this.parentDocument.createElement('div')
        const isSelected = this.selectedColumns.includes(column.field)

        chip.textContent = column.title
        chip.style.cssText = `
          padding: 6px 12px;
          border-radius: 16px;
          font-size: 14px;
          cursor: pointer;
          user-select: none;
          transition: all 0.2s;
          ${
            isSelected
              ? 'background: #1976d2; color: white; border: 1px solid #1976d2;'
              : 'background: white; color: #333; border: 1px solid #e0e0e0;'
          }
        `

        chip.addEventListener('click', () => {
          this.toggleColumnSelection(column.field)
          this.refreshTeleportDialog()
        })

        chipsContainer.appendChild(chip)
      })

      columnSection.appendChild(columnTitle)
      columnSection.appendChild(chipsContainer)
      content.appendChild(columnSection)
    },

    renderFilterControls(content: HTMLElement): void {
      if (this.selectedColumns.length === 0 || !this.parentDocument) return

      const filterSection = this.parentDocument.createElement('div')

      const filterTitle = this.parentDocument.createElement('h6')
      filterTitle.textContent = 'Filter Settings:'
      filterTitle.style.cssText =
        'color: #333; margin: 0 0 16px 0; font-size: 16px; font-weight: 500;'

      const filterContainer = this.parentDocument.createElement('div')
      filterContainer.style.cssText = `
        display: flex;
        flex-direction: column;
        gap: 16px;
        background-color: #f9f9f9;
        border-radius: 4px;
        padding: 16px;
      `

      this.columnNames.forEach((column) => {
        if (this.selectedColumns.includes(column.field)) {
          const filterItem = this.createFilterItem(column.field)
          filterContainer.appendChild(filterItem)
        }
      })

      filterSection.appendChild(filterTitle)
      filterSection.appendChild(filterContainer)
      content.appendChild(filterSection)
    },

    createFilterItem(columnField: string): HTMLElement {
      if (!this.parentDocument) {
        throw new Error('Parent document not available')
      }

      const filterItem = this.parentDocument.createElement('div')
      filterItem.style.cssText = `
        display: flex;
        flex-direction: column;
        gap: 8px;
        padding: 12px;
        background-color: white;
        border-radius: 4px;
        border: 1px solid #e0e0e0;
      `

      const label = this.parentDocument.createElement('label')
      label.style.cssText = 'font-weight: 500; font-size: 14px; color: #555;'

      const column = (this.args.columnDefinitions || []).find((col) => col.field === columnField)
      const title = (column?.title as string) || columnField
      const type = this.getFilterType(columnField)
      label.innerHTML = `${title} <span style="font-size: 12px; color: #888; font-weight: normal;">(${type})</span>`

      filterItem.appendChild(label)

      if (type === 'categorical') {
        const select = this.createCategoricalFilter(columnField)
        filterItem.appendChild(select)
      } else if (type === 'numeric') {
        const numericFilter = this.createNumericFilter(columnField)
        filterItem.appendChild(numericFilter)
      } else {
        const textFilter = this.createTextFilter(columnField)
        filterItem.appendChild(textFilter)
      }

      return filterItem
    },

    createCategoricalFilter(columnField: string): HTMLElement {
      if (!this.parentDocument) {
        throw new Error('Parent document not available')
      }

      const container = this.parentDocument.createElement('div')

      const select = this.parentDocument.createElement('select')
      select.multiple = true
      select.style.cssText = `
        width: 100%;
        padding: 8px;
        border: 1px solid #ddd;
        border-radius: 4px;
        font-size: 14px;
        min-height: 80px;
      `

      const uniqueValues = this.getUniqueValues(columnField)
      const currentValues = this.filterValues[columnField]?.categorical || []

      uniqueValues.forEach((value) => {
        if (!this.parentDocument) return
        const option = this.parentDocument.createElement('option')
        option.value = value
        option.textContent = value
        option.selected = currentValues.includes(value)
        select.appendChild(option)
      })

      select.addEventListener('change', () => {
        const selectedValues = Array.from(select.selectedOptions).map((opt) => opt.value)
        if (!this.filterValues[columnField]) {
          this.filterValues[columnField] = {}
        }
        this.filterValues[columnField].categorical = selectedValues
        this.applyFilters()
      })

      container.appendChild(select)
      return container
    },

    createNumericFilter(columnField: string): HTMLElement {
      if (!this.parentDocument) {
        throw new Error('Parent document not available')
      }

      const container = this.parentDocument.createElement('div')
      container.style.cssText = 'padding: 8px 0;'

      const minValue = Math.floor(this.getMinValue(columnField))
      const maxValue = Math.ceil(this.getMaxValue(columnField))
      const currentFilter = this.filterValues[columnField]?.numeric

      const range = maxValue - minValue
      const step = range > 1 ? 1 : 0.01

      // Values display
      const valuesDisplay = this.parentDocument.createElement('div')
      valuesDisplay.style.cssText =
        'display: flex; justify-content: space-between; margin-bottom: 8px; font-size: 14px; color: #333;'

      const minValueDisplay = this.parentDocument.createElement('span')
      minValueDisplay.textContent = String(currentFilter?.min || minValue)
      minValueDisplay.style.cssText =
        'font-weight: 500; padding: 4px 8px; background: #f0f0f0; border-radius: 4px;'

      const maxValueDisplay = this.parentDocument.createElement('span')
      maxValueDisplay.textContent = String(currentFilter?.max || maxValue)
      maxValueDisplay.style.cssText =
        'font-weight: 500; padding: 4px 8px; background: #f0f0f0; border-radius: 4px;'

      valuesDisplay.appendChild(minValueDisplay)
      valuesDisplay.appendChild(maxValueDisplay)

      // Simple min/max inputs
      const inputsContainer = this.parentDocument.createElement('div')
      inputsContainer.style.cssText = 'display: flex; gap: 8px; align-items: center;'

      const minInput = this.parentDocument.createElement('input')
      minInput.type = 'number'
      minInput.value = String(currentFilter?.min || minValue)
      minInput.min = String(minValue)
      minInput.max = String(maxValue)
      minInput.step = String(step)
      minInput.style.cssText = 'width: 100px; padding: 4px 8px; border: 1px solid #ddd; border-radius: 4px;'

      const toLabel = this.parentDocument.createElement('span')
      toLabel.textContent = 'to'

      const maxInput = this.parentDocument.createElement('input')
      maxInput.type = 'number'
      maxInput.value = String(currentFilter?.max || maxValue)
      maxInput.min = String(minValue)
      maxInput.max = String(maxValue)
      maxInput.step = String(step)
      maxInput.style.cssText = 'width: 100px; padding: 4px 8px; border: 1px solid #ddd; border-radius: 4px;'

      const updateFilter = () => {
        const minVal = parseFloat(minInput.value) || minValue
        const maxVal = parseFloat(maxInput.value) || maxValue

        if (!this.filterValues[columnField]) {
          this.filterValues[columnField] = {}
        }
        this.filterValues[columnField].numeric = { min: minVal, max: maxVal }
        minValueDisplay.textContent = String(minVal)
        maxValueDisplay.textContent = String(maxVal)
        this.applyFilters()
      }

      minInput.addEventListener('change', updateFilter)
      maxInput.addEventListener('change', updateFilter)

      inputsContainer.appendChild(minInput)
      inputsContainer.appendChild(toLabel)
      inputsContainer.appendChild(maxInput)

      container.appendChild(valuesDisplay)
      container.appendChild(inputsContainer)
      return container
    },

    createTextFilter(columnField: string): HTMLElement {
      if (!this.parentDocument) {
        throw new Error('Parent document not available')
      }

      const input = this.parentDocument.createElement('input')
      input.type = 'text'
      input.placeholder = 'Search pattern (regex supported)'
      input.value = this.filterValues[columnField]?.text || ''
      input.style.cssText = `
        width: 100%;
        padding: 8px;
        border: 1px solid #ddd;
        border-radius: 4px;
        font-size: 14px;
      `

      input.addEventListener('input', () => {
        if (!this.filterValues[columnField]) {
          this.filterValues[columnField] = {}
        }
        this.filterValues[columnField].text = input.value
        this.applyFilters()
      })

      return input
    },

    refreshTeleportDialog(): void {
      if (!this.teleportDialog || !this.teleportContainer) return
      this.teleportContainer.innerHTML = ''
      this.renderFilterDialog()
    },

    closeTeleportDialog(): void {
      this.teleportDialog = false
      this.cleanupTeleport()
    },

    cleanupTeleport(): void {
      if (this.teleportBackdrop && this.parentDocument) {
        this.parentDocument.body.removeChild(this.teleportBackdrop)
        this.teleportBackdrop = null
      }
      if (this.teleportContainer) {
        this.teleportContainer = null
      }
    },

    // Go-to functionality
    initializeGoTo(): void {
      if (this.args.goToFields && this.args.goToFields.length > 0) {
        this.selectedGoToField = this.args.goToFields[0]
      }
    },

    toggleGoTo(): void {
      this.showGoTo = !this.showGoTo
      if (this.showGoTo && this.args.goToFields && this.args.goToFields.length > 0) {
        this.selectedGoToField = this.args.goToFields[0]
      }
      this.$nextTick(() => {
        this.redrawTableWithNewHeight()
      })
    },

    redrawTableWithNewHeight(): void {
      if (!this.tabulator) return
      this.tabulator.destroy()
      this.drawTable()
    },

    findRowByValue(field: string, value: string): number {
      const searchValue = isNaN(Number(value)) ? value : Number(value)
      return this.preparedTableData.findIndex((row) => row[field] === searchValue)
    },

    performGoTo(): void {
      if (!this.goToInputValue.trim()) return

      const rowIndex = this.findRowByValue(this.selectedGoToField, this.goToInputValue.trim())

      if (rowIndex >= 0) {
        this.tabulator?.scrollToRow(rowIndex, 'top', false)
        this.tabulator?.deselectRow()
        this.tabulator?.selectRow([rowIndex])
        this.onTableClick()
        this.goToInputValue = ''
      }
    },

    getGoToFieldLabel(field: string): string {
      const column = (this.args.columnDefinitions || []).find((col) => col.field === field)
      if (column?.title) {
        return column.title as string
      }
      return field
    },

    getGoToPlaceholder(): string {
      const fieldLabel = this.getGoToFieldLabel(this.selectedGoToField)
      return `Enter ${fieldLabel.toLowerCase()}...`
    },
  },
})
</script>

<style>
@import 'tabulator-tables/dist/css/tabulator_bootstrap4.min.css';

.tabulator-col-title,
.tabulator-cell {
  font-size: 14px;
}

.filter-badge {
  position: absolute;
  top: -4px;
  right: -4px;
  background-color: #f44336;
  color: white;
  border-radius: 50%;
  min-width: 18px;
  height: 18px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  font-weight: 500;
  line-height: 1;
  z-index: 10;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.3);
}
</style>
