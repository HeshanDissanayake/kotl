// Kotl in VS Code: the status bar and the Kotl panel. On the workstation it reads the Kotl
// daemon's shared status file (/run/kotl/status.json) every second, with no process started;
// when that file is missing or stale it runs `kotl status --json`, at most every 30 s. With the
// kotl.ssh setting (your own PC) it reads the same file over ssh every few seconds.
// Read-only: it never starts or stops a job.
'use strict';
const vscode = require('vscode');
const fs = require('fs');
const os = require('os');
const { execFile } = require('child_process');
const { statusText, tooltip, tree, fromShared } = require('./format');

const SHARED = '/run/kotl/status.json';
const CLIENT_SSH = require('path').join(os.homedir(), '.kotl-client', 'ssh');   // set by kotl-client/install.sh

// The workstation's ssh name on a user's own PC: the kotl.ssh setting, KOTL_SSH, or ~/.kotl-client/ssh
function sshName() {
  const set = vscode.workspace.getConfiguration('kotl').get('ssh') || process.env.KOTL_SSH;
  if (set) return set;
  try { return fs.readFileSync(CLIENT_SSH, 'utf8').trim(); } catch (e) { return ''; }
}
const USER = os.userInfo().username;
let lastFallback = 0;
let lastSnap = null;

async function readSnapshot(ssh) {
  if (ssh) {
    const doc = await new Promise(resolve => execFile('ssh', ['-o', 'BatchMode=yes', '-o', 'ConnectTimeout=5', ssh, `cat ${SHARED}; echo; id -un`],
      { timeout: 10000 }, (err, out) => resolve(err ? null : out)));
    if (doc) {
      const lines = doc.trim().split('\n');
      try { const s = fromShared(JSON.parse(lines.slice(0, -1).join('\n')), lines[lines.length - 1], Date.now()); if (s) return s; } catch (e) { /* fall back */ }
    }
  } else {
    try { const s = fromShared(JSON.parse(await fs.promises.readFile(SHARED, 'utf8')), USER, Date.now()); if (s) return s; } catch (e) { /* fall back */ }
  }
  if (lastSnap && Date.now() - lastFallback < 30000) return lastSnap;   // ask directly at most every 30 s
  lastFallback = Date.now();
  return readStatus(ssh);
}

function readStatus(ssh) {
  const [cmd, args] = ssh
    ? ['ssh', ['-o', 'BatchMode=yes', '-o', 'ConnectTimeout=5', ssh, 'kotl status --json']]
    : ['kotl', ['status', '--json']];
  return new Promise(resolve => {
    execFile(cmd, args, { timeout: 20000 }, (err, stdout, stderr) => {
      if (err) return resolve({ problem: `${cmd === 'ssh' ? `ssh ${ssh}` : 'kotl'} failed: ${(stderr || err.message).trim().split('\n').pop()}` });
      try { resolve(JSON.parse(stdout)); } catch (e) { resolve({ problem: 'kotl status --json gave no JSON' }); }
    });
  });
}

class KotlTree {
  constructor() { this.snap = null; this._ev = new vscode.EventEmitter(); this.onDidChangeTreeData = this._ev.event; }
  set(s) { this.snap = s; this._ev.fire(); }
  getChildren(el) { return el ? el.children || [] : tree(this.snap); }
  getTreeItem(el) {
    const kids = el.children && el.children.length;
    const it = new vscode.TreeItem(el.label, kids ? vscode.TreeItemCollapsibleState.Expanded : vscode.TreeItemCollapsibleState.None);
    it.description = el.description;
    it.tooltip = el.tooltip || [el.label, el.description].filter(Boolean).join(' — ');
    if (el.state) it.iconPath = new vscode.ThemeIcon('circuit-board', new vscode.ThemeColor(el.state === 'idle' ? 'testing.iconPassed' : el.state === 'busy' ? 'list.warningForeground' : 'list.errorForeground'));
    if (el.command) it.command = { command: el.command, title: el.label };
    return it;
  }
}

function activate(context) {
  const panel = new KotlTree();
  context.subscriptions.push(vscode.window.registerTreeDataProvider('kotl.status', panel));
  if (!context.globalState.get('kotl.welcomed')) {
    context.globalState.update('kotl.welcomed', true);
    vscode.window.showInformationMessage('Kotl is in the status bar (bottom left) and in the Kotl panel (the chip icon on the left).', 'Open Kotl panel')
      .then(pick => pick && vscode.commands.executeCommand('workbench.view.extension.kotl'));
  }
  const item = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 50);
  item.command = 'kotl.top';
  item.text = statusText(null);
  item.show();
  context.subscriptions.push(item);

  let mine = '';
  try { mine = require('fs').readFileSync(require('path').join(context.extensionPath, 'BUILD'), 'utf8').trim(); } catch (e) { /* a dev copy */ }
  const nudged = () => context.globalState.get('kotl.nudged');
  const nudge = (current) => {
    if (!mine || !current || current === mine || nudged() === current) return false;
    context.globalState.update('kotl.nudged', current);
    vscode.window.showInformationMessage(`Kotl was updated (${current}). Run "kotl setup" in a terminal, then reload the window, to get the new extension and Claude plugins.`, 'Run kotl setup')
      .then(pick => pick && terminal('Kotl setup', 'kotl setup'));
    return true;
  };

  let timer = null;
  const refresh = async () => {
    const cfg = vscode.workspace.getConfiguration('kotl');
    const ssh = sshName();
    const s = await readSnapshot(ssh);
    lastSnap = s;
    const outdated = !!(mine && s && s.build && s.build !== mine);
    item.text = statusText(s) + (outdated ? ' $(arrow-up)' : '');
    if (outdated) nudge(s.build);
    panel.set(s);
    const md = new vscode.MarkdownString(tooltip(s, Date.now()) + (outdated ? `\n\n$(arrow-up) Kotl was updated (${s.build}; yours: ${mine}): run \`kotl setup\`, then reload.` : ''));
    md.supportThemeIcons = true;
    item.tooltip = md;
    item.backgroundColor = s.problem || s.unread || outdated ? new vscode.ThemeColor('statusBarItem.warningBackground') : undefined;
  };
  const schedule = () => {
    if (timer) clearInterval(timer);
    const cfg = vscode.workspace.getConfiguration('kotl');
    const remote = sshName();
    const secs = Math.max(remote ? 5 : 1, cfg.get('refreshSeconds') || 1);
    timer = setInterval(refresh, secs * 1000);
  };
  const terminal = (name, cmd) => {
    const ssh = sshName();
    const t = vscode.window.createTerminal({ name });
    t.sendText(ssh ? `ssh -t ${ssh} ${cmd}` : cmd);
    t.show();
  };

  context.subscriptions.push(
    vscode.commands.registerCommand('kotl.refresh', refresh),
    vscode.commands.registerCommand('kotl.top', () => terminal('Kotl', 'kotl top')),
    vscode.commands.registerCommand('kotl.notices', async () => { terminal('Kotl notices', 'kotl notices'); setTimeout(refresh, 3000); }),
    vscode.workspace.onDidChangeConfiguration(e => { if (e.affectsConfiguration('kotl')) { schedule(); refresh(); } }),
    { dispose: () => timer && clearInterval(timer) },
  );
  refresh();
  schedule();
}

function deactivate() {}
module.exports = { activate, deactivate };
