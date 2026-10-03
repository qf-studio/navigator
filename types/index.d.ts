export type NavPhase = 'INIT' | 'RESEARCH' | 'IMPL' | 'VERIFY' | 'COMPLETE'

export type NavStatus = {
  phase: NavPhase | null
  next: string | null
  ctxPercent: number | null
}

export type NavGraph = { nodes: number; edges: number; memories: number }
export type NavRate = { kind: string; percentUsed: number; resetsAt: string | null }
export type NavTask = { id: string; title: string; path?: string }
export type NavMemory = { kind: string; text: string; percent: number | null }

export type NavPane = {
  tasks: NavTask[]
  marker: string | null
  graph: NavGraph | null
  docsTreeBytes: number
  /** Memories recalled for the open tasks (memory_recall.py --auto). */
  memories: NavMemory[]
  /** Steps of the active task doc: its checklist, else its numbered plan (the route when present). */
  steps?: { id?: string; label: string; done: boolean }[]
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
/** The /nav trip panel: Claude Code's OTel metrics from Prometheus, today and over 7 days. */
export type NavTrip = { today: NavTripSpan; week: NavTripSpan; perMinute: number[]; source: string }

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
      pace: NavPace
      pinned: string | null
      crashes: Record<string, number>
      trip: NavTrip | null
    }
  }
}
