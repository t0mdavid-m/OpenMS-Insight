/**
 * Zoom history of a plot: the toolbar's Back button returns to the zoom before
 * the last one, step by step, as far back as the full view.
 *
 * A view is the range of each x / y axis, or "auto" while the axis shows its
 * full extent. Every zoom, pan or reset (by mouse, toolbar or keys) reaches
 * the plot as a `plotly_relayout` event; the view before it is kept, unless the
 * event follows the last kept one within `SETTLE_MS` (a component that fits
 * the y axis to a new x range answers a zoom with a relayout of its own, and
 * the two are one step). The view is followed through relayout events only:
 * Plotly emits `plotly_afterplot` of a relayout before `plotly_relayout`, so a
 * view read at afterplot would already be the new one.
 *
 * Going back relayouts the plot with `xaxis.range[0]`-style keys, or
 * `xaxis.autorange` for the full extent, the way a mouse zoom and a
 * double-click do, so every component follows it as it follows the mouse
 * (Heatmap levels, zoom identifiers in the shared state).
 */

export interface AxisView {
  auto: boolean
  range: [number, number]
}

/** Axis name (`xaxis`, `yaxis`, `xaxis2`, ...) to its view. */
export type View = Record<string, AxisView>

/** At most this many views are kept; older ones are dropped. */
export const MAX_HISTORY = 50

/** Relayouts within this many milliseconds of a kept view count as the same step. */
export const SETTLE_MS = 400

const AXIS = /^[xy]axis\d*$/
const ZOOM_KEY = /^([xy]axis\d*)\.(range(\[[01]\])?|autorange)$/

/** The view of a drawn plot, read from its `_fullLayout`. */
export function readView(fullLayout: Record<string, unknown> | undefined): View {
  const view: View = {}
  if (!fullLayout) return view
  for (const [name, axis] of Object.entries(fullLayout)) {
    if (!AXIS.test(name) || !axis || typeof axis !== 'object') continue
    const { range, autorange } = axis as { range?: unknown; autorange?: unknown }
    if (!Array.isArray(range) || range.length !== 2) continue
    const lo = Number(range[0])
    const hi = Number(range[1])
    if (!Number.isFinite(lo) || !Number.isFinite(hi)) continue
    view[name] = { auto: autorange === true || autorange === 'reversed', range: [lo, hi] }
  }
  return view
}

/** Whether a relayout event changed an axis range (zoom, pan, reset, autoscale). */
export function isZoomEvent(event: Record<string, unknown> | undefined): boolean {
  if (!event) return false
  return Object.keys(event).some((key) => ZOOM_KEY.test(key))
}

/** Two views show the same: the same axes, each auto in both or with ranges equal to 1e-9 of their span. */
export function sameView(a: View, b: View): boolean {
  const names = Object.keys(a)
  if (names.length !== Object.keys(b).length) return false
  return names.every((name) => {
    const p = a[name]
    const q = b[name]
    if (!q) return false
    if (p.auto || q.auto) return p.auto === q.auto
    const tol = Math.abs(p.range[1] - p.range[0]) * 1e-9
    return Math.abs(p.range[0] - q.range[0]) <= tol && Math.abs(p.range[1] - q.range[1]) <= tol
  })
}

/** The relayout that shows `view` again. */
export function relayoutFor(view: View): Record<string, unknown> {
  const update: Record<string, unknown> = {}
  for (const [name, axis] of Object.entries(view)) {
    if (axis.auto) {
      update[`${name}.autorange`] = true
    } else {
      update[`${name}.range[0]`] = axis.range[0]
      update[`${name}.range[1]`] = axis.range[1]
    }
  }
  return update
}

/**
 * The kept views of one plot. `observe` takes every relayout event with the
 * view the plot shows after it; `back` returns the view to show, if any.
 */
export class ZoomHistory {
  private views: View[] = []
  private current: View | null = null
  private keptAt = -Infinity
  private restoring = false

  /** Views Back can return to. */
  get size(): number {
    return this.views.length
  }

  /** The plot was drawn (again): its view becomes the current one without a step. */
  reset(view: View): void {
    this.current = view
  }

  /** A relayout event, with the view after it; `now` in milliseconds. */
  observe(event: Record<string, unknown> | undefined, view: View, now: number): void {
    const before = this.current
    this.current = view
    if (this.restoring) {
      // The plot's own answer to the restored view (a fitted y axis) is no step either
      this.restoring = false
      this.keptAt = now
      return
    }
    if (!before || !isZoomEvent(event) || sameView(before, view)) return
    if (now - this.keptAt < SETTLE_MS) return
    this.views.push(before)
    if (this.views.length > MAX_HISTORY) this.views.shift()
    this.keptAt = now
  }

  /** The view before the last step, removed from the history; null when there is none. */
  back(): View | null {
    const view = this.views.pop()
    if (!view) return null
    this.restoring = true
    return view
  }

  /** The relayout that `back` started did not happen (no plot): nothing to skip. */
  cancelRestore(): void {
    this.restoring = false
  }

  clear(): void {
    this.views = []
    this.keptAt = -Infinity
  }
}
