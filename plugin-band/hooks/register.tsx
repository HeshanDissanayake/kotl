import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import type { KotlSnapshot } from '../types'

// A live Kotl band above the prompt. Every second it reads the Kotl daemon's shared status file
// (/run/kotl/status.json), with no process started. When that file is missing or stale (the
// daemon is down, or this is a user's own PC), it runs `kotl status --json` instead, locally or
// over `ssh $KOTL_SSH`, at most every 5 s. Read-only: it never starts or stops a job.
// Collapsed (the default): one short line. Expanded: the full status: each board (who, what,
// time against ETA, last check), the running jobs, everyone waiting in order, your jobs. Board
// warnings show only as a ⚠ count (details: kotl board list, or ask Claude). The ▸/▾ button (or k, once the band has the focus) and /kotl-band expand|collapse
// switch; the choice is kept for the next session.
const snapshot = atom({ plugin: 'kotl-band', key: 'snapshot' } as const, null)
const isHidden = atom({ plugin: 'kotl-band', key: 'isHidden' } as const, false)
const isExpanded = atom({ plugin: 'kotl-band', key: 'isExpanded' } as const, false)
const error = atom({ plugin: 'kotl-band', key: 'error' } as const, null)
const EXPANDED_KEY = 'expanded'      // in $.store: the choice, across sessions
const MAX_WAITING_ROWS = 8

const POLL_MS = 1_000
const SHARED = '/run/kotl/status.json'
const SHARED_MAX_AGE_MS = 5_000
const FALLBACK_MS = 5_000     // asking directly (or over ssh from a user's own PC)
const LOCAL = ['kotl', 'status', '--json']
const REMOTE = ['sh', '-c', '[ -n "$KOTL_SSH" ] || exit 127; exec ssh -o BatchMode=yes -o ConnectTimeout=5 "$KOTL_SSH" kotl status --json']

// Slurm times: '12:03' (m:s), '1:02:03' (h:m:s), '1-02:00:00' (d-h:m:s)
function minutes(slurmTime: string): number | null {
  const m = /^(?:(\d+)-)?(?:(\d+):)?(\d+):(\d+)$/.exec(slurmTime.trim())
  if (!m) return null
  const [, d, h, mi] = m
  return (Number(d ?? 0) * 24 + Number(h ?? 0)) * 60 + Number(mi)
}
function fmtMin(n: number | null): string {
  if (n === null) return '?'
  return n >= 60 ? `${Math.floor(n / 60)}h${String(n % 60).padStart(2, '0')}m` : `${n}m`
}
function usedOfEta(q: { used: string; eta: string }): string {
  return `${fmtMin(minutes(q.used))} of ${fmtMin(minutes(q.eta))} ETA`
}
function kind(name: string): string {
  return name.replace(/^kotl-/, '')
}
// squeue's estimated start: '2026-11-23T10:52:00', or 'N/A' when Slurm has none yet
function startsAt(start: string): string {
  const m = /T(\d\d:\d\d)/.exec(start)
  return m ? `~${m[1]}` : 'when a board frees'
}
function ordinal(n: number): string {
  return n === 1 ? '1st' : n === 2 ? '2nd' : n === 3 ? '3rd' : `${n}th`
}

async function setExpanded($: EngineInterface, on: boolean): Promise<void> {
  await update($, isExpanded, () => on)
  try { await $.store.set(EXPANDED_KEY, on) } catch { /* kept for this session only */ }
}

function warningsOf(w: string | null | undefined): string[] {
  if (!w || w === '[]') return []
  try { const v = JSON.parse(w); return Array.isArray(v) ? v.map(String) : [String(w)] } catch { return [String(w)] }
}

let inflight: Promise<void> | null = null
let me: string | null = null
let lastFallback = 0

async function whoAmI($: EngineInterface): Promise<string> {
  if (me) return me
  try {
    const r = await $.process.run(['id', '-un'], { timeoutMs: 5_000 })
    if (r.exitCode === 0) me = r.stdout.trim()
  } catch { /* unknown: your own jobs just won't be marked */ }
  return me ?? ''
}

// The daemon's file, seen by this user; null when missing or older than SHARED_MAX_AGE_MS
async function fromShared($: EngineInterface): Promise<Omit<KotlSnapshot, 'at'> | null> {
  let text: string
  try { text = await $.fs.read(SHARED) } catch { return null }
  const doc = JSON.parse(text) as { updated: number; boards: KotlSnapshot['boards']; queue: KotlSnapshot['queue']; unread?: Record<string, number> }
  if ((await $.clock.now()) - doc.updated * 1000 > SHARED_MAX_AGE_MS) return null
  const user = await whoAmI($)
  return {
    user, boards: doc.boards, queue: doc.queue, problem: null,
    running_mine: doc.queue.filter(q => q.user === user && q.state === 'RUNNING').map(q => ({ job_id: Number(q.job), mode: q.name.replace('kotl-', '') })),
    unread: doc.unread?.[user] ?? 0,
  }
}

// One poll at a time: a caller during a poll waits for that one's answer.
function poll($: EngineInterface): Promise<void> {
  inflight ??= fetchSnapshot($).finally(() => { inflight = null })
  return inflight
}

async function fetchSnapshot($: EngineInterface): Promise<void> {
  try {
    const shared = await fromShared($).catch(() => null)
    if (shared) {
      const at = await $.clock.now()
      await update($, snapshot, () => ({ ...shared, at }))
      await update($, error, () => null)
      return
    }
    // no fresh shared file: ask Kotl directly, but not every second
    const now = await $.clock.now()
    if (now - lastFallback < FALLBACK_MS && (await read($, snapshot)) !== null) return
    lastFallback = now
    let out: string | null = null
    for (const argv of [LOCAL, REMOTE]) {
      try {
        const r = await $.process.run(argv, { timeoutMs: 15_000 })
        if (r.exitCode === 0) { out = r.stdout; break }
      } catch { /* not installed here: try the next way */ }
    }
    if (out === null) {
      await update($, error, () => 'Kotl not reachable (no kotl here, KOTL_SSH unset or failing)')
      return
    }
    const s = JSON.parse(out) as Omit<KotlSnapshot, 'at'>
    const at = await $.clock.now()
    await update($, snapshot, () => ({ ...s, at }))
    await update($, error, () => null)
  } catch (e) {
    await update($, error, () => `Kotl: ${String(e).slice(0, 120)}`)
  }
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    const started = await next(e)
    // the band's own work first: a refused command below must never stop it
    void poll($)
    $.clock.every(POLL_MS, () => poll($))
    try {
      if ((await $.store.get(EXPANDED_KEY)) === true) await update($, isExpanded, () => true)
    } catch { /* no saved choice: collapsed */ }
    try {
      // not /kotl: that name belongs to the kotl plugin's skill
      await $.command.register({
        name: 'kotl-band',
        description: 'The Kotl band above the prompt: /kotl-band (refresh), expand, collapse, hide, show',
      })
    } catch (err) {
      $.ui.log(`kotl-band: /kotl-band not registered: ${String(err).slice(0, 200)}`, { to: 'debug' })
    }
    return started
  })

  on('command.run', { command: 'kotl-band' }, async ($, e) => {
    const arg = e.args.trim()
    if (arg === 'expand' || arg === 'collapse') {
      await setExpanded($, arg === 'expand')
      await update($, isHidden, () => false)
      return { text: arg === 'expand' ? 'Kotl band expanded: boards, your jobs and everyone waiting.' : 'Kotl band collapsed to one line.' }
    }
    if (arg === 'hide') {
      await update($, isHidden, () => true)
      return { text: 'Kotl band hidden (/kotl-band show brings it back).' }
    }
    await update($, isHidden, () => false)
    await poll($)
    const s = await read($, snapshot)
    return { text: s ? `Kotl line refreshed: ${s.boards.length} board(s), ${s.queue.filter(q => q.state === 'PENDING').length} waiting.` : 'Kotl not reachable.' }
  })

  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    if (e.props.hasSurvey || (await read($, isHidden))) return next(e)
    const s = await read($, snapshot)
    const err = await read($, error)
    const { Box, Text } = $.ui.resolve(e)
    if (!s) return err ? <Box><Text dimColor>{err}</Text></Box> : next(e)
    if (s.problem) return <Box><Text color="claude" weight="bold">Kotl </Text><Text color="warning">{s.problem}</Text></Box>

    const byJob = new Map(s.queue.map(q => [q.job, q]))
    const running = s.queue.filter(q => q.state === 'RUNNING')
    const waiting = s.queue.filter(q => q.state === 'PENDING')
    const mine = s.queue.filter(q => q.user === s.user)
    const warned = s.boards.filter(b => warningsOf(b.warnings).length).length
    const expanded = await read($, isExpanded)
    const { Button } = $.ui.resolve(e)
    const toggle = (
      <Button key="kotl-band-toggle" plain hotkey="k" label={expanded ? '\u25BE' : '\u25B8'}
        onPress={() => setExpanded($, !expanded)} />
    )
    const who = (u: string) => (u === s.user ? 'you' : u)
    const stateColor = (st: string) => (st === 'idle' ? 'success' : st === 'busy' ? 'warning' : 'error')
    const warnIcon = warned ? <Text color="warning"> {'\u26A0'} {warned}</Text> : null

    if (!expanded) {
      return (
        <Box flexDirection="row">
          {toggle}
          <Text color="claude" weight="bold"> Kotl </Text>
          {s.boards.length ? s.boards.map(b => (
            <Text key={b.name}> {b.name} <Text color={stateColor(b.state)}>{b.state}</Text></Text>
          )) : <Text dimColor> no boards</Text>}
          {waiting.length ? <Text dimColor> · {waiting.length} waiting</Text> : null}
          {mine.length ? <Text dimColor> · you {mine.length}</Text> : null}
          {s.unread ? <Text color="warning"> · {s.unread} unread</Text> : null}
          {warnIcon}
        </Box>
      )
    }

    const label = (t: string) => <Text dimColor>{('  ' + t).padEnd(11)}</Text>
    const left = (q: { used: string; eta: string }) => {
      const u = minutes(q.used), e2 = minutes(q.eta)
      if (u === null || e2 === null) return ''
      return u <= e2 ? `, ~${fmtMin(e2 - u)} left` : `, ${fmtMin(u - e2)} over ETA`
    }
    const boardOf = new Map(s.boards.filter(b => b.job_id).map(b => [String(b.job_id), b.name]))
    return (
      <Box flexDirection="column">
        <Box flexDirection="row">
          {toggle}
          <Text color="claude" weight="bold"> Kotl </Text>
          <Text dimColor> {s.boards.length} board{s.boards.length === 1 ? '' : 's'} · {running.length} running · {waiting.length} waiting</Text>
          {warnIcon}{warned ? <Text dimColor> (kotl board list)</Text> : null}
        </Box>
        {s.boards.map((b, i) => {
          const q = b.job_id ? byJob.get(String(b.job_id)) : undefined
          return (
            <Box key={`b${b.name}`} flexDirection="row">
              {label(i === 0 ? 'boards' : '')}
              <Text>{b.name}{b.type ? <Text dimColor> ({b.type})</Text> : null} <Text color={stateColor(b.state)}>{b.state}</Text></Text>
              {q ? <Text dimColor> · job {q.job} {who(q.user)} · {kind(q.name)} · {usedOfEta(q)}{left(q)}</Text> : null}
              {b.last_healthy ? <Text dimColor> · checked {b.last_healthy.slice(-5)}</Text> : null}
            </Box>
          )
        })}
        {running.map((q, i) => (
          <Box key={`r${q.job}`} flexDirection="row">
            {label(i === 0 ? 'running' : '')}
            <Text>{q.job} {who(q.user)}</Text>
            <Text dimColor> · {kind(q.name)}{boardOf.get(q.job) ? ` on ${boardOf.get(q.job)}` : ''} · {usedOfEta(q)}{left(q)}</Text>
          </Box>
        ))}
        {waiting.slice(0, MAX_WAITING_ROWS).map((q, i) => (
          <Box key={`w${q.job}`} flexDirection="row">
            {label(i === 0 ? 'waiting' : '')}
            <Text>{i + 1}. {q.job} {who(q.user)}</Text>
            <Text dimColor> · {kind(q.name)} · ETA {fmtMin(minutes(q.eta))} · starts {startsAt(q.start)}{q.reason && q.reason !== 'None' ? ` · ${q.reason}` : ''}</Text>
          </Box>
        ))}
        {waiting.length > MAX_WAITING_ROWS ? <Box flexDirection="row">{label('')}<Text dimColor>and {waiting.length - MAX_WAITING_ROWS} more (kotl status)</Text></Box> : null}
        <Box flexDirection="row">
          {label('you')}
          <Text>{mine.length ? `${mine.length} job${mine.length === 1 ? '' : 's'}` : 'no jobs'}</Text>
          {mine.map(q => (
            <Text key={`m${q.job}`} dimColor>
              {' '}· {q.job} {q.state === 'RUNNING' ? `${kind(q.name)} running ${usedOfEta(q)}` : `${kind(q.name)} waiting, starts ${startsAt(q.start)} (${ordinal(waiting.indexOf(q) + 1)} in line)`}
            </Text>
          ))}
          {s.unread ? <Text color="warning"> · {s.unread} unread notice{s.unread > 1 ? 's' : ''} (kotl notices)</Text> : null}
        </Box>
      </Box>
    )
  })
}
