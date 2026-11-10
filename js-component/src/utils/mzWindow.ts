/**
 * A shaded x window on a spectrum, kept in the shared state under the
 * component's `window_identifier` (for example the m/z window of an XIC).
 *
 * The stored value is a centre, widened by the tolerance on each side, a
 * `[low, high]` pair, or nothing for no band.
 */

import type Plotly from "plotly.js-dist-min";

export type ToleranceUnit = "Da" | "ppm";

/** The stored value as `[low, high]`, or undefined for no band. */
export function windowRange(
  value: unknown,
  tolerance: number,
  unit: ToleranceUnit,
): [number, number] | undefined {
  if (typeof value === "number" && Number.isFinite(value)) {
    const half =
      unit === "ppm" ? (Math.abs(value) * tolerance) / 1e6 : tolerance;
    return half > 0 ? [value - half, value + half] : undefined;
  }
  if (Array.isArray(value) && value.length === 2) {
    const [a, b] = value.map(Number);
    if (!Number.isFinite(a) || !Number.isFinite(b) || a === b) return undefined;
    return a < b ? [a, b] : [b, a];
  }
  return undefined;
}

/** How the window reads in its label: `523.2711 ± 10 ppm` or `523.20–523.40`. */
export function windowText(
  value: unknown,
  range: [number, number],
  tolerance: number,
  unit: ToleranceUnit,
): string {
  if (typeof value === "number") {
    const t =
      unit === "ppm"
        ? `${Number(tolerance.toPrecision(4))} ppm`
        : `${Number(tolerance.toPrecision(4))}`;
    return `${value.toFixed(4)} ± ${t}`;
  }
  return `${range[0].toFixed(4)}–${range[1].toFixed(4)}`;
}

export interface WindowOverlay {
  shapes: Partial<Plotly.Shape>[];
  annotations: Partial<Plotly.Annotations>[];
}

/**
 * The band over the plot's height (at least `minWidthPx` wide, so a 10 ppm
 * window stays visible at full range) and its label at the top.
 */
export function windowOverlay(
  range: [number, number] | undefined,
  text: string,
  xRange: number[],
  widthPx: number,
  color: string,
  minWidthPx = 3,
): WindowOverlay {
  if (!range || !(xRange[1] > xRange[0]) || widthPx <= 0)
    return { shapes: [], annotations: [] };
  if (range[1] < xRange[0] || range[0] > xRange[1])
    return { shapes: [], annotations: [] };
  const centre = (range[0] + range[1]) / 2;
  const minHalf = ((xRange[1] - xRange[0]) / widthPx) * (minWidthPx / 2);
  const half = Math.max((range[1] - range[0]) / 2, minHalf);
  return {
    shapes: [
      {
        type: "rect",
        xref: "x",
        yref: "paper",
        x0: centre - half,
        x1: centre + half,
        y0: 0,
        y1: 1,
        fillcolor: color,
        opacity: 0.18,
        line: { width: 0 },
        layer: "below",
      },
    ],
    annotations: [
      {
        x: centre,
        y: 1,
        xref: "x",
        yref: "paper",
        yanchor: "bottom",
        text,
        showarrow: false,
        font: { size: 11, color },
        captureevents: false,
      },
    ],
  };
}
