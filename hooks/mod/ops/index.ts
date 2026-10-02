// Ops per Claude Code event, in registry order (hooks/nav_hook_lib/registry.py EVENT_OPS).
import type { Op } from '../lib/types'
import { promptAdhd } from './prompt_adhd'
import { promptBrief } from './prompt_brief'
import { promptGate } from './prompt_gate'
import { promptTier1 } from './prompt_tier1'

export const EVENT_OPS: Record<string, readonly Op[]> = {
  UserPromptSubmit: [promptGate, promptTier1, promptAdhd, promptBrief],
}
