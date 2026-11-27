/**
 * The "Top peaks" switch in the plot toolbar of the stick spectra (LinePlot,
 * MirrorPlot, DeconvolvedSpectrum).
 *
 * Switched on, the most intense peaks in the visible x range carry their x
 * value (the m/z of a spectrum) above the stick. The labels are placed again
 * on every zoom or pan: the most intense peaks come first, and a label that
 * would overlap one already placed is left out, so zooming in shows more of
 * them. The labels are part of the layout, so the image download has them.
 *
 * The component's `top_peak_labels` sets how many peaks are labelled (0
 * removes the button); `show_top_peak_labels` switches the labels on from
 * the start.
 */

import { onBeforeUnmount, reactive, ref, watch } from 'vue'
import type Plotly from 'plotly.js-dist-min'
import { ICONS, type PlotTool } from '@/utils/plotTools'

/** Class on the plot element while the labels are shown. */
const ACTIVE_CLASS = 'top-peaks-labelled'

const FONT_SIZE = 11
/** Space kept free around each label, in pixels. */
const GAP_PX = 3
/** Pixels between the top of a peak and its label. */
const LIFT_PX = 2
/** Peaks looked at per label before giving up (a crowded view stays cheap). */
const CANDIDATES_PER_LABEL = 50

export interface TopPeakLabelInput {
  x: ArrayLike<number>
  y: ArrayLike<number>
  xRange: number[]
  yRange: number[]
  /** Size of the plot area (inside the axes), in pixels. */
  widthPx: number
  heightPx: number
  /** Width of a label's text, in pixels. */
  textWidth: (text: string, fontSize: number) => number
  /** Peaks that already carry a label of another kind. */
  skip?: (index: number) => boolean
  color: string
}

/** The x value as shown on a label: 4 decimals below 10, else 2. */
export function formatPeakX(x: number): string {
  return Math.abs(x) < 10 ? x.toFixed(4) : x.toFixed(2)
}

/** Peak indices from the most to the least intense (ties: smaller x first). */
export function intensityOrder(x: ArrayLike<number>, y: ArrayLike<number>): Uint32Array {
  const order = new Uint32Array(y.length)
  for (let i = 0; i < order.length; i++) order[i] = i
  order.sort((a, b) => y[b] - y[a] || x[a] - x[b])
  return order
}

/**
 * The labels for the most intense peaks in view, at most `count` of them,
 * none overlapping another. `order` comes from `intensityOrder()`.
 */
export function placeTopPeakLabels(
  input: TopPeakLabelInput,
  order: Uint32Array,
  count: number,
): Partial<Plotly.Annotations>[] {
  const { x, y, xRange, yRange, widthPx, heightPx } = input
  const xSpan = xRange[1] - xRange[0]
  const ySpan = yRange[1] - yRange[0]
  if (count <= 0 || !(xSpan > 0) || !(ySpan > 0) || widthPx <= 0 || heightPx <= 0) return []

  const placed: Array<[number, number, number, number]> = []
  const labels: Partial<Plotly.Annotations>[] = []
  const textHeight = FONT_SIZE + 2
  const limit = count * CANDIDATES_PER_LABEL
  let looked = 0

  for (let k = 0; k < order.length && labels.length < count && looked < limit; k++) {
    const i = order[k]
    const px = x[i]
    const py = y[i]
    if (!(py > 0) || px < xRange[0] || px > xRange[1] || !Number.isFinite(px)) continue
    looked += 1
    if (input.skip?.(i)) continue

    const text = formatPeakX(px)
    const width = input.textWidth(text, FONT_SIZE)
    const cx = ((px - xRange[0]) / xSpan) * widthPx
    // Pixel y from the top of the plot area
    const bottom = heightPx - ((Math.min(py, yRange[1]) - yRange[0]) / ySpan) * heightPx - LIFT_PX
    const box: [number, number, number, number] = [
      cx - width / 2 - GAP_PX,
      bottom - textHeight - GAP_PX,
      cx + width / 2 + GAP_PX,
      bottom + GAP_PX,
    ]
    // Fully inside the plot area
    if (box[0] < 0 || box[2] > widthPx || box[1] < 0) continue
    const overlaps = placed.some(
      (p) => box[0] < p[2] && box[2] > p[0] && box[1] < p[3] && box[3] > p[1],
    )
    if (overlaps) continue

    placed.push(box)
    labels.push({
      x: px,
      y: py,
      xref: 'x',
      yref: 'y',
      yanchor: 'bottom',
      yshift: LIFT_PX,
      text,
      showarrow: false,
      font: { size: FONT_SIZE, color: input.color },
      captureevents: false,
    })
  }
  return labels
}

let measureCanvas: HTMLCanvasElement | null = null

/** Width of a label's text in pixels, measured on a canvas. */
export function canvasTextWidth(text: string, fontSize: number, font = 'Arial'): number {
  if (!measureCanvas) measureCanvas = document.createElement('canvas')
  const ctx = measureCanvas.getContext('2d')
  if (!ctx) return text.length * fontSize * 0.6
  ctx.font = `${fontSize}px ${font}`
  return ctx.measureText(text).width
}

/**
 * The labels of a spectrum drawn below the axis (y negated, as the lower half
 * of a mirror plot): placed as if above it, then flipped.
 */
export function mirrorBelow(labels: Partial<Plotly.Annotations>[]): Partial<Plotly.Annotations>[] {
  return labels.map((label) => ({
    ...label,
    y: -(label.y as number),
    yanchor: 'top',
    yshift: -LIFT_PX,
  }))
}

export function useTopPeakLabels(
  count: () => number,
  initial: () => boolean,
  help: () => string = () => 'show the m/z of the most intense peaks in view',
) {
  const on = ref(initial())
  let plotElement: HTMLElement | null = null
  // The intensity order of the last two peak sets (a mirror plot has two)
  let orders: { x: ArrayLike<number>; y: ArrayLike<number>; order: Uint32Array }[] = []

  function markActive(): void {
    plotElement?.classList.toggle(ACTIVE_CLASS, on.value && count() > 0)
  }

  const stopInitial = watch(initial, (value) => {
    on.value = value
  })
  watch(on, markActive)
  onBeforeUnmount(stopInitial)

  function toggle(): void {
    on.value = !on.value
  }

  /** Remember the plot element (after each draw) so it carries the state. */
  function bind(element: HTMLElement | null): void {
    plotElement = element
    markActive()
  }

  /** The labels to add to the layout (none while switched off). */
  function annotations(input: TopPeakLabelInput): Partial<Plotly.Annotations>[] {
    const n = count()
    if (!on.value || n <= 0 || !input.x || input.x.length === 0) return []
    // Sorted once per spectrum; zooming only walks the order again
    let hit = orders.find((entry) => entry.x === input.x && entry.y === input.y)
    if (!hit) {
      hit = { x: input.x, y: input.y, order: intensityOrder(input.x, input.y) }
      orders = [hit, ...orders].slice(0, 2)
    }
    return placeTopPeakLabels(input, hit.order, n)
  }

  /** The "Top peaks" switch of the plot toolbar (none when `count` is 0). */
  function tools(): PlotTool[] {
    if (count() <= 0) return []
    return [
      {
        id: 'top-peaks',
        group: 'annotate',
        icon: ICONS.number,
        label: 'Label top peaks',
        short: 'Top peaks',
        help: help(),
        active: on.value,
        run: toggle,
      },
    ]
  }

  return reactive({ on, toggle, bind, annotations, tools })
}
