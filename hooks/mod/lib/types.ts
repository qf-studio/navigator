// Contracts shared by the runner and the ops (TASK-84). OpResult mirrors the Python op
// dict keys (hooks/ops/README.md) so parity tests compare like with like.
export type Phase = 'gates' | 'responders' | 'injectors' | 'recorders'

export type OpResult = {
  additional_context?: string
  decision?: 'block'
  reason?: string
  permission_decision?: 'deny' | 'ask'
  permission_reason?: string
  exit_code?: number
  stderr?: string
  system_message?: string
  continue_?: boolean
  /** v6 `{}` acknowledgment (TASK-61 parity); no output of its own. */
  ack?: true
}

export type Json = Record<string, unknown>

export type EnvSnapshot = {
  PILOT_EXECUTOR?: string
  NAVIGATOR_CONFIG_HOME?: string
  XDG_CONFIG_HOME?: string
  HOME?: string
  TYPESAFE_API_KEY?: string
}

/**
 * The mods API, narrowed to what ops need. The engine's static scan follows `$` only into
 * functions declared in the hooks module itself, so register.tsx builds this object (each
 * method a direct `$.noun.method` call there) and passes it to imported modules instead.
 */
export type Io = {
  pluginRoot: string
  read: (path: string) => Promise<string>
  write: (path: string, text: string) => Promise<void>
  exists: (path: string) => Promise<boolean>
  list: (path: string) => Promise<{ name: string; mtimeMs: number; kind: 'file' | 'dir' | 'other' }[]>
  run: (argv: readonly string[], cwd: string, timeoutMs: number) =>
    Promise<{ exitCode: number; stdout: string }>
  cwd: () => Promise<string>
  sessionId: () => Promise<string | null>
  nowMs: () => Promise<number>
  version: () => Promise<{ version: string; base?: string }>
  env: () => Promise<EnvSnapshot>
  setOwned: (value: string) => Promise<void>
  http: (url: string, init: { method: string; headers: Record<string, string>; body: string }) =>
    Promise<{ ok: boolean; status: number; text: string }>
  sleep: (ms: number) => Promise<void>
  disowned: () => Promise<string[]>
  noteCrash: (op: string) => Promise<number>
  disown: (op: string) => Promise<void>
  // ---- step 5b io ----
  /**
   * `$.process.run` keeping stderr (graph_sync / profile_sync diagnostics). Rejects when the
   * command cannot start or outlives `timeoutMs`; the ops classify the rejection. Optional:
   * without it the ops fall back to `run` and report an empty stderr.
   */
  runCapture?: (argv: readonly string[], cwd: string, timeoutMs: number) =>
    Promise<{ exitCode: number; stdout: string; stderr: string }>
  // ---- step 5b io ----
  // ---- step 5d io ----
  /** `$.fs.stat`: kind and mtime, or null when missing. Optional: falls back to io.list. */
  stat?: (path: string) => Promise<{ kind: 'file' | 'dir' | 'other'; mtimeMs: number } | null>
  /** Minutes east of UTC at `ms` (Python local time). Optional: falls back to the JS Date zone. */
  localOffsetMinutes?: (ms: number) => number
  // ---- end step 5d io ----
}

export type OpCtx = {
  io: Io
  sessionId: string | null
  /** Shared schema-2 runtime state; ops mutate it, the event saves it once. */
  state: Json
  /** Judge answer cached per event (undefined = not asked yet). */
  judgment?: unknown
  event: string
  payload: Json
  config: Json
  root: string
  pilotExecutor: boolean
  now: number
}

export type OpSpec = {
  name: string
  phase: Phase
  configKey: string | null
  /** Optional filter on the event payload (tool name for tool events). */
  matcher?: (payload: Json) => boolean
}

export type Op = { spec: OpSpec; run: (ctx: OpCtx) => Promise<OpResult | null> }

/** What one event's ops add up to, in the mod's own vocabulary. */
export type Merged = {
  context: string | null
  drop: string | null
  deny: string | null
  block: string | null
  toast: string | null
  /** Non-blocking stderr (e.g. read_guard's warn); delivered as context by the mod. */
  notes: string | null
}
