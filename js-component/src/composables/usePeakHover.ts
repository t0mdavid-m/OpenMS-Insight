/**
 * One hover read-out for every 2D plot: a dot on the point and a small box
 * with its values. `bind` serves stick spectra, `bindPoints` the plots where
 * Plotly's own picking fits (scatter, bars, lines).
 *
 * Stick spectra: the peak nearest the mouse along x.
 *
 * Plotly's own hover picks the nearest drawn point, and a stick is drawn as
 * three points (baseline, top, baseline), so over the lower part of a tall
 * peak it shows a neighbour's top or nothing at all. Here the mouse's x is
 * matched to the nearest peak by a binary search over the peaks sorted by x
 * (sorted once per spectrum), anywhere in the plot area's height; within two
 * pixels of the mouse the most intense peak wins, as that is the one drawn in a
 * dense profile spectrum. A small box beside the peak top shows its x and y. A dot marks the peak. Peaks more
 * than SNAP_PX pixels away from the mouse are not shown.
 */

import { onBeforeUnmount, reactive, ref } from 'vue'
import { plotPointPosition } from './usePeakLabels'

/** Peaks closer than this to the right edge get the box on their left. */
const FLIP_MARGIN_PX = 200
/** Farthest a peak may be from the mouse, in pixels along x. */
export const SNAP_PX = 12

export interface PeakHoverSource {
  x: ArrayLike<number> | undefined
  y: ArrayLike<number> | undefined
  /** Extra line for a peak, e.g. its annotation. */
  extra?: (index: number) => string | undefined
  xName: string
  yName: string
  /** -1 when the peaks are drawn below the axis (y negated), as in a mirror plot. */
  sign?: 1 | -1
  /** Which set of peaks this is (e.g. 'top' or 'bottom'), passed on by hitAt. */
  group?: string
}

/** Where the mouse is, for a source that depends on it (y in data units). */
export interface PeakHoverAt {
  y?: number
}

export interface PeakHoverTip {
  /** Peak top, relative to the container. */
  left: number
  top: number
  index: number
  lines: string[]
  /** Box to the left of the peak (near the right edge). */
  flip: boolean
}

/** Peak indices sorted by x (NaN last). */
export function xOrder(x: ArrayLike<number>): Uint32Array {
  const order = new Uint32Array(x.length)
  for (let i = 0; i < order.length; i++) order[i] = i
  order.sort((a, b) => {
    const xa = x[a]
    const xb = x[b]
    if (Number.isNaN(xa)) return Number.isNaN(xb) ? 0 : 1
    if (Number.isNaN(xb)) return -1
    return xa - xb
  })
  return order
}

/** Index of the peak whose x is nearest `target` (undefined when empty). */
export function nearestByX(
  x: ArrayLike<number>,
  order: Uint32Array,
  target: number,
): number | undefined {
  const n = finiteCount(x, order)
  if (n === 0) return undefined
  const lo = lowerBound(x, order, n, target)
  if (lo === n) return order[n - 1]
  // lo: first peak at or right of target; compare with its left neighbour
  if (lo > 0 && Math.abs(x[order[lo - 1]] - target) <= Math.abs(x[order[lo]] - target)) {
    return order[lo - 1]
  }
  return order[lo]
}

/**
 * The most intense peak with x within `halfWidth` of `target`, else the
 * nearest one. In a dense profile spectrum many peaks share a pixel, and the
 * tallest is the one drawn. At most MAX_SCAN peaks are looked at.
 */
export function peakAt(
  x: ArrayLike<number>,
  y: ArrayLike<number>,
  order: Uint32Array,
  target: number,
  halfWidth: number,
): number | undefined {
  const n = finiteCount(x, order)
  if (n === 0) return undefined
  const lo = lowerBound(x, order, n, target)
  let best: number | undefined
  let scanned = 0
  for (let k = lo - 1; k >= 0 && scanned < MAX_SCAN && target - x[order[k]] <= halfWidth; k--, scanned++) {
    if (best === undefined || y[order[k]] > y[best]) best = order[k]
  }
  scanned = 0
  for (let k = lo; k < n && scanned < MAX_SCAN && x[order[k]] - target <= halfWidth; k++, scanned++) {
    if (best === undefined || y[order[k]] > y[best]) best = order[k]
  }
  return best ?? nearestByX(x, order, target)
}

/** Peaks looked at on each side of the mouse. */
const MAX_SCAN = 5000
/**
 * The peak next to `current` along x: the next larger x for `step` 1, the
 * next smaller for -1 (equal x in index order). Only peaks `accept` lets
 * through count; undefined at the end of the data.
 */
export function stepIndex(
  x: ArrayLike<number>,
  order: Uint32Array,
  current: number,
  step: 1 | -1,
  accept: (index: number) => boolean = () => true,
): number | undefined {
  const at = order.indexOf(current)
  if (at < 0) return undefined
  for (let k = at + step; k >= 0 && k < order.length; k += step) {
    const index = order[k]
    if (Number.isNaN(x[index])) continue
    if (accept(index)) return index
  }
  return undefined
}

/** Half the width, in pixels, of the window where the tallest peak wins. */
export const PIXEL_WINDOW = 2

/** Number of leading non-NaN entries of `order` (NaN sorts last). */
function finiteCount(x: ArrayLike<number>, order: Uint32Array): number {
  let n = order.length
  while (n > 0 && Number.isNaN(x[order[n - 1]])) n -= 1
  return n
}

/** First position in `order` (of n) whose x is at or right of target. */
function lowerBound(x: ArrayLike<number>, order: Uint32Array, n: number, target: number): number {
  let lo = 0
  let hi = n
  while (lo < hi) {
    const mid = (lo + hi) >> 1
    if (x[order[mid]] < target) lo = mid + 1
    else hi = mid
  }
  return lo
}

/** x with 4 decimals; y rounded (4 significant digits below 100, exponent from 1e6). */
export function formatHoverValues(x: number, y: number): [string, string] {
  const ay = Math.abs(y)
  let ys: string
  if (ay >= 1e6 || (ay > 0 && ay < 0.01)) ys = y.toExponential(3)
  else if (ay >= 100) ys = Math.round(y).toLocaleString('en-US')
  else ys = String(Number(y.toPrecision(4)))
  return [x.toFixed(4), ys]
}

/** A point of a Plotly hover event (the fields bindPoints reads). */
export interface HoverPoint {
  x: unknown
  y: unknown
  curveNumber: number
  pointIndex?: number
  pointNumber?: number
  customdata?: unknown
  text?: unknown
  hovertext?: unknown
  data?: { name?: string; type?: string; orientation?: string }
  /** The point's box in client pixels (plotly.js 2.x). */
  bbox?: { x0: number; x1: number; y0: number; y1: number }
}

/** Lines of a Plotly hover text: split at <br>, tags and entities removed. */
export function textLines(text: unknown): string[] {
  if (text === undefined || text === null) return []
  return String(text)
    .split(/<br\s*\/?>/i)
    .map((line) =>
      line
        .replace(/<[^>]*>/g, '')
        .replace(/&nbsp;/g, ' ')
        .replace(/&lt;/g, '<')
        .replace(/&gt;/g, '>')
        .replace(/&amp;/g, '&')
        .trim(),
    )
    .filter((line) => line !== '')
}

/** A value for the box: numbers as formatHoverValues writes y, the rest as text. */
export function formatValue(value: unknown): string {
  if (typeof value === 'number') return formatHoverValues(0, value)[1]
  return String(value ?? '')
}

/** The box of a point: its hover text, else its x and y under the axis names. */
export function pointLines(point: HoverPoint, xName: string, yName: string): string[] {
  const text = textLines(point.hovertext ?? point.text)
  if (text.length > 0) return text
  return [`${xName} ${formatValue(point.x)}`, `${yName} ${formatValue(point.y)}`]
}

interface PlotEvents {
  on?: (name: string, handler: (event: never) => void) => void
  removeListener?: (name: string, handler: (event: never) => void) => void
}

interface PlotLayout {
  _size?: { l: number; t: number; w: number; h: number }
  xaxis?: { p2l?: (px: number) => number; l2p?: (v: number) => number }
  yaxis?: { p2l?: (px: number) => number }
}

export function usePeakHover() {
  const tip = ref<PeakHoverTip | null>(null)
  let element: HTMLElement | null = null
  let container: HTMLElement | null = null
  let source: (at: PeakHoverAt) => PeakHoverSource = () => ({
    x: undefined,
    y: undefined,
    xName: 'x',
    yName: 'y',
  })
  // The x order of the last two peak sets (a mirror plot alternates between two)
  let sorted: { x: ArrayLike<number>; order: Uint32Array }[] = []

  function orderOf(x: ArrayLike<number>): Uint32Array {
    const hit = sorted.find((entry) => entry.x === x)
    if (hit) return hit.order
    const order = xOrder(x)
    sorted = [{ x, order }, ...sorted].slice(0, 2)
    return order
  }
  let frame = 0
  let lastEvent: MouseEvent | null = null

  function hide(): void {
    tip.value = null
  }

  /** The plot area, the peaks drawn now and the mouse in plot pixels. */
  function locate(event: MouseEvent | null) {
    const layout = (element as unknown as { _fullLayout?: PlotLayout } | null)?._fullLayout
    const size = layout?._size
    const xaxis = layout?.xaxis
    if (!event || !element || !size || !xaxis?.p2l || !xaxis.l2p) return null
    const rect = element.getBoundingClientRect()
    const px = event.clientX - rect.left - size.l
    const py = event.clientY - rect.top - size.t
    if (px < 0 || px > size.w || py < 0 || py > size.h) return null
    const src = source({ y: layout?.yaxis?.p2l?.(py) })
    const { x, y } = src
    if (!x || !y || x.length === 0) return null

    const target = xaxis.p2l(px)
    const halfWidth = Math.abs(xaxis.p2l(px + PIXEL_WINDOW) - target)
    const index = peakAt(x, y, orderOf(x), target, halfWidth)
    if (index === undefined || Math.abs(xaxis.l2p(x[index]) - px) > SNAP_PX) return null
    return { index, x, y, src, size, rect }
  }

  /** Index of the peak the hover would show for this mouse event, if any. */
  function indexAt(event: MouseEvent): number | undefined {
    return locate(event)?.index
  }

  /** The peak the hover would show, with its source's group (mirror plots). */
  function hitAt(event: MouseEvent): { index: number; group?: string } | undefined {
    const found = locate(event)
    return found ? { index: found.index, group: found.src.group } : undefined
  }

  function update(): void {
    frame = 0
    const event = lastEvent
    // Hidden while a button is held (a zoom box or pan)
    if (!event || event.buttons !== 0) return hide()
    const found = locate(event)
    if (!found || !element) return hide()
    showTip(found.index, found.src)
  }

  /**
   * Show the box for peak `index`, without the mouse (keyboard stepping).
   * `at` picks the source of a plot with several (y below 0: the lower
   * spectrum of a mirror plot).
   */
  function showIndex(index: number, at: PeakHoverAt = {}): void {
    lastEvent = null
    showTip(index, source(at))
  }

  function showTip(index: number, src: PeakHoverSource): void {
    const layout = (element as unknown as { _fullLayout?: PlotLayout } | null)?._fullLayout
    const size = layout?._size
    const { x, y, extra, xName, yName } = src
    if (!element || !size || !x || !y || index < 0 || index >= x.length) return hide()
    const rect = element.getBoundingClientRect()

    const position = plotPointPosition(element, container, x[index], (src.sign ?? 1) * y[index])
    if (!position) return hide()
    const [xs, ys] = formatHoverValues(x[index], y[index])
    const lines = [`${xName} ${xs}`, `${yName} ${ys}`]
    const note = extra?.(index)
    if (note) lines.push(note)
    // Keep the dot inside the plot area for peaks beyond the visible y range
    const plotTop = rect.top - (container?.getBoundingClientRect().top ?? rect.top) + size.t
    const width = container?.clientWidth ?? rect.width
    tip.value = {
      left: position.left,
      top: Math.min(Math.max(position.top, plotTop), plotTop + size.h),
      index,
      lines,
      flip: position.left > width - FLIP_MARGIN_PX,
    }
  }

  /** Show the box at a position relative to the container. */
  function showAt(left: number, top: number, index: number, lines: string[]): void {
    const width = container?.clientWidth ?? element?.clientWidth ?? 0
    tip.value = { left, top, index, lines, flip: left > width - FLIP_MARGIN_PX }
  }

  let describePoint: (point: HoverPoint) => string[] | null | undefined = () => null

  /** Show the box for the point Plotly's hover picked. */
  function onPointHover(event: { points?: HoverPoint[] }): void {
    const point = event?.points?.[0]
    const lines = point ? describePoint(point) : null
    if (!point || !lines || lines.length === 0 || !element) return hide()
    const box = point.bbox
    let position: { left: number; top: number } | null = null
    if (box && Number.isFinite(box.x0) && Number.isFinite(box.y0)) {
      const origin = (container ?? element).getBoundingClientRect()
      const bar = point.data?.type === 'bar'
      const horizontal = point.data?.orientation === 'h'
      position = {
        // A bar's box is the bar: the dot goes on its end
        left: (bar && horizontal ? Math.max(box.x0, box.x1) : (box.x0 + box.x1) / 2) - origin.left,
        top: (bar && !horizontal ? Math.min(box.y0, box.y1) : (box.y0 + box.y1) / 2) - origin.top,
      }
    } else if (typeof point.x === 'number' && typeof point.y === 'number') {
      position = plotPointPosition(element, container, point.x, point.y)
    }
    if (!position) return hide()
    showAt(position.left, position.top, point.pointIndex ?? point.pointNumber ?? -1, lines)
  }

  /**
   * Show the box for the point Plotly's own hover picks (traces drawn with
   * `hoverinfo: 'none'`, so Plotly still picks and clicks but draws no label).
   * `describe` gives the box's lines, or nothing to show none.
   */
  function bindPoints(
    plotElement: HTMLElement | null,
    root: HTMLElement | null,
    describe: (point: HoverPoint) => string[] | null | undefined,
  ): void {
    describePoint = describe
    container = root
    if (!plotElement) return
    if (plotElement !== element) {
      unbind()
      element = plotElement
      element.addEventListener('mouseleave', onLeave)
      element.addEventListener('mousedown', hide)
      element.addEventListener('wheel', hide, { passive: true })
    }
    // Again on every call: Plotly.newPlot drops the listeners of the element
    const plot = plotElement as unknown as PlotEvents
    plot.removeListener?.('plotly_hover', onPointHover)
    plot.removeListener?.('plotly_unhover', hide)
    plot.on?.('plotly_hover', onPointHover)
    plot.on?.('plotly_unhover', hide)
  }

  function onMove(event: MouseEvent): void {
    lastEvent = event
    if (!frame) frame = requestAnimationFrame(update)
  }

  function onLeave(): void {
    lastEvent = null
    if (frame) cancelAnimationFrame(frame)
    frame = 0
    hide()
  }

  /**
   * Follow the mouse over a plot element (once per element). `getSource`
   * gives the peaks drawn now.
   */
  function bind(
    plotElement: HTMLElement | null,
    root: HTMLElement | null,
    getSource: (at: PeakHoverAt) => PeakHoverSource,
  ): void {
    source = getSource
    container = root
    if (!plotElement || plotElement === element) return
    unbind()
    element = plotElement
    element.addEventListener('mousemove', onMove)
    element.addEventListener('mouseleave', onLeave)
    element.addEventListener('mousedown', hide)
    element.addEventListener('wheel', hide, { passive: true })
  }

  function unbind(): void {
    if (!element) return
    const plot = element as unknown as PlotEvents
    plot.removeListener?.('plotly_hover', onPointHover)
    plot.removeListener?.('plotly_unhover', hide)
    element.removeEventListener('mousemove', onMove)
    element.removeEventListener('mouseleave', onLeave)
    element.removeEventListener('mousedown', hide)
    element.removeEventListener('wheel', hide)
    element = null
  }

  onBeforeUnmount(() => {
    if (frame) cancelAnimationFrame(frame)
    unbind()
  })

  return reactive({ tip, bind, bindPoints, hide, indexAt, hitAt, showIndex })
}
