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

test('expanded, the band shows the board, who holds it, the queue and unread notices', async ($, on) => {
  on('command.register', () => ({ value: { command: 'kotl-band' } }))
  on('clock.every', () => ({ value: undefined }))
  on('clock.now', () => ({ value: 1_000 }))
  on('process.run', () => ({ value: { exitCode: 0, stdout: JSON.stringify(SNAP), stderr: '' } }))
  on('fs.read', () => { throw new Error('ENOENT') })
  on('session.start', (_, e) => ({ cwd: e.cwd }))

  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  await $.command.run({ command: 'kotl-band', args: '' })
  await $.command.run({ command: 'kotl-band', args: 'expand' })

  for (const surface of ['terminal', 'desktop', 'vscode', 'mobile'] as const) {
    const ui = await $.ui.mount({ ...BAND, surface })
    expect((await ui.find({ type: 'Text', text: /1 board · 1 running · 2 waiting/ }))).toBeTruthy()
    expect((await ui.find({ type: 'Text', text: /vcu118-pc1/ }))?.text).toContain('vcu118-pc1 busy')
    expect((await ui.find({ type: 'Text', text: /job 41 bob · run · 12m of 30m ETA, ~18m left/ }))).toBeTruthy()
    expect((await ui.find({ type: 'Text', text: /^41 bob$/ }))).toBeTruthy()
    expect((await ui.find({ type: 'Text', text: /run on vcu118-pc1 · 12m of 30m ETA/ }))).toBeTruthy()
    expect((await ui.find({ type: 'Text', text: /^1\. 42 you$/ }))).toBeTruthy()
    expect((await ui.find({ type: 'Text', text: /lease · ETA 1h00m · starts ~10:52 · Licenses/ }))).toBeTruthy()
    expect((await ui.find({ type: 'Text', text: /^2\. 43 you$/ }))).toBeTruthy()
    expect((await ui.find({ type: 'Text', text: /^2 jobs$/ }))).toBeTruthy()
    expect((await ui.find({ type: 'Text', text: /42 lease waiting, starts ~10:52 \(1st in line\)/ }))).toBeTruthy()
    expect((await ui.find({ type: 'Text', text: /2 unread notices/ }))).toBeTruthy()
    expect((await ui.find({ type: 'Text', text: /\u26A0 1/ }))).toBeTruthy()          // warnings: a count only
    expect((await ui.find({ type: 'Text', text: /glibc/ }))).toBeFalsy()
    await ui.unmount()
  }
})

test('/kotl-band hide hides the band', async ($, on) => {
  on('command.register', () => ({ value: { command: 'kotl-band' } }))
  on('clock.every', () => ({ value: undefined }))
  on('clock.now', () => ({ value: 1_000 }))
  on('process.run', () => ({ value: { exitCode: 0, stdout: JSON.stringify(SNAP), stderr: '' } }))
  on('fs.read', () => { throw new Error('ENOENT') })
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
  on('fs.read', () => { throw new Error('ENOENT') })
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
  on('fs.read', () => { throw new Error('ENOENT') })
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
  on('fs.read', () => { throw new Error('ENOENT') })
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  await $.command.run({ command: 'kotl-band', args: '' })
  await $.command.run({ command: 'kotl-band', args: 'expand' })
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect((await ui.find({ type: 'Text', text: /job 41 you · run · 1h05m of 1h30m ETA, ~25m left/ }))).toBeTruthy()
  expect((await ui.find({ type: 'Text', text: /^1 job$/ }))).toBeTruthy()
  expect((await ui.find({ type: 'Text', text: /41 run running 1h05m of 1h30m ETA/ }))).toBeTruthy()
  await ui.unmount()
})


test('a refused command never stops the band (the kotl plugin owns /kotl)', async ($, on) => {
  on('command.register', () => { throw new Error('"/kotl-band" refused: taken') })
  on('clock.every', () => ({ value: undefined }))
  on('clock.now', () => ({ value: 1_000 }))
  on('process.run', () => ({ value: { exitCode: 0, stdout: JSON.stringify(SNAP), stderr: '' } }))
  on('ui.log', () => ({ value: undefined }))
  on('fs.read', () => { throw new Error('ENOENT') })
  on('session.start', (_, e) => ({ cwd: e.cwd }))

  await $.session.start({ cwd: '/', surface: 'vscode', isInteractive: true })
  await new Promise(resolve => setTimeout(resolve, 20))
  const ui = await $.ui.mount({ ...BAND, surface: 'vscode' })
  expect((await ui.find({ type: 'Text', text: /vcu118-pc1/ }))).toBeTruthy()
  await ui.unmount()
})


test('reads the Kotl daemon\'s shared file, with no process per refresh', async ($, on) => {
  let runs = 0
  const doc = { updated: 1_000, boards: SNAP.boards, queue: SNAP.queue, unread: { alice: 3, bob: 1 } }
  on('command.register', () => ({ value: { command: 'kotl-band' } }))
  on('clock.every', () => ({ value: undefined }))
  on('clock.now', () => ({ value: 1_000_500 }))              // 0.5 s after the file was written
  on('fs.read', () => ({ value: JSON.stringify(doc) }))
  on('process.run', (_, e) => { runs += e.argv[0] === 'id' ? 0 : 1; return { value: { exitCode: 0, stdout: 'alice\n', stderr: '' } } })
  on('session.start', (_, e) => ({ cwd: e.cwd }))

  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  await $.command.run({ command: 'kotl-band', args: '' })
  await $.command.run({ command: 'kotl-band', args: 'expand' })
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect((await ui.find({ type: 'Text', text: /^2 jobs$/ }))).toBeTruthy()
  expect((await ui.find({ type: 'Text', text: /3 unread notices/ }))).toBeTruthy()
  expect(runs).toBe(0)                                          // only `id -un`, once
  await ui.unmount()
})

function fakes(on: Parameters<Parameters<typeof test>[1]>[1], store: Record<string, unknown>) {
  on('command.register', () => ({ value: { command: 'kotl-band' } }))
  on('clock.every', () => ({ value: undefined }))
  on('clock.now', () => ({ value: 1_000 }))
  on('process.run', () => ({ value: { exitCode: 0, stdout: JSON.stringify(SNAP), stderr: '' } }))
  on('fs.read', () => { throw new Error('ENOENT') })
  on('store.get', (_, e) => ({ value: store[e.key] ?? null }))
  on('store.set', (_, e) => { store[e.key] = e.value; return { value: undefined } })
  on('session.start', (_, e) => ({ cwd: e.cwd }))
}

test('collapsed (the default), the band is one line', async ($, on) => {
  fakes(on, {})
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  await $.command.run({ command: 'kotl-band', args: '' })
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect((await ui.find({ type: 'Text', text: /vcu118-pc1/ }))?.text).toContain('vcu118-pc1 busy')
  for (const part of [/· 2 waiting/, /· you 2/, /· 2 unread/, /\u26A0 1/]) {
    expect((await ui.find({ type: 'Text', text: part }))).toBeTruthy()
  }
  for (const gone of [/bob/, /ETA/, /starts/, /glibc/]) {
    expect((await ui.find({ type: 'Text', text: gone }))).toBeFalsy()
  }
  expect((await ui.find({ type: 'Button' }))?.text).toBe('\u25B8')
  await ui.unmount()
})

test('the button expands and collapses it, and the choice is kept', async ($, on) => {
  const store: Record<string, unknown> = {}
  fakes(on, store)
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  await $.command.run({ command: 'kotl-band', args: '' })
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  await ui.press({ key: 'kotl-band-toggle' })
  expect((await ui.find({ type: 'Text', text: /^1\. 42 you$/ }))).toBeTruthy()
  expect(store.expanded).toBe(true)
  await ui.press({ key: 'kotl-band-toggle' })
  expect((await ui.find({ type: 'Text', text: /starts/ }))).toBeFalsy()
  expect(store.expanded).toBe(false)
  await ui.unmount()
})

test('a saved choice opens it expanded; /kotl-band collapse folds it', async ($, on) => {
  const store: Record<string, unknown> = { expanded: true }
  fakes(on, store)
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  await $.command.run({ command: 'kotl-band', args: '' })
  let ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect((await ui.find({ type: 'Text', text: /^2\. 43 you$/ }))).toBeTruthy()
  await ui.unmount()
  await $.command.run({ command: 'kotl-band', args: 'collapse' })
  ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect((await ui.find({ type: 'Text', text: /starts/ }))).toBeFalsy()
  expect(store.expanded).toBe(false)
  await ui.unmount()
})
