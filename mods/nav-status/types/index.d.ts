export type NavPhase = 'INIT' | 'RESEARCH' | 'IMPL' | 'VERIFY' | 'COMPLETE'

export type NavStatus = {
  phase: NavPhase | null
  next: string | null
  ctxPercent: number | null
}

export type NavMemory = { kind: string; text: string; percent: number | null }
export type NavGraph = { nodes: number; edges: number; memories: number }
export type NavRate = { kind: string; percentUsed: number }

export type NavTask = { id: string; title: string }

export type NavPane = {
  tasks: NavTask[]
  marker: string | null
  memories: NavMemory[]
  graph: NavGraph | null
}

export type NavUsage = { rates: NavRate[]; usd: number | null }
export type NavReads = { total: number; docs: number; turn: number }
export type NavHistory = { ctx: number[]; reads: number[] }

declare module 'claude-code' {
  interface PluginState {
    'nav-status': {
      status: NavStatus | null
      pane: NavPane | null
      usage: NavUsage | null
      reads: NavReads
      history: NavHistory
      pinned: string | null
    }
  }
}
