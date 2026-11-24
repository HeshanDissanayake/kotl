'use strict';
const test = require('node:test');
const assert = require('node:assert');
const { minutes, statusText, tooltip, tree, fromShared } = require('../format');

const SNAP = {
  user: 'alice',
  boards: [{ name: 'vcu118-pc1', state: 'busy', job_id: 41, warnings: '["glibc differs"]' }],
  queue: [
    { job: '41', user: 'bob', name: 'kotl-run', state: 'RUNNING', eta: '30:00', used: '12:03', start: 'N/A', reason: 'None' },
    { job: '42', user: 'alice', name: 'kotl-lease', state: 'PENDING', eta: '1:00:00', used: '0:00', start: '2026-11-23T10:52:00', reason: 'Licenses' },
    { job: '43', user: 'alice', name: 'kotl-run', state: 'PENDING', eta: '30:00', used: '0:00', start: 'N/A', reason: 'Priority' },
  ],
  running_mine: [], unread: 2, problem: null,
};

test('slurm times', () => {
  assert.equal(minutes('12:03'), 12); assert.equal(minutes('1:05:10'), 65); assert.equal(minutes('1-02:00:00'), 1560);
  assert.equal(minutes('N/A'), null);
});

test('status bar: who holds the board, waiting, my job count, notices', () => {
  assert.equal(statusText(SNAP), '$(circuit-board) Kotl: vcu118-pc1 busy · bob 12m/30m · 2 waiting · you: 2 jobs · $(bell) 2');
});

test('my own job shows as you', () => {
  const s = { ...SNAP, user: 'bob', unread: 0 };
  assert.equal(statusText(s), '$(circuit-board) Kotl: vcu118-pc1 busy · you 12m/30m · 2 waiting · you: 1 job');
});

test('hover has the queue, my ETA and place in line, and warnings', () => {
  const t = tooltip(SNAP, 0);
  assert.match(t, /\| vcu118-pc1 \| busy \| bob \(job 41, run\) \| 12m\/30m \|/);
  assert.match(t, /- vcu118-pc1: glibc differs/);
  assert.match(t, /job 42 lease waiting, starts ~10:52 \(1st in line\)/);
  assert.match(t, /job 43 run waiting, starts when a board frees \(2nd in line\)/);
  assert.match(t, /\*\*2 unread notices\*\*/);
});

test('unreachable says why', () => {
  const s = { problem: "this terminal can't reach Kotl: not in kotl-users yet" };
  assert.equal(statusText(s), '$(warning) Kotl: unreachable');
  assert.match(tooltip(s), /not in kotl-users/);
});

test('panel: boards, waiting, your jobs, notices', () => {
  const [boards, waiting, mine, notices] = tree(SNAP);
  assert.equal(boards.children[0].description, 'busy · bob · run · 12m/30m of ETA');
  assert.equal(boards.children[0].children[0].label, '⚠ glibc differs');
  assert.equal(waiting.description, '2');
  assert.equal(waiting.children[0].label, '1st: job 42');
  assert.equal(mine.description, '2');
  assert.equal(mine.children[0].description, 'waiting · starts ~10:52 · 1st in line');
  assert.equal(notices.description, '2 unread');
  assert.equal(notices.command, 'kotl.notices');
});

test('panel says why when unreachable', () => {
  const t = tree({ problem: 'not in kotl-users yet' });
  assert.equal(t[0].label, "Kotl can't be reached here");
  assert.equal(t[0].children[0].label, 'not in kotl-users yet');
});

test('the daemon\'s shared file, seen by one user; stale means ask directly', () => {
  const doc = { updated: 1000, boards: SNAP.boards, queue: SNAP.queue, unread: { alice: 4 } };
  const s = fromShared(doc, 'alice', 1000 * 1000 + 800);
  assert.equal(s.unread, 4); assert.equal(s.user, 'alice');
  assert.equal(statusText(s), '$(circuit-board) Kotl: vcu118-pc1 busy · bob 12m/30m · 2 waiting · you: 2 jobs · $(bell) 4');
  assert.equal(fromShared(doc, 'alice', 1000 * 1000 + 6000), null);
  assert.equal(fromShared(null, 'alice', 0), null);
});
