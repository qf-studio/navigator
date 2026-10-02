export type NavPhase = 'INIT' | 'RESEARCH' | 'IMPL' | 'VERIFY' | 'COMPLETE'

export type NavStatus = {
  phase: NavPhase | null
  next: string | null
  ctxPercent: number | null
}

export type NavMemory = { kind: string; text: string; percent: number | null }

export type NavPane = {
  task: string | null
  marker: string | null
  memories: NavMemory[]
}

export type NavReads = { total: number; docs: number }

declare module 'claude-code' {
  interface PluginState {
    'nav-status': {
      status: NavStatus | null
      pane: NavPane | null
      reads: NavReads
      pinned: string | null
    }
  }
}
