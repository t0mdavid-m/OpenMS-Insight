/** Data of the SequenceCoverage component, built in Python by ``build_model``. */

export interface CoverageModification {
  position: number
  label: string
}

export interface CoverageHit {
  id: number
  start: number
  end: number
  label: string
  count: number | null
  color: string
  lane: number
  modifications: CoverageModification[]
  /** Values a click sets, per interactivity identifier */
  values: Record<string, unknown>
}

export interface CoverageTrack {
  name: string
  note: string | null
  hits: CoverageHit[]
  lanes: number
  covered: number
  coverage: number
}

export interface CoverageModel {
  reference: string[]
  length: number
  covered: number
  coverage: number
  tracks: CoverageTrack[]
  name: string | null
}
