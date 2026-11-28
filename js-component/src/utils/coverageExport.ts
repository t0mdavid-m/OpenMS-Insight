/**
 * Downloads of the SequenceCoverage map: the drawn SVG as an image or a web
 * page of its own, and the drawn matches as a tab-separated table.
 */

import type { CoverageModel } from '@/types/coverage-data'
import { RASTER_SCALE, encodeCanvas, type ImageFormat } from '@/utils/imageExport'

/** One cell of a TSV: tabs and line breaks would break the table. */
function cell(value: unknown): string {
  if (value === null || value === undefined) return ''
  return String(value).replace(/[\t\r\n]+/g, ' ')
}

/**
 * The matches of every track as a table: track, label, start, end, the
 * count (when the map colours by one) and the modified positions.
 */
export function coverageTsv(model: CoverageModel, countLabel: string | null): string {
  const header = ['Track', 'Label', 'Start', 'End']
  if (countLabel) header.push(countLabel)
  header.push('Modifications')
  const rows = [header.map(cell).join('\t')]
  for (const track of model.tracks) {
    for (const hit of track.hits) {
      const row: unknown[] = [track.name, hit.label, hit.start, hit.end]
      if (countLabel) row.push(hit.count)
      row.push(hit.modifications.map((m) => (m.label ? `${m.position}:${m.label}` : String(m.position))).join(';'))
      rows.push(row.map(cell).join('\t'))
    }
  }
  return rows.join('\n') + '\n'
}

/** Margin around an exported map, so its labels do not touch the edge. */
export const EXPORT_MARGIN = 16

/** The SVG element as a standalone document of `width` x `height`, drawn on `background` with a margin. */
export function standaloneSvg(svg: SVGSVGElement, width: number, height: number, background: string): string {
  const copy = svg.cloneNode(true) as SVGSVGElement
  const m = EXPORT_MARGIN
  copy.setAttribute('xmlns', 'http://www.w3.org/2000/svg')
  copy.setAttribute('width', String(width + 2 * m))
  copy.setAttribute('height', String(height + 2 * m))
  copy.setAttribute('viewBox', `${-m} ${-m} ${width + 2 * m} ${height + 2 * m}`)
  const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect')
  rect.setAttribute('x', String(-m))
  rect.setAttribute('y', String(-m))
  rect.setAttribute('width', String(width + 2 * m))
  rect.setAttribute('height', String(height + 2 * m))
  rect.setAttribute('fill', background)
  copy.insertBefore(rect, copy.firstChild)
  return new XMLSerializer().serializeToString(copy)
}

function escapeHtml(text: string): string {
  return text.replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c] as string)
}

/** A web page holding the map, its tooltips kept, without the app. */
export function coverageHtml(svgText: string, title: string, background: string, color: string): string {
  const name = escapeHtml(title)
  return `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>${name}</title>
<style>body{margin:24px;background:${background};color:${color};font-family:sans-serif}
h1{font-size:16px;font-weight:600;margin:0 0 12px}svg{max-width:none}</style></head>
<body><h1>${name}</h1>
${svgText}
</body></html>
`
}

/** A text download (TSV, SVG, HTML) as a blob URL. */
export function textUrl(text: string, mime: string): string {
  return URL.createObjectURL(new Blob([text], { type: `${mime};charset=utf-8` }))
}

/** Draw an SVG document on a canvas at RASTER_SCALE and encode it. */
export async function rasterize(
  svgText: string,
  width: number,
  height: number,
  format: Exclude<ImageFormat, 'svg'>,
): Promise<{ url: string; format: ImageFormat }> {
  const url = textUrl(svgText, 'image/svg+xml')
  try {
    const image = new Image()
    image.src = url
    await image.decode()
    const canvas = document.createElement('canvas')
    canvas.width = Math.ceil(width * RASTER_SCALE)
    canvas.height = Math.ceil(height * RASTER_SCALE)
    const context = canvas.getContext('2d') as CanvasRenderingContext2D
    context.scale(RASTER_SCALE, RASTER_SCALE)
    context.drawImage(image, 0, 0, width, height)
    return encodeCanvas(canvas, format)
  } finally {
    URL.revokeObjectURL(url)
  }
}
