/**
 * Relative intensities: the values as a percentage of the highest one, as the
 * Relative switch of LinePlot shows them (relative_intensity).
 */

/** Each value as % of the highest finite one; unchanged when none is above 0. */
export function relativeValues(values: number[]): number[] {
  let max = 0
  for (const v of values) if (Number.isFinite(v) && v > max) max = v
  if (max <= 0) return values
  return values.map((v) => (v / max) * 100)
}

/** The y axis title in relative mode: "Intensity (cps)" becomes "Relative intensity (%)". */
export function relativeLabel(label: string | undefined): string {
  const base = (label || 'Intensity').replace(/\s*\([^)]*\)\s*$/, '').trim() || 'Intensity'
  return `Relative ${base.charAt(0).toLowerCase()}${base.slice(1)} (%)`
}
