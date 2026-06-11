/**
 * Custom Tabulator formatters for statistical and scientific data display.
 *
 * These formatters extend Tabulator's built-in formatters with support for:
 * - Scientific notation (exponential format)
 * - Signed numbers (explicit +/- prefix)
 * - Badge/pill display for categorical values
 */

import type { CellComponent } from 'tabulator-tables'

/**
 * Base type for formatter parameters.
 * Tabulator doesn't export FormatterParams, so we define our own base.
 */
export interface BaseFormatterParams {
  [key: string]: unknown
}

/**
 * Parameters for the scientific notation formatter.
 */
export interface ScientificFormatterParams extends BaseFormatterParams {
  /** Number of significant digits (default: 3) */
  precision?: number
}

/**
 * Parameters for the signed number formatter.
 */
export interface SignedFormatterParams extends BaseFormatterParams {
  /** Number of decimal places (default: 3) */
  precision?: number
  /** Whether to show sign for positive numbers (default: true) */
  showPositive?: boolean
}

/**
 * Parameters for the badge formatter.
 */
export interface BadgeFormatterParams extends BaseFormatterParams {
  /** Map of value -> color for badges */
  colorMap?: Record<string, string>
  /** Default color if value not in colorMap (default: #888) */
  defaultColor?: string
  /** Text color (default: white) */
  textColor?: string
}

/**
 * Parameters for the fixed-decimals formatter.
 */
export interface FixedFormatterParams extends BaseFormatterParams {
  /** Number of decimal places to render (default: 4) */
  precision?: number
  /**
   * Only reformat when the value's string representation is longer than this
   * (default: 4). Shorter representations (e.g. "12", "1.5", "-1", "100") are
   * returned untouched with no trailing-zero padding. Set to 0 for an
   * unconditional toFixed().
   */
  minLength?: number
}

/**
 * Parameters for the placeholder (sentinel-substitution) formatter.
 */
export interface PlaceholderFormatterParams extends BaseFormatterParams {
  /** Values that should be replaced by `text` (default: [-1]) */
  sentinels?: Array<number | string>
  /** Replacement text rendered when a sentinel matches (default: "-") */
  text?: string
  /** Use loose (==) comparison when true, strict (===) when false (default: true) */
  loose?: boolean
}

/**
 * Type for custom formatter functions.
 * Matches Tabulator's formatter signature. The return type includes `number`
 * because passthrough formatters (e.g. `fixed`, `placeholder`) may return the
 * raw cell value untouched when their guard/sentinel does not apply; Tabulator
 * renders such values directly.
 */
export type CustomFormatterFunction = (
  cell: CellComponent,
  params: BaseFormatterParams,
  onRendered?: (callback: () => void) => void
) => string | number | HTMLElement

/**
 * Format a number in scientific (exponential) notation.
 *
 * Example: 0.0000123 -> "1.23e-05"
 *
 * @param cell - Tabulator cell component
 * @param params - Formatter parameters
 * @param params.precision - Number of significant digits (default: 3)
 */
export function scientificFormatter(
  cell: CellComponent,
  params: ScientificFormatterParams
): string {
  const value = cell.getValue()

  if (value === null || value === undefined || value === '') {
    return ''
  }

  const num = Number(value)
  if (isNaN(num)) {
    return String(value)
  }

  const precision = params.precision ?? 3
  // toExponential takes digits after decimal, so precision-1
  return num.toExponential(Math.max(0, precision - 1))
}

/**
 * Format a number with explicit sign prefix.
 *
 * Example: 1.234 -> "+1.234", -1.234 -> "-1.234"
 *
 * @param cell - Tabulator cell component
 * @param params - Formatter parameters
 * @param params.precision - Number of decimal places (default: 3)
 * @param params.showPositive - Show + for positive numbers (default: true)
 */
export function signedFormatter(
  cell: CellComponent,
  params: SignedFormatterParams
): string {
  const value = cell.getValue()

  if (value === null || value === undefined || value === '') {
    return ''
  }

  const num = Number(value)
  if (isNaN(num)) {
    return String(value)
  }

  const precision = params.precision ?? 3
  const showPositive = params.showPositive !== false

  const formatted = num.toFixed(precision)

  if (num > 0 && showPositive) {
    return '+' + formatted
  }

  return formatted
}

/**
 * Format a value as a colored badge/pill.
 *
 * Useful for categorical data like significance status.
 *
 * Example: "Up-regulated" -> <span class="badge" style="background:#E74C3C">Up-regulated</span>
 *
 * @param cell - Tabulator cell component
 * @param params - Formatter parameters
 * @param params.colorMap - Map of value -> color
 * @param params.defaultColor - Fallback color (default: #888)
 * @param params.textColor - Text color (default: white)
 */
export function badgeFormatter(
  cell: CellComponent,
  params: BadgeFormatterParams
): string {
  const value = cell.getValue()

  if (value === null || value === undefined || value === '') {
    return ''
  }

  const stringValue = String(value)
  const colorMap = params.colorMap || {}
  const defaultColor = params.defaultColor || '#888888'
  const textColor = params.textColor || 'white'

  const backgroundColor = colorMap[stringValue] || defaultColor

  return `<span style="
    display: inline-block;
    padding: 2px 8px;
    border-radius: 12px;
    background-color: ${backgroundColor};
    color: ${textColor};
    font-size: 12px;
    font-weight: 500;
    line-height: 1.4;
  ">${stringValue}</span>`
}

/**
 * Format a number with a fixed number of decimal places, but only when its
 * string representation is "long enough".
 *
 * Reproduces the original `toFixedFormatter(decimalPlaces = 4)`: short values
 * (string length <= minLength, e.g. "12", "1.5", "-1", "100") are returned
 * UNCHANGED (no trailing-zero padding); longer numeric values are truncated to
 * `precision` decimals via Number.toFixed(precision). Non-numeric / empty values
 * pass through untouched. This is fixed-decimals-with-min-length-guard, NOT a
 * plain toFixed.
 *
 * Examples (defaults precision=4, minLength=4):
 *   12         -> 12          (len 2, unchanged)
 *   1.5        -> 1.5         (len 3, unchanged)
 *   -1         -> -1          (len 2, unchanged)
 *   1234.56789 -> "1234.5679" (len > 4, 4 dp)
 *
 * @param cell - Tabulator cell component
 * @param params - Formatter parameters
 * @param params.precision - Number of decimal places (default: 4)
 * @param params.minLength - Min string length before reformatting (default: 4)
 */
export function fixedFormatter(
  cell: CellComponent,
  params: FixedFormatterParams
): string | number {
  const value: unknown = cell.getValue()

  if (value === null || value === undefined || value === '') {
    return ''
  }

  const precision = params.precision ?? 4
  const minLength = params.minLength ?? 4

  if (String(value).length > minLength) {
    const num = Number(value)
    if (!isNaN(num)) {
      return num.toFixed(precision)
    }
  }

  // Guard not satisfied (or non-numeric): return the raw value untouched.
  return value as string | number
}

/**
 * Replace sentinel "missing value" markers with placeholder text.
 *
 * Generalizes the inline `value == -1 ? '-' : value` formatter: if the cell
 * value matches any configured sentinel, render `text`; otherwise render the
 * raw value unchanged.
 *
 * Examples (defaults sentinels=[-1], text="-", loose=true):
 *   -1   -> "-"
 *   5    -> 5
 *   "-1" -> "-"   (loose ==)
 *
 * @param cell - Tabulator cell component
 * @param params - Formatter parameters
 * @param params.sentinels - Values to replace (default: [-1])
 * @param params.text - Replacement text (default: "-")
 * @param params.loose - Use loose == comparison (default: true)
 */
export function placeholderFormatter(
  cell: CellComponent,
  params: PlaceholderFormatterParams
): string | number {
  const value: unknown = cell.getValue()

  const sentinels = params.sentinels ?? [-1]
  const text = params.text ?? '-'
  const loose = params.loose !== false

  const matches = sentinels.some((sentinel) =>
    // eslint-disable-next-line eqeqeq
    loose ? value == sentinel : value === sentinel
  )

  return matches ? text : (value as string | number)
}

/**
 * Map of custom formatter names to their implementations.
 * Use this to resolve string formatter names from Python column definitions.
 *
 * Supported names: scientific, signed, badge, fixed, placeholder.
 */
export const customFormatters: Record<string, CustomFormatterFunction> = {
  scientific: scientificFormatter,
  signed: signedFormatter,
  badge: badgeFormatter,
  fixed: fixedFormatter,
  placeholder: placeholderFormatter,
}

/**
 * Check if a formatter name is a custom formatter.
 */
export function isCustomFormatter(formatterName: string): boolean {
  return formatterName in customFormatters
}

/**
 * Get a custom formatter by name.
 * Returns undefined if not a custom formatter.
 */
export function getCustomFormatter(
  formatterName: string
): CustomFormatterFunction | undefined {
  return customFormatters[formatterName]
}
