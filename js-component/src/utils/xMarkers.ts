/**
 * Labelled x markers on a LinePlot (x_markers).
 *
 * Each marker gets a dotted guide over the plot's height at its x, in its own
 * colour. With a tolerance, the most intense peak within it of the marker is
 * the marker's peak: it gets a dot in the marker colour, and the label sits
 * above it (at the guide's top for a marker without a peak, whose guide is
 * then fainter). Labels are left out where they would overlap a label already
 * placed, left to right, so zooming in shows more of them.
 */

import type Plotly from 'plotly.js-dist-min'

export interface XMarker {
  x: number
  label: string
  color?: string
}

export interface MarkerMatch extends XMarker {
  color: string
  /** Index of the matched peak, or undefined without one in tolerance. */
  index?: number
}

export interface MarkerOverlay {
  shapes: Partial<Plotly.Shape>[]
  annotations: Partial<Plotly.Annotations>[]
}

const FONT_SIZE = 11
/** Pixels kept between marker labels. */
const LABEL_GAP_PX = 3

/** A distinct colour per marker, evenly spaced around the hue circle. */
export function markerColor(i: number, n: number): string {
  const hue = Math.round((i * 360) / Math.max(n, 1) + 200) % 360
  return `hsl(${hue}, 70%, 45%)`
}

/** First index in `order` (x ascending) whose x is at or right of target. */
function lowerBound(x: ArrayLike<number>, order: ArrayLike<number>, target: number): number {
  let lo = 0
  let hi = order.length
  while (lo < hi) {
    const mid = (lo + hi) >> 1
    if (x[order[mid]] < target) lo = mid + 1
    else hi = mid
  }
  return lo
}

/** Peak indices sorted by x. */
export function sortedByX(x: ArrayLike<number>): Uint32Array {
  const order = new Uint32Array(x.length)
  for (let i = 0; i < order.length; i++) order[i] = i
  order.sort((a, b) => x[a] - x[b])
  return order
}

/**
 * Each marker with its colour and the most intense peak within `tolerance`
 * of it (no peak without a tolerance).
 */
export function matchMarkers(
  markers: XMarker[],
  x: ArrayLike<number>,
  y: ArrayLike<number>,
  order: ArrayLike<number>,
  tolerance: number | null | undefined,
): MarkerMatch[] {
  return markers.map((marker, i) => {
    const match: MarkerMatch = { ...marker, color: marker.color || markerColor(i, markers.length) }
    if (!tolerance || !(tolerance > 0)) return match
    let best = -Infinity
    for (let k = lowerBound(x, order, marker.x - tolerance); k < order.length; k++) {
      const j = order[k]
      if (x[j] > marker.x + tolerance) break
      if (y[j] > best) {
        best = y[j]
        match.index = j
      }
    }
    return match
  })
}

export interface MarkerOverlayInput {
  matches: MarkerMatch[]
  x: ArrayLike<number>
  y: ArrayLike<number>
  xRange: number[]
  yRange: number[]
  /** Width of the plot area, in pixels. */
  widthPx: number
  /** Whether markers are matched to peaks; unmatched guides are then fainter. */
  matching: boolean
  textWidth: (text: string, fontSize: number) => number
}

/** Guides and labels for the markers in the visible x range. */
export function markerOverlay(input: MarkerOverlayInput): MarkerOverlay {
  const { matches, x, y, xRange, yRange, widthPx } = input
  const span = xRange[1] - xRange[0]
  const shapes: Partial<Plotly.Shape>[] = []
  const annotations: Partial<Plotly.Annotations>[] = []
  if (!(span > 0) || widthPx <= 0) return { shapes, annotations }

  let labelRight = -Infinity
  for (const m of matches) {
    if (m.x < xRange[0] || m.x > xRange[1]) continue
    const matched = m.index !== undefined
    shapes.push({
      type: 'line',
      xref: 'x',
      yref: 'paper',
      x0: m.x,
      x1: m.x,
      y0: 0,
      y1: 1,
      line: { color: m.color, width: 1, dash: 'dot' },
      opacity: matched || !input.matching ? 0.9 : 0.45,
      layer: 'below',
    })
    if (!m.label) continue
    // The label sits over the marker's peak, or at the top without one
    const peakY = matched ? y[m.index as number] : undefined
    const labelX = matched ? x[m.index as number] : m.x
    const px = ((labelX - xRange[0]) / span) * widthPx
    const width = input.textWidth(m.label, FONT_SIZE)
    if (px - width / 2 < labelRight + LABEL_GAP_PX) continue
    labelRight = px + width / 2
    const onPeak = matched && (peakY as number) < yRange[1]
    annotations.push({
      x: labelX,
      y: onPeak ? (peakY as number) : 1,
      xref: 'x',
      yref: onPeak ? 'y' : 'paper',
      yanchor: onPeak ? 'bottom' : 'top',
      yshift: onPeak ? 6 : 0,
      text: m.label,
      showarrow: false,
      font: { size: FONT_SIZE, color: m.color },
      captureevents: false,
    })
  }

  return { shapes, annotations }
}

/** Dots on the markers' peaks, as a trace without hover or clicks. */
export function markerDots(
  matches: MarkerMatch[],
  x: ArrayLike<number>,
  y: ArrayLike<number>,
): Plotly.Data | undefined {
  const found = matches.filter((m) => m.index !== undefined)
  if (found.length === 0) return undefined
  return {
    x: found.map((m) => x[m.index as number]),
    y: found.map((m) => y[m.index as number]),
    type: 'scatter',
    mode: 'markers',
    marker: { color: found.map((m) => m.color), size: 7 },
    hoverinfo: 'skip',
    showlegend: false,
  }
}
