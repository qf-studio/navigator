// Pilot TUI design system for the Navigator pane: palette, framed cards, sparklines.
// Pure: produces rows of colored segments; the hooks module turns them into Text.

export const PALETTE = {
  accent: '#7eb8da',   // titles, values
  success: '#7ec699',  // healthy numbers
  warning: '#d4a054',  // context climbing
  error: '#d48a8a',    // context critical, failures
  border: '#3d4450',   // card frames
  label: '#c9d1d9',    // body text
  dim: '#8b949e',      // secondary text
} as const

export type Segment = { text: string; color?: string; bold?: true }
export type Row = Segment[]

const SPARK = ['▁', '▂', '▃', '▄', '▅', '▆', '▇', '█']

export const seg = (text: string, color?: string, bold?: true): Segment =>
  bold ? { text, color, bold } : { text, color }

export const rowWidth = (row: Row): number => row.reduce((n, s) => n + s.text.length, 0)

/** Pad or cut a row to exactly `width` cells. */
export const fit = (row: Row, width: number): Row => {
  const w = rowWidth(row)
  if (w === width) return row
  if (w < width) return [...row, seg(' '.repeat(width - w))]
  const out: Row = []
  let left = width
  for (const s of row) {
    if (left <= 0) break
    const take = s.text.length > left ? `${s.text.slice(0, Math.max(0, left - 1))}…` : s.text
    out.push({ ...s, text: take })
    left -= take.length
  }
  return out
}

/** `▁▂▄▆█` for a series, scaled to its own min/max; blank when empty. */
export const sparkline = (values: readonly number[], width: number): string => {
  if (width <= 0) return ''
  const tail = values.slice(-width)
  if (tail.length === 0) return '▁'.repeat(width)
  const min = Math.min(...tail)
  const span = Math.max(...tail) - min || 1
  const body = tail.map(v => SPARK[Math.min(7, Math.round(((v - min) / span) * 7))] ?? '▁').join('')
  return body.padStart(width, '▁')
}

/** `[████░░░░]`-style gauge without brackets; color chosen by the caller. */
export const gauge = (percent: number | null, width: number): string => {
  const p = percent === null ? 0 : Math.min(100, Math.max(0, percent))
  const filled = Math.round((p / 100) * width)
  return '█'.repeat(filled) + '░'.repeat(width - filled)
}

export const percentColor = (percent: number | null): string =>
  percent === null ? PALETTE.dim
    : percent >= 85 ? PALETTE.error
      : percent >= 70 ? PALETTE.warning
        : PALETTE.success

/**
 * A Pilot-style framed card, `width` cells wide:
 * ╭─ title ─────╮ / │ body rows   │ / ╰─────────────╯
 */
export const card = (title: string, body: readonly Row[], width: number): Row[] => {
  const inner = Math.max(4, width - 4)
  const head = `─ ${title} `
  const top: Row = [
    seg('╭', PALETTE.border),
    seg(head.slice(0, inner + 2), PALETTE.accent),
    seg('─'.repeat(Math.max(0, inner + 2 - head.length)) + '╮', PALETTE.border),
  ]
  const rows = body.map(r => [
    seg('│ ', PALETTE.border), ...fit(r, inner), seg(' │', PALETTE.border),
  ])
  const bottom: Row = [seg(`╰${'─'.repeat(inner + 2)}╯`, PALETTE.border)]
  return [top, ...rows, bottom]
}

/** Lay cards side by side, one space apart; shorter cards are padded with blank rows. */
export const beside = (cards: readonly Row[][], gap = 1): Row[] => {
  const height = Math.max(0, ...cards.map(c => c.length))
  const widths = cards.map(c => rowWidth(c[0] ?? []))
  return Array.from({ length: height }, (_, i) =>
    cards.flatMap((c, k) => {
      const row = c[i] ?? [seg(' '.repeat(widths[k] ?? 0))]
      return k === 0 ? row : [seg(' '.repeat(gap)), ...row]
    }),
  )
}

/** Split `total` cells into `n` card widths that sum exactly, gaps included. */
export const splitWidths = (total: number, n: number, gap = 1): number[] => {
  const usable = total - gap * (n - 1)
  const base = Math.floor(usable / n)
  return Array.from({ length: n }, (_, i) => base + (i < usable - base * n ? 1 : 0))
}

export const compact = (n: number): string =>
  n >= 1_000_000 ? `${(n / 1_000_000).toFixed(1)}M` : n >= 1_000 ? `${(n / 1_000).toFixed(1)}K` : `${n}`
