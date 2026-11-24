#!/bin/sh
# managed by kotl (deploy/client/install.sh)
# Kotl on your own PC: the Claude Code plugins (kotl, kotl-band) and the VS Code extension,
# reading Kotl over ssh from the workstation. Get this folder with:
#
#   ssh <workstation> kotl client-bundle > kotl-client.tar && tar xf kotl-client.tar
#   ./kotl-client/install.sh [--ssh <workstation ssh name>]     install (re-run after updates)
#   ./kotl-client/install.sh --undo                             remove it all again
#
# It keeps its files in ~/.kotl-client, sets KOTL_SSH for Claude Code (~/.claude/settings.json)
# and tells the VS Code extension the workstation's name (~/.kotl-client/ssh). Needs ssh to the
# workstation with a key (no password prompt), python3, and Claude Code and/or VS Code.
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
DEST="$HOME/.kotl-client"
SSH=$(cat "$HERE/workstation" 2>/dev/null || true)
UNDO=0
while [ $# -gt 0 ]; do
  case "$1" in
    --ssh) SSH=${2:-}; shift ;;
    --undo) UNDO=1 ;;
    -h|--help) sed -n '3,15p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown option $1" >&2; exit 2 ;;
  esac
  shift
done

settings_env() {  # settings_env set NAME VALUE | settings_env unset NAME   (~/.claude/settings.json)
  python3 - "$@" <<'PY'
import json, os, sys
p = os.path.expanduser("~/.claude/settings.json")
os.makedirs(os.path.dirname(p), exist_ok=True)
try:
    s = json.load(open(p))
except (OSError, ValueError):
    s = {}
env = s.setdefault("env", {})
if sys.argv[1] == "set":
    env[sys.argv[2]] = sys.argv[3]
else:
    env.pop(sys.argv[2], None)
    if not env:
        s.pop("env")
json.dump(s, open(p, "w"), indent=2)
PY
}

if [ "$UNDO" = 1 ]; then
  if command -v claude >/dev/null; then
    claude plugin uninstall kotl@kotl >/dev/null 2>&1 && echo "- Claude Code: kotl removed"
    claude plugin uninstall kotl-band@kotl >/dev/null 2>&1 && echo "- Claude Code: kotl-band removed"
    claude plugin marketplace remove kotl >/dev/null 2>&1 && echo "- Claude Code: marketplace removed"
    settings_env unset KOTL_SSH && echo "- Claude Code: KOTL_SSH removed"
  fi
  if command -v code >/dev/null; then
    code --uninstall-extension kotl.kotl-status >/dev/null 2>&1 && echo "- VS Code: extension removed"
  fi
  rm -rf "$DEST" && echo "- removed $DEST"
  exit 0
fi

[ -n "$SSH" ] || { echo "give the workstation's ssh name: --ssh NAME" >&2; exit 2; }
echo "Workstation: $SSH"
if ssh -o BatchMode=yes -o ConnectTimeout=5 "$SSH" kotl status --json >/dev/null 2>&1; then
  echo "- ssh $SSH kotl: works"
else
  echo "! ssh $SSH kotl status failed: check you can ssh there with a key, and that you are in kotl-users"
fi

# a stable copy: Claude Code reads the plugins from this folder
if [ "$HERE" != "$DEST" ]; then mkdir -p "$(dirname "$DEST")"; rm -rf "$DEST"; cp -R "$HERE" "$DEST"; fi
printf '%s\n' "$SSH" >"$DEST/ssh"

if command -v claude >/dev/null; then
  claude plugin marketplace list 2>/dev/null | grep -q kotl || claude plugin marketplace add "$DEST" >/dev/null
  for p in kotl@kotl kotl-band@kotl; do
    claude plugin install "$p" >/dev/null 2>&1 || true
    echo "- Claude Code: $p installed"
  done
  settings_env set KOTL_SSH "$SSH" && echo "- Claude Code: KOTL_SSH=$SSH"
else
  echo "- Claude Code: not installed here; skipped"
fi

if command -v code >/dev/null; then
  code --install-extension "$DEST/kotl-status.vsix" --force >/dev/null && echo "- VS Code: extension installed (reload the window)"
else
  echo "- VS Code: the 'code' command isn't on PATH; skipped (in VS Code: Shell Command: Install 'code' command, then re-run)"
fi
echo "Done. Start a new Claude Code session; in VS Code, Kotl is in the status bar and the Kotl panel."
