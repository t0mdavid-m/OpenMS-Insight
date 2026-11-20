/**
 * Keyboard navigation of a 2D plot: zoom, pan and reset.
 *
 * `+` / `=` zoom in, `-` zooms out (both by a factor of two, around the centre
 * of the view), the arrow keys pan by a quarter of the view, and `0` / Home
 * reset the axes. An axis the component fixes (`fixedrange`) is left alone,
 * so a spectrum whose y axis follows the visible peaks only zooms along m/z.
 *
 * `plotKeyAction` and `relayoutFor` are pure, so they can be tested and reused;
 * the toolbar (PlotToolbar.vue) applies the result with `Plotly.relayout`,
 * which goes through each component's own zoom handling.
 */

export type PlotKeyAction =
  | { kind: 'zoom'; factor: number }
  | { kind: 'pan'; axis: 'x' | 'y'; fraction: number }
  | { kind: 'reset' }

/** Zoom factor of one key press. */
export const ZOOM_FACTOR = 2
/** Share of the view one arrow key press pans by. */
export const PAN_FRACTION = 0.25

/** The part of a keyboard event that decides the action. */
export interface KeyLike {
  key: string
  ctrlKey?: boolean
  metaKey?: boolean
  altKey?: boolean
}

/** The action of a key, or null for a key the plot does not use. */
export function plotKeyAction(event: KeyLike): PlotKeyAction | null {
  // Shortcuts of the browser and the system keep working
  if (event.ctrlKey || event.metaKey || event.altKey) return null
  switch (event.key) {
    case '+':
    case '=':
      return { kind: 'zoom', factor: 1 / ZOOM_FACTOR }
    case '-':
    case '_':
      return { kind: 'zoom', factor: ZOOM_FACTOR }
    case 'ArrowLeft':
      return { kind: 'pan', axis: 'x', fraction: -PAN_FRACTION }
    case 'ArrowRight':
      return { kind: 'pan', axis: 'x', fraction: PAN_FRACTION }
    case 'ArrowUp':
      return { kind: 'pan', axis: 'y', fraction: PAN_FRACTION }
    case 'ArrowDown':
      return { kind: 'pan', axis: 'y', fraction: -PAN_FRACTION }
    case '0':
    case 'Home':
      return { kind: 'reset' }
    default:
      return null
  }
}

/** What `relayoutFor` reads of an axis of Plotly's full layout. */
export interface AxisLike {
  range?: unknown[]
  fixedrange?: boolean
  type?: string
}

const AXIS_NAME = /^([xy])axis\d*$/

/** The axes of a full layout that the keys can move, by their layout name. */
export function movableAxes(layout: Record<string, unknown>): Array<[string, 'x' | 'y', [number, number]]> {
  const axes: Array<[string, 'x' | 'y', [number, number]]> = []
  for (const [name, value] of Object.entries(layout)) {
    const match = AXIS_NAME.exec(name)
    if (!match || !value || typeof value !== 'object') continue
    const axis = value as AxisLike
    if (axis.fixedrange || axis.type === 'date' || axis.type === 'category' || axis.type === 'multicategory') continue
    const range = axis.range
    if (!Array.isArray(range) || range.length !== 2) continue
    const [lo, hi] = range.map(Number)
    if (!Number.isFinite(lo) || !Number.isFinite(hi) || lo === hi) continue
    axes.push([name, match[1] as 'x' | 'y', [lo, hi]])
  }
  return axes
}

/**
 * The `Plotly.relayout` update for a zoom or pan action on the plot whose full
 * layout is `layout` (`gd._fullLayout`), or null when no axis can move. Ranges
 * are in axis units, so a log axis zooms by decades as Plotly's own buttons do.
 */
export function relayoutFor(
  action: PlotKeyAction,
  layout: Record<string, unknown>,
): Record<string, number | boolean> | null {
  const update: Record<string, number | boolean> = {}
  for (const [name, letter, [lo, hi]] of movableAxes(layout)) {
    if (action.kind === 'reset') {
      update[`${name}.autorange`] = true
    } else if (action.kind === 'zoom') {
      const centre = (lo + hi) / 2
      const half = ((hi - lo) / 2) * action.factor
      update[`${name}.range[0]`] = centre - half
      update[`${name}.range[1]`] = centre + half
    } else {
      // Every axis is named, as a pan by drag does, so handlers that wait for
      // both ranges see this one too; only the axis of the key moves
      const shift = action.axis === letter ? (hi - lo) * action.fraction : 0
      update[`${name}.range[0]`] = lo + shift
      update[`${name}.range[1]`] = hi + shift
    }
  }
  if (action.kind === 'pan' && !movableAxes(layout).some(([, letter]) => letter === action.axis)) return null
  return Object.keys(update).length ? update : null
}

/** Whether a key event comes from a field the user types in. */
export function isTypingTarget(target: EventTarget | null): boolean {
  const element = target as HTMLElement | null
  if (!element || typeof element.tagName !== 'string') return false
  const tag = element.tagName.toLowerCase()
  return tag === 'input' || tag === 'textarea' || tag === 'select' || !!element.isContentEditable
}
