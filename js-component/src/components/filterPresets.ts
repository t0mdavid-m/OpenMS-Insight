/**
 * Filter presets: ready-made filters listed at the top of a table's filter
 * dialog, each switched on and off with a check box. A preset that is on keeps
 * only the rows matching every one of its conditions.
 *
 * Shared by the general table (`Table(filter_presets=...)`, filtered in Python)
 * and the fragment table of the sequence view (filtered in the browser).
 */

export type PresetOp = '==' | '!=' | '<=' | '>=' | '<' | '>' | 'in' | 'not in'

export interface PresetCondition {
  column: string
  op: PresetOp
  value: unknown
}

export interface FilterPreset {
  id: string
  label: string
  help?: string
  /** Every condition must hold for a row to stay */
  filters: PresetCondition[]
  /** On until the viewer switches it (default: off) */
  default?: boolean
}

/** Whether `row` passes one condition of a preset. */
export function conditionMatches(row: Record<string, unknown>, condition: PresetCondition): boolean {
  const cell = row[condition.column]
  const value = condition.value
  switch (condition.op) {
    case '==':
      return cell === value
    case '!=':
      return cell !== value
    case '<=':
      return typeof cell === 'number' && cell <= (value as number)
    case '>=':
      return typeof cell === 'number' && cell >= (value as number)
    case '<':
      return typeof cell === 'number' && cell < (value as number)
    case '>':
      return typeof cell === 'number' && cell > (value as number)
    case 'in':
      return Array.isArray(value) && value.includes(cell)
    case 'not in':
      return !Array.isArray(value) || !value.includes(cell)
    default:
      return true
  }
}

/** Whether `row` passes every condition of `preset`. */
export function presetMatches(row: Record<string, unknown>, preset: FilterPreset): boolean {
  return preset.filters.every((condition) => conditionMatches(row, condition))
}

/** The columns a set of presets reads, so a table keeps them in its rows. */
export function presetColumns(presets: FilterPreset[]): string[] {
  return [...new Set(presets.flatMap((preset) => preset.filters.map((c) => c.column)))]
}

/**
 * Draw the "Presets" section of a filter dialog into `content`: one check box
 * per preset, with its help below it. Nothing is drawn without presets.
 */
export function renderPresetSection(
  doc: Document,
  content: HTMLElement,
  presets: FilterPreset[],
  isActive: (preset: FilterPreset) => boolean,
  setActive: (preset: FilterPreset, active: boolean) => void,
): void {
  if (presets.length === 0) return
  const section = doc.createElement('div')
  section.className = 'filter-presets'
  section.style.cssText = `
    background-color: white;
    border-radius: 4px;
    border: 1px solid #e0e0e0;
    padding: 16px;
    margin-bottom: 24px;
  `
  const heading = doc.createElement('h6')
  heading.textContent = 'Presets:'
  heading.style.cssText = 'color: #333; margin: 0 0 12px 0; font-size: 16px; font-weight: 500;'
  section.appendChild(heading)
  for (const preset of presets) {
    const label = doc.createElement('label')
    label.style.cssText =
      'display: flex; align-items: center; gap: 8px; color: #333; font-size: 14px; cursor: pointer; margin-bottom: 4px;'
    if (preset.help) label.title = preset.help
    const box = doc.createElement('input')
    box.type = 'checkbox'
    box.checked = isActive(preset)
    box.addEventListener('change', () => setActive(preset, box.checked))
    const text = doc.createElement('span')
    text.textContent = preset.label
    label.appendChild(box)
    label.appendChild(text)
    section.appendChild(label)
    if (preset.help) {
      const help = doc.createElement('div')
      help.textContent = preset.help
      help.style.cssText = 'color: #666; font-size: 12px; margin: 0 0 8px 26px;'
      section.appendChild(help)
    }
  }
  content.appendChild(section)
}
