/**
 * Go to: the plot toolbar's form for an exact range of each axis, e.g.
 * RT 25.0 to 26.5 and m/z 400 to 450 on a peak map.
 *
 * The form starts with the ranges in view. An axis whose two fields are both
 * left empty keeps its range. The plot is relayouted with the
 * `xaxis.range[0]`-style keys a mouse zoom sends, so every component follows
 * it as it follows the mouse (Heatmap levels, zoom identifiers).
 */

/** One axis of the form: its layout name, label and range in view. */
export interface GoToAxis {
  name: string
  label: string
  low: number
  high: number
}

/** What the user typed for an axis. */
export interface GoToInput {
  low: string
  high: string
}

const AXIS = /^[xy]axis\d*$/

/** The text of an axis title without markup (`<b>m/z</b>` → `m/z`). */
function plainTitle(title: unknown): string {
  const text = typeof title === 'string' ? title : (title as { text?: unknown } | undefined)?.text
  return typeof text === 'string' ? text.replace(/<[^>]*>/g, '').trim() : ''
}

/** The numeric axes of a drawn plot, x before y, from its `_fullLayout`. */
export function goToAxes(fullLayout: Record<string, unknown> | undefined): GoToAxis[] {
  if (!fullLayout) return []
  const axes: GoToAxis[] = []
  for (const [name, value] of Object.entries(fullLayout)) {
    if (!AXIS.test(name) || !value || typeof value !== 'object') continue
    const axis = value as { range?: unknown; type?: unknown; visible?: unknown; title?: unknown }
    if (axis.visible === false) continue
    if (axis.type !== undefined && axis.type !== 'linear' && axis.type !== '-') continue
    if (!Array.isArray(axis.range) || axis.range.length !== 2) continue
    const low = Number(axis.range[0])
    const high = Number(axis.range[1])
    if (!Number.isFinite(low) || !Number.isFinite(high)) continue
    axes.push({ name, label: plainTitle(axis.title) || name.replace('axis', ''), low, high })
  }
  return axes.sort((a, b) => a.name.localeCompare(b.name))
}

/** A field's number, or null when it is empty; NaN when it is not a number. */
function parse(text: string): number | null {
  const trimmed = text.trim()
  if (trimmed === '') return null
  return Number(trimmed.replace(',', '.'))
}

/** Put `[a, b]` into `update` in the axis's direction (a reversed axis stays reversed). */
function setRange(update: Record<string, number>, axis: GoToAxis, a: number, b: number): void {
  const reversed = axis.low > axis.high
  update[`${axis.name}.range[0]`] = reversed ? Math.max(a, b) : Math.min(a, b)
  update[`${axis.name}.range[1]`] = reversed ? Math.min(a, b) : Math.max(a, b)
}

/**
 * The relayout for the typed ranges, or the reason it cannot be applied.
 * Reversed bounds are swapped; both bounds of an axis must be given, or
 * neither (that axis keeps its range).
 */
export function goToRelayout(
  axes: GoToAxis[],
  inputs: Record<string, GoToInput>,
): { update: Record<string, number> } | { error: string } {
  const update: Record<string, number> = {}
  for (const axis of axes) {
    const input = inputs[axis.name]
    if (!input) continue
    const low = parse(input.low)
    const high = parse(input.high)
    if (low === null && high === null) continue
    if (low === null || high === null) return { error: `${axis.label}: give both bounds, or neither` }
    if (!Number.isFinite(low) || !Number.isFinite(high)) return { error: `${axis.label}: not a number` }
    if (low === high) return { error: `${axis.label}: the bounds are equal` }
    setRange(update, axis, low, high)
  }
  if (!Object.keys(update).length) return { error: 'Type a range' }
  // A Heatmap reads a zoom only with both axes: fill in the ranges in view
  for (const axis of axes) {
    if (!(`${axis.name}.range[0]` in update)) setRange(update, axis, axis.low, axis.high)
  }
  return { update }
}

/** The text a field starts with: the bound in view, rounded to what the axis span shows. */
export function formatBound(value: number, low: number, high: number): string {
  const span = Math.abs(high - low)
  const decimals = span > 0 ? Math.min(6, Math.max(0, 3 - Math.floor(Math.log10(span)))) : 4
  return String(Number(value.toFixed(decimals)))
}
