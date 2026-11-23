import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import type { KotlSnapshot } from '../types'

// A live Kotl line above the prompt. Reads `kotl status --json` every 30 s: on the workstation
// directly, on a user's own PC over `ssh $KOTL_SSH`. Read-only: it never starts or stops a job.
const snapshot = atom({ plugin: 'kotl-band', key: 'snapshot' } as const, null)
const isHidden = atom({ plugin: 'kotl-band', key: 'isHidden' } as const, false)
const error = atom({ plugin: 'kotl-band', key: 'error' } as const, null)

const POLL_MS = 30_000
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

let inflight: Promise<void> | null = null

// One poll at a time: a caller during a poll waits for that one's answer.
function poll($: EngineInterface): Promise<void> {
  inflight ??= fetchSnapshot($).finally(() => { inflight = null })
  return inflight
}

async function fetchSnapshot($: EngineInterface): Promise<void> {
  try {
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
    await $.command.register({
      name: 'kotl',
      description: 'Kotl line above the prompt: /kotl (refresh), /kotl hide, /kotl show',
    })
    void poll($)
    $.clock.every(POLL_MS, () => poll($))
    return started
  })

  on('command.run', { command: 'kotl' }, async ($, e) => {
    const arg = e.args.trim()
    if (arg === 'hide') {
      await update($, isHidden, () => true)
      return { text: 'Kotl line hidden (/kotl show brings it back).' }
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
    const waiting = s.queue.filter(q => q.state === 'PENDING')
    const mine = s.queue.filter(q => q.user === s.user)
    const warned = s.boards.filter(b => b.warnings && b.warnings !== '[]').length
    return (
      <Box flexDirection="column">
        <Box flexDirection="row">
          <Text color="claude" weight="bold">Kotl  </Text>
          {s.boards.length ? s.boards.map(b => {
            const q = b.job_id ? byJob.get(String(b.job_id)) : undefined
            const color = b.state === 'idle' ? 'success' : b.state === 'busy' ? 'warning' : 'error'
            return (
              <Text key={b.name}>
                {b.name} <Text color={color}>{b.state}</Text>
                {q ? <Text>: {q.user === s.user ? 'you' : q.user} <Text dimColor>· {kind(q.name)} · {usedOfEta(q)}</Text></Text> : null}
                {'   '}
              </Text>
            )
          }) : <Text dimColor>no boards   </Text>}
          <Text dimColor>· {waiting.length ? `${waiting.length} waiting` : 'nobody waiting'}</Text>
          {warned ? <Text dimColor> · {warned} warning{warned > 1 ? 's' : ''} (kotl board list)</Text> : null}
        </Box>
        <Box flexDirection="row">
          <Text>      you: {mine.length} job{mine.length === 1 ? '' : 's'}</Text>
          {mine.map(q => (
            <Text key={q.job} dimColor>
              {' '}· {q.job} {q.state === 'RUNNING' ? `${kind(q.name)} running ${usedOfEta(q)}` : `${kind(q.name)} waiting, starts ${startsAt(q.start)} (${ordinal(waiting.indexOf(q) + 1)} in line)`}
            </Text>
          ))}
          {s.unread ? <Text color="warning"> · {s.unread} unread notice{s.unread > 1 ? 's' : ''} (kotl notices)</Text> : null}
        </Box>
      </Box>
    )
  })
}
