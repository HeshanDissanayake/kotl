// Kotl in VS Code's status bar. Reads `kotl status --json` (locally, or over ssh with the
// kotl.ssh setting) every 30 s. Read-only: it never starts or stops a job.
'use strict';
const vscode = require('vscode');
const { execFile } = require('child_process');
const { statusText, tooltip, tree } = require('./format');

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

  let timer = null;
  const refresh = async () => {
    const cfg = vscode.workspace.getConfiguration('kotl');
    const s = await readStatus(cfg.get('ssh') || process.env.KOTL_SSH || '');
    item.text = statusText(s);
    panel.set(s);
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
