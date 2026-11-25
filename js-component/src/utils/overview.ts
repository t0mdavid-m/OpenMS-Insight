/**
 * The overview of a zoomed heatmap (Heatmap ``overview=True``): a raster of the
 * whole map sent by Python (openms_insight/preprocessing/overview.py) and the
 * zoomed region framed on it.
 */

/** The raster: cells of 0 (empty) or 1..255, row by row from the lowest y up. */
export interface OverviewData {
  x: [number, number]
  y: [number, number]
  width: number
  height: number
  /** base64 of width * height bytes */
  cells: string
}

/** A region in data coordinates. */
export interface OverviewView {
  x: [number, number]
  y: [number, number]
}

export function decodeCells(cells: string): Uint8Array {
  const text = atob(cells)
  const bytes = new Uint8Array(text.length)
  for (let i = 0; i < text.length; i++) bytes[i] = text.charCodeAt(i)
  return bytes
}

const clamp01 = (v: number) => Math.max(0, Math.min(1, v))

/** Where `view` sits on the overview, as fractions of its frame (top from the highest y). */
export function viewBox(
  overview: OverviewData,
  view: OverviewView,
): { left: number; top: number; width: number; height: number } {
  const [xLo, xHi] = overview.x
  const [yLo, yHi] = overview.y
  const x0 = clamp01((Math.min(...view.x) - xLo) / (xHi - xLo))
  const x1 = clamp01((Math.max(...view.x) - xLo) / (xHi - xLo))
  const y0 = clamp01((Math.min(...view.y) - yLo) / (yHi - yLo))
  const y1 = clamp01((Math.max(...view.y) - yLo) / (yHi - yLo))
  return { left: x0, top: 1 - y1, width: x1 - x0, height: y1 - y0 }
}

/** `[lo, hi]` of width `size` centered on `center`, moved inside `[min, max]` where it fits. */
function centeredRange(center: number, size: number, min: number, max: number): [number, number] {
  let lo = center - size / 2
  if (size < max - min) lo = Math.max(min, Math.min(max - size, lo))
  return [lo, lo + size]
}

/**
 * `view` moved, at its size, so that it is centered on the point at fraction
 * (`fx`, `fy`) of the overview's frame (`fy` from the top).
 */
export function centeredView(overview: OverviewData, view: OverviewView, fx: number, fy: number): OverviewView {
  const [xLo, xHi] = overview.x
  const [yLo, yHi] = overview.y
  const cx = xLo + clamp01(fx) * (xHi - xLo)
  const cy = yHi - clamp01(fy) * (yHi - yLo)
  return {
    x: centeredRange(cx, Math.abs(view.x[1] - view.x[0]), xLo, xHi),
    y: centeredRange(cy, Math.abs(view.y[1] - view.y[0]), yLo, yHi),
  }
}
