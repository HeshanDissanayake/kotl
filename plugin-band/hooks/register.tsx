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

const short = (slurmTime: string) => slurmTime.replace(/^0:/, '').replace(/^(\d+):(\d\d):\d\d$/, '$1h$2m')

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
    const warned = s.boards.filter(b => b.warnings && b.warnings !== '[]').length
    return (
      <Box flexDirection="row">
        <Text color="claude" weight="bold">Kotl </Text>
        {s.boards.map(b => {
          const q = b.job_id ? byJob.get(String(b.job_id)) : undefined
          const color = b.state === 'idle' ? 'success' : b.state === 'busy' ? 'warning' : 'error'
          return (
            <Text key={b.name}>
              {b.name} <Text color={color}>{b.state}</Text>
              {q ? <Text dimColor> ({q.user}, {q.name.replace('kotl-', '')} {short(q.used)}/{short(q.eta)})</Text> : null}
              {'  '}
            </Text>
          )
        })}
        <Text dimColor>· {waiting.length ? `${waiting.length} waiting` : 'nobody waiting'}</Text>
        {s.running_mine.length ? <Text> · you: job {s.running_mine.map(j => j.job_id).join(', ')}</Text> : null}
        {s.unread ? <Text color="warning"> · {s.unread} unread (kotl notices)</Text> : null}
        {warned ? <Text dimColor> · {warned} warning{warned > 1 ? 's' : ''} (kotl board list)</Text> : null}
      </Box>
    )
  })
}
