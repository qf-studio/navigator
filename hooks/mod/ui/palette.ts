// Pilot TUI design system for the Navigator pane: palette and glyph helpers. Pure.

export const PALETTE = {
  accent: '#7eb8da',   // titles, values
  success: '#7ec699',  // healthy numbers
  warning: '#d4a054',  // context climbing
  error: '#d48a8a',    // context critical, failures
  border: '#3d4450',   // card frames
  label: '#c9d1d9',    // body text
  dim: '#8b949e',      // secondary text
} as const

const SPARK = ['▁', '▂', '▃', '▄', '▅', '▆', '▇', '█']

/** `▁▂▄▆█` for a series, scaled to its own min/max; flat when empty. */
export const sparkline = (values: readonly number[], width: number): string => {
  if (width <= 0) return ''
  const tail = values.slice(-width)
  if (tail.length === 0) return '▁'.repeat(width)
  const min = Math.min(...tail)
  const span = Math.max(...tail) - min || 1
  const body = tail.map(v => SPARK[Math.min(7, Math.round(((v - min) / span) * 7))] ?? '▁').join('')
  return body.padStart(width, '▁')
}

/** `███▓░░░░` gauge (grom's Meter: a soft edge cell); color chosen by the caller. */
export const gauge = (percent: number | null, width: number): string => {
  const p = percent === null ? 0 : Math.min(100, Math.max(0, percent))
  const filled = Math.round((p / 100) * width)
  const edge = filled > 1 && filled < width
  return '█'.repeat(edge ? filled - 1 : filled) + (edge ? '▓' : '') + '░'.repeat(width - filled)
}

// ---- grom's braille area chart (pkg/tui/render/braille.go, gradient.go), ported ----------

const parseHex = (hex: string): [number, number, number] => {
  const m = /^#([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(hex)
  return m ? [parseInt(m[1]!, 16), parseInt(m[2]!, 16), parseInt(m[3]!, 16)] : [255, 255, 255]
}
const toHex = (r: number, g: number, b: number): string =>
  `#${[r, g, b].map(v => Math.max(0, Math.min(255, Math.trunc(v))).toString(16).padStart(2, '0')).join('')}`

/** The color scaled toward black: 0 = black, 1 = unchanged. */
export const dimHex = (hex: string, factor: number): string => {
  const [r, g, b] = parseHex(hex)
  return toHex(r * factor, g * factor, b * factor)
}

export const lerpHex = (a: string, b: string, t: number): string => {
  const k = Math.max(0, Math.min(1, t))
  const [ar, ag, ab] = parseHex(a)
  const [br, bg, bb] = parseHex(b)
  return toHex(ar + (br - ar) * k, ag + (bg - ag) * k, ab + (bb - ab) * k)
}

/** `n` colors sweeping through the stops; one stop runs from its dimmed self to itself. */
export const gradient = (stops: readonly string[], n: number): string[] => {
  if (n <= 0) return []
  const s = stops.length === 0 ? ['#ffffff'] : stops.length === 1 ? [dimHex(stops[0]!, 0.55), stops[0]!] : [...stops]
  if (n === 1) return [s[s.length - 1]!]
  const segs = s.length - 1
  return Array.from({ length: n }, (_, i) => {
    const t = (i / (n - 1)) * segs
    const seg = Math.min(segs - 1, Math.trunc(t))
    return lerpHex(s[seg]!, s[seg + 1]!, t - seg)
  })
}

// Dot bits of one braille cell (2 columns × 4 rows), U+2800 + mask.
const BRAILLE_BITS = [[0x01, 0x08], [0x02, 0x10], [0x04, 0x20], [0x40, 0x80]] as const

/** Dot heights (1..dotH, 0 = gap) for `dotW` columns, right-aligned when fewer values. */
const dotHeights = (values: readonly number[], dotW: number, dotH: number): number[] => {
  const heights = new Array<number>(dotW).fill(0)
  const valid = values.filter(v => Number.isFinite(v))
  const n = values.length
  if (n === 0 || valid.length === 0) return heights
  const min = Math.min(...valid)
  const span = Math.max(...valid) - min
  const cols = Math.min(n, dotW)
  const offset = dotW - cols
  for (let i = 0; i < cols; i++) {
    const idx = cols === 1 ? n - 1 : Math.round((i / (cols - 1)) * (n - 1))
    const v = values[idx]!
    if (!Number.isFinite(v)) continue
    const h = span === 0 ? (v > 0 ? Math.trunc(dotH / 2) : 1) : Math.round(((v - min) / span) * (dotH - 1)) + 1
    heights[offset + i] = Math.max(1, Math.min(dotH, h))
  }
  return heights
}

/**
 * A filled braille area chart: `rows` strings of `width` cells, top row first, each dot
 * column filled from the bottom to its value. Resolution 2×4 dots per cell; values are
 * min/max scaled and resampled to the width; non-finite values leave a gap.
 */
export const brailleArea = (values: readonly number[], width: number, rows: number): string[] => {
  if (width <= 0 || rows <= 0) return []
  const dotW = width * 2
  const dotH = rows * 4
  const heights = dotHeights(values, dotW, dotH)
  const masks = Array.from({ length: rows }, () => new Array<number>(width).fill(0))
  for (let dc = 0; dc < dotW; dc++) {
    for (let dr = 0; dr < heights[dc]!; dr++) {
      const y = dotH - 1 - dr
      masks[Math.trunc(y / 4)]![Math.trunc(dc / 2)]! |= BRAILLE_BITS[y % 4]![dc % 2]!
    }
  }
  return masks.map(row => row.map(m => (m === 0 ? ' ' : String.fromCodePoint(0x2800 | m))).join(''))
}

/** grom's stat texture: a subdued vertical gradient of `color`, brightest on top. */
export const areaColors = (color: string, rows: number): string[] =>
  gradient([dimHex(color, 0.35), dimHex(color, 0.75)], rows).reverse()

/** A series with fewer than two distinct values draws as a flat bar; show it dim. */
export const isFlat = (values: readonly number[]): boolean => new Set(values).size < 2

export const sparkColor = (values: readonly number[]): string =>
  isFlat(values) ? PALETTE.dim : PALETTE.accent

export const percentColor = (percent: number | null): string =>
  percent === null ? PALETTE.dim
    : percent >= 85 ? PALETTE.error
      : percent >= 70 ? PALETTE.warning
        : PALETTE.success

export const compact = (n: number): string =>
  n >= 1_000_000 ? `${(n / 1_000_000).toFixed(1)}M` : n >= 1_000 ? `${(n / 1_000).toFixed(1)}K` : `${n}`
