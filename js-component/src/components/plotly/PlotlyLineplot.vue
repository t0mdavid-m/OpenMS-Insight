<template>
  <div :id="id" class="plot-container" :style="cssCustomProperties">
    <button v-if="showBackButton" class="simple-button" @click="backButton">↩</button>
  </div>
</template>

<script lang="ts">
import { defineComponent, type PropType } from 'vue'
import Plotly from 'plotly.js-dist-min'
import { Streamlit, type Theme } from 'streamlit-component-lib'
import { useStreamlitDataStore } from '@/stores/streamlit-data'
import { useSelectionStore } from '@/stores/selection'
import type { LinePlotComponentArgs, PlotData, TagWalk } from '@/types/component'

// Default styling configuration
const DEFAULT_STYLING = {
  highlightColor: '#E4572E',
  selectedColor: '#F3A712',
  unhighlightedColor: 'lightblue',
  highlightHiddenColor: '#1f77b4',
  annotationBackground: '#f8f8f8',
  // Tagger extension defaults (used only when the corresponding feature is enabled)
  secondSeriesColor: '#9ad1f0',
  signalPeakColor: '#2E86AB',
  tagHighlightColor: '#E4572E',
}

// Default config for annotation scaling
const DEFAULT_CONFIG = {
  xPosScalingFactor: 80,
  xPosScalingThreshold: 500,
  minAnnotationWidth: 40,
  // Legacy FLASHApp constants for the augmented/tag-walk views (P1):
  //   half-width = rangeWidth / legacyXPosScalingFactor (27.5),
  //   all-or-nothing hide when half-width > legacyXPosScalingThreshold (30).
  legacyXPosScalingFactor: 27.5,
  legacyXPosScalingThreshold: 30,
}

export default defineComponent({
  name: 'PlotlyLineplot',
  props: {
    args: {
      type: Object as PropType<LinePlotComponentArgs>,
      required: true,
    },
    index: {
      type: Number,
      required: true,
    },
  },
  setup() {
    const streamlitDataStore = useStreamlitDataStore()
    const selectionStore = useSelectionStore()
    return { streamlitDataStore, selectionStore }
  },
  data() {
    return {
      isInitialized: false as boolean,
      manualXRange: undefined as number[] | undefined,
      lastAutoZoomedPeakIndex: undefined as number | undefined,
      textMeasureCanvas: null as HTMLCanvasElement | null,
      // --- Augmented-view (charge drill-down) + modebar toggle state (parity) ---
      // localTitle drives the deconv ↔ m/z (charge) sub-view switch without
      // mutating the prop (FLASHApp PlotlyLineplotUnified localTitle pattern).
      localTitle: undefined as string | undefined,
      // Index (into the FIRST-series peak rows) of the deconv mass the user
      // drilled into; undefined → deconv view.
      selectedMassIndex: undefined as number | undefined,
      // Modebar toggles (FLASHApp): annotations on/off, deconvolved-peaks highlight.
      annotationsVisible: true as boolean,
      deconvolvedPeaksHighlightMode: false as boolean,
    }
  },
  computed: {
    id(): string {
      return `plot-${this.index}`
    },

    theme(): Theme | undefined {
      return this.streamlitDataStore.theme
    },

    styling() {
      return {
        ...DEFAULT_STYLING,
        ...this.args.styling,
      }
    },

    config() {
      return {
        ...DEFAULT_CONFIG,
        ...this.args.config,
      }
    },

    /**
     * Effective plot title. Defaults to the prop title but is overridden by
     * localTitle once the user drills into the charge sub-view (parity with
     * FLASHApp localTitle, which flips to 'Augmented Annotated Spectrum').
     */
    effectiveTitle(): string {
      return this.localTitle ?? this.args.title ?? ''
    },

    /**
     * True when we are in the charge-state drill-down ("Augmented Annotated
     * Spectrum") sub-view. Driven by selectedMassIndex (set on a deconv-peak
     * click that carries signal arrays).
     */
    inChargeSubView(): boolean {
      return this.selectedMassIndex !== undefined && this.hasSignalDrilldown
    },

    /**
     * Whether the per-row signal arrays needed for the charge drill-down are
     * present (FLASHApp gates the drill-down + "Show Deconvolved Peaks" on this).
     */
    hasSignalDrilldown(): boolean {
      const config = this.plotConfig
      const flag =
        (config?.hasSignalDrilldown as boolean) ?? this.args.hasSignalDrilldown ?? false
      const pd = this.plotData
      return flag && !!pd && !!pd.signal_mzs && !!pd.signal_charges
    },

    /**
     * Back button is shown only in the charge sub-view (FLASHApp showBackButton).
     */
    showBackButton(): boolean {
      return this.inChargeSubView
    },

    /**
     * Whether to draw signal-peak dot markers. Default OFF for FLASHApp parity (the
     * legacy renderer does not draw these); enabled via showSignalMarkers (P2).
     */
    showSignalMarkers(): boolean {
      const config = this.plotConfig
      return (
        (config?.showSignalMarkers as boolean) ?? this.args.showSignalMarkers ?? false
      )
    },

    /**
     * Get actual plot width from DOM.
     */
    actualPlotWidth(): number {
      const element = document.getElementById(this.id)
      if (element) {
        const rect = element.getBoundingClientRect()
        if (rect.width > 0) {
          return rect.width
        }
      }
      return 800 // default
    },

    /**
     * Get plot config from Python (sent with data, may have dynamic column names).
     * When dynamic annotations are set, _plotConfig contains updated column names.
     */
    plotConfig(): Record<string, unknown> | undefined {
      return this.streamlitDataStore.allDataForDrawing?._plotConfig as Record<string, unknown> | undefined
    },

    /**
     * Tagger extension: the selected tag's residue WALK, sent at render time as a
     * top-level `tagWalk` payload ({masses, residues}). Present only when Python
     * resolved a selected tag that carries residue letters. When absent, the plot
     * renders exactly as today (no walk, no auto-zoom) — guaranteeing no
     * regression for plain LinePlot / highlight-only tagger usage.
     */
    tagWalk(): TagWalk | undefined {
      const tw = this.streamlitDataStore.allDataForDrawing?.tagWalk as TagWalk | undefined
      if (!tw || !Array.isArray(tw.masses) || tw.masses.length === 0) {
        return undefined
      }
      return tw
    },

    /**
     * Sorted unique tag masses for the walk, ascending in x. residues[i] labels
     * the gap between walkMasses[i] and walkMasses[i+1]. The legacy tagger draws
     * the same letters regardless of mass ordering; we sort ascending so the
     * arrows always point left→right while keeping the residue alignment that
     * Python sent (residues[i] ↔ gap i in the supplied mass order).
     */
    walkMasses(): number[] {
      const tw = this.tagWalk
      if (!tw) return []
      return tw.masses.slice()
    },

    /**
     * The tag's mass span [min, max] used for auto-zoom, with 2% padding on each
     * side (mirrors FLASHApp PlotlyLineplotTagger xRange: min*0.98 .. max*1.02).
     */
    tagWalkSpan(): number[] | undefined {
      const masses = this.walkMasses
      if (masses.length === 0) return undefined
      const lo = Math.min(...masses)
      const hi = Math.max(...masses)
      if (!isFinite(lo) || !isFinite(hi)) return undefined
      // Match legacy multiplicative padding (0.98 / 1.02) around the span.
      return [lo * 0.98, hi * 1.02]
    },

    /**
     * Get plot data from Python.
     * Data arrives as column arrays: {columnName: [values...], ...}
     * We map to the expected format using xColumn/yColumn from args.
     */
    plotData(): PlotData | undefined {
      const rawData = this.streamlitDataStore.allDataForDrawing?.plotData as
        | Record<string, unknown[]>
        | undefined
      if (!rawData) return undefined

      // Get column names from args (static) or plotConfig (dynamic, may be updated at runtime)
      const config = this.plotConfig
      const xCol = (config?.xColumn as string) || this.args.xColumn || 'x'
      const yCol = (config?.yColumn as string) || this.args.yColumn || 'y'

      // Map to expected PlotData format
      const result: PlotData = {
        x_values: (rawData[xCol] as number[]) || [],
        y_values: (rawData[yCol] as number[]) || [],
      }

      // Add highlight mask if present
      // Use plotConfig column name if available (for dynamic annotations), otherwise args
      const highlightCol = (config?.highlightColumn as string) || this.args.highlightColumn
      if (highlightCol && rawData[highlightCol]) {
        result.highlight_mask = rawData[highlightCol] as boolean[]
      }

      // Add annotations if present
      const annotationCol = (config?.annotationColumn as string) || this.args.annotationColumn
      if (annotationCol && rawData[annotationCol]) {
        result.annotations = rawData[annotationCol] as string[]
      }

      // --- Tagger extension: second overlaid series ---
      const hasSecond =
        (config?.hasSecondSeries as boolean) ?? this.args.hasSecondSeries ?? false
      const x2Col = (config?.x2Column as string) || this.args.x2Column
      const y2Col = (config?.y2Column as string) || this.args.y2Column
      if (hasSecond && x2Col && y2Col && rawData[x2Col] && rawData[y2Col]) {
        result.x2_values = (rawData[x2Col] as number[]) || []
        result.y2_values = (rawData[y2Col] as number[]) || []
        const highlight2Col =
          (config?.highlight2Column as string) || this.args.highlight2Column
        if (highlight2Col && rawData[highlight2Col]) {
          result.highlight2_mask = rawData[highlight2Col] as boolean[]
        }
        const annotation2Col =
          (config?.annotation2Column as string) || this.args.annotation2Column
        if (annotation2Col && rawData[annotation2Col]) {
          result.annotations2 = rawData[annotation2Col] as string[]
        }
      }

      // --- Tagger extension: signal-peak membership flags ---
      const signalCol =
        (config?.signalPeakColumn as string) || this.args.signalPeakColumn
      if (signalCol && rawData[signalCol]) {
        result.signal_mask = rawData[signalCol] as boolean[]
      }

      // --- Charge drill-down: per-row signal arrays (lists per deconv peak) ---
      const signalMzCol =
        (config?.signalMzColumn as string) || this.args.signalMzColumn
      const signalChargeCol =
        (config?.signalChargeColumn as string) || this.args.signalChargeColumn
      const signalIntCol =
        (config?.signalIntensityColumn as string) || this.args.signalIntensityColumn
      if (signalMzCol && rawData[signalMzCol]) {
        result.signal_mzs = rawData[signalMzCol] as unknown as number[][]
      }
      if (signalChargeCol && rawData[signalChargeCol]) {
        result.signal_charges = rawData[signalChargeCol] as unknown as number[][]
      }
      if (signalIntCol && rawData[signalIntCol]) {
        result.signal_intensities = rawData[signalIntCol] as unknown as number[][]
      }

      // --- Tagger extension: tag-overlay highlight + labels ---
      const tagHighlightCol =
        (config?.tagHighlightColumn as string) || this.args.tagHighlightColumn
      if (tagHighlightCol && rawData[tagHighlightCol]) {
        result.tag_mask = rawData[tagHighlightCol] as boolean[]
      }
      const tagAnnotationCol =
        (config?.tagAnnotationColumn as string) || this.args.tagAnnotationColumn
      if (tagAnnotationCol && rawData[tagAnnotationCol]) {
        result.tag_annotations = rawData[tagAnnotationCol] as string[]
      }

      // Add interactivity column data for click handling
      // Columns are stored with their original names in rawData
      if (this.args.interactivity) {
        for (const [identifier, column] of Object.entries(this.args.interactivity)) {
          const colName = column as string
          if (rawData[colName]) {
            result[`interactivity_${colName}`] = rawData[colName]
          }
        }
      }

      return result
    },

    /**
     * Get interactivity mapping from args.
     * Maps identifier names to column names.
     */
    interactivity(): Record<string, string> {
      return this.args.interactivity || {}
    },

    /**
     * Tagger extension: effective per-peak highlight mask for the FIRST series.
     * Merges the static/dynamic highlight_mask with the tag-overlay tag_mask so
     * tag-matched peaks (abs(Δ)<1e-5, computed in Python) are highlighted exactly
     * like annotated peaks. When neither tag overlay nor a highlight column is
     * present this returns the original highlight_mask unchanged (no regression).
     */
    effectiveHighlightMask(): boolean[] | undefined {
      const pd = this.plotData
      if (!pd) return undefined
      const base = pd.highlight_mask
      const tag = pd.tag_mask
      if (!tag) return base
      const n = pd.x_values.length
      const out: boolean[] = new Array(n)
      for (let i = 0; i < n; i++) {
        out[i] = (base ? !!base[i] : false) || !!tag[i]
      }
      return out
    },

    /**
     * Tagger extension: effective per-peak annotation labels for the FIRST series.
     * Tag labels take precedence where present; otherwise falls back to the
     * existing annotations. Returns the original annotations untouched when no
     * tag labels exist.
     */
    effectiveAnnotations(): string[] | undefined {
      const pd = this.plotData
      if (!pd) return undefined
      const base = pd.annotations
      const tag = pd.tag_annotations
      if (!tag) return base
      const n = pd.x_values.length
      const out: string[] = new Array(n)
      for (let i = 0; i < n; i++) {
        const t = tag[i]
        out[i] = t && t.length > 0 ? t : base ? base[i] || '' : ''
      }
      return out
    },

    /**
     * Find the index of the selected peak based on interactivity mapping.
     * Looks up the selection value and finds the matching index in the data.
     */
    selectedPeakIndex(): number | undefined {
      if (!this.isDataReady || !this.plotData) {
        return undefined
      }

      // For each identifier in interactivity, check if there's a selection
      for (const [identifier, column] of Object.entries(this.interactivity)) {
        const selectedValue = this.selectionStore.$state[identifier]
        if (selectedValue === undefined || selectedValue === null) {
          continue
        }

        // Look for the interactivity column data (e.g., interactivity_peak_id)
        const columnKey = `interactivity_${column}`
        const columnValues = this.plotData[columnKey] as unknown[] | undefined

        if (columnValues && Array.isArray(columnValues)) {
          // Find the index with matching value
          for (let i = 0; i < columnValues.length; i++) {
            if (columnValues[i] === selectedValue) {
              return i
            }
          }
        } else if (column === this.args.xColumn) {
          // Fallback: if no interactivity column data, try matching x values
          const xValues = this.plotData.x_values
          for (let i = 0; i < xValues.length; i++) {
            if (xValues[i] === selectedValue) {
              return i
            }
          }
        }
      }
      return undefined
    },

    /**
     * Check if data is ready for rendering.
     */
    isDataReady(): boolean {
      if (!this.plotData) return false
      return (
        Array.isArray(this.plotData.x_values) &&
        Array.isArray(this.plotData.y_values) &&
        this.plotData.x_values.length > 0
      )
    },

    /**
     * Generate stick format x values from raw data.
     * Each data point (x) becomes triplet: [x, x, x]
     */
    xValuesStick(): number[] {
      if (!this.isDataReady || !this.plotData) return []
      const result: number[] = []
      for (const x of this.plotData.x_values) {
        result.push(x, x, x)
      }
      return result
    },

    /**
     * Generate stick format y values from raw data.
     * Each data point (y) becomes triplet: [-10000000, y, -10000000]
     * Using large negative value (matching FLASHApp) to avoid visual artifacts.
     */
    yValuesStick(): number[] {
      if (!this.isDataReady || !this.plotData) return []
      const result: number[] = []
      const baseline = -10000000
      for (const y of this.plotData.y_values) {
        result.push(baseline, y, baseline)
      }
      return result
    },

    /**
     * Compute x range for the plot.
     */
    xRange(): number[] {
      // Use manual range if set (from zoom)
      if (this.manualXRange) {
        return this.manualXRange
      }

      // Charge drill-down sub-view: zoom to the drilled mass's m/z span.
      if (this.inChargeSubView) {
        const span = this.chargeSubViewSpan
        if (span) return span
      }

      // Deconvolved-peaks highlight mode shows the ENTIRE spectrum (FLASHApp
      // priority 1: overrides the tag-walk auto-zoom).
      if (this.deconvolvedPeaksHighlightMode && this.isDataReady && this.plotData) {
        const xs = this.plotData.x_values
        if (xs.length > 0) {
          return [Math.min(...xs) * 0.98, Math.max(...xs) * 1.02]
        }
      }

      // Tagger extension: when a tag walk is present, auto-zoom to the tag's
      // mass span (with padding). Matches FLASHApp PlotlyLineplotTagger, which
      // ranges to [min(masses)*0.98, max(masses)*1.02] for the deconv view.
      const span = this.tagWalkSpan
      if (span) {
        return span
      }

      if (!this.isDataReady || !this.plotData) return [0, 1]

      // Include the second overlaid series (if any) so it is not clipped.
      let xValues = this.plotData.x_values
      const x2 = this.plotData.x2_values
      if (x2 && x2.length > 0) {
        xValues = xValues.concat(x2)
      }
      // Filter out null/NaN before min/max: the diagonal-concat anno series can
      // contribute null MonoMass values, which would poison Math.min/Math.max
      // (mirrors the guarding in tagWalkSpan / chargeSubViewSpan).
      const finiteX = xValues.filter((x) => x != null && Number.isFinite(x))
      if (finiteX.length === 0) return [0, 1]
      const minX = Math.min(...finiteX)
      const maxX = Math.max(...finiteX)
      const padding = (maxX - minX) * 0.02

      return [minX - padding, maxX + padding]
    },

    /**
     * Compute y range for the plot based on visible x range.
     * Adds extra space at top for annotations.
     */
    yRange(): number[] {
      if (!this.isDataReady || !this.plotData) return [0, 1]

      const xRange = this.xRange

      // Charge drill-down sub-view: the spectrum shown is the signal m/z peaks,
      // so the y-range must come from their intensities (not the deconv sticks).
      if (this.inChargeSubView) {
        const sig = this.chargeSignal
        let maxY = 0
        if (sig && sig.intensities.length > 0) {
          for (let i = 0; i < sig.mzs.length; i++) {
            const x = sig.mzs[i]
            const y = sig.intensities[i]
            if (x >= xRange[0] && x <= xRange[1] && y > maxY) maxY = y
          }
        }
        if (maxY === 0) return [0, 1]
        return [0, maxY * 1.8]
      }

      const { x_values, y_values } = this.plotData

      // Find max y within the visible x range
      let maxY = 0
      for (let i = 0; i < x_values.length; i++) {
        const x = x_values[i]
        const y = y_values[i]
        if (x >= xRange[0] && x <= xRange[1] && y > maxY) {
          maxY = y
        }
      }

      // Include the second overlaid series in the y-range computation.
      const x2 = this.plotData.x2_values
      const y2 = this.plotData.y2_values
      if (x2 && y2) {
        for (let i = 0; i < x2.length; i++) {
          if (x2[i] >= xRange[0] && x2[i] <= xRange[1] && y2[i] > maxY) {
            maxY = y2[i]
          }
        }
      }

      if (maxY === 0) return [0, 1]

      // Add headroom for annotations (1.8x like FLASHApp)
      return [0, maxY * 1.8]
    },

    /**
     * Compute x position scaling factor based on current zoom level.
     */
    xPosScalingFactor(): number {
      const xRange = this.xRange
      const rangeWidth = xRange[1] - xRange[0]
      const actualWidth = this.actualPlotWidth
      return (1200 / actualWidth) * rangeWidth / this.config.xPosScalingFactor
    },

    /**
     * Get annotation data: positions, labels, and visibility based on overlap.
     * Uses raw x_values/y_values (not stick format triplets).
     */
    annotatedPeaks(): Array<{
      x: number
      y: number
      label: string
      index: number
    }> {
      if (!this.isDataReady || !this.plotData) return []

      const { x_values, y_values } = this.plotData
      // Use tag-merged labels/mask so tag-overlay peaks get annotation boxes too.
      const annotations = this.effectiveAnnotations
      const highlight_mask = this.effectiveHighlightMask
      if (!annotations) return []

      const peaks: Array<{ x: number; y: number; label: string; index: number }> = []

      for (let i = 0; i < annotations.length; i++) {
        const label = annotations[i]
        // Only include highlighted peaks with non-empty labels
        if (!label || label.length === 0) continue
        if (highlight_mask && !highlight_mask[i]) continue

        peaks.push({
          x: x_values[i],
          y: y_values[i],
          label: label,
          index: i,
        })
      }

      return peaks
    },

    /**
     * Compute annotation boxes with overlap detection.
     * Returns which annotations should be visible.
     * Uses greedy intensity-based resolution: highest intensity annotations
     * get priority, lower intensity ones are hidden if they would overlap.
     */
    annotationBoxData(): Array<{
      x: number
      y: number
      width: number
      height: number
      label: string
      visible: boolean
      index: number
    }> {
      const peaks = this.annotatedPeaks
      if (peaks.length === 0) return []

      const yRange = this.yRange
      const xRange = this.xRange

      if (yRange[1] <= 0 || xRange[1] <= xRange[0]) return []

      const ymax = yRange[1] / 1.8
      const ypos_low = ymax * 1.18
      const ypos_high = ymax * 1.32
      const boxHeight = ypos_high - ypos_low

      // Padding around text in pixels (8px on each side)
      const textPaddingPx = 16

      // Create boxes for each annotation with peak intensity preserved
      // Box width is calculated from actual text width + padding
      const boxes: Array<{
        x: number
        y: number
        width: number
        height: number
        label: string
        visible: boolean
        inVisibleRange: boolean
        index: number
        peakY: number  // Original peak intensity for sorting
      }> = []

      for (const peak of peaks) {
        const inVisibleRange = peak.x >= xRange[0] && peak.x <= xRange[1]
        // Measure text width and convert to data units
        const textWidthPx = this.measureTextWidth(peak.label)
        const boxWidthDataUnits = this.pixelWidthToDataUnits(textWidthPx + textPaddingPx)

        boxes.push({
          x: peak.x,
          y: (ypos_low + ypos_high) / 2,
          width: boxWidthDataUnits,
          height: boxHeight,
          label: peak.label,
          visible: false,  // Will be set by overlap resolution
          inVisibleRange: inVisibleRange,
          index: peak.index,
          peakY: peak.y,  // Preserve intensity for sorting
        })
      }

      // Filter to visible boxes and sort by intensity (descending)
      // Use x position as secondary sort for determinism when intensities are equal
      const visibleBoxes = boxes
        .filter((box) => box.inVisibleRange)
        .sort((a, b) => {
          if (b.peakY !== a.peakY) return b.peakY - a.peakY  // Highest intensity first
          return a.x - b.x  // Leftmost first as tiebreaker
        })

      // Greedy overlap resolution: show highest intensity, hide overlapping lower ones
      // Use a small gap between boxes (4px converted to data units)
      const gapDataUnits = this.pixelWidthToDataUnits(4)
      const committedBoxes: typeof visibleBoxes = []

      for (const box of visibleBoxes) {
        const boxLeft = box.x - box.width / 2 - gapDataUnits
        const boxRight = box.x + box.width / 2 + gapDataUnits

        // Check overlap with all committed (visible) boxes
        let hasOverlap = false
        for (const committed of committedBoxes) {
          const committedLeft = committed.x - committed.width / 2
          const committedRight = committed.x + committed.width / 2

          // Check x overlap (y is the same for all annotation boxes)
          if (!(boxRight < committedLeft || boxLeft > committedRight)) {
            hasOverlap = true
            break
          }
        }

        if (!hasOverlap) {
          box.visible = true
          committedBoxes.push(box)
        }
      }

      return boxes
    },

    /**
     * Build Plotly shapes for annotation background boxes.
     * Box color matches the peak: selectedColor if peak is selected, highlightColor otherwise.
     */
    annotationShapes(): Partial<Plotly.Shape>[] {
      const boxes = this.annotationBoxData
      const shapes: Partial<Plotly.Shape>[] = []

      const yRange = this.yRange
      if (yRange[1] <= 0) return shapes

      const ymax = yRange[1] / 1.8
      const ypos_low = ymax * 1.18
      const ypos_high = ymax * 1.32

      const selectedIndex = this.selectedPeakIndex

      for (const box of boxes) {
        if (!box.visible) continue

        // Use selected color if this annotation's peak is selected
        const isSelected = box.index === selectedIndex
        const boxColor = isSelected ? this.styling.selectedColor : this.styling.highlightColor

        shapes.push({
          type: 'rect',
          x0: box.x - box.width / 2,
          y0: ypos_low,
          x1: box.x + box.width / 2,
          y1: ypos_high,
          fillcolor: boxColor,
          line: { width: 0 },
        })
      }

      return shapes
    },

    /**
     * Build Plotly annotations for peak labels.
     */
    peakAnnotations(): Partial<Plotly.Annotations>[] {
      const boxes = this.annotationBoxData
      const annotations: Partial<Plotly.Annotations>[] = []

      const yRange = this.yRange
      if (yRange[1] <= 0) return annotations

      const ymax = yRange[1] / 1.8
      const ypos = ymax * 1.25

      for (const box of boxes) {
        if (!box.visible) continue

        annotations.push({
          x: box.x,
          y: ypos,
          xref: 'x',
          yref: 'y',
          text: box.label,
          showarrow: false,
          font: {
            size: 14,
            color: 'white',
          },
        })
      }

      return annotations
    },

    /**
     * Legacy box half-width for the augmented/tag-walk views:
     *   xpos_scaling = rangeWidth / legacyXPosScalingFactor (27.5).
     * Unified across the tag-walk and charge-sub-view paths (P1 — was /27.5 inline
     * for tag-walk but the annotation path used 80; these are now distinct configs
     * so each path keeps its intended geometry while sharing one named constant).
     */
    legacyXposScaling(): number {
      const xRange = this.xRange
      return (xRange[1] - xRange[0]) / this.config.legacyXPosScalingFactor
    },

    /**
     * Legacy all-or-nothing overlap suppression for the tag-walk (augmented deconv)
     * view: when the per-mass box half-width exceeds legacyXPosScalingThreshold (30),
     * hide ALL mass annotations (FLASHApp PlotlyLineplotTagger:385-391). This is the
     * documented divergence from the greedy resolver used for plain annotated
     * spectra — the augmented views match the legacy threshold behavior exactly.
     */
    tagWalkAnnotationsHidden(): boolean {
      if (!this.tagWalk) return false
      return this.legacyXposScaling > this.config.legacyXPosScalingThreshold
    },

    /**
     * The residue-walk gap index selected by the user (tag-walk selectedAA),
     * mapped into walkMasses gap-space honoring direction (nTerminal). residues[i]
     * labels the gap between walkMasses[i] and walkMasses[i+1].
     *
     * OPTIONAL/backward-compatible: when selectedAA is absent this is undefined and
     * nothing is highlighted as "selected" (legacy fallback to mass-order only).
     * When nTerminal is false the index is mirrored (gaps - 1 - selectedAA),
     * matching the legacy reversedSelectedAA convention for C-terminal-ordered tags.
     */
    walkSelectedGap(): number | undefined {
      const tw = this.tagWalk
      if (!tw || tw.selectedAA === undefined) return undefined
      const gaps = Math.max(this.walkMasses.length - 1, 0)
      if (gaps === 0) return undefined
      // Default (nTerminal true or unspecified): direct index.
      // nTerminal === false: mirror into the reversed gap space (legacy behavior).
      const nTerm = tw.nTerminal
      const idx = nTerm === false ? gaps - 1 - tw.selectedAA : tw.selectedAA
      if (idx < 0 || idx >= gaps) return undefined
      return idx
    },

    /**
     * Tagger extension: invisible hover markers at each tag-walk mass (parity
     * with the legacy buttonTraces) so the user can hover a mass to read it.
     */
    tagWalkTraces(): Plotly.Data[] {
      const masses = this.walkMasses
      if (masses.length === 0) return []

      const yRange = this.yRange
      if (yRange[1] <= 0) return []
      const ymax = yRange[1] / 1.8
      const ypos = ymax * 1.25

      return [
        {
          x: masses,
          y: masses.map(() => ypos),
          mode: 'markers',
          type: 'scatter',
          marker: { size: 20, opacity: 0 },
          hoverinfo: 'text',
          hovertext: masses.map((m) => m.toFixed(2)),
        },
      ]
    },

    /**
     * Tagger extension: background rectangles for each tag-walk mass label,
     * mirroring the legacy mass "buttons" (ypos_low..ypos_high band).
     */
    tagWalkShapes(): Partial<Plotly.Shape>[] {
      const masses = this.walkMasses
      if (masses.length === 0 || this.tagWalkAnnotationsHidden) return []

      const yRange = this.yRange
      if (yRange[1] <= 0) return []
      const ymax = yRange[1] / 1.8
      const ypos_low = ymax * 1.18
      const ypos_high = ymax * 1.32

      // Legacy box half-width (rangeWidth / legacyXPosScalingFactor, default 27.5).
      const xpos_scaling = this.legacyXposScaling

      const color = this.styling.annotationColors?.massButton || this.styling.highlightColor
      const selColor =
        this.styling.annotationColors?.selectedMassButton || this.styling.selectedColor
      const sel = this.walkSelectedGap

      const shapes: Partial<Plotly.Shape>[] = []
      for (let i = 0; i < masses.length; i++) {
        // Legacy: a mass box is "selected" when it bounds the selected gap
        // (selectedAA == i || selectedAA == i-1).
        const isSelected = sel !== undefined && (sel === i || sel === i - 1)
        shapes.push({
          type: 'rect',
          x0: masses[i] - xpos_scaling,
          y0: ypos_low,
          x1: masses[i] + xpos_scaling,
          y1: ypos_high,
          fillcolor: isSelected ? selColor : color,
          line: { width: 0 },
        })
      }
      return shapes
    },

    /**
     * Tagger extension: the residue-walk annotations — the mass labels above
     * each tag stick PLUS the residue letter for each consecutive-mass gap.
     * Geometry mirrors PlotlyLineplotTagger.annotationData (deconv branch):
     *   - mass label at (mass, ypos=ymax*1.25)
     *   - residue letter at (midpoint, yPosAA=ypos*0.6)
     * residues[i] labels the gap between walkMasses[i] and walkMasses[i+1].
     */
    tagWalkAnnotations(): Partial<Plotly.Annotations>[] {
      const tw = this.tagWalk
      const masses = this.walkMasses
      if (!tw || masses.length === 0 || this.tagWalkAnnotationsHidden) return []

      const yRange = this.yRange
      if (yRange[1] <= 0) return []
      const ymax = yRange[1] / 1.8
      const ypos = ymax * 1.25
      const yPosAA = ypos * 0.6

      const color = this.styling.annotationColors?.massButton || this.styling.highlightColor
      const arrowColor =
        this.styling.annotationColors?.sequenceArrow || this.styling.highlightColor

      const annotations: Partial<Plotly.Annotations>[] = []

      // Mass labels (white text on the colored button band).
      for (const mass of masses) {
        annotations.push({
          x: mass,
          y: ypos,
          xref: 'x',
          yref: 'y',
          text: mass.toFixed(2),
          showarrow: false,
          font: { size: 15, color: 'white' },
        })
      }

      // Residue letters for each gap (selected gap → selected color + bold).
      const residues = tw.residues || []
      const selArrowColor =
        this.styling.annotationColors?.selectedSequenceArrow || this.styling.selectedColor
      const sel = this.walkSelectedGap
      for (let i = 0; i < masses.length - 1; i++) {
        const xMid = (masses[i] + masses[i + 1]) / 2
        const aa = i < residues.length ? residues[i] : ''
        const delta = Math.abs(masses[i + 1] - masses[i])
        const isSelected = sel !== undefined && sel === i
        annotations.push({
          x: xMid,
          y: yPosAA,
          xref: 'x',
          yref: 'y',
          text: aa,
          hovertext: 'Δ=' + delta.toFixed(2) + ' Da',
          showarrow: false,
          font: {
            size: 15,
            color: isSelected ? selArrowColor : arrowColor,
            family: isSelected
              ? 'Arial Black, Arial Bold, Arial, sans-serif'
              : 'sans-serif',
          },
        })
      }

      return annotations
    },

    /**
     * Tagger extension: the connector ARROWS between consecutive tag masses,
     * drawn as Plotly arrow-annotations. Mirrors the legacy two-segment arrow
     * (head-less from midpoint to start, headed from midpoint to end) at
     * yPosArrow = ypos*0.5, with the same inward-shrink (diff = |Δ|*0.9).
     */
    tagWalkArrows(): Partial<Plotly.Annotations>[] {
      const masses = this.walkMasses
      if (masses.length < 2 || this.tagWalkAnnotationsHidden) return []

      const yRange = this.yRange
      if (yRange[1] <= 0) return []
      const ymax = yRange[1] / 1.8
      const ypos = ymax * 1.25
      const yPosArrow = ypos * 0.5

      const arrowColor =
        this.styling.annotationColors?.sequenceArrow || this.styling.highlightColor
      const selArrowColor =
        this.styling.annotationColors?.selectedSequenceArrow || this.styling.selectedColor
      const sel = this.walkSelectedGap

      const arrows: Partial<Plotly.Annotations>[] = []
      for (let i = 0; i < masses.length - 1; i++) {
        const color = sel !== undefined && sel === i ? selArrowColor : arrowColor
        let xStart = masses[i]
        let xEnd = masses[i + 1]
        const xMid = (xStart + xEnd) / 2
        let xMidStart = xMid
        let xMidEnd = xMid
        const diff = Math.abs(xStart - xEnd) * 0.9

        if (xStart > xEnd) {
          xStart -= diff
          xMidStart += diff * 0.1
          xEnd += diff
          xMidEnd -= diff * 0.1
        } else {
          xStart += diff
          xMidStart -= diff * 0.1
          xEnd -= diff
          xMidEnd += diff * 0.1
        }

        // Head-less segment (mid → start)
        arrows.push({
          ax: xMidStart,
          ay: yPosArrow,
          xref: 'x',
          yref: 'y',
          x: xStart,
          y: yPosArrow,
          axref: 'x',
          ayref: 'y',
          showarrow: true,
          arrowhead: 0,
          arrowsize: 1,
          arrowwidth: 2,
          arrowcolor: color,
        })
        // Headed segment (mid → end)
        arrows.push({
          ax: xMidEnd,
          ay: yPosArrow,
          xref: 'x',
          yref: 'y',
          x: xEnd,
          y: yPosArrow,
          axref: 'x',
          ayref: 'y',
          showarrow: true,
          arrowhead: 2,
          arrowsize: 1,
          arrowwidth: 2,
          arrowcolor: color,
        })
      }
      return arrows
    },

    /**
     * Charge drill-down: the raw signal m/z / charge / intensity arrays for the
     * deconv peak the user drilled into (selectedMassIndex). Mirrors the legacy
     * highlightedValues[selectedMass] tuple (mzs/charges/intensity).
     */
    chargeSignal(): { mzs: number[]; charges: number[]; intensities: number[] } | undefined {
      const pd = this.plotData
      const idx = this.selectedMassIndex
      if (!pd || idx === undefined || !pd.signal_mzs || !pd.signal_charges) {
        return undefined
      }
      const mzs = (pd.signal_mzs[idx] as number[]) || []
      const charges = (pd.signal_charges[idx] as number[]) || []
      const intensities = pd.signal_intensities
        ? ((pd.signal_intensities[idx] as number[]) || [])
        : []
      if (mzs.length === 0) return undefined
      return { mzs, charges, intensities }
    },

    /**
     * Charge drill-down: per charge state, the intensity-weighted center-of-gravity
     * m/z (FLASHApp PlotlyLineplotTagger:345-373 / Unified:848-902). When intensity
     * is unavailable the COG falls back to a plain mean of the m/z values.
     */
    chargeGroups(): Array<{ charge: number; cogMz: number }> {
      const sig = this.chargeSignal
      if (!sig) return []
      const grouped = new Map<number, { mz: number; intensity: number }[]>()
      for (let i = 0; i < sig.mzs.length; i++) {
        const mz = sig.mzs[i]
        const charge = sig.charges[i]
        const intensity = sig.intensities.length > i ? sig.intensities[i] : 1
        const entry = { mz, intensity }
        if (grouped.has(charge)) {
          grouped.get(charge)!.push(entry)
        } else {
          grouped.set(charge, [entry])
        }
      }
      const out: Array<{ charge: number; cogMz: number }> = []
      grouped.forEach((entries, charge) => {
        const summed = entries.reduce((s, v) => s + v.intensity, 0)
        let cogMz: number
        if (summed > 0) {
          cogMz = entries.reduce((s, v) => s + (v.intensity / summed) * v.mz, 0)
        } else {
          cogMz = entries.reduce((s, v) => s + v.mz, 0) / entries.length
        }
        out.push({ charge, cogMz })
      })
      return out
    },

    /**
     * Charge drill-down: the m/z span [min,max]*[0.98,1.02] for auto-zoom in the
     * sub-view (FLASHApp PlotlyLineplotTagger:596-598).
     */
    chargeSubViewSpan(): number[] | undefined {
      const sig = this.chargeSignal
      if (!sig || sig.mzs.length === 0) return undefined
      const lo = Math.min(...sig.mzs)
      const hi = Math.max(...sig.mzs)
      if (!isFinite(lo) || !isFinite(hi)) return undefined
      return [lo * 0.98, hi * 1.02]
    },

    /**
     * Charge drill-down: the z="+charge" box shapes at each charge's COG m/z.
     * Uses the legacy half-width geometry: 0.5 * rangeWidth / legacyXPosScalingFactor
     * (FLASHApp xpos_scaling/2 with xPosScalingFactor=27.5). Fill rule follows the
     * legacy #E4572E (highlight) / #F3A712 (selected-residue) palette.
     */
    chargeSubViewShapes(): Partial<Plotly.Shape>[] {
      const groups = this.chargeGroups
      if (groups.length === 0) return []
      const yRange = this.yRange
      if (yRange[1] <= 0) return []
      const ymax = yRange[1] / 1.8
      const ypos_low = ymax * 1.18
      const ypos_high = ymax * 1.32

      const xRange = this.xRange
      const halfWidth = 0.5 * (xRange[1] - xRange[0]) / this.config.legacyXPosScalingFactor

      // #F3A712 when the drilled mass is the selected residue, #E4572E otherwise.
      const fill = this.isSelectedResidueMass
        ? this.styling.selectedColor
        : this.styling.highlightColor

      const shapes: Partial<Plotly.Shape>[] = []
      for (const g of groups) {
        shapes.push({
          type: 'rect',
          x0: g.cogMz - halfWidth,
          y0: ypos_low,
          x1: g.cogMz + halfWidth,
          y1: ypos_high,
          fillcolor: fill,
          line: { width: 0 },
        })
      }
      return shapes
    },

    /**
     * Charge drill-down: the z="+charge" label annotations at each COG m/z.
     */
    chargeSubViewAnnotations(): Partial<Plotly.Annotations>[] {
      const groups = this.chargeGroups
      if (groups.length === 0) return []
      const yRange = this.yRange
      if (yRange[1] <= 0) return []
      const ymax = yRange[1] / 1.8
      const ypos = ymax * 1.25

      const annotations: Partial<Plotly.Annotations>[] = []
      for (const g of groups) {
        annotations.push({
          x: g.cogMz,
          y: ypos,
          xref: 'x',
          yref: 'y',
          text: 'z=' + g.charge,
          showarrow: false,
          font: { size: 15, color: 'white' },
        })
      }
      return annotations
    },

    /**
     * Charge drill-down: stick traces for the drilled mass's signal m/z peaks.
     */
    chargeSubViewTraces(): Plotly.Data[] {
      const sig = this.chargeSignal
      if (!sig) return this.getFallbackData()
      const baseline = -10000000
      const x: number[] = []
      const y: number[] = []
      for (let i = 0; i < sig.mzs.length; i++) {
        const intensity = sig.intensities.length > i ? sig.intensities[i] : 1
        x.push(sig.mzs[i], sig.mzs[i], sig.mzs[i])
        y.push(baseline, intensity, baseline)
      }
      return [
        {
          x,
          y,
          mode: 'lines',
          type: 'scatter',
          connectgaps: false,
          marker: { color: this.styling.highlightColor },
          hoverinfo: 'x+y',
        },
      ]
    },

    /**
     * Whether the drilled-into mass is the currently selected residue (tag-walk
     * selectedAA), driving the #F3A712 fill in the sub-view. Matches FLASHApp
     * `selectedAA == selectedMass || selectedAA == selectedMass-1`.
     */
    isSelectedResidueMass(): boolean {
      const tw = this.tagWalk
      const sel = this.selectedMassIndex
      if (!tw || sel === undefined || tw.selectedAA === undefined) return false
      return tw.selectedAA === sel || tw.selectedAA === sel - 1
    },

    /**
     * Check if the selected peak is annotated but its annotation is currently hidden.
     */
    selectedAnnotationHidden(): boolean {
      const selectedIndex = this.selectedPeakIndex
      if (selectedIndex === undefined) return false

      const boxes = this.annotationBoxData
      const selectedBox = boxes.find(box => box.index === selectedIndex)

      // Not annotated = not hidden
      if (!selectedBox) return false

      // Return true if annotation exists but is not visible
      return !selectedBox.visible
    },

    /**
     * Build Plotly traces.
     * Uses stick format triplets generated from raw data.
     * Includes a separate gold trace for the selected peak.
     */
    traces(): Plotly.Data[] {
      if (!this.isDataReady || !this.plotData) {
        return this.getFallbackData()
      }

      // Charge drill-down sub-view: render the drilled mass's signal m/z peaks as
      // sticks (the z="+charge" labels/boxes are drawn via layout shapes/annots).
      if (this.inChargeSubView) {
        return this.chargeSubViewTraces
      }

      const traces: Plotly.Data[] = []
      // Tag-merged highlight mask (falls back to plain highlight_mask when no tags)
      const highlight_mask = this.effectiveHighlightMask
      const selectedIndex = this.selectedPeakIndex
      const baseline = -10000000

      // Split into unhighlighted, highlighted, and selected
      const unhighlighted_x: number[] = []
      const unhighlighted_y: number[] = []
      const highlighted_x: number[] = []
      const highlighted_y: number[] = []
      const selected_x: number[] = []
      const selected_y: number[] = []

      const numPoints = this.plotData.x_values.length

      for (let i = 0; i < numPoints; i++) {
        const x = this.plotData.x_values[i]
        const y = this.plotData.y_values[i]
        const isHighlighted = highlight_mask ? highlight_mask[i] : false
        const isSelected = selectedIndex !== undefined && i === selectedIndex

        if (isSelected) {
          // Selected peak goes in gold trace (drawn last, on top)
          selected_x.push(x, x, x)
          selected_y.push(baseline, y, baseline)
        } else if (isHighlighted) {
          // Highlighted peaks (annotated)
          highlighted_x.push(x, x, x)
          highlighted_y.push(baseline, y, baseline)
        } else {
          // Normal unhighlighted peaks
          unhighlighted_x.push(x, x, x)
          unhighlighted_y.push(baseline, y, baseline)
        }
      }

      // --- Tagger extension: SECOND overlaid series (drawn first, underneath) ---
      // Renders raw/annotated peaks as a second set of sticks in the same figure.
      // Highlighted points of the 2nd series use highlightColor; the rest use
      // secondSeriesColor. Guarded so single-series plots are unaffected.
      const pd = this.plotData
      if (pd.x2_values && pd.y2_values && pd.x2_values.length > 0) {
        const x2 = pd.x2_values
        const y2 = pd.y2_values
        const h2 = pd.highlight2_mask
        const s2_x: number[] = []
        const s2_y: number[] = []
        const s2h_x: number[] = []
        const s2h_y: number[] = []
        const n2 = x2.length
        for (let i = 0; i < n2; i++) {
          const x = x2[i]
          const y = y2[i]
          if (h2 && h2[i]) {
            s2h_x.push(x, x, x)
            s2h_y.push(baseline, y, baseline)
          } else {
            s2_x.push(x, x, x)
            s2_y.push(baseline, y, baseline)
          }
        }
        if (s2_x.length > 0) {
          traces.push({
            x: s2_x,
            y: s2_y,
            mode: 'lines',
            type: 'scatter',
            connectgaps: false,
            marker: { color: this.styling.secondSeriesColor },
            hoverinfo: 'x+y',
          })
        }
        if (s2h_x.length > 0) {
          traces.push({
            x: s2h_x,
            y: s2h_y,
            mode: 'lines',
            type: 'scatter',
            connectgaps: false,
            marker: { color: this.styling.highlightColor },
            hoverinfo: 'x+y',
          })
        }
      }

      // Unhighlighted trace (drawn first, bottom layer)
      if (unhighlighted_x.length > 0) {
        traces.push({
          x: unhighlighted_x,
          y: unhighlighted_y,
          mode: 'lines',
          type: 'scatter',
          connectgaps: false,
          marker: { color: this.styling.unhighlightedColor },
          hoverinfo: 'x+y',
        })
      }

      // Highlighted trace (middle layer)
      if (highlighted_x.length > 0) {
        traces.push({
          x: highlighted_x,
          y: highlighted_y,
          mode: 'lines',
          type: 'scatter',
          connectgaps: false,
          marker: { color: this.styling.highlightColor },
          hoverinfo: 'x+y',
        })
      }

      // Selected trace (top layer, gold color)
      if (selected_x.length > 0) {
        traces.push({
          x: selected_x,
          y: selected_y,
          mode: 'lines',
          type: 'scatter',
          connectgaps: false,
          marker: { color: this.styling.selectedColor },
          line: { width: 3 }, // Make selected peak slightly thicker
          hoverinfo: 'x+y',
        })
      }

      // --- Tagger extension: signal-peak markers (drawn on top of sticks) ---
      // Marks peaks flagged as SignalPeaks members with a distinct dot at the tip.
      // NOT a legacy feature → OFF by default; gated behind showSignalMarkers (P2).
      // Guarded by presence of signal_mask → no effect on plots without it.
      if (pd.signal_mask && this.showSignalMarkers) {
        const sm = pd.signal_mask
        const marker_x: number[] = []
        const marker_y: number[] = []
        const np = pd.x_values.length
        for (let i = 0; i < np; i++) {
          if (sm[i]) {
            marker_x.push(pd.x_values[i])
            marker_y.push(pd.y_values[i])
          }
        }
        if (marker_x.length > 0) {
          traces.push({
            x: marker_x,
            y: marker_y,
            mode: 'markers',
            type: 'scatter',
            marker: {
              color: this.styling.signalPeakColor,
              size: 7,
              symbol: 'circle',
            },
            hoverinfo: 'x+y',
          })
        }
      }

      // --- Tagger extension: tag-walk hover markers (invisible, on top) ---
      if (this.tagWalk) {
        traces.push(...this.tagWalkTraces)
      }

      // If no data was added (no highlight mask and no selection), show all as default
      if (traces.length === 0) {
        traces.push({
          x: this.xValuesStick,
          y: this.yValuesStick,
          mode: 'lines',
          type: 'scatter',
          connectgaps: false,
          marker: { color: this.styling.highlightHiddenColor },
          hoverinfo: 'x+y',
        })
      }

      return traces
    },

    /**
     * Build Plotly layout.
     */
    layout(): Partial<Plotly.Layout> {
      const title = this.effectiveTitle
      // In the charge sub-view the x-axis becomes m/z (FLASHApp xAxisLabel).
      const xLabel = this.inChargeSubView ? 'm/z' : this.args.xLabel
      return {
        title: title ? { text: `<b>${title}</b>` } : undefined,
        showlegend: false,
        height: this.args.height || 400,
        xaxis: {
          title: xLabel ? { text: xLabel } : undefined,
          showgrid: false,
          showline: true,
          linecolor: 'grey',
          linewidth: 1,
          range: this.xRange,
        },
        yaxis: {
          title: this.args.yLabel ? { text: this.args.yLabel } : undefined,
          showgrid: true,
          gridcolor: this.theme?.secondaryBackgroundColor || '#f0f0f0',
          rangemode: 'nonnegative',
          // Spectrum modes lock the y-axis (FLASHApp PlotlyLineplotTagger:634).
          fixedrange: true,
          showline: true,
          linecolor: 'grey',
          linewidth: 1,
          range: this.yRange,
        },
        paper_bgcolor: this.theme?.backgroundColor || 'white',
        plot_bgcolor: this.theme?.backgroundColor || 'white',
        font: {
          color: this.theme?.textColor || 'black',
          family: this.theme?.font || 'Arial',
        },
        margin: {
          l: 60,
          r: 20,
          t: title ? 50 : 20,
          b: 50,
        },
        shapes: this.layoutShapes,
        annotations: this.layoutAnnotations,
      }
    },

    /**
     * Consolidated layout shapes, honoring the charge sub-view, the tag walk, and
     * the annotationsVisible toggle.
     */
    layoutShapes(): Partial<Plotly.Shape>[] {
      if (this.inChargeSubView) {
        return this.annotationsVisible ? this.chargeSubViewShapes : []
      }
      if (!this.annotationsVisible) return []
      return this.tagWalk
        ? [...this.annotationShapes, ...this.tagWalkShapes]
        : this.annotationShapes
    },

    /**
     * Consolidated layout annotations, honoring the charge sub-view, the tag walk,
     * and the annotationsVisible toggle.
     */
    layoutAnnotations(): Partial<Plotly.Annotations>[] {
      if (this.inChargeSubView) {
        return this.annotationsVisible ? this.chargeSubViewAnnotations : []
      }
      if (!this.annotationsVisible) return []
      return this.tagWalk
        ? [...this.peakAnnotations, ...this.tagWalkAnnotations, ...this.tagWalkArrows]
        : this.peakAnnotations
    },

    cssCustomProperties(): Record<string, string> {
      return {
        '--highlight-color': this.styling.highlightColor,
        '--selected-color': this.styling.selectedColor,
        '--unhighlighted-color': this.styling.unhighlightedColor,
      }
    },
  },

  watch: {
    isDataReady: {
      handler(newVal: boolean) {
        if (newVal && this.isInitialized) {
          this.renderPlot()
        }
      },
      immediate: true,
    },

    'streamlitDataStore.allDataForDrawing.plotData': {
      handler(newData, oldData) {
        console.log('[LinePlot] plotData changed', {
          newLength: newData?.x_values?.length,
          oldLength: oldData?.x_values?.length,
          newFirstX: newData?.x_values?.[0],
          oldFirstX: oldData?.x_values?.[0],
        })
        if (this.isInitialized) {
          // Reset zoom + charge sub-view when data changes (e.g. switching spectra),
          // mirroring the legacy selectedScan watcher restoring the deconv view.
          this.manualXRange = undefined
          this.lastAutoZoomedPeakIndex = undefined
          this.selectedMassIndex = undefined
          this.localTitle = undefined
          this.renderPlot()
        }
      },
      deep: true,
    },

    // Re-render when plot config changes (e.g., dynamic annotations)
    'streamlitDataStore.allDataForDrawing._plotConfig': {
      handler() {
        if (this.isInitialized) {
          this.renderPlot()
        }
      },
      deep: true,
    },

    // Re-render (and re-zoom) when the tag walk changes (tagger extension).
    'streamlitDataStore.allDataForDrawing.tagWalk': {
      handler() {
        if (this.isInitialized) {
          // A new tag walk owns the x-range; drop any stale manual zoom and exit
          // any charge sub-view (legacy selectedTag watcher restores deconv view).
          this.manualXRange = undefined
          this.lastAutoZoomedPeakIndex = undefined
          this.selectedMassIndex = undefined
          this.localTitle = undefined
          this.renderPlot()
        }
      },
      deep: true,
    },

    // Re-render when selection changes (to update gold highlighting)
    // Also auto-zoom if selected annotated peak's label is hidden
    'selectionStore.$state': {
      handler(newState) {
        console.log('[LinePlot] selection changed', newState)
        if (this.isDataReady && this.isInitialized) {
          this.autoZoomToSelectedAnnotation()
          this.renderPlot()
        }
      },
      deep: true,
    },
  },

  mounted() {
    this.isInitialized = true
    // Use nextTick to ensure DOM is fully ready
    this.$nextTick(() => {
      if (this.isDataReady) {
        this.renderPlot()
      }
    })
  },

  methods: {
    /**
     * Measure text width in pixels using Canvas API.
     * Caches the canvas context for performance.
     */
    measureTextWidth(text: string): number {
      if (!this.textMeasureCanvas) {
        this.textMeasureCanvas = document.createElement('canvas')
      }
      const ctx = this.textMeasureCanvas.getContext('2d')
      if (!ctx) return text.length * 8 // Fallback estimate
      ctx.font = '14px Arial'
      return ctx.measureText(text).width
    },

    /**
     * Convert pixel width to data units (x-axis scale).
     * Accounts for current zoom level and plot width.
     */
    pixelWidthToDataUnits(pixelWidth: number): number {
      const xRange = this.xRange
      const rangeWidth = xRange[1] - xRange[0]
      const plotWidth = this.actualPlotWidth
      // pixels / (pixels/dataUnit) = dataUnits
      return pixelWidth / (plotWidth / rangeWidth)
    },

    async renderPlot(): Promise<void> {
      try {
        const element = document.getElementById(this.id)
        if (!element) {
          console.warn(`PlotlyLineplot: DOM element with id '${this.id}' not found`)
          return
        }

        const modeBarButtons: Array<Record<string, unknown>> = [
          // "Hide/Show Annotations" toggle (FLASHApp parity).
          {
            title: this.annotationsVisible ? 'Hide Annotations' : 'Show Annotations',
            name: 'toggleAnnotations',
            icon: {
              width: 1792,
              height: 1792,
              path: 'M1664 960q-152-236-381-353 61 104 61 225 0 185-131.5 316.5t-316.5 131.5-316.5-131.5-131.5-316.5q0-121 61-225-229 117-381 353 133 205 333.5 326.5t434.5 121.5 434.5-121.5 333.5-326.5zm-720-384q0-20-14-34t-34-14q-125 0-214.5 89.5t-89.5 214.5q0 20 14 34t34 14 34-14 14-34q0-86 61-147t147-61q20 0 34-14t14-34zm848 384q0 34-20 69-140 230-376.5 368.5t-499.5 138.5-499.5-139-376.5-368q-20-35-20-69t20-69q140-229 376.5-368t499.5-139 499.5 139 376.5 368q20 35 20 69z',
            },
            click: () => {
              this.toggleAnnotations()
            },
          },
        ]

        // "Show/Hide Deconvolved Peaks" — gated on presence of signal data (parity).
        if (this.hasSignalDrilldown) {
          modeBarButtons.push({
            title: this.deconvolvedPeaksHighlightMode
              ? 'Hide Deconvolved Peaks'
              : 'Show Deconvolved Peaks',
            name: 'toggleDeconvolvedPeaks',
            icon: {
              width: 1792,
              height: 1792,
              path: 'M448 1024h896v128h-896v-128zm0-256h896v128h-896v-128zm0-256h896v128h-896v-128zm0-256h896v128h-896v-128zm-448 768h384v128h-384v-128zm0-256h384v128h-384v-128zm0-256h384v128h-384v-128zm0-256h384v128h-384v-128z',
            },
            click: () => {
              this.toggleDeconvolvedPeaksHighlight()
            },
          })
        }

        modeBarButtons.push({
          title: 'Download as SVG',
          name: 'toImageSvg',
          icon: {
            width: 1792,
            height: 1792,
            path: 'M1152 1376v-160q0-14-9-23t-23-9h-96v-512q0-14-9-23t-23-9h-320q-14 0-23 9t-9 23v160q0 14 9 23t23 9h96v320h-96q-14 0-23 9t-9 23v160q0 14 9 23t23 9h320q14 0 23-9t9-23zm-128-896v-160q0-14-9-23t-23-9h-192q-14 0-23 9t-9 23v160q0 14 9 23t23 9h192q14 0 23-9t9-23zm640 416q0 209-103 385.5t-279.5 279.5-385.5 103-385.5-103-279.5-279.5-103-385.5 103-385.5 279.5-279.5 385.5-103 385.5 103 279.5 279.5 103 385.5z',
          },
          click: () => {
            const element = document.getElementById(this.id)
            if (element) {
              Plotly.downloadImage(element, {
                filename: this.effectiveTitle || 'plot',
                height: 400,
                width: 1200,
                format: 'svg',
              })
            }
          },
        })

        await Plotly.newPlot(this.id, this.traces, this.layout, {
          modeBarButtonsToRemove: ['toImage', 'sendDataToCloud'],
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          modeBarButtonsToAdd: modeBarButtons as any,
          scrollZoom: true,
          responsive: true,
        })

        // Update Streamlit iframe height after plot is rendered
        this.$nextTick(() => {
          if (this.args.height) {
            Streamlit.setFrameHeight(this.args.height)
          } else {
            Streamlit.setFrameHeight()
          }
        })

        // Add event listeners
        const plotElement = document.getElementById(this.id) as any
        if (plotElement) {
          plotElement.on('plotly_click', (eventData: any) => {
            this.onPlotClick(eventData)
          })

          plotElement.on('plotly_relayout', (eventData: any) => {
            this.onRelayout(eventData)
          })
        }
      } catch (error) {
        console.error('PlotlyLineplot: Error rendering plot:', error)
        this.renderFallback()
      }
    },

    onRelayout(eventData: any): void {
      // Handle zoom/pan events
      if (eventData['xaxis.range[0]'] !== undefined && eventData['xaxis.range[1]'] !== undefined) {
        const newXRange = [eventData['xaxis.range[0]'], eventData['xaxis.range[1]']]
        if (newXRange[0] < 0) {
          newXRange[0] = 0
        }
        this.manualXRange = newXRange
        // Reset auto-zoom tracking when user manually zooms
        this.lastAutoZoomedPeakIndex = undefined
        this.renderPlot()
      } else if (eventData['xaxis.autorange'] === true) {
        // Reset to auto range
        this.manualXRange = undefined
        this.lastAutoZoomedPeakIndex = undefined
        this.renderPlot()
      }
    },

    /**
     * Auto-zoom to show the selected peak's annotation if it's currently hidden.
     * Only triggers once per peak selection to allow manual zoom adjustments.
     */
    autoZoomToSelectedAnnotation(): void {
      const selectedIndex = this.selectedPeakIndex

      // Reset tracking if no selection
      if (selectedIndex === undefined) {
        this.lastAutoZoomedPeakIndex = undefined
        return
      }

      // Don't re-zoom for the same peak (allows user to manually adjust after auto-zoom)
      if (selectedIndex === this.lastAutoZoomedPeakIndex) {
        return
      }

      // Check if selected peak is annotated and its annotation is hidden
      if (!this.selectedAnnotationHidden) {
        return
      }

      // Calculate zoom range to show the annotation
      const newRange = this.calculateZoomForSelectedAnnotation()
      if (newRange) {
        this.manualXRange = newRange
        this.lastAutoZoomedPeakIndex = selectedIndex
      }
    },

    /**
     * Calculate a zoom range that would show the selected annotated peak's label
     * without overlapping with neighboring annotations.
     */
    calculateZoomForSelectedAnnotation(): number[] | undefined {
      const selectedIndex = this.selectedPeakIndex
      if (selectedIndex === undefined || !this.plotData) return undefined

      const peaks = this.annotatedPeaks
      const selectedPeak = peaks.find(p => p.index === selectedIndex)
      if (!selectedPeak) return undefined

      // Find distances to nearest annotated neighbors
      let leftNeighborDist = Infinity
      let rightNeighborDist = Infinity

      for (const peak of peaks) {
        if (peak.index === selectedIndex) continue
        const dist = peak.x - selectedPeak.x
        if (dist < 0 && -dist < leftNeighborDist) {
          leftNeighborDist = -dist
        } else if (dist > 0 && dist < rightNeighborDist) {
          rightNeighborDist = dist
        }
      }

      // Use the smaller distance to nearest neighbor for zoom calculation
      const minNeighborDist = Math.min(leftNeighborDist, rightNeighborDist)

      // Calculate range width that would prevent overlap
      // Box width formula: 2 * (1200 / actualWidth) * rangeWidth / scalingFactor
      // For no overlap: neighborDist > boxWidth + padding
      // Solving for rangeWidth that gives comfortable spacing
      const actualWidth = this.actualPlotWidth
      const scalingFactor = this.config.xPosScalingFactor

      let rangeWidth: number
      if (minNeighborDist < Infinity) {
        // Zoom aggressively to show just the selected peak and its immediate context
        // Use 2x the neighbor distance as the visible range
        rangeWidth = minNeighborDist * 2
      } else {
        // No annotated neighbors - zoom to show 20% of total data range
        const xValues = this.plotData.x_values
        const dataRange = Math.max(...xValues) - Math.min(...xValues)
        rangeWidth = dataRange * 0.2
      }

      // Center on selected peak, clamped to data bounds
      const xValues = this.plotData.x_values
      const minX = Math.min(...xValues)
      const maxX = Math.max(...xValues)

      let newLeft = selectedPeak.x - rangeWidth / 2
      let newRight = selectedPeak.x + rangeWidth / 2

      // Clamp to data bounds while maintaining range width
      if (newLeft < minX) {
        newLeft = minX
        newRight = Math.min(minX + rangeWidth, maxX)
      }
      if (newRight > maxX) {
        newRight = maxX
        newLeft = Math.max(maxX - rangeWidth, minX)
      }

      return [newLeft, newRight]
    },

    onPlotClick(eventData: any): void {
      if (!this.plotData) return
      if (!eventData.points || eventData.points.length === 0) return

      const point = eventData.points[0]
      const clickedX = point.x

      // In the charge sub-view, clicks do not re-drill (a back button restores
      // the deconv view) — match FLASHApp (onPlotClick only acts on deconv view).
      if (this.inChargeSubView) return

      // Find the nearest deconv peak to the clicked x position
      // (Plotly click returns a triplet index; we map back to the actual peak).
      const xValues = this.plotData.x_values
      let nearestIndex = 0
      let nearestDistance = Infinity
      for (let i = 0; i < xValues.length; i++) {
        const distance = Math.abs(xValues[i] - clickedX)
        if (distance < nearestDistance) {
          nearestDistance = distance
          nearestIndex = i
        }
      }

      // --- Charge-state drill-down (P0): clicking a deconv peak that carries
      // signal arrays switches to the "Augmented Annotated Spectrum" m/z sub-view.
      if (this.hasSignalDrilldown) {
        const pd = this.plotData
        const sigMz = pd.signal_mzs && (pd.signal_mzs[nearestIndex] as number[])
        if (sigMz && sigMz.length > 0) {
          this.selectedMassIndex = nearestIndex
          this.localTitle = 'Augmented Annotated Spectrum'
          this.manualXRange = undefined
          this.lastAutoZoomedPeakIndex = undefined
          this.renderPlot()
          // Fall through so the selection store is still updated for the click.
        }
      }

      // Only update selection if interactivity is configured.
      if (!this.interactivity || Object.keys(this.interactivity).length === 0) {
        return
      }

      // Update selection store using the interactivity mapping
      for (const [identifier, column] of Object.entries(this.interactivity)) {
        // Look for the interactivity column data (e.g., interactivity_peak_id)
        const columnKey = `interactivity_${column}`
        const columnValues = this.plotData[columnKey] as unknown[] | undefined

        if (columnValues && Array.isArray(columnValues) && nearestIndex < columnValues.length) {
          // Use the value from the interactivity column
          this.selectionStore.updateSelection(identifier, columnValues[nearestIndex])
        } else if (column === this.args.xColumn) {
          // Fallback: use x value if no interactivity column data
          this.selectionStore.updateSelection(identifier, xValues[nearestIndex])
        }
      }
    },

    /**
     * Restore the deconv view from the charge sub-view (FLASHApp back button).
     */
    backButton(): void {
      this.selectedMassIndex = undefined
      this.localTitle = undefined
      this.manualXRange = undefined
      this.lastAutoZoomedPeakIndex = undefined
      this.renderPlot()
    },

    /**
     * Toggle annotation visibility (FLASHApp "Hide/Show Annotations").
     */
    toggleAnnotations(): void {
      this.annotationsVisible = !this.annotationsVisible
      this.renderPlot()
    },

    /**
     * Toggle deconvolved-peaks highlighting (FLASHApp "Show Deconvolved Peaks").
     * When ON, the whole spectrum's x-range is shown (no auto-zoom-to-tag).
     */
    toggleDeconvolvedPeaksHighlight(): void {
      this.deconvolvedPeaksHighlightMode = !this.deconvolvedPeaksHighlightMode
      this.manualXRange = undefined
      this.lastAutoZoomedPeakIndex = undefined
      this.renderPlot()
    },

    getFallbackData(): Plotly.Data[] {
      return [
        {
          x: [0, 1],
          y: [0, 0],
          mode: 'lines',
          type: 'scatter',
          marker: { color: this.styling.unhighlightedColor },
          name: 'No Data',
        },
      ]
    },

    async renderFallback(): Promise<void> {
      try {
        const fallbackLayout: Partial<Plotly.Layout> = {
          title: { text: '<b>No Data Available</b>' },
          showlegend: false,
          height: 400,
          xaxis: { title: { text: 'X' }, showgrid: false },
          yaxis: { title: { text: 'Y' }, showgrid: true, rangemode: 'nonnegative' },
          paper_bgcolor: this.theme?.backgroundColor || 'white',
          plot_bgcolor: this.theme?.backgroundColor || 'white',
          font: {
            color: this.theme?.textColor || 'black',
            family: this.theme?.font || 'Arial',
          },
        }

        await Plotly.newPlot(this.id, this.getFallbackData(), fallbackLayout, {
          staticPlot: true,
        })
      } catch (error) {
        console.error('PlotlyLineplot: Failed to render fallback:', error)
      }
    },
  },
})
</script>

<style scoped>
.plot-container {
  position: relative;
  width: 100%;
  min-height: 100px;
}
</style>
