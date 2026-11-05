/**
 * Matching an m/z difference between two peaks against amino-acid residue
 * masses. Pure functions only, so they can be checked without a browser.
 */

/**
 * Monoisotopic residue masses (Da) of the 20 standard amino acids. Isoleucine
 * and leucine are isobaric and share one entry.
 */
export const STANDARD_RESIDUE_MASSES: Readonly<Record<string, number>> = {
  G: 57.02146,
  A: 71.03711,
  S: 87.03203,
  P: 97.05276,
  V: 99.06841,
  T: 101.04768,
  C: 103.00919,
  'I/L': 113.08406,
  N: 114.04293,
  D: 115.02694,
  Q: 128.05858,
  K: 128.09496,
  E: 129.04259,
  M: 131.04049,
  H: 137.05891,
  F: 147.06841,
  R: 156.10111,
  Y: 163.06333,
  W: 186.07931,
}

/** Charges at which a difference is compared with the residue masses. */
export const MEASURE_CHARGES = [1, 2] as const

export interface ResidueMatch {
  name: string
  mass: number
  charge: number
  /** Absolute mass error in Da (|delta * charge - mass|). */
  error: number
}

/**
 * Residues whose mass matches `delta` (an m/z difference, positive or
 * negative). A match at charge z means |delta| * z is within `2 * tolerance`
 * of the residue mass: each of the two peaks may be off by `tolerance`.
 * Matches are ordered by charge, then by mass error.
 */
export function matchResidues(
  delta: number,
  tolerance: number,
  extraResidues: Record<string, number> = {},
): ResidueMatch[] {
  const absDelta = Math.abs(delta)
  if (!Number.isFinite(absDelta) || absDelta === 0) return []
  const window = 2 * Math.max(tolerance, 0)
  const table: Record<string, number> = { ...STANDARD_RESIDUE_MASSES, ...extraResidues }
  const matches: ResidueMatch[] = []
  for (const charge of MEASURE_CHARGES) {
    const neutral = absDelta * charge
    const atCharge: ResidueMatch[] = []
    for (const [name, mass] of Object.entries(table)) {
      const error = Math.abs(neutral - mass)
      if (error <= window) atCharge.push({ name, mass, charge, error })
    }
    atCharge.sort((a, b) => a.error - b.error || a.mass - b.mass)
    matches.push(...atCharge)
  }
  return matches
}

/**
 * Label of a measurement: "Δm/z 128.059", followed by the matches if any,
 * e.g. "Δm/z 128.059 ≈ Q/K" or "Δm/z 28.511 ≈ G (2+)".
 */
export function formatMeasureLabel(delta: number, matches: ResidueMatch[]): string {
  const base = `Δm/z ${Math.abs(delta).toFixed(3)}`
  if (matches.length === 0) return base
  const parts: string[] = []
  for (const charge of MEASURE_CHARGES) {
    const names = matches.filter((m) => m.charge === charge).map((m) => m.name)
    if (names.length === 0) continue
    parts.push(charge === 1 ? names.join('/') : `${names.join('/')} (${charge}+)`)
  }
  return `${base} ≈ ${parts.join(', ')}`
}
