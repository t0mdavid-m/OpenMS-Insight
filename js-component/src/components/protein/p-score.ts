// P-score of a fragment match: how likely it is to arise by chance.
//
// The P-score is the probability of matching at least `matched` of the
// `observed` fragment masses to the sequence by chance, under a Poisson model
// (Meng et al., Nat. Biotechnol. 2001). Here the chance that one
// observed mass hits a random theoretical fragment is the fraction of the mass
// range [0, mass] covered by the tolerance windows of all theoretical
// fragments, so the expected number of random matches is
// `observed * min(1, windowWidth / mass)`.
//
// The value can underflow a double (big proteins with many matches reach
// 1e-400), so it is computed and returned as log10.

export type PScore = {
  // log10 of the P-score (<= 0)
  log10: number
  // Expected number of random matches
  expected: number
}

const LN10 = Math.LN10

function logFactorial(n: number): number {
  let sum = 0
  for (let k = 2; k <= n; k++) sum += Math.log(k)
  return sum
}

// log of P(X >= n) for X ~ Poisson(lambda)
export function logPoissonTail(n: number, lambda: number): number {
  if (n <= 0) return 0
  if (lambda <= 0) return -Infinity
  if (lambda >= n) {
    // The tail holds most of the mass: 1 - P(X < n)
    let term = Math.exp(-lambda)
    let cdf = term
    for (let k = 1; k < n; k++) {
      term *= lambda / k
      cdf += term
    }
    if (cdf < 0.5) return Math.log(1 - cdf)
    // cdf near 1 loses precision; fall through to the direct sum
  }
  // Direct sum from k = n, relative to its first term
  const logFirst = -lambda + n * Math.log(lambda) - logFactorial(n)
  let ratio = 1
  let sum = 1
  for (let k = n + 1; k < n + 100000; k++) {
    ratio *= lambda / k
    sum += ratio
    if (ratio < sum * 1e-16) break
  }
  return Math.min(0, logFirst + Math.log(sum))
}

export function pScore(
  matched: number,
  observed: number,
  windowWidth: number,
  mass: number
): PScore | null {
  if (!(observed > 0) || !(mass > 0) || !(windowWidth >= 0)) return null
  const hitChance = Math.min(1, windowWidth / mass)
  const expected = observed * hitChance
  return { log10: logPoissonTail(matched, expected) / LN10, expected }
}

// e.g. "3.2e-45", or "1" when nothing matched
export function formatPScore(score: PScore): string {
  if (score.log10 >= -3) {
    const value = Math.pow(10, score.log10)
    return value >= 0.9995 ? '1' : value.toPrecision(2)
  }
  let exponent = Math.floor(score.log10)
  let mantissa = Math.pow(10, score.log10 - exponent)
  if (mantissa >= 9.95) {
    mantissa = 1
    exponent += 1
  }
  return `${mantissa.toFixed(1)}e${exponent}`
}
