import { computed, inject, onBeforeUnmount, onMounted, reactive, type ComputedRef, type InjectionKey } from 'vue'

/**
 * The view's help text, shared by App.vue with the row (a plot toolbar or a
 * table's title) that draws the info icon in line with its own controls. The
 * first row mounted owns the icon; while none does, App.vue floats it in the
 * view's corner.
 */
export interface HelpState {
  text: string
  owners: number[]
  claimed: number
}

export const HELP_KEY: InjectionKey<HelpState> = Symbol('insight-help')

export function createHelpState(): HelpState {
  return reactive({ text: '', owners: [] as number[], claimed: 0 })
}

let nextId = 1

/** The help text this row should show inline, or '' when another row shows it. */
export function useHelp(): ComputedRef<string> {
  const state = inject(HELP_KEY, null) ?? createHelpState()
  const id = nextId++
  onMounted(() => {
    state.owners.push(id)
    state.claimed = state.owners.length
  })
  onBeforeUnmount(() => {
    state.owners = state.owners.filter((o) => o !== id)
    state.claimed = state.owners.length
  })
  return computed(() => (state.owners[0] === id ? state.text : ''))
}
