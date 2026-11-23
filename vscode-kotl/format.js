// What the Kotl status bar shows, from `kotl status --json`. Pure functions, tested with node.
'use strict';

// Slurm times: '12:03' (m:s), '1:02:03' (h:m:s), '1-02:00:00' (d-h:m:s) -> minutes
function minutes(t) {
  const m = /^(?:(\d+)-)?(?:(\d+):)?(\d+):(\d+)$/.exec(String(t || '').trim());
  if (!m) return null;
  return (Number(m[1] || 0) * 24 + Number(m[2] || 0)) * 60 + Number(m[3]);
}
function fmt(n) {
  if (n === null) return '?';
  return n >= 60 ? `${Math.floor(n / 60)}h${String(n % 60).padStart(2, '0')}m` : `${n}m`;
}
const usedOfEta = q => `${fmt(minutes(q.used))}/${fmt(minutes(q.eta))}`;
const kind = name => String(name || '').replace(/^kotl-/, '');
function startsAt(start) {
  const m = /T(\d\d:\d\d)/.exec(String(start || ''));
  return m ? `~${m[1]}` : 'when a board frees';
}
const ordinal = n => (n === 1 ? '1st' : n === 2 ? '2nd' : n === 3 ? '3rd' : `${n}th`);

function parts(s) {
  const byJob = new Map(s.queue.map(q => [q.job, q]));
  const waiting = s.queue.filter(q => q.state === 'PENDING');
  const mine = s.queue.filter(q => q.user === s.user);
  return { byJob, waiting, mine };
}

// The short text in the status bar.
function statusText(s) {
  if (!s) return '$(circuit-board) Kotl: …';
  if (s.problem) return '$(warning) Kotl: unreachable';
  const { byJob, waiting, mine } = parts(s);
  const boards = s.boards.map(b => {
    const q = b.job_id ? byJob.get(String(b.job_id)) : null;
    const who = q ? ` · ${q.user === s.user ? 'you' : q.user} ${usedOfEta(q)}` : '';
    return `${b.name} ${b.state}${who}`;
  });
  const bits = [boards.join(' | ') || 'no boards'];
  if (waiting.length) bits.push(`${waiting.length} waiting`);
  bits.push(`you: ${mine.length} job${mine.length === 1 ? '' : 's'}`);
  if (s.unread) bits.push(`$(bell) ${s.unread}`);
  return `$(circuit-board) Kotl: ${bits.join(' · ')}`;
}

// The hover: everything, in Markdown.
function tooltip(s, now) {
  if (!s) return 'Kotl: reading status…';
  if (s.problem) return `**Kotl can't be reached here.**\n\n${s.problem}`;
  const { byJob, waiting, mine } = parts(s);
  const out = ['**Kotl: the lab\'s FPGA board queue**', '', '| Board | State | Held by | Used / ETA |', '|---|---|---|---|'];
  for (const b of s.boards) {
    const q = b.job_id ? byJob.get(String(b.job_id)) : null;
    out.push(`| ${b.name} | ${b.state} | ${q ? `${q.user === s.user ? 'you' : q.user} (job ${q.job}, ${kind(q.name)})` : '–'} | ${q ? usedOfEta(q) : '–'} |`);
  }
  const warnings = s.boards.flatMap(b => { try { return JSON.parse(b.warnings || '[]').map(w => `${b.name}: ${w}`); } catch (e) { return []; } });
  if (warnings.length) out.push('', '**Warnings**', ...warnings.map(w => `- ${w}`));
  out.push('', `**Waiting:** ${waiting.length ? '' : 'nobody'}`);
  waiting.forEach((q, i) => out.push(`- ${ordinal(i + 1)}: job ${q.job} (${q.user}, ${kind(q.name)}, ETA ${fmt(minutes(q.eta))}), starts ${startsAt(q.start)}`));
  out.push('', `**Your jobs:** ${mine.length}`);
  for (const q of mine) {
    out.push(q.state === 'RUNNING'
      ? `- job ${q.job} ${kind(q.name)} running, ${usedOfEta(q)} of its ETA`
      : `- job ${q.job} ${kind(q.name)} waiting, starts ${startsAt(q.start)} (${ordinal(waiting.indexOf(q) + 1)} in line)`);
  }
  if (s.unread) out.push('', `**${s.unread} unread notice${s.unread > 1 ? 's' : ''}** (Kotl: Show notices)`);
  out.push('', `_Click to open kotl top. Updated ${new Date(now || Date.now()).toLocaleTimeString()}._`);
  return out.join('\n');
}

module.exports = { minutes, fmt, statusText, tooltip };
