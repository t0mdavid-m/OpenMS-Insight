/**
 * The precursor of a fragment spectrum on its m/z axis (LinePlot, and the top
 * half of MirrorPlot): a dashed line from the axis to the top of the plot at
 * the precursor's m/z, a small triangle and "precursor 2+" at its top. It is
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
        xref: 'x',
        yref: 'y',
        x: mz,
        y: yTop,
        text: '▼',
        showarrow: false,
        xanchor: 'center',
        yanchor: 'top',
        font: { size: FONT_SIZE - 2, color },
        hovertext: hover,
        captureevents: false,
      },
      {
        xref: 'x',
        yref: 'y',
        x: mz,
        y: yTop,
        xshift: 6,
        text: precursorLabel(precursor.charge),
        showarrow: false,
        xanchor: 'left',
        yanchor: 'top',
        font: { size: FONT_SIZE, color },
        bgcolor: background,
        hovertext: hover,
        captureevents: false,
      },
    ],
  }
}
