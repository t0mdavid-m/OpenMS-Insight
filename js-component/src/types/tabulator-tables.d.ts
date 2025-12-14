declare module 'tabulator-tables' {
  export interface ColumnDefinition {
    field?: string
    title?: string
    sorter?: string
    formatter?: string
    formatterParams?: Record<string, unknown>
    width?: number | string
    hozAlign?: 'left' | 'center' | 'right'
    headerTooltip?: boolean | string
    [key: string]: unknown
  }

  export interface Options {
    layout?: 'fitData' | 'fitDataFill' | 'fitDataStretch' | 'fitDataTable' | 'fitColumns'
    [key: string]: unknown
  }

  export interface RowComponent {
    getData(): Record<string, unknown>
    getIndex(): number | string
    getElement(): HTMLElement
    select(): void
    deselect(): void
    scrollTo(position?: string, ifVisible?: boolean): Promise<void>
    pageTo(): Promise<void>
  }

  export interface CellComponent {
    getValue(): unknown
    getField(): string
    getRow(): RowComponent
  }

  export class TabulatorFull {
    constructor(element: string | HTMLElement, options: Record<string, unknown>)
    options: Record<string, unknown>
    destroy(): void
    setData(data: unknown[]): Promise<void>
    replaceData(data: unknown[]): Promise<void>
    getData(): unknown[]
    getRows(filter?: string): RowComponent[]
    getRow(index: any): RowComponent | false
    selectRow(row?: RowComponent | number | string | RowComponent[] | any): void
    deselectRow(row?: RowComponent | number | string | any): void
    getSelectedRows(): RowComponent[]
    scrollToRow(row: any, position?: string, ifVisible?: boolean): Promise<void>
    setFilter(field: string, type: string, value: unknown): void
    addFilter(field: string, type: string, value: unknown): void
    removeFilter(field: string, type: string, value: unknown): void
    clearFilter(notifySelectors?: boolean): void
    on(event: string, callback: (...args: any[]) => void): void
    off(event: string, callback?: (...args: any[]) => void): void
    download(type: string, filename: string, options?: Record<string, unknown>): void
    setHeight(height: number | string): void
    setPageToRow(row: number | string): Promise<void>
  }

  export default TabulatorFull
}
