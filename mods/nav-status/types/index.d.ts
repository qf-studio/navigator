export type NavPhase = 'INIT' | 'RESEARCH' | 'IMPL' | 'VERIFY' | 'COMPLETE'

export type NavStatus = {
  phase: NavPhase | null
  next: string | null
  ctxPercent: number | null
}

declare module 'claude-code' {
  interface PluginState {
    'nav-status': { status: NavStatus | null }
  }
}
