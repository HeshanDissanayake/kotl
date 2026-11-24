#!/usr/bin/env bash
# managed by kotl (deploy/kotl/pc.sh)
# Kotl's FPGA PCs: add one, remove one, or update Kotl's side on them. Run as the admin (not with
# sudo: it asks for sudo here, and for the sudo password on the PC, once per PC).
#
#   bash deploy/kotl/pc.sh add NAME TYPE ADDRESS     e.g. add vcu118-pc2 vcu118 192.168.1.3
#       sets up the PC (kotl account and key, kotl-keys, every enabled adapter's helpers), gives
#       Kotl's own SSH a login to it, adds the board to the registry, the users' SSH entries and
#       Slurm's license count, then runs the board check. Safe to re-run for a board you have.
#   bash deploy/kotl/pc.sh remove NAME               refused while a job holds the board
#       takes the board out of the registry, Slurm and the SSH entries, and removes Kotl's side
#       from the PC (--keep-pc leaves the PC as it is, e.g. when it's gone or unreachable)
#   bash deploy/kotl/pc.sh update [NAME...]          re-installs Kotl's helpers on the PCs (all
#       if no NAME); deploy/kotl/update.sh runs this after the workstation
#   bash deploy/kotl/pc.sh undo [NAME...]            removes Kotl's side from the PCs (all if no
#       NAME), and nothing on the workstation; deploy/uninstall.sh runs this first
#
# Logging in to the PC: as the board account (pc_account in /etc/kotl/kotl.conf, e.g. virtex-host),
# which needs sudo there. --login USER logs in as someone else with sudo on the PC.
# Add --dry-run to print what it would run, changing nothing.
set -uo pipefail
DEPLOY=$(cd "$(dirname "$0")/.." && pwd)
ROOT=${KOTL_ROOT:-}
DRY=0 LOGIN="" KEEP_PC=0 ARGS=()
say() { printf 'kotl-pc: %s\n' "$*"; }
die() { printf 'kotl-pc: error: %s\n' "$*" >&2; exit 1; }
run() { if [ "$DRY" = 1 ]; then printf 'would run: %s\n' "$*"; else "$@"; fi; }
conf() { sed -n "s/^[[:space:]]*$1[[:space:]]*=[[:space:]]*//p" "$ROOT/etc/kotl/kotl.conf" 2>/dev/null | tail -n 1; }
# the boards' PCs as the users' SSH entries know them: NAME ADDRESS
known_pcs() {
  awk '$1 == "Host" { h = $2 } $1 == "HostName" && h { print h, $2; h = "" }' "$ROOT/etc/ssh/ssh_config.d/kotl.conf" 2>/dev/null
}
address_of() { known_pcs | awk -v n="$1" '$1 == n { print $2 }'; }

while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY=1 ;;
    --login) LOGIN=${2:-}; shift ;;
    --keep-pc) KEEP_PC=1 ;;
    -h|--help) sed -n '3,21p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    -*) die "unknown option $1" ;;
    *) ARGS+=("$1") ;;
  esac
  shift
done
[ ${#ARGS[@]} -gt 0 ] || die "say what to do: add, remove, update or undo (--help)"
[ "$(id -u)" != 0 ] || [ "$DRY" = 1 ] || die "run it as yourself, not as root: it uses sudo where it needs it"
ACTION=${ARGS[0]}; ARGS=("${ARGS[@]:1}")
for x in "${ARGS[@]}" "$LOGIN"; do
  case "$x" in *[!A-Za-z0-9._:-]*) die "odd name or address: '$x'" ;; esac
done

ACCOUNT=$(conf pc_account); ACCOUNT=${ACCOUNT:-virtex-host}
PARTS=(pc)
for a in $(conf adapters | tr ',' ' '); do
  case "$a" in *[!a-z0-9]*) die "odd adapter name in kotl.conf: '$a'" ;; esac
  [ -f "$DEPLOY/adapters/$a/pc-setup.sh" ] && PARTS+=("adapters/$a")
done
CTL=$(mktemp -d "${TMPDIR:-/tmp}/kotl-pc.XXXXXX")
trap 'ssh -o ControlPath="$CTL/c" -O exit x 2>/dev/null; rm -rf "$CTL"' EXIT
SSHO=(-o ControlMaster=auto -o ControlPath="$CTL/c" -o ControlPersist=120 -o ConnectTimeout=15)

# on_pc ADDRESS install|undo [setup.sh options...]: copy Kotl's PC parts there and run them as root,
# all in one terminal session (one ssh login, one sudo password), then remove the copy
on_pc() {
  local addr=$1 what=$2 login remote d part
  shift 2
  login="${LOGIN:-$ACCOUNT}@$addr"
  if [ "$what" = install ]; then
    remote="sudo bash \$d/pc/setup.sh --account $ACCOUNT --keys-helper \$d/pc/kotl-keys"
    [ $# -eq 0 ] || remote+=" $(printf '%q ' "$@")"
    for part in "${PARTS[@]:1}"; do remote+=" && sudo bash \$d/$part/pc-setup.sh"; done
  else
    remote="true"
    for part in "${PARTS[@]:1}"; do remote+=" && sudo bash \$d/$part/pc-setup.sh --undo"; done
    remote+=" && sudo bash \$d/pc/setup.sh --undo --account $ACCOUNT"
  fi
  say "on $login ($what: ${PARTS[*]}); it may ask for the sudo password there"
  if [ "$DRY" = 1 ]; then
    printf 'would run: tar -C %s -cf - %s | ssh %s (into a new temporary folder)\n' "$DEPLOY" "${PARTS[*]}" "$login"
    printf 'would run: ssh -t %s "%s; rm -rf the folder"\n' "$login" "$remote"
    return 0
  fi
  d=$(tar -C "$DEPLOY" -cf - "${PARTS[@]}" | ssh "${SSHO[@]}" "$login" 'd=$(mktemp -d /tmp/kotl-pc.XXXXXX) && tar -C "$d" -xf - && echo "$d"') ||
    { say "couldn't copy Kotl's PC parts to $login"; return 1; }
  case "$d" in /tmp/kotl-pc.*) ;; *) say "odd folder from $login: '$d'"; return 1 ;; esac
  ssh -t "${SSHO[@]}" "$login" "d=$d; $remote; rc=\$?; rm -rf \"\$d\"; exit \$rc" ||
    { say "the $what on $login failed (see above)"; return 1; }
}

targets() {   # NAME ADDRESS for the named boards, or all of them
  if [ $# -eq 0 ]; then known_pcs; return; fi
  local n a
  for n in "$@"; do a=$(address_of "$n"); [ -n "$a" ] || die "no board $n in /etc/ssh/ssh_config.d/kotl.conf"; echo "$n $a"; done
}

case "$ACTION" in
  add)
    [ ${#ARGS[@]} -eq 3 ] || die "usage: pc.sh add NAME TYPE ADDRESS"
    NAME=${ARGS[0]} TYPE=${ARGS[1]} ADDR=${ARGS[2]}
    case "$TYPE" in *[!a-z0-9]*) die "TYPE is a board type like vcu118" ;; esac
    say "1/5 Kotl's own SSH login to $NAME ($ADDR)"
    run sudo bash "$DEPLOY/ssh/setup-kotl-key.sh" --add "$NAME=$ADDR" || die "setting up Kotl's SSH entry failed"
    if [ "$DRY" = 1 ]; then PUB="<kotl's public key>"; else
      PUB=$(sudo cat /home/kotl/.ssh/id_ed25519.pub) || die "can't read kotl's public key"; fi
    say "2/5 the PC: kotl account, kotl-keys, adapters"
    on_pc "$ADDR" install --key "$PUB" || die "setting up the PC failed, so the board isn't in Kotl yet (re-run when it's fixed)"
    say "3/5 checking that Kotl can log in"
    run sudo -u kotl ssh "$NAME" true || die "Kotl can't log in to $NAME yet (see above); re-run when it's fixed"
    say "4/5 the registry, the users' SSH entries and Slurm's license count"
    run sudo bash "$DEPLOY/kotl/install.sh" --board "$NAME=$TYPE@$NAME" || die "adding the board failed"
    say "5/5 the board check"
    run kotl board check || say "the board check found problems (above); kotl board list shows them"
    say "added $NAME. Users reach it through kotl run / kotl lease."
    ;;
  remove)
    [ ${#ARGS[@]} -eq 1 ] || die "usage: pc.sh remove NAME [--keep-pc]"
    NAME=${ARGS[0]}
    ADDR=$(address_of "$NAME")
    say "1/4 out of the registry (refused while a job holds it)"
    run sudo runuser -u kotl -- /opt/kotl/launch board-remove "$NAME" || die "not removed (see above)"
    if [ "$KEEP_PC" = 1 ]; then
      say "2/4 leaving the PC as it is (--keep-pc)"
    elif [ -z "$ADDR" ]; then
      say "2/4 no address known for $NAME: Kotl's side stays on its PC (remove it there with pc/setup.sh --undo)"
    else
      say "2/4 removing Kotl's side from the PC"
      on_pc "$ADDR" undo || say "the PC wasn't cleaned (see above); clean it later on the PC: sudo bash pc/setup.sh --undo"
    fi
    say "3/4 Kotl's own SSH entry"
    run sudo bash "$DEPLOY/ssh/setup-kotl-key.sh" --remove "$NAME"
    say "4/4 the users' SSH entries and Slurm's license count"
    run sudo bash "$DEPLOY/kotl/install.sh" || die "the workstation update failed"
    say "removed $NAME"
    ;;
  update|undo)
    rows=$(targets "${ARGS[@]}") || exit 1
    [ -n "$rows" ] || { say "no board PCs in /etc/ssh/ssh_config.d/kotl.conf"; exit 0; }
    fails=0
    while read -r n a <&3; do     # the list on fd 3: ssh keeps the terminal for the sudo password
      on_pc "$a" "$([ "$ACTION" = update ] && echo install || echo undo)" || fails=$((fails + 1))
    done 3<<<"$rows"
    [ "$fails" -eq 0 ] || { say "$fails PC(s) failed"; exit 1; }
    ;;
  *) die "unknown action $ACTION (add, remove, update or undo)" ;;
esac
