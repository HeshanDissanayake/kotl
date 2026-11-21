#!/usr/bin/env bash
# The kotl SSH key on the workstation: Kotl's own path to the FPGA PCs. Run as root,
# after accounts.sh install.
#
#   ssh/setup-kotl-key.sh --pc vcu118-pc1=192.168.1.2 [--pc NAME=ADDRESS ...]
#       makes the kotl key (once) and writes kotl's SSH config with one entry per PC.
#       Then copy the printed public key to each PC with pc/setup.sh.
#   ssh/setup-kotl-key.sh --undo [--purge]
#       removes kotl's SSH config; --purge also deletes the key
#
# Add --dry-run to preview without changing anything.
source "$(dirname "$0")/../lib.sh"

SSHDIR=/home/kotl/.ssh
usage() { sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'; exit "${1:-0}"; }

install_all() {
  [ ${#PCS[@]} -gt 0 ] || die "give at least one --pc NAME=ADDRESS"
  if [ "$KOTL_DRY_RUN" != 1 ]; then getent passwd kotl >/dev/null || die "run accounts.sh install first"; fi

  make_dir "$SSHDIR" 700 kotl:kotl
  if [ "$KOTL_DRY_RUN" = 1 ] || [ ! -e "$SSHDIR/id_ed25519" ]; then
    run runuser -u kotl -- ssh-keygen -q -t ed25519 -N '' -C "kotl@$(hostname -s)" -f "$SSHDIR/id_ed25519"
  fi

  local pc name addr
  {
    printf '# %s (deploy/ssh/setup-kotl-key.sh). Kotl'"'"'s own logins to the FPGA PCs.\n' "$MARK"
    for pc in "${PCS[@]}"; do
      name=${pc%%=*}; addr=${pc#*=}
      [ -n "$name" ] && [ -n "$addr" ] && [ "$name" != "$pc" ] || die "--pc wants NAME=ADDRESS, got '$pc'"
      printf '\nHost %s\n  HostName %s\n  User kotl\n  IdentityFile ~/.ssh/id_ed25519\n  IdentitiesOnly yes\n  StrictHostKeyChecking accept-new\n  BatchMode yes\n  ConnectTimeout 10\n' "$name" "$addr"
    done
  } | put_file "$SSHDIR/config" 600 kotl:kotl

  say "kotl's public key (give it to pc/setup.sh on each PC):"
  if [ "$KOTL_DRY_RUN" = 1 ]; then say "  (made on the real run: $SSHDIR/id_ed25519.pub)"; else cat "$SSHDIR/id_ed25519.pub"; fi
}

undo_all() {
  remove_file "$SSHDIR/config"
  if [ "${PURGE:-0}" = 1 ]; then
    remove_file "$SSHDIR/id_ed25519"; remove_file "$SSHDIR/id_ed25519.pub"
  else
    say "kept the kotl key (add --purge to delete it)"
  fi
}

ACTION=install PURGE=0 PCS=()
while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) KOTL_DRY_RUN=1 ;;
    --undo) ACTION=undo ;;
    --purge) PURGE=1 ;;
    --pc) PCS+=("${2:-}"); shift ;;
    -h|--help) usage ;;
    *) die "unknown option $1" ;;
  esac
  shift
done
start_mode
if [ "$ACTION" = undo ]; then undo_all; else install_all; fi
