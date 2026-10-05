// Ops per Claude Code event, in registry order (hooks/nav_hook_lib/registry.py EVENT_OPS).
// The keys are the Python event names; ops branch on ctx.event.
import type { Op } from '../lib/types'
import { compactMarkerPost, compactMarkerPre } from './compact_marker'
import { configGuard } from './config_guard'
import { failureDiagnosis } from './failure_diagnosis'
import { graphSync } from './graph_sync'
import { jitMemory } from './jit_memory'
import { profileSync } from './profile_sync'
import { promptBrief } from './prompt_brief'
import { promptGate } from './prompt_gate'
import { promptModes } from './prompt_modes'
import { promptTier1 } from './prompt_tier1'
import { readGuard } from './read_guard'
import { sessionStart } from './session_start'
import { setup } from './setup'
import { stopCompletion } from './stop_completion'
import { stopState } from './stop_state'
import { subagentContext } from './subagent_context'

export const EVENT_OPS: Record<string, readonly Op[]> = {
  SessionStart: [sessionStart],
  UserPromptSubmit: [promptGate, promptTier1, promptModes, promptBrief],
  PreToolUse: [readGuard],
  PostToolUse: [jitMemory, graphSync, profileSync],
  Stop: [stopCompletion, stopState],
  PreCompact: [compactMarkerPre],
  PostCompact: [compactMarkerPost],
  SubagentStart: [subagentContext],
  PostToolUseFailure: [failureDiagnosis],
  TaskCreated: [graphSync],
  TaskCompleted: [graphSync],
  ConfigChange: [configGuard],
  Setup: [setup],
}
