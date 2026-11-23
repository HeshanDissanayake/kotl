// Kotl in VS Code's status bar. Reads `kotl status --json` (locally, or over ssh with the
// kotl.ssh setting) every 30 s. Read-only: it never starts or stops a job.
'use strict';
const vscode = require('vscode');
const { execFile } = require('child_process');
const { statusText, tooltip } = require('./format');

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

function activate(context) {
  const item = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 50);
  item.command = 'kotl.top';
  item.text = statusText(null);
  item.show();
  context.subscriptions.push(item);

  let timer = null;
  const refresh = async () => {
    const cfg = vscode.workspace.getConfiguration('kotl');
    const s = await readStatus(cfg.get('ssh') || process.env.KOTL_SSH || '');
    item.text = statusText(s);
    const md = new vscode.MarkdownString(tooltip(s, Date.now()));
    md.supportThemeIcons = true;
    item.tooltip = md;
    item.backgroundColor = s.problem || s.unread ? new vscode.ThemeColor('statusBarItem.warningBackground') : undefined;
  };
  const schedule = () => {
    if (timer) clearInterval(timer);
    const secs = Math.max(10, vscode.workspace.getConfiguration('kotl').get('refreshSeconds') || 30);
    timer = setInterval(refresh, secs * 1000);
  };
  const terminal = (name, cmd) => {
    const ssh = vscode.workspace.getConfiguration('kotl').get('ssh') || process.env.KOTL_SSH || '';
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
