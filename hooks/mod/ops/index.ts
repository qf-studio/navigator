// Ops per Claude Code event, in registry order (hooks/nav_hook_lib/registry.py EVENT_OPS).
import type { Op } from '../lib/types'
import { promptAdhd } from './prompt_adhd'

export const EVENT_OPS: Record<string, readonly Op[]> = {
  UserPromptSubmit: [promptAdhd],
}
