// Mirror of nav_hook_lib/budget.py clamp; budgets generated from Python. Lengths and cuts are
// in code points, like Python's len() and slicing (JS string length counts UTF-16 units).
import { BUDGETS, TRUNCATION_MARKER } from './gen/sentinels.gen'

export const clamp = (text: string | null, event: string): string => {
  if (text === null) return ''
  const budget = (BUDGETS as Record<string, number>)[event]
  const points = Array.from(text)
  if (budget === undefined || points.length <= budget) return text
  const marker = Array.from(TRUNCATION_MARKER)
  const room = budget - marker.length
  if (room <= 0) return points.slice(0, budget).join('')
  let head = points.slice(0, room)
  const cut = head.lastIndexOf('\n')
  if (cut > 0) head = head.slice(0, cut)
  return head.join('') + TRUNCATION_MARKER
}
