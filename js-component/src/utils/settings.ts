/**
 * The gear button of a plot's `settings` (see core/settings.py).
 *
 * Each setting writes its value to a selection identifier; Python reads it
 * back from the StateManager and builds the plot's data from it.
 */

import { ICONS, type PlotTool, type ToolMenuSection } from '@/utils/plotTools'

export interface SettingArgs {
  identifier: string
  label: string
  kind: 'choice' | 'range' | 'toggle'
  default: unknown
  options?: { value: unknown; label: string }[]
  min?: number
  max?: number
  step?: number
}

export function settingsTools(
  settings: SettingArgs[] | undefined,
  state: Record<string, unknown>,
  select: (identifier: string, value: unknown) => void,
): PlotTool[] {
  if (!settings || settings.length === 0) return []
  const current = (s: SettingArgs) => {
    const value = state[s.identifier]
    return value === undefined || value === null ? s.default : value
  }
  const menu: ToolMenuSection[] = settings.map((s): ToolMenuSection => {
    if (s.kind === 'range') {
      return {
        kind: 'range',
        label: s.label,
        min: s.min ?? 0,
        max: s.max ?? 100,
        step: s.step ?? 1,
        value: Number(current(s)),
        // Only the released value goes to Python: every write reruns the app
        input: () => {},
        change: (value: number) => select(s.identifier, value),
      }
    }
    if (s.kind === 'toggle') {
      return {
        kind: 'toggles',
        label: s.label,
        items: [{ value: s.identifier, label: s.label, active: !!current(s) }],
        toggle: () => select(s.identifier, !current(s)),
      }
    }
    const options = s.options ?? []
    return {
      kind: 'choice',
      label: s.label,
      options: options.map((o) => ({ value: String(o.value), label: o.label })),
      value: String(current(s)),
      select: (value: string) => {
        const option = options.find((o) => String(o.value) === value)
        select(s.identifier, option ? option.value : value)
      },
    }
  })
  return [
    {
      id: 'settings',
      group: 'view',
      icon: ICONS.settings,
      label: 'Settings',
      help: settings.map((s) => s.label).join(', '),
      menu,
      run: () => {},
    },
  ]
}
