'use strict';
const test = require('node:test');
const assert = require('node:assert');
const { minutes, statusText, tooltip } = require('../format');

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
