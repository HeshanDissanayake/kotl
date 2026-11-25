#!/usr/bin/env bash
# Install (or update) Kotl's own code on the workstation. Run as root, from the repo, after M1.
#
#   kotl/install.sh --board vcu118-pc1=vcu118@vcu118-pc1
#       copies kotl/ to /opt/kotl/lib, installs /opt/kotl/launch, /opt/kotl/job.sh,
#       /opt/kotl/epilog.sh, the kotl command (/opt/kotl/bin/kotl, linked from /usr/local/bin),
#       an SSH client entry per board (/etc/ssh/ssh_config.d/kotl.conf: your job key during a lease),
#       the Kotl daemon (kotl-daemon.service: kotld, Kotl's one always-running process),
#       the Claude Code plugin (/opt/kotl/plugin, a marketplace at /opt/kotl: users add it with
#       /plugin marketplace add /opt/kotl; each enabled adapter's skill with it, and its user tools
#       in /opt/kotl/adapters), Kotl's rules for every Claude Code session
#       (/etc/claude-code/CLAUDE.md, kept as is if the admin wrote their own), the notifier's systemd timer (every minute), adds each board to the registry, and makes
#       kotl a Slurm admin (its guards cancel hung jobs; its health check holds a down board's
#       license with a reservation). Re-run after every update of the repo.
#   kotl/install.sh --adapters firesim   also switches adapters on (kotl.conf `adapters =`;
#       "" switches them all off). Without it the current setting stays.
#   kotl/install.sh --undo     removes the code (the registry and results stay)
#
# Add --dry-run to preview without changing anything.
source "$(dirname "$0")/../lib.sh"

REPO=$(cd "$DEPLOY_DIR/.." && pwd)
ADAPTER_TOOLS=(firesim/firesim-smoke.sh)   # installed as /opt/kotl/adapters/<path> when the adapter is on
usage() { sed -n '2,19p' "$0" | sed 's/^# \{0,1\}//'; exit "${1:-0}"; }

py_wrapper() {  # py_wrapper MODULE   -> a tiny entry script; -I ignores the caller's Python env
  cat <<EOF
#!/usr/bin/python3 -I
# $MARK (deploy/kotl/install.sh)
import sys
sys.path.insert(0, "/opt/kotl/lib")
from $1 import main
sys.exit(main())
EOF
}

build_id() {   # VERSION+COMMIT, plus .dirty-HASH when the installed parts have uncommitted changes
  local v c d="" parts=(kotl deploy plugin plugin-band vscode-kotl)
  v=$(sed -n 's/^__version__ = "\(.*\)"/\1/p' "$REPO/kotl/__init__.py")
  c=$(git -c safe.directory="$REPO" -C "$REPO" rev-parse --short HEAD 2>/dev/null) || c=nogit
  if [ -n "$(git -c safe.directory="$REPO" -C "$REPO" status --porcelain -- "${parts[@]}" 2>/dev/null)" ]; then
    d=$(git -c safe.directory="$REPO" -C "$REPO" diff HEAD -- "${parts[@]}" 2>/dev/null | sha256sum | cut -c1-6) || d=x
  fi
  printf '%s+%s%s' "${v:-0}" "$c" "${d:+.dirty-$d}"
}

# every board in the registry -> the users' SSH entries (/etc/ssh/ssh_config.d/kotl.conf) and
# Slurm's license counts (one license per board, by type). Runs on every install, so adding or
# removing a board (deploy/kotl/pc.sh) is just: change the registry, then re-run this.
sync_boards() {
  local rows account client name type host addr want have conf
  account=$(get_conf /etc/kotl/kotl.conf pc_account); account=${account:-virtex-host}
  if [ "$KOTL_DRY_RUN" = 1 ]; then
    rows=$(for b in "${BOARDS[@]}"; do t=${b#*=}; printf '%s %s %s\n' "${b%%=*}" "${t%%@*}" "${t#*@}"; done)
  else
    rows=$(runuser -u kotl -- /opt/kotl/launch boards --json |
      python3 -c 'import json,sys; [print(b["name"], b["type"], b["host"]) for b in json.load(sys.stdin)]') ||
      die "couldn't read the boards from the registry"
  fi
  client="# $MARK (deploy/kotl/install.sh). During a lease, plain 'ssh <board>' uses your job key."$'\n'
  while read -r name type host; do
    [ -n "$name" ] || continue
    if [ "$KOTL_DRY_RUN" = 1 ]; then addr="<address of $host>"; else
      addr=$(runuser -u kotl -- ssh -G "$host" | sed -n 's/^hostname //p'); fi
    client+=$'\n'"Host $name"$'\n'"  HostName $addr"$'\n'"  User $account"$'\n'"  IdentityFile /tmp/kotl-keys-%u/%n"$'\n'
  done <<<"$rows"
  if [ -n "$(printf '%s' "$rows" | tr -d '[:space:]')" ]; then
    printf '%s' "$client" | put_file /etc/ssh/ssh_config.d/kotl.conf 644 root:root
  elif [ "$KOTL_DRY_RUN" != 1 ]; then
    remove_file /etc/ssh/ssh_config.d/kotl.conf
  fi

  # Slurm: one license per board, counted by type (e.g. vcu118:2); restart slurmctld if it changed
  want=$(printf '%s\n' "$rows" | awk 'NF == 3 { n[$2]++ } END { for (t in n) print t ":" n[t] }' | sort | paste -sd, -)
  conf=$(p /etc/slurm/slurm.conf)
  have=$(sed -n 's/^Licenses=//p' "$conf" 2>/dev/null || true)
  if [ -z "$want" ]; then
    [ "$KOTL_DRY_RUN" = 1 ] || say "no boards in the registry; Slurm's licenses stay ${have:-unset}"
  elif [ "$want" != "$have" ] && [ -f "$conf" ]; then
    sed -i "s/^Licenses=.*/Licenses=$want/" "$conf"
    say "Slurm licenses: ${have:-none} -> $want"
    run systemctl restart slurmctld
  fi
}

install_all() {
  if [ "$KOTL_DRY_RUN" != 1 ]; then
    getent passwd kotl >/dev/null || die "run M1 first (accounts.sh install)"
    command -v sbatch >/dev/null || die "run M1 first (slurm/install.sh)"
  fi

  # the package: a clean copy, root-owned, so nobody can change what runs as kotl
  local lib
  lib=$(p /opt/kotl/lib)
  if [ "$KOTL_DRY_RUN" = 1 ]; then say "would replace /opt/kotl/lib/kotl with $REPO/kotl"; fi
  rm -rf "$lib/kotl"
  mkdir -p "$lib"
  cp -r "$REPO/kotl" "$lib/kotl"
  find "$lib" -name __pycache__ -prune -exec rm -rf {} +
  find "$lib" -type d -exec chmod 755 {} +
  find "$lib" -type f -exec chmod 644 {} +
  if [ "$KOTL_DRY_RUN" != 1 ]; then chown -R root:root "$lib"; fi
  say "copied kotl/ to /opt/kotl/lib/kotl"

  # the build: VERSION+COMMIT (+ a hash of uncommitted changes); the plugins and the VS Code
  # extension carry a copy, so they can tell a person when Kotl was updated after their kotl setup
  BUILD=$(build_id)
  rm -f "$(p /opt/kotl/BUILD)"     # one line, no room for the "managed by kotl" mark: replace it outright
  printf '%s\n' "$BUILD" | put_file /opt/kotl/BUILD 644 root:root

  py_wrapper kotl.core.launcher | put_file /opt/kotl/launch 755 root:root
  make_dir /opt/kotl/bin 755 root:root
  py_wrapper kotl.cli.main | put_file /opt/kotl/bin/kotl 755 root:root
  # gone in the generic design: the firesim wrapper and its PATH snippet (if an earlier install left them)
  remove_file /opt/kotl/bin/firesim
  remove_file /etc/profile.d/kotl.sh
  put_file /opt/kotl/job.sh 755 root:root <"$DEPLOY_DIR/job.sh"
  put_file /opt/kotl/epilog.sh 755 root:root <"$DEPLOY_DIR/epilog.sh"
  put_file /opt/kotl/health.sh 755 root:root <"$DEPLOY_DIR/health.sh"
  run ln -sfn /opt/kotl/bin/kotl /usr/local/bin/kotl

  # the Claude Code plugin, readable by everyone, as a marketplace at /opt/kotl
  local plug
  plug=$(p /opt/kotl/plugin)
  rm -rf "$plug"
  cp -r "$REPO/plugin" "$plug"
  find "$plug" -type d -exec chmod 755 {} +
  find "$plug" -type f -exec chmod 644 {} +
  find "$plug" -name '*.sh' -exec chmod 755 {} +
  if [ "$KOTL_DRY_RUN" != 1 ]; then chown -R root:root "$plug"; fi
  printf '%s\n' "$BUILD" >"$plug/BUILD"
  # each adapter brings a skill (plugin/skills/kotl-<adapter>): keep only the enabled adapters'
  local on sk
  if [ "$ADAPTERS" != unset ]; then on=$ADAPTERS; else on=$(get_conf /etc/kotl/kotl.conf adapters); fi
  for sk in "$plug"/skills/kotl-*; do
    [ -d "$sk" ] || continue
    case ",${on// /}," in *",${sk##*/kotl-},"*) ;; *) rm -rf "$sk" ;; esac
  done
  say "copied plugin/ to /opt/kotl/plugin (adapter skills: ${on:-none})"
  # the adapters' tools for users (e.g. FireSim's smoke run), readable and runnable by everyone
  rm -rf "$(p /opt/kotl/adapters)"
  local a
  for a in $(tr ',' ' ' <<<"$on"); do
    for t in "${ADAPTER_TOOLS[@]}"; do
      [ "${t%%/*}" = "$a" ] || continue
      make_dir "/opt/kotl/adapters/$a" 755 root:root
      put_file "/opt/kotl/adapters/$t" 755 root:root <"$DEPLOY_DIR/adapters/$t"
    done
  done
  local band
  band=$(p /opt/kotl/plugin-band)
  rm -rf "$band"
  cp -r "$REPO/plugin-band" "$band"
  find "$band" -type d -exec chmod 755 {} +
  find "$band" -type f -exec chmod 644 {} +
  find "$band" -name '*.test.tsx' -delete
  if [ "$KOTL_DRY_RUN" != 1 ]; then chown -R root:root "$band"; fi
  printf '%s\n' "$BUILD" >"$band/BUILD"
  say "copied plugin-band/ to /opt/kotl/plugin-band"
  # JSON can't carry the "managed by kotl" mark, so replace it outright (no .kotl-orig backup)
  rm -f "$(p /opt/kotl/.claude-plugin/marketplace.json)" "$(p /opt/kotl/.claude-plugin/marketplace.json.kotl-orig)"
  put_file /opt/kotl/.claude-plugin/marketplace.json 644 root:root <"$REPO/.claude-plugin/marketplace.json"

  # the VS Code extension, as a .vsix anyone can install (code --install-extension)
  local vsix
  vsix=$(python3 "$REPO/vscode-kotl/build_vsix.py" "$(mktemp -d)" "$BUILD")
  # a .vsix (zip) can't carry the "managed by kotl" mark either: replace it outright
  rm -f "$(p /opt/kotl/kotl-status.vsix)" "$(p /opt/kotl/kotl-status.vsix.kotl-orig)"
  put_file /opt/kotl/kotl-status.vsix 644 root:root <"$vsix"
  make_dir /opt/kotl/client 755 root:root
  rm -f "$(p /opt/kotl/client/install.sh.kotl-orig)"     # an earlier install's backup of our own file
  put_file /opt/kotl/client/install.sh 755 root:root <"$DEPLOY_DIR/client/install.sh"

  # kotl cancels hung jobs (guards) and holds a down board's license (reservations): Slurm admin
  if [ "$KOTL_DRY_RUN" = 1 ] || [ -z "$(sacctmgr -n -P show user kotl format=user 2>/dev/null)" ]; then
    run sacctmgr -i add user name=kotl account=kotl adminlevel=Admin
  else
    run sacctmgr -i modify user name=kotl set adminlevel=Admin
  fi

  # Kotl's rules for every Claude Code session here, plugin or not (Claude Code's managed CLAUDE.md)
  if [ -e "$(p /etc/claude-code/CLAUDE.md)" ] && ! grep -q "$MARK" "$(p /etc/claude-code/CLAUDE.md)"; then
    say "left /etc/claude-code/CLAUDE.md as it is (not Kotl's); add $DEPLOY_DIR/claude/CLAUDE.md to it by hand"
  else
    put_file /etc/claude-code/CLAUDE.md 644 root:root <"$DEPLOY_DIR/claude/CLAUDE.md"
  fi

  # the ETA notifier: one pass a minute, as kotl
  put_file /etc/systemd/system/kotl-notifier.service 644 root:root <"$DEPLOY_DIR/systemd/kotl-notifier.service"
  put_file /etc/systemd/system/kotl-notifier.timer 644 root:root <"$DEPLOY_DIR/systemd/kotl-notifier.timer"
  run systemctl daemon-reload
  run systemctl enable --now kotl-notifier.timer

  # the Kotl daemon (kotld): restarted so it runs the code just installed
  put_file /etc/systemd/system/kotl-daemon.service 644 root:root <"$DEPLOY_DIR/systemd/kotl-daemon.service"
  run systemctl daemon-reload
  run systemctl enable kotl-daemon.service
  run systemctl restart kotl-daemon.service

  # adapters (task-specific parts: FireSim's checks and cleanup), switched on in kotl.conf
  if [ "$ADAPTERS" != unset ]; then set_conf /etc/kotl/kotl.conf adapters "$ADAPTERS"; fi

  local b name type host
  for b in "${BOARDS[@]}"; do
    name=${b%%=*}; type=${b#*=}; host=${type#*@}; type=${type%%@*}
    [ -n "$name" ] && [ -n "$type" ] && [ -n "$host" ] && [ "$b" != "$name" ] || die "--board wants NAME=TYPE@HOST, got '$b'"
    run runuser -u kotl -- /opt/kotl/launch board-add "$name" "$type" "$host"
  done
  sync_boards
  say "installed. Try (as yourself): kotl status; kotl run --eta 5m -- hostname"
}

undo_all() {
  local lib
  lib=$(p /opt/kotl/lib)
  rm -rf "$lib"     # under the dry-run folder in a dry run
  say "removed /opt/kotl/lib"
  rm -rf "$(p /opt/kotl/plugin)" "$(p /opt/kotl/plugin-band)" "$(p /opt/kotl/adapters)"   # under the dry-run folder in a dry run
  remove_file /opt/kotl/.claude-plugin/marketplace.json
  remove_file /opt/kotl/kotl-status.vsix
  remove_file /opt/kotl/client/install.sh
  remove_file /opt/kotl/BUILD
  if grep -qs "$MARK" "$(p /etc/claude-code/CLAUDE.md)"; then remove_file /etc/claude-code/CLAUDE.md; fi
  remove_file /opt/kotl/launch
  remove_file /opt/kotl/bin/kotl
  remove_file /etc/ssh/ssh_config.d/kotl.conf
  run systemctl disable --now kotl-notifier.timer || true
  run systemctl disable --now kotl-daemon.service || true
  remove_file /etc/systemd/system/kotl-daemon.service
  remove_file /etc/systemd/system/kotl-notifier.service
  remove_file /etc/systemd/system/kotl-notifier.timer
  run systemctl daemon-reload
  # release any license a down board still holds
  if [ "$KOTL_DRY_RUN" != 1 ]; then
    for r in $(scontrol show reservation -o 2>/dev/null | sed -n 's/^ReservationName=\(kotl-down-[^ ]*\).*/\1/p'); do
      run scontrol delete ReservationName="$r"
    done
  fi
  remove_file /opt/kotl/job.sh
  run rm -f /usr/local/bin/kotl
  # Slurm still names the epilog: leave a no-op so the node never drains
  printf '#!/bin/sh\n# %s: no-op after kotl/install.sh --undo\nexit 0\n' "$MARK" | put_file /opt/kotl/epilog.sh 755 root:root
  say "kept the registry (/var/lib/kotl), results and lab notes (/srv/kotl)"
}

ACTION=install BOARDS=() ADAPTERS=unset
while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) KOTL_DRY_RUN=1 ;;
    --undo) ACTION=undo ;;
    --board) BOARDS+=("${2:-}"); shift ;;
    --adapters) ADAPTERS=${2:-}; shift
      case "$ADAPTERS" in *[!a-z0-9,]*) die "--adapters: names like firesim, comma-separated" ;; esac ;;
    -h|--help) usage ;;
    *) die "unknown option $1" ;;
  esac
  shift
done
start_mode
if [ "$ACTION" = undo ]; then undo_all; else install_all; fi
