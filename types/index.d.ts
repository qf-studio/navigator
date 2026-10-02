export type NavPhase = 'INIT' | 'RESEARCH' | 'IMPL' | 'VERIFY' | 'COMPLETE'

export type NavStatus = {
  phase: NavPhase | null
  next: string | null
  ctxPercent: number | null
}

export type NavMemory = { kind: string; text: string; percent: number | null }
export type NavGraph = { nodes: number; edges: number; memories: number }
export type NavRate = { kind: string; percentUsed: number; resetsAt: string | null }
export type NavTask = { id: string; title: string; path?: string }

export type NavPane = {
  tasks: NavTask[]
  marker: string | null
  memories: NavMemory[]
  memoriesFor: string | null
  graph: NavGraph | null
  concepts: string[]
  docsTreeBytes: number
  /** `- [ ]` / `- [x]` items of the active task doc (the route when present). */
  checklist?: { label: string; done: boolean }[]
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
export type NavDestination = { title: string; taskId: string | null; source: 'brief' | 'task' }
export type NavOffRoute = { topic: string; prompt: string; count: number }
export type NavWaypointClock = { label: string; turns: number }

declare module 'claude-code' {
  interface PluginState {
    'navigator': {
      status: NavStatus | null
      pane: NavPane | null
      usage: NavUsage | null
      activity: NavActivity
      history: NavHistory
      pinned: string | null
      disowned: string[]
      destination: NavDestination | null
      offRoute: NavOffRoute | null
      waypointClock: NavWaypointClock | null
      showTasks: boolean
      crashes: Record<string, number>
    }
  }
}
