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
 * Type for custom formatter functions.
 * Matches Tabulator's formatter signature.
 */
export type CustomFormatterFunction = (
  cell: CellComponent,
  params: BaseFormatterParams,
  onRendered?: (callback: () => void) => void
) => string | HTMLElement

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
 * Parameters for the fixed-precision formatter.
 */
export interface FixedFormatterParams extends BaseFormatterParams {
  /** Number of decimal places (default: 4) */
  precision?: number
}

/**
 * Format a number with a fixed number of decimals and NO thousands grouping.
 *
 * Mirrors the legacy FLASHApp `toFixedFormatter()` (4 decimals, no comma
 * grouping) used by the Scan/Mass tables. Unlike Tabulator's built-in "money"
 * formatter, this never inserts thousands separators.
 *
 * Example (precision 4): 47712.3456 -> "47712.3456"
 */
export function fixedFormatter(
  cell: CellComponent,
  params: FixedFormatterParams
): string {
  const value = cell.getValue()
  if (value === null || value === undefined || value === '') {
    return ''
  }
  const num = Number(value)
  if (isNaN(num)) {
    return String(value)
  }
  const precision = params.precision ?? 4
  return num.toFixed(precision)
}

/**
 * Parameters for the dash-on-negative-one formatter.
 */
export interface DashNegativeOneFormatterParams extends BaseFormatterParams {
  /** When set, non-sentinel values render with this many decimals (no grouping). */
  precision?: number
}

/**
 * Render the FLASHApp `-1` sentinel as a dash ("-"), otherwise the number.
 *
 * Mirrors the legacy Protein/Tag tables, which display ProteoformMass /
 * ProteoformLevelQvalue / N mass / C mass equal to -1 as "-". When `precision`
 * is given, non-sentinel values are formatted with that many decimals and no
 * thousands grouping; otherwise the raw value is shown.
 *
 * Example: -1 -> "-"; 1234.5 (precision 2) -> "1234.50"
 */
export function dashNegativeOneFormatter(
  cell: CellComponent,
  params: DashNegativeOneFormatterParams
): string {
  const value = cell.getValue()
  if (value === null || value === undefined || value === '') {
    return ''
  }
  const num = Number(value)
  if (isNaN(num)) {
    return String(value)
  }
  if (num === -1) {
    return '-'
  }
  if (params.precision !== undefined && params.precision !== null) {
    return num.toFixed(params.precision)
  }
  return String(value)
}

/**
 * Map of custom formatter names to their implementations.
 * Use this to resolve string formatter names from Python column definitions.
 */
export const customFormatters: Record<string, CustomFormatterFunction> = {
  scientific: scientificFormatter,
  signed: signedFormatter,
  badge: badgeFormatter,
  fixed: fixedFormatter,
  dashNegativeOne: dashNegativeOneFormatter,
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
