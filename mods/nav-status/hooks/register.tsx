// nav-status: Navigator's status band and ADHD-mode injection as a Claude Code mod.
//
// Spike for the v8 runtime question (see memory project-claude-code-mods-assessment).
// While loaded it owns ADHD mode end to end and tells the Python runtime so through
// NAVIGATOR_MOD_OWNS; unloaded, hooks/ops/prompt_adhd.py keeps doing the same job.

import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import type { NavStatus } from '../types'
import {
  RULE_BLOCK, classify, personalBody, personalPath, resolve, toggleReason,
} from './adhd'
import { bandLine, isQuiet, statusOf } from './status'

const PLUGIN = 'nav-status'
const SHARED_CONFIG = '.agent/.nav-config.json'
const LOCAL_CONFIG = '.agent/.nav-config.local.json'

const status = atom({ plugin: 'nav-status', key: 'status' } as const, null as NavStatus | null)

type Json = Record<string, unknown>

const readJson = async ($: EngineInterface, path: string): Promise<Json | null> => {
  try {
    const parsed: unknown = JSON.parse(String(await $.fs.read(path)))
    return parsed !== null && typeof parsed === 'object' && !Array.isArray(parsed)
      ? (parsed as Json)
      : null
  } catch {
    return null
  }
}

const parentOf = (dir: string): string | null => {
  const cut = dir.lastIndexOf('/')
  return cut <= 0 ? null : dir.slice(0, cut)
}

/** Nearest ancestor of cwd holding `.agent/`, as nav_hook_lib.hio.project_root. */
const projectRoot = async ($: EngineInterface): Promise<string | null> => {
  let dir: string | null = await $.session.cwd()
  while (dir !== null) {
    if (await $.fs.exists(`${dir}/.agent`)) return dir
    dir = parentOf(dir)
  }
  return null
}

/** `adhd_mode.on` after DEFAULTS < shared < local merging; undefined when unset. */
const repoPin = async ($: EngineInterface): Promise<unknown> => {
  const root = await projectRoot($)
  if (root === null) return undefined
  const pinOf = (cfg: Json | null): unknown => {
    const block = cfg?.adhd_mode
    return block !== null && typeof block === 'object' && 'on' in (block as Json)
      ? (block as Json).on
      : undefined
  }
  const local = pinOf(await readJson($, `${root}/${LOCAL_CONFIG}`))
  return local !== undefined ? local : pinOf(await readJson($, `${root}/${SHARED_CONFIG}`))
}

const personalFile = async ($: EngineInterface): Promise<string> =>
  personalPath({
    NAVIGATOR_CONFIG_HOME: await $.env.get('NAVIGATOR_CONFIG_HOME'),
    XDG_CONFIG_HOME: await $.env.get('XDG_CONFIG_HOME'),
    HOME: await $.env.get('HOME'),
  })

const resolveAdhd = async ($: EngineInterface, pinned: unknown, path: string) =>
  resolve(pinned, (await readJson($, path))?.on)

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    await $.env.set('NAVIGATOR_MOD_OWNS', 'adhd')
    return next(e)
  })

  on('prompt.submit', async ($, e, next) => {
    if (await $.env.get('PILOT_EXECUTOR')) return next(e)
    const kind = classify(e.text)
    const pinned = await repoPin($)
    const path = await personalFile($)
    if (kind === null) {
      const { on: active } = await resolveAdhd($, pinned, path)
      return active ? next({ ...e, context: [...(e.context ?? []), RULE_BLOCK] }) : next(e)
    }
    if (kind === 'status') {
      const resolved = await resolveAdhd($, pinned, path)
      return { drop: toggleReason({ kind, pinned, resolved, path, wrote: false }) }
    }
    const wanted = kind === 'on'
    const wrote = await $.fs.write(path, personalBody(wanted, await $.clock.now()))
      .then(() => true, () => false)
    if (!wrote) $.ui.toast(`${PLUGIN}: could not write ${path}`)
    const resolved = await resolveAdhd($, pinned, path)
    return { drop: toggleReason({ kind, pinned, resolved, path, wrote }) }
  })

  on('turn.complete', async ($, e, next) => {
    if (e.agentId !== undefined) return next(e)
    const percent = (await $.session.usage()).context.percent
    const fresh = statusOf(e.answer, percent === undefined ? null : percent)
    await update($, status, () => fresh)
    return next(e)
  })

  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    const s = await read($, status)
    if (e.props.hasSurvey || isQuiet(s) || s === null) return next(e)
    const { Box, Text } = $.ui.resolve(e)
    return (
      <Box>
        <Text dimColor wrap="truncate-end">{bandLine(s, e.props.bodyColumns)}</Text>
      </Box>
    )
  })
}
