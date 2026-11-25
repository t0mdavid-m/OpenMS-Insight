/**
 * Placement of point labels (Plotly annotations with a leader line) so that a
 * label's box covers neither another point nor another label.
 *
 * Positions are in pixels of the plot area: x to the right, y downwards, the
 * way Plotly's `ax`/`ay` offsets count.
 */

export interface LabelRequest {
  /** Pixel position of the labelled point. */
  px: number
  py: number
  text: string
}

export interface LabelOffset {
  ax: number
  ay: number
}

/** Offsets tried in order: above, below, the four diagonals, then the sides. */
const CANDIDATES: LabelOffset[] = [
  { ax: 0, ay: -25 },
  { ax: 0, ay: 25 },
  { ax: -45, ay: -22 },
  { ax: 45, ay: -22 },
  { ax: -45, ay: 22 },
  { ax: 45, ay: 22 },
  { ax: 0, ay: -45 },
  { ax: 0, ay: 45 },
]

/** Size of a label's box for a font of `fontSize` px (Plotly's borderpad included). */
export function labelBox(text: string, fontSize = 10): { w: number; h: number } {
  return { w: text.length * fontSize * 0.6 + 8, h: fontSize + 8 }
}

interface Box { x0: number; x1: number; y0: number; y1: number }

function overlaps(a: Box, b: Box): boolean {
  return a.x0 < b.x1 && b.x0 < a.x1 && a.y0 < b.y1 && b.y0 < a.y1
}

/**
 * Offsets for `labels`, placed in order (most important first). Every
 * point in `points` (the labelled ones included) is kept clear by
 * `pointRadius` px; a label that fits nowhere keeps the first candidate.
 */
export function placeLabels(
  labels: LabelRequest[],
  points: Array<{ px: number; py: number }>,
  plotWidth: number,
  plotHeight: number,
  pointRadius = 7,
  fontSize = 10,
): LabelOffset[] {
  const placed: Box[] = []
  return labels.map((label) => {
    const { w, h } = labelBox(label.text, fontSize)
    const boxFor = (o: LabelOffset): Box => {
      const cx = label.px + o.ax
      const cy = label.py + o.ay
      return { x0: cx - w / 2, x1: cx + w / 2, y0: cy - h / 2, y1: cy + h / 2 }
    }
    const fits = (box: Box): boolean => {
      if (box.x0 < 0 || box.x1 > plotWidth || box.y0 < -20 || box.y1 > plotHeight) return false
      for (const p of points) {
        const dot = { x0: p.px - pointRadius, x1: p.px + pointRadius, y0: p.py - pointRadius, y1: p.py + pointRadius }
        if (overlaps(box, dot)) return false
      }
      return !placed.some((other) => overlaps(box, other))
    }
    const chosen = CANDIDATES.find((o) => fits(boxFor(o))) ?? CANDIDATES[0]
    placed.push(boxFor(chosen))
    return chosen
  })
}
