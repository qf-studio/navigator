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

/** `████░░░░` gauge; color chosen by the caller. */
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

export const compact = (n: number): string =>
  n >= 1_000_000 ? `${(n / 1_000_000).toFixed(1)}M` : n >= 1_000 ? `${(n / 1_000).toFixed(1)}K` : `${n}`
