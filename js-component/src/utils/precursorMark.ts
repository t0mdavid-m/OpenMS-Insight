/**
 * The precursor of a fragment spectrum on its m/z axis (LinePlot, and the top
 * half of MirrorPlot): a dashed line from the axis to the top of the plot at
 * the precursor's m/z, and "precursor 2+" in a box centered on its top. It is
 * drawn whether or not a peak is there, and it is part of the layout, so the
 * image download has it. Hovering the label shows the exact m/z.
 *
 * The page passes the precursor with the component's `precursor_mz` and
 * `precursor_charge`; nothing is drawn without it.
 */

import type Plotly from 'plotly.js-dist-min'

const FONT_SIZE = 11

export interface PrecursorMarkInput {
  precursor: { mz: number; charge: number } | null | undefined
  /** Top of the line in data units of the y axis (the top of the visible range). */
  yTop: number
  color: string
  background: string
}

export interface PrecursorMark {
  shapes: Partial<Plotly.Shape>[]
  annotations: Partial<Plotly.Annotations>[]
}

/** "precursor 2+", or "precursor" when the charge is unknown. */
export function precursorLabel(charge: number): string {
  return charge > 0 ? `precursor ${charge}+` : 'precursor'
}

export function precursorMark(input: PrecursorMarkInput): PrecursorMark {
  const { precursor, yTop, color, background } = input
  if (!precursor || !Number.isFinite(precursor.mz) || precursor.mz <= 0 || !(yTop > 0)) {
    return { shapes: [], annotations: [] }
  }
  const mz = precursor.mz
  const hover = `Precursor · m/z ${mz.toFixed(4)}${precursor.charge > 0 ? ` · ${precursor.charge}+` : ''}`
  return {
    shapes: [
      {
        name: 'precursor-mark',
        type: 'line',
        xref: 'x',
        yref: 'y',
        x0: mz,
        x1: mz,
        y0: 0,
        y1: yTop,
        layer: 'below',
        opacity: 0.7,
        line: { color, width: 1, dash: 'dash' },
      },
    ],
    annotations: [
      {
        // A tag centered on the line at its top, filled like the fragment
        // labels, so the line runs out of it rather than past its side
        xref: 'x',
        yref: 'y',
        x: mz,
        y: yTop,
        text: precursorLabel(precursor.charge),
        showarrow: false,
        xanchor: 'center',
        yanchor: 'top',
        align: 'center',
        font: { size: FONT_SIZE, color: background },
        bgcolor: color,
        borderpad: 3,
        hovertext: hover,
        captureevents: false,
      },
    ],
  }
}
