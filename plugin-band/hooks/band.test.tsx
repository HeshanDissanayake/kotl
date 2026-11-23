import { expect, test } from 'claude-code/testing'

const SNAP = {
  user: 'alice',
  boards: [{ name: 'vcu118-pc1', state: 'busy', job_id: 41, warnings: '["glibc differs"]' }],
  queue: [
    { job: '41', user: 'bob', name: 'kotl-run', state: 'RUNNING', eta: '30:00', used: '12:03', start: 'N/A', reason: 'None' },
    { job: '42', user: 'alice', name: 'kotl-lease', state: 'PENDING', eta: '1:00:00', used: '0:00', start: '10:52', reason: 'Licenses' },
  ],
  running_mine: [],
  unread: 2,
}

const BAND = { plugin: 'kotl-band', component: 'AbovePrompt', props: { hasSurvey: false } } as const

test('the band shows the board, who holds it, the queue and unread notices', async ($, on) => {
  on('command.register', () => ({ value: { command: 'kotl' } }))
  on('clock.every', () => ({ value: undefined }))
  on('clock.now', () => ({ value: 1_000 }))
  on('process.run', () => ({ value: { exitCode: 0, stdout: JSON.stringify(SNAP), stderr: '' } }))
  on('session.start', (_, e) => ({ cwd: e.cwd }))

  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  await $.command.run({ command: 'kotl', args: '' })

  for (const surface of ['terminal', 'desktop'] as const) {
    const ui = await $.ui.mount({ ...BAND, surface })
    expect((await ui.find({ type: 'Text', text: /vcu118-pc1/ }))?.text).toContain('vcu118-pc1 busy')
    expect((await ui.find({ type: 'Text', text: /bob, run 12:03\/30:00/ }))).toBeTruthy()
    expect((await ui.find({ type: 'Text', text: /1 waiting/ }))).toBeTruthy()
    expect((await ui.find({ type: 'Text', text: /2 unread/ }))).toBeTruthy()
    await ui.unmount()
  }
})

test('/kotl hide hides the band', async ($, on) => {
  on('command.register', () => ({ value: { command: 'kotl' } }))
  on('clock.every', () => ({ value: undefined }))
  on('clock.now', () => ({ value: 1_000 }))
  on('process.run', () => ({ value: { exitCode: 0, stdout: JSON.stringify(SNAP), stderr: '' } }))
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  on('ui.render', ($, e) => {
    const { Text } = $.ui.resolve(e)
    return <Text>engine</Text>
  })

  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  await $.command.run({ command: 'kotl', args: 'hide' })
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect((await ui.find({ type: 'Text', text: /vcu118-pc1/ }))).toBeFalsy()
  await ui.unmount()
})


test('without Kotl the band says so instead of guessing', async ($, on) => {
  on('command.register', () => ({ value: { command: 'kotl' } }))
  on('clock.every', () => ({ value: undefined }))
  on('clock.now', () => ({ value: 1_000 }))
  on('process.run', () => ({ value: { exitCode: 127, stdout: '', stderr: 'not found' } }))
  on('session.start', (_, e) => ({ cwd: e.cwd }))

  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  expect((await $.command.run({ command: 'kotl', args: '' })).text).toBe('Kotl not reachable.')
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect((await ui.find({ type: 'Text', text: /not reachable/ }))).toBeTruthy()
  await ui.unmount()
})


test('a terminal that can\'t reach Kotl is told why', async ($, on) => {
  on('command.register', () => ({ value: { command: 'kotl' } }))
  on('clock.every', () => ({ value: undefined }))
  on('clock.now', () => ({ value: 1_000 }))
  const s = { ...SNAP, boards: [], problem: "this terminal can't reach Kotl: not in kotl-users yet (log in again, or restart tmux)" }
  on('process.run', () => ({ value: { exitCode: 0, stdout: JSON.stringify(s), stderr: '' } }))
  on('session.start', (_, e) => ({ cwd: e.cwd }))

  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  await $.command.run({ command: 'kotl', args: '' })
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect((await ui.find({ type: 'Text', text: /not in kotl-users/ }))).toBeTruthy()
  await ui.unmount()
})
