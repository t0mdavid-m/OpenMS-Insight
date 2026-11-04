import { defineStore } from 'pinia'

import type { LibraryModification } from '@/components/sequence/modification'

export const useModificationStore = defineStore('variable-mod', {
  state: () => ({
    variableMod: {} as Record<number, number>,
    // Name of each residue's variable modification (library id, built-in
    // name or 'Custom'), for the list of applied modifications
    variableModLabels: {} as Record<number, string>,
    // Modifications the residue menus offer instead of the built-in list
    library: null as LibraryModification[] | null,
  }),
  getters: {
    variableModifications: (state) => state.variableMod,
    isEmpty: (state) =>
      Object.values(state.variableMod).filter((value) => value !== undefined && value !== 0)
        .length === 0,
  },
  actions: {
    updateVariableModifications(aaIndex: number, modMass: number, label?: string) {
      this.variableMod = {
        ...this.variableMod,
        [aaIndex]: modMass,
      }
      const labels = { ...this.variableModLabels }
      if (modMass && label) {
        labels[aaIndex] = label
      } else {
        delete labels[aaIndex]
      }
      this.variableModLabels = labels
    },
    setLibrary(library: LibraryModification[] | null | undefined) {
      this.library = library && library.length > 0 ? library : null
    },
  },
})
