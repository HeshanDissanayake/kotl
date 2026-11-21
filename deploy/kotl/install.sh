#!/usr/bin/env bash
# Install (or update) Kotl's own code on the workstation. Run as root, from the repo, after M1.
#
#   kotl/install.sh --board vcu118-pc1=vcu118@vcu118-pc1
#       copies kotl/ to /opt/kotl/lib, installs /opt/kotl/launch, /opt/kotl/job.sh,
#       /opt/kotl/epilog.sh, the kotl command (/opt/kotl/bin/kotl, linked from /usr/local/bin),
#       an SSH client entry per board (/etc/ssh/ssh_config.d/kotl.conf: your job key during a lease),
#       adds each board to the registry, and makes kotl a Slurm operator (so its guards can
#       cancel a hung job). Re-run after every update of the repo.
#   kotl/install.sh --undo     removes the code (the registry and results stay)
#
# Add --dry-run to preview without changing anything.
source "$(dirname "$0")/../lib.sh"

REPO=$(cd "$DEPLOY_DIR/.." && pwd)
usage() { sed -n '2,13p' "$0" | sed 's/^# \{0,1\}//'; exit "${1:-0}"; }

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

  py_wrapper kotl.core.launcher | put_file /opt/kotl/launch 755 root:root
  make_dir /opt/kotl/bin 755 root:root
  py_wrapper kotl.cli.main | put_file /opt/kotl/bin/kotl 755 root:root
  # gone in the generic design: the firesim wrapper and its PATH snippet (if an earlier install left them)
  remove_file /opt/kotl/bin/firesim
  remove_file /etc/profile.d/kotl.sh
  put_file /opt/kotl/job.sh 755 root:root <"$DEPLOY_DIR/job.sh"
  put_file /opt/kotl/epilog.sh 755 root:root <"$DEPLOY_DIR/epilog.sh"
  run ln -sfn /opt/kotl/bin/kotl /usr/local/bin/kotl

  # kotl may cancel jobs (only its guards do), so it is a Slurm operator
  if [ "$KOTL_DRY_RUN" = 1 ] || [ -z "$(sacctmgr -n -P show user kotl format=user 2>/dev/null)" ]; then
    run sacctmgr -i add user name=kotl account=kotl adminlevel=Operator
  else
    run sacctmgr -i modify user name=kotl set adminlevel=Operator
  fi

  local b name type host addr account client
  account=$(get_conf /etc/kotl/kotl.conf pc_account); account=${account:-virtex-host}
  client="# $MARK (deploy/kotl/install.sh). During a lease, plain 'ssh <board>' uses your job key."$'\n'
  for b in "${BOARDS[@]}"; do
    name=${b%%=*}; type=${b#*=}; host=${type#*@}; type=${type%%@*}
    [ -n "$name" ] && [ -n "$type" ] && [ -n "$host" ] && [ "$b" != "$name" ] || die "--board wants NAME=TYPE@HOST, got '$b'"
    run runuser -u kotl -- /opt/kotl/launch board-add "$name" "$type" "$host"
    if [ "$KOTL_DRY_RUN" = 1 ]; then addr="<address of $host>"; else
      addr=$(runuser -u kotl -- ssh -G "$host" | sed -n 's/^hostname //p'); fi
    client+=$'\n'"Host $name"$'\n'"  HostName $addr"$'\n'"  User $account"$'\n'"  IdentityFile /tmp/kotl-keys-%u/%n"$'\n'
  done
  if [ ${#BOARDS[@]} -gt 0 ]; then printf '%s' "$client" | put_file /etc/ssh/ssh_config.d/kotl.conf 644 root:root; fi
  say "installed. Try (as yourself): kotl status; kotl run --eta 5m -- hostname"
}

undo_all() {
  local lib
  lib=$(p /opt/kotl/lib)
  [ "$KOTL_DRY_RUN" = 1 ] || rm -rf "$lib"
  say "removed /opt/kotl/lib"
  remove_file /opt/kotl/launch
  remove_file /opt/kotl/bin/kotl
  remove_file /etc/ssh/ssh_config.d/kotl.conf
  remove_file /opt/kotl/job.sh
  run rm -f /usr/local/bin/kotl
  # Slurm still names the epilog: leave a no-op so the node never drains
  printf '#!/bin/sh\n# %s: no-op after kotl/install.sh --undo\nexit 0\n' "$MARK" | put_file /opt/kotl/epilog.sh 755 root:root
  say "kept the registry (/var/lib/kotl) and results (/srv/kotl)"
}

ACTION=install BOARDS=()
while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) KOTL_DRY_RUN=1 ;;
    --undo) ACTION=undo ;;
    --board) BOARDS+=("${2:-}"); shift ;;
    -h|--help) usage ;;
    *) die "unknown option $1" ;;
  esac
  shift
done
start_mode
if [ "$ACTION" = undo ]; then undo_all; else install_all; fi
