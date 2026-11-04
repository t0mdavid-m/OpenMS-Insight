/**
 * Modification definitions and extra fragment types for SequenceView.
 */

export type KnownModification =
  | 'Methyl'
  | 'Acetyl'
  | 'Phospho'
  | 'Oxidation'
  | 'Deamidated'
  | 'Amidated'

export const modificationMassMap: Record<KnownModification, number> = {
  Acetyl: 42.010565,
  Methyl: 14.01565,
  Phospho: 79.966331,
  Oxidation: 15.994915,
  Deamidated: 0.984016,
  Amidated: -0.984016,
}

export const potentialModificationMap: Record<string, KnownModification[]> = {
  'N-term': ['Acetyl', 'Methyl', 'Phospho'],
  'C-term': ['Amidated'],
  C: ['Acetyl', 'Methyl', 'Phospho'],
  E: ['Methyl', 'Phospho'],
  D: ['Methyl', 'Phospho'],
  H: ['Methyl', 'Phospho'],
  I: ['Methyl'],
  K: ['Methyl', 'Phospho'],
  L: ['Methyl'],
  M: ['Oxidation'],
  N: ['Methyl'],
  Q: ['Deamidated', 'Methyl'],
  R: ['Methyl', 'Phospho'],
  S: ['Acetyl', 'Methyl', 'Phospho'],
  T: ['Acetyl', 'Methyl', 'Phospho'],
  Y: ['Phospho'],
}

/** A modification of an app-provided library (e.g. pyOpenMS ModificationsDB). */
export interface LibraryModification {
  id: string
  mass: number
  site?: string | null
}

/** One entry of a residue's modification menu. */
export interface ModificationOption {
  title: string
  value: string
  mass: number | null
}

/**
 * The modification menu of a residue (one-letter code) or terminus
 * ('N-term' / 'C-term'): None, Custom, then the library's modifications at
 * that site, or the built-in ones without a library.
 */
export function modificationOptions(
  site: string,
  library?: LibraryModification[] | null
): ModificationOption[] {
  const options: ModificationOption[] = [
    { title: 'None', value: 'None', mass: null },
    { title: 'Custom', value: 'Custom', mass: null },
  ]
  if (library && library.length > 0) {
    for (const m of library) {
      if (m.site === site) {
        const mass = m.mass.toLocaleString('en-US', {
          signDisplay: 'always',
          maximumFractionDigits: 4,
        })
        options.push({ title: `${m.id}  ${mass} Da`, value: m.id, mass: m.mass })
      }
    }
    return options
  }
  for (const name of potentialModificationMap[site] ?? []) {
    options.push({ title: name, value: name, mass: modificationMassMap[name] })
  }
  return options
}

export type ExtraFragmentType = 'water loss' | 'ammonium loss' | 'proton loss/addition'

export const extraFragmentTypeObject: Record<
  ExtraFragmentType | 'default',
  { typeName: string; typeMass: number }[]
> = {
  default: [{ typeName: '', typeMass: 0 }],
  'water loss': [{ typeName: '-H2O', typeMass: -18.0105646863 }],
  'ammonium loss': [{ typeName: '-NH3', typeMass: -17.0265491015 }],
  'proton loss/addition': [
    { typeName: '-H', typeMass: -1.0078250319 },
    { typeName: '+H', typeMass: 1.0078250319 },
  ],
}
