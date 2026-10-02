// Mirror of nav_hook_lib/budget.py clamp; budgets generated from Python.
import { BUDGETS, TRUNCATION_MARKER } from './gen/sentinels.gen'

export const clamp = (text: string | null, event: string): string => {
  if (text === null) return ''
  const budget = (BUDGETS as Record<string, number>)[event]
  if (budget === undefined || text.length <= budget) return text
  const room = budget - TRUNCATION_MARKER.length
  if (room <= 0) return text.slice(0, budget)
  let head = text.slice(0, room)
  const cut = head.lastIndexOf('\n')
  if (cut > 0) head = head.slice(0, cut)
  return head + TRUNCATION_MARKER
}
