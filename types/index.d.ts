export type NavPhase = 'INIT' | 'RESEARCH' | 'IMPL' | 'VERIFY' | 'COMPLETE'

export type NavStatus = {
  phase: NavPhase | null
  next: string | null
  ctxPercent: number | null
}

export type NavRate = { kind: string; percentUsed: number; resetsAt: string | null }
export type NavTask = { id: string; title: string; path?: string }

/** TASK-111: one step of the route report (skills/nav-route/functions/route_render.py --format json). */
export type NavRouteStep = {
  key: string
  number: string
  text: string
  /** `#50`, `TASK-12 · PR #7`, `Operator step`, `Not filed`. */
  ticket: string
  /** The words the reader sees: `Done 2026-11-08`, `In the queue now`, `Blocked: needs step 2`. */
  state: string
  /** done | queue | work | next | blocked | later */
  kind: string
  changed: string
}
export type NavRoutePhase = { title: string; done: number; total: number; steps: NavRouteStep[] }
export type NavRouteDoc = { path: string; id: string; title: string; kind: string }
/** A row of the roadmaps list: a roadmap or an open task document. */
export type NavRouteRow = NavRouteDoc & { hasRoute: boolean; done: number; total: number; active: boolean }
export type NavRouteReport = {
  doc: NavRouteDoc
  goal: string
  source: string
  /** True when GitHub answered for at least one ticket. */
  github: boolean
  phases: NavRoutePhase[]
  side: NavRouteStep[]
  queue: { ticket: string; text: string }[]
  waits: string[]
  done: number
  total: number
  /** When the script ran (ms). */
  at: number
}

export type NavPane = {
  tasks: NavTask[]
  marker: string | null
  docsTreeBytes: number
  /** Every route document (roadmaps, then open task docs); the active one drives the pane. */
  routes: NavRouteRow[]
  active: NavRouteDoc | null
  /** Steps of the active task doc: its checklist, else its numbered plan (the route when present). */
  steps?: { id?: string; label: string; done: boolean }[]
}

/** TASK-88: the reject log (`.agent/.nav-rejects.jsonl`) as the pane shows it. */
export type NavRejects = {
  /** Lines whose timestamp falls on the local calendar day of `now`. */
  today: number
  /** The newest line, or null when the log is empty. */
  last: { clock: string; op: string; reason: string } | null
  /** The newest lines, formatted `HH:MM op · reason`, oldest first (REJECTS_TAIL at most). */
  tail: string[]
}

export type NavUsage = { rates: NavRate[]; usd: number | null }

export type NavActivity = {
  docsBytes: number
  docsReads: number
  agentRuns: number
  agentTokens: number
  committed: boolean
  lastTurnCommitted: boolean
  /** A Write/Edit under `.agent/` this turn: the task list, marker and memories may have moved. */
  docsTouched: boolean
  /** Bash calls this turn, and whether any came back without Claude Code's `isReadOnly` (TASK-85). */
  bashCalls: number
  bashMutating: boolean
  /** A `gh` call or a push / merge / pull this turn: ticket state may have moved (TASK-111). */
  ticketsTouched: boolean
}

export type NavHistory = { ctx: number[]; saved: number[] }
/** Read-tool counts: the session so far, the turn in progress, and the last completed turn. */
export type NavReads = {
  total: number
  docs: number
  turnTotal: number
  turnDocs: number
  lastTurnTotal: number
  lastTurnDocs: number
}
/** The typed judge's verdict on the last prompt, in words, and what Navigator did with it. */
export type NavJudge = {
  verdict: string
  effect: string
  /** Axes where the judge overrode the keyword rule, in words; null when none. */
  override: string | null
  model: string
  latencyMs: number
  /** The prompt, secret-redacted and head-capped, and when it was judged (ms). */
  text: string
  at: number
  /** Set from the pane: `y` confirmed the verdict as the label, `x` disputed it. */
  label?: 'confirmed' | 'disputed'
}
/** One entry of the personal label file `scripts/judge_label.py` / `judge_eval.py` read. */
export type NavJudgeLabel = {
  text: string
  tier: 'DIRECT' | 'TASK' | 'LOOP' | null
  task: boolean | null
  ambiguous: boolean | null
  project: string
  source: 'pane'
  at: string
  judged: string
  disputed?: true
}
export type NavDestination = { title: string; taskId: string | null; source: 'brief' | 'task' }
export type NavOffRoute = { topic: string; prompt: string; count: number }
export type NavWaypointClock = { label: string; turns: number }
/** Pace for the ETA: turns each completed leg took, and how long recent turns ran. */
export type NavPace = { legTurns: number[]; turnMs: number[] }
export type NavTripSpan = {
  usd: number
  tokens: number
  /** cacheRead share of input-side tokens; null when there were none. */
  cacheHit: number | null
  commits: number
  added: number
  removed: number
  activeSec: number
}
/** The /nav session card: this session's own Claude Code OTel metrics from Prometheus. */
export type NavTrip = {
  /** This session's counters over its whole life (a resumed session keeps its id). */
  session: NavTripSpan
  perMinute: number[]
  source: string
  /** False when Prometheus has no series for this session after its first turns (TASK-102). */
  sessionSeen: boolean
}

declare module 'claude-code' {
  interface PluginState {
    'navigator': {
      status: NavStatus | null
      pane: NavPane | null
      usage: NavUsage | null
      activity: NavActivity
      history: NavHistory
      disowned: string[]
      destination: NavDestination | null
      offRoute: NavOffRoute | null
      waypointClock: NavWaypointClock | null
      reads: NavReads
      judge: NavJudge | null
      judgeTrail: NavJudge[]
      showJudge: boolean
      showDetails: boolean
      rejects: NavRejects | null
      showRejects: boolean
      pace: NavPace
      route: NavRouteReport | null
      showRoutes: boolean
      crashes: Record<string, number>
      trip: NavTrip | null
    }
  }
}
