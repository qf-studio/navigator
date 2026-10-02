export type NavPhase = 'INIT' | 'RESEARCH' | 'IMPL' | 'VERIFY' | 'COMPLETE'

export type NavStatus = {
  phase: NavPhase | null
  next: string | null
  ctxPercent: number | null
}

export type NavMemory = { kind: string; text: string; percent: number | null }
export type NavGraph = { nodes: number; edges: number; memories: number }
export type NavRate = { kind: string; percentUsed: number; resetsAt: string | null }
export type NavTask = { id: string; title: string }

export type NavPane = {
  tasks: NavTask[]
  marker: string | null
  memories: NavMemory[]
  memoriesFor: string | null
  graph: NavGraph | null
  concepts: string[]
  docsTreeBytes: number
}

export type NavUsage = { rates: NavRate[]; usd: number | null }

export type NavActivity = {
  docsBytes: number
  docsReads: number
  agentRuns: number
  agentTokens: number
  committed: boolean
  lastTurnCommitted: boolean
}

export type NavHistory = { ctx: number[]; saved: number[] }

declare module 'claude-code' {
  interface PluginState {
    'nav-status': {
      status: NavStatus | null
      pane: NavPane | null
      usage: NavUsage | null
      activity: NavActivity
      history: NavHistory
      pinned: string | null
    }
  }
}
