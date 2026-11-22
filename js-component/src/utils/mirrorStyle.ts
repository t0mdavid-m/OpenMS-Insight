/**
 * Dash style for the sticks of a mirror plot side that are not highlighted,
 * e.g. theoretical ions without a matching experimental peak.
 *
 * Read from the styling keys `topUnhighlightedDash` / `bottomUnhighlightedDash`
 * (any Plotly dash style: 'dot', 'dash', 'dashdot', 'longdash', '5px,3px', ...).
 * Unset, empty or 'solid' keep the stick solid and return undefined.
 */

import type Plotly from 'plotly.js-dist-min'

export function unhighlightedDash(styling: Record<string, unknown>, side: 'top' | 'bottom'): Plotly.Dash | undefined {
  const value = styling[side === 'top' ? 'topUnhighlightedDash' : 'bottomUnhighlightedDash']
  if (typeof value !== 'string') return undefined
  const dash = value.trim()
  return dash && dash !== 'solid' ? (dash as Plotly.Dash) : undefined
}
