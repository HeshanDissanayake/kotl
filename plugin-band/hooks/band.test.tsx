import { expect, test } from 'claude-code/testing'

const SNAP = {
  user: 'alice',
  boards: [{ name: 'vcu118-pc1', state: 'busy', job_id: 41, warnings: '["glibc differs"]' }],
  queue: [
    { job: '41', user: 'bob', name: 'kotl-run', state: 'RUNNING', eta: '30:00', used: '12:03', start: 'N/A', reason: 'None' },
    { job: '42', user: 'alice', name: 'kotl-lease', state: 'PENDING', eta: '1:00:00', used: '0:00', start: '2026-11-23T10:52:00', reason: 'Licenses' },
    { job: '43', user: 'alice', name: 'kotl-run', state: 'PENDING', eta: '30:00', used: '0:00', start: 'N/A', reason: 'Priority' },
  ],
  running_mine: [],
  unread: 2,
}

const BAND = { plugin: 'kotl-band', component: 'AbovePrompt', props: { hasSurvey: false } } as const

test('the band shows the board, who holds it, the queue and unread notices', async ($, on) => {
  on('command.register', () => ({ value: { command: 'kotl-band' } }))
  on('clock.every', () => ({ value: undefined }))
  on('clock.now', () => ({ value: 1_000 }))
  on('process.run', () => ({ value: { exitCode: 0, stdout: JSON.stringify(SNAP), stderr: '' } }))
  on('session.start', (_, e) => ({ cwd: e.cwd }))

  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  await $.command.run({ command: 'kotl-band', args: '' })

  for (const surface of ['terminal', 'desktop', 'vscode', 'mobile'] as const) {
    const ui = await $.ui.mount({ ...BAND, surface })
    expect((await ui.find({ type: 'Text', text: /vcu118-pc1/ }))?.text).toContain('vcu118-pc1 busy')
    expect((await ui.find({ type: 'Text', text: /: bob/ }))).toBeTruthy()
    expect((await ui.find({ type: 'Text', text: /run · 12m of 30m ETA/ }))).toBeTruthy()
    expect((await ui.find({ type: 'Text', text: /2 waiting/ }))).toBeTruthy()
    expect((await ui.find({ type: 'Text', text: /you: 2 jobs/ }))).toBeTruthy()
    expect((await ui.find({ type: 'Text', text: /42 lease waiting, starts ~10:52 \(1st in line\)/ }))).toBeTruthy()
    expect((await ui.find({ type: 'Text', text: /43 run waiting, starts when a board frees \(2nd in line\)/ }))).toBeTruthy()
    expect((await ui.find({ type: 'Text', text: /2 unread notices/ }))).toBeTruthy()
    await ui.unmount()
  }
})

test('/kotl-band hide hides the band', async ($, on) => {
  on('command.register', () => ({ value: { command: 'kotl-band' } }))
  on('clock.every', () => ({ value: undefined }))
  on('clock.now', () => ({ value: 1_000 }))
  on('process.run', () => ({ value: { exitCode: 0, stdout: JSON.stringify(SNAP), stderr: '' } }))
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  on('ui.render', ($, e) => {
    const { Text } = $.ui.resolve(e)
    return <Text>engine</Text>
  })

  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  await $.command.run({ command: 'kotl-band', args: 'hide' })
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect((await ui.find({ type: 'Text', text: /vcu118-pc1/ }))).toBeFalsy()
  await ui.unmount()
})


test('without Kotl the band says so instead of guessing', async ($, on) => {
  on('command.register', () => ({ value: { command: 'kotl-band' } }))
  on('clock.every', () => ({ value: undefined }))
  on('clock.now', () => ({ value: 1_000 }))
  on('process.run', () => ({ value: { exitCode: 127, stdout: '', stderr: 'not found' } }))
  on('session.start', (_, e) => ({ cwd: e.cwd }))

  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  expect((await $.command.run({ command: 'kotl-band', args: '' })).text).toBe('Kotl not reachable.')
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect((await ui.find({ type: 'Text', text: /not reachable/ }))).toBeTruthy()
  await ui.unmount()
})


test('a terminal that can\'t reach Kotl is told why', async ($, on) => {
  on('command.register', () => ({ value: { command: 'kotl-band' } }))
  on('clock.every', () => ({ value: undefined }))
  on('clock.now', () => ({ value: 1_000 }))
  const s = { ...SNAP, boards: [], problem: "this terminal can't reach Kotl: not in kotl-users yet (log in again, or restart tmux)" }
  on('process.run', () => ({ value: { exitCode: 0, stdout: JSON.stringify(s), stderr: '' } }))
  on('session.start', (_, e) => ({ cwd: e.cwd }))

  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  await $.command.run({ command: 'kotl-band', args: '' })
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect((await ui.find({ type: 'Text', text: /not in kotl-users/ }))).toBeTruthy()
  await ui.unmount()
})


test('your own running job shows as you, with its time against its ETA', async ($, on) => {
  on('command.register', () => ({ value: { command: 'kotl-band' } }))
  on('clock.every', () => ({ value: undefined }))
  on('clock.now', () => ({ value: 1_000 }))
  const s = { ...SNAP, queue: [{ job: '41', user: 'alice', name: 'kotl-run', state: 'RUNNING', eta: '1:30:00', used: '1:05:10', start: 'N/A', reason: 'None' }],
              boards: [{ name: 'vcu118-pc1', state: 'busy', job_id: 41 }], unread: 0 }
  on('process.run', () => ({ value: { exitCode: 0, stdout: JSON.stringify(s), stderr: '' } }))
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  await $.command.run({ command: 'kotl-band', args: '' })
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect((await ui.find({ type: 'Text', text: /: you/ }))).toBeTruthy()
  expect((await ui.find({ type: 'Text', text: /you: 1 job$/ }))).toBeTruthy()
  expect((await ui.find({ type: 'Text', text: /41 run running 1h05m of 1h30m ETA/ }))).toBeTruthy()
  await ui.unmount()
})


test('a refused command never stops the band (the kotl plugin owns /kotl)', async ($, on) => {
  on('command.register', () => { throw new Error('"/kotl-band" refused: taken') })
  on('clock.every', () => ({ value: undefined }))
  on('clock.now', () => ({ value: 1_000 }))
  on('process.run', () => ({ value: { exitCode: 0, stdout: JSON.stringify(SNAP), stderr: '' } }))
  on('ui.log', () => ({ value: undefined }))
  on('session.start', (_, e) => ({ cwd: e.cwd }))

  await $.session.start({ cwd: '/', surface: 'vscode', isInteractive: true })
  await new Promise(resolve => setTimeout(resolve, 20))
  const ui = await $.ui.mount({ ...BAND, surface: 'vscode' })
  expect((await ui.find({ type: 'Text', text: /vcu118-pc1/ }))).toBeTruthy()
  await ui.unmount()
})
