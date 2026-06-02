<template>
  <div class="featureview-container">
    <div :id="tableId" class="featureview-table"></div>
    <div :id="plotId" class="featureview-plot" style="width: 90%"></div>
  </div>
</template>

<script lang="ts">
import { defineComponent, type PropType } from 'vue'
import Plotly from 'plotly.js-dist-min'
import {
  TabulatorFull as Tabulator,
  type ColumnDefinition,
  type Options,
} from 'tabulator-tables'
import { useStreamlitDataStore } from '@/stores/streamlit-data'
import type { Theme } from 'streamlit-component-lib'

/**
 * Component args sent from the Python FeatureView component.
 */
interface FeatureViewArgs {
  componentType: string
  title?: string
  columnDefinitions: { title: string; field: string }[]
  tableIndexField?: string
  defaultRow?: number
  plotTitle?: string
  lineColor?: string
  plotHeight?: number
  xAxisTitle?: string
  yAxisTitle?: string
  zAxisTitle?: string
  sentinelIntensity?: number
  selectionIdentifier?: string
}

/**
 * Split a comma-joined point string into floats.
 * Mirrors the original FLASHQuantView.vue `.split(',').map(parseFloat)`.
 * Tolerant of values already provided as arrays (ragged Arrow lists).
 */
function splitFloats(value: unknown): number[] {
  if (value === null || value === undefined) return []
  if (Array.isArray(value)) {
    return value.map((v) => Number.parseFloat(String(v)))
  }
  const s = String(value)
  if (s.trim() === '') return []
  return s.split(',').map((tok) => Number.parseFloat(tok))
}

export default defineComponent({
  name: 'PlotlyFeatureView',
  props: {
    args: {
      type: Object as PropType<FeatureViewArgs>,
      required: true,
    },
    index: {
      type: Number,
      required: true,
    },
  },
  setup() {
    const streamlitDataStore = useStreamlitDataStore()
    return { streamlitDataStore }
  },
  data() {
    return {
      tabulator: null as Tabulator | null,
      selectedFeatureGroupIndex: undefined as number | undefined,
      maximumIntensity: 0 as number,
    }
  },
  computed: {
    theme(): Theme | undefined {
      return this.streamlitDataStore.theme
    },
    tableId(): string {
      return `featureview-table-${this.index}`
    },
    plotId(): string {
      return `featureview-plot-${this.index}`
    },
    sentinel(): number {
      return this.args.sentinelIntensity ?? -1000
    },
    lineColor(): string {
      return this.args.lineColor ?? '#3366CC'
    },
    /**
     * The feature-group table rows (one per feature group), as parsed from the
     * Arrow `quant_data` payload by the streamlit-data store.
     */
    featureGroupTableData(): Record<string, unknown>[] {
      const data = this.streamlitDataStore.allDataForDrawing?.quant_data
      return (data as Record<string, unknown>[]) || []
    },
    columnDefinitions(): ColumnDefinition[] {
      return (this.args.columnDefinitions || []).map((c) => ({
        title: c.title,
        field: c.field,
      })) as ColumnDefinition[]
    },
    /**
     * 3D plot layout — title plain (NOT bold-wrapped), height 800,
     * scene axes m/z / retention time / intensity (z range starts at 0).
     */
    trace3DgraphLayout(): Partial<Plotly.Layout> {
      return {
        title: { text: this.args.plotTitle ?? 'Feature group signals' },
        paper_bgcolor: this.theme?.backgroundColor,
        plot_bgcolor: this.theme?.secondaryBackgroundColor,
        height: this.args.plotHeight ?? 800,
        font: {
          color: this.theme?.textColor,
          family: this.theme?.font,
        },
        scene: {
          xaxis: { title: { text: this.args.xAxisTitle ?? 'm/z' } },
          yaxis: { title: { text: this.args.yAxisTitle ?? 'retention time' } },
          zaxis: {
            title: { text: this.args.zAxisTitle ?? 'intensity' },
            range: [0, this.maximumIntensity],
          },
        },
        showlegend: true,
      }
    },
  },
  watch: {
    // Redraw the 3D plot whenever the selected feature group changes
    // (internal round-trip — no Python involvement).
    selectedFeatureGroupIndex() {
      this.trace3DGraph()
    },
    // Re-build the table when fresh data arrives from Python.
    'streamlitDataStore.hash'() {
      this.$nextTick(() => this.rebuildTable())
    },
  },
  mounted() {
    this.$nextTick(() => this.rebuildTable())
  },
  beforeUnmount() {
    if (this.tabulator) {
      this.tabulator.destroy()
      this.tabulator = null
    }
  },
  methods: {
    rebuildTable(): void {
      const element = document.getElementById(this.tableId)
      if (!element) return

      const options: Options = {
        data: this.featureGroupTableData,
        columns: this.columnDefinitions,
        layout: 'fitDataFill',
        selectableRows: 1,
        index: this.args.tableIndexField || 'FeatureGroupIndex',
        height: '300px',
      }

      if (this.tabulator) {
        this.tabulator.destroy()
        this.tabulator = null
      }

      this.tabulator = new Tabulator(`#${this.tableId}`, options)
      this.tabulator.on('tableBuilt', () => {
        this.tabulator?.on('rowSelected', (row) => {
          // Map the clicked row to its position in the UNSORTED underlying data
          // (featureGroupTableData), which is what drives the 3D plot. Using the
          // visible position (row.getPosition) would mis-index after the user
          // sorts the table, selecting the wrong feature group.
          const indexField = this.args.tableIndexField || 'FeatureGroupIndex'
          const rowData = row.getData()
          const arrayPos = this.featureGroupTableData.findIndex(
            (r) => r[indexField] === rowData[indexField],
          )
          if (arrayPos >= 0) {
            this.updateSelectedFeatureGroupRow(arrayPos)
          }
        })

        // Default selection: first row (defaultRow, default 0).
        const defaultRow = this.args.defaultRow ?? 0
        const rows = this.tabulator?.getRows() ?? []
        if (defaultRow >= 0 && rows.length > defaultRow) {
          rows[defaultRow].select()
        }
      })
    },

    updateSelectedFeatureGroupRow(selectedRow?: number): void {
      if (selectedRow !== undefined) {
        this.selectedFeatureGroupIndex = selectedRow
      }
    },

    /**
     * Port of `trace3DgraphData`: group the selected feature group's traces by
     * charge, split the comma-string MZs/RTs/Intensities, bracket each trace
     * with -1e3 sentinel z-values, and emit one scatter3d line trace per charge.
     * Also updates `maximumIntensity`.
     */
    trace3DgraphData(): Plotly.Data[] {
      if (this.selectedFeatureGroupIndex === undefined) return []

      const featureGroup = this.featureGroupTableData[this.selectedFeatureGroupIndex]
      if (!featureGroup) return []

      const charges = (featureGroup.Charges as number[]) || []
      if (charges.length === 0) {
        this.maximumIntensity = 0
        return []
      }

      const traceChargeSet = [...new Set(charges)] as number[]
      const traceObjects: Record<number, { mzs: number[]; rts: number[]; intys: number[] }> = {}
      traceChargeSet.forEach((value) => {
        traceObjects[value] = { mzs: [], rts: [], intys: [] }
      })

      const mzsCol = (featureGroup.MZs as unknown[]) || []
      const rtsCol = (featureGroup.RTs as unknown[]) || []
      const intysCol = (featureGroup.Intensities as unknown[]) || []

      charges.forEach((charge, index) => {
        const currentMzs = splitFloats(mzsCol[index])
        const currentRts = splitFloats(rtsCol[index])
        const currentIntys = splitFloats(intysCol[index])

        const acc = traceObjects[charge]

        // Leading sentinel (z = -1000) so the line segment starts fresh.
        acc.mzs.push(currentMzs[0])
        acc.rts.push(currentRts[0])
        acc.intys.push(this.sentinel)

        // Main push.
        acc.mzs.push(...currentMzs)
        acc.rts.push(...currentRts)
        acc.intys.push(...currentIntys)

        // Trailing sentinel (z = -1000) so the line segment closes.
        // Original .vue uses currentMzs[-1] (=== undefined in JS); only the
        // sentinel z matters for breaking the segment.
        acc.mzs.push(currentMzs[currentMzs.length - 1])
        acc.rts.push(currentRts[currentRts.length - 1])
        acc.intys.push(this.sentinel)
      })

      // maximumIntensity = max over all real intensities (sentinels are
      // negative so they never win); guard against an empty selection.
      const allIntys: number[] = []
      Object.values(traceObjects).forEach((o) => allIntys.push(...o.intys))
      const finite = allIntys.filter((v) => Number.isFinite(v) && v !== this.sentinel)
      this.maximumIntensity = finite.length > 0 ? Math.max(...finite) : 0

      const tracesForDrawing: Plotly.Data[] = []
      Object.entries(traceObjects).forEach(([charge, feature]) => {
        tracesForDrawing.push({
          x: feature.mzs,
          y: feature.rts,
          z: feature.intys,
          mode: 'lines',
          line: {
            color: this.lineColor,
          },
          type: 'scatter3d',
          name: `Charge: ${charge}`,
        })
      })
      return tracesForDrawing
    },

    async trace3DGraph(): Promise<void> {
      const element = document.getElementById(this.plotId)
      if (!element) return
      await Plotly.newPlot(this.plotId, this.trace3DgraphData(), this.trace3DgraphLayout, {
        responsive: true,
      })
    },
  },
})
</script>

<style scoped>
.featureview-container {
  padding: 16px;
}
.featureview-table {
  width: 100%;
  margin-bottom: 16px;
}
@import 'tabulator-tables/dist/css/tabulator_bootstrap4.min.css';
</style>
