/**
 * Scripts that show the structure view's colouring in a desktop molecular
 * viewer: a ChimeraX Python script (.py) and a PyMOL script (.pml). Each
 * carries the structure itself, so the one file opens on its own (ChimeraX:
 * File > Open or `open evidence.py`; PyMOL: File > Run Script or `@evidence.pml`).
 */

export type ScriptModification = {
  /** Structure residue numbers the modification covers. */
  residues: number[]
  label: string
}

export type ScriptInput = {
  /** Object name in the viewer, e.g. the accession. */
  name: string
  format: 'pdb' | 'cif'
  /** The structure file's text. */
  data: string
  /** Chain the sequence is mapped to ('' for a file without chain ids). */
  chain: string
  /** Residue colours of the mapped chain: colour -> structure residue numbers. */
  colors: Map<string, number[]>
  /** Residues of the mapped chain not drawn (outside the sequence range). */
  hidden: number[]
  /** Colour of every other chain. */
  otherChains: string
  modifications: ScriptModification[]
  modificationColor: string
  /** What the colours mean, written into the script's header. */
  legend: { label: string; color: string }[]
  /** Where the view was made (app, entry), for the header. */
  title?: string
}

/** Residue numbers as ranges: [[1, 4], [7, 7]]. Negative numbers stay single. */
export function residueRanges(residues: number[]): [number, number][] {
  const sorted = [...new Set(residues)].sort((a, b) => a - b)
  const ranges: [number, number][] = []
  sorted.forEach((r) => {
    const last = ranges[ranges.length - 1]
    if (last !== undefined && r === last[1] + 1 && last[0] >= 0 && r >= 0) last[1] = r
    else ranges.push([r, r])
  })
  return ranges
}

/** Stands for the opened model in the ChimeraX commands; the script puts in its id. */
export const CHIMERAX_MODEL = '#MODEL'

/** ChimeraX residue spec: `#MODEL/A:1-4,7` (no chain id: `#MODEL:1-4,7`). */
export function chimeraxSpec(chain: string, residues: number[]): string {
  const list = residueRanges(residues)
    .map(([a, b]) => (a === b ? `${a}` : `${a}-${b}`))
    .join(',')
  return `${CHIMERAX_MODEL}${chain ? `/${chain}` : ''}:${list}`
}

/** PyMOL selection: `obj and chain A and resi 1-4+7` (a negative number escaped). */
export function pymolSelection(name: string, chain: string, residues: number[]): string {
  const num = (r: number) => (r < 0 ? `\\${r}` : `${r}`)
  const list = residueRanges(residues)
    .map(([a, b]) => (a === b ? num(a) : `${num(a)}-${num(b)}`))
    .join('+')
  return `${name} and chain ${chain ? chain : '""'} and resi ${list}`
}

/** A name a viewer accepts as an object name. */
export function objectName(name: string): string {
  const cleaned = name.replace(/[^A-Za-z0-9_]+/g, '_').replace(/^_+|_+$/g, '')
  return cleaned || 'structure'
}

function header(input: ScriptInput, comment: string, how: string): string[] {
  const lines = [
    `${comment} ${input.title ?? 'Fragment evidence on the structure'}`,
    `${comment} ${how}`,
    `${comment} Colours:`,
    ...input.legend.map((l) => `${comment}   ${l.color}  ${l.label}`),
  ]
  return lines
}

/** Python string literal of `text` (JSON's escapes are valid in Python). */
function pyString(text: string): string {
  return JSON.stringify(text)
}

/** ChimeraX Python script: writes the structure to a temporary file, opens it and colours it. */
export function chimeraxScript(input: ScriptInput): string {
  const chain = input.chain
  const model = CHIMERAX_MODEL
  const commands: string[] = [
    `cartoon ${model}`,
    `hide ${model} atoms`,
    `color ${model} ${input.otherChains} target ac`,
  ]
  input.colors.forEach((residues, color) => {
    if (residues.length > 0) commands.push(`color ${chimeraxSpec(chain, residues)} ${color} target c`)
  })
  if (input.hidden.length > 0) commands.push(`cartoon hide ${chimeraxSpec(chain, input.hidden)}`)
  input.modifications.forEach((m) => {
    if (m.residues.length === 0) return
    const spec = chimeraxSpec(chain, m.residues)
    commands.push(`show ${spec} atoms`, `style ${spec} sphere`, `color ${spec} ${input.modificationColor} target a`)
    commands.push(`label ${chimeraxSpec(chain, [m.residues[0]])} residues text ${pyString(m.label)}`)
  })
  commands.push(`view ${model}${chain ? `/${chain}` : ''}`)
  return [
    ...header(input, '#', 'Open in ChimeraX: File > Open, or the command "open <this file>".'),
    '',
    'import os',
    'import tempfile',
    '',
    'from chimerax.core.commands import run',
    '',
    `STRUCTURE = ${pyString(input.data)}`,
    '',
    `path = os.path.join(tempfile.mkdtemp(), ${pyString(`${objectName(input.name)}.${input.format}`)})`,
    'with open(path, "w") as f:',
    '    f.write(STRUCTURE)',
    `models = run(session, "open %s format ${input.format === 'cif' ? 'mmcif' : 'pdb'}" % path)`,
    'model = models[0].atomspec',
    `run(session, "rename %s ${objectName(input.name)}" % model)`,
    '',
    'COMMANDS = [',
    ...commands.map((c) => `    ${pyString(c)},`),
    ']',
    'for command in COMMANDS:',
    `    run(session, command.replace(${pyString(CHIMERAX_MODEL)}, model))`,
    '',
  ].join('\n')
}

/** PyMOL script: loads the structure from the script itself and colours it. */
export function pymolScript(input: ScriptInput): string {
  const name = objectName(input.name)
  const chain = input.chain
  const lines: string[] = [
    ...header(input, '#', 'Run in PyMOL: File > Run Script, or "@<this file>".'),
    '',
    'python',
    `cmd.load_raw(${pyString(input.data)}, ${pyString(input.format)}, ${pyString(name)})`,
    'python end',
    `hide everything, ${name}`,
    `show cartoon, ${name}`,
    `set_color oi_other, ${hexToPymol(input.otherChains)}`,
    `color oi_other, ${name}`,
  ]
  let index = 0
  input.colors.forEach((residues, color) => {
    if (residues.length === 0) return
    const colorName = `oi_c${index++}`
    lines.push(`set_color ${colorName}, ${hexToPymol(color)}`)
    lines.push(`color ${colorName}, ${pymolSelection(name, chain, residues)}`)
  })
  if (input.hidden.length > 0) lines.push(`hide cartoon, ${pymolSelection(name, chain, input.hidden)}`)
  if (input.modifications.length > 0) lines.push(`set_color oi_mod, ${hexToPymol(input.modificationColor)}`)
  input.modifications.forEach((m) => {
    if (m.residues.length === 0) return
    const sel = pymolSelection(name, chain, m.residues)
    lines.push(`show spheres, ${sel}`, `color oi_mod, (${sel}) and not name CA`)
    lines.push(`label ${pymolSelection(name, chain, [m.residues[0]])} and name CA, ${pyString(m.label)}`)
  })
  lines.push(`orient ${name} and chain ${chain ? chain : '""'}`, '')
  return lines.join('\n')
}

/** `#rrggbb` as PyMOL's `[r, g, b]` (0-1). */
export function hexToPymol(hex: string): string {
  const m = /^#?([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(hex.trim())
  if (!m) return '[0.6, 0.6, 0.6]'
  return `[${m.slice(1, 4).map((h) => (parseInt(h, 16) / 255).toFixed(3)).join(', ')}]`
}
