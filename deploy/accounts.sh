#!/usr/bin/env bash
# Kotl accounts and folders on the workstation. Run as root.
#
#   accounts.sh install --admin USER    kotl account, kotl-users group (every regular user),
#                                       /etc/kotl/kotl.conf, Kotl's folders, the sudoers rule
#   accounts.sh add-user USER...        add people to kotl-users (and to Slurm, once installed)
#   accounts.sh remove-user USER...     take people out again
#   accounts.sh set-admin USER          change the admin (notices, urgent/maint priority)
#   accounts.sh sync                    add every regular account that isn't in kotl-users yet
#   accounts.sh --undo [--purge]        remove the files and group; --purge also deletes the kotl account
#
# Add --dry-run to any of these to preview without changing anything.
source "$(dirname "$0")/lib.sh"

CONF=/etc/kotl/kotl.conf
GROUP=kotl-users

usage() { sed -n '2,13p' "$0" | sed 's/^# \{0,1\}//'; exit "${1:-0}"; }

regular_users() {
  # real people: uid 1000-59999 with a login shell
  getent passwd | awk -F: '$3>=1000 && $3<60000 && $7 !~ /(nologin|false)$/ {print $1}'
}

slurm_ready() {
  if [ "$KOTL_DRY_RUN" = 1 ]; then return 0; fi
  command -v sacctmgr >/dev/null 2>&1 && systemctl is-active -q slurmdbd 2>/dev/null
}

add_users() {
  local u
  for u in "$@"; do
    getent passwd "$u" >/dev/null || die "no such user: $u"
    run gpasswd -a "$u" "$GROUP"
    if slurm_ready; then run sacctmgr -i add user name="$u" account=kotl; fi
  done
}

remove_users() {
  local u admin
  admin=$(get_conf "$CONF" admin)
  for u in "$@"; do
    [ "$u" != "$admin" ] || die "$u is the admin; run set-admin with someone else first"
    run gpasswd -d "$u" "$GROUP"
    if slurm_ready; then run sacctmgr -i delete user name="$u" account=kotl; fi
  done
}

set_admin() {
  local new=$1 old
  getent passwd "$new" >/dev/null || die "no such user: $new"
  old=$(get_conf "$CONF" admin)
  set_conf "$CONF" admin "$new"
  if slurm_ready; then
    if [ -n "$old" ] && [ "$old" != "$new" ]; then run sacctmgr -i modify user name="$old" set qos-=urgent,maint; fi
    run sacctmgr -i modify user name="$new" set qos+=urgent,maint
  fi
}

install_all() {
  local admin=$1
  [ -n "$admin" ] || die "install needs --admin USER"
  getent passwd "$admin" >/dev/null || die "no such user: $admin"

  run groupadd -f "$GROUP"
  if ! getent passwd kotl >/dev/null; then
    run useradd --system --create-home --home-dir /home/kotl --shell /bin/bash --comment "Kotl FPGA job manager" kotl
  fi
  run passwd -l kotl   # no password login, ever

  make_dir /etc/kotl 755 root:root
  if [ ! -e "$(p $CONF)" ]; then
    put_file "$CONF" 644 root:root <<EOF
# $MARK (deploy/accounts.sh). Change values with accounts.sh, or edit by hand.
# soft: password logins to the PC account and existing keys still work; the end step
#       kills only the job's own sessions and simulations
# full: PC account key-only, the end step kills every process of the PC account
lockdown = soft
admin = $admin
pc_account = virtex-host
idle = 30m
EOF
  else
    set_conf "$CONF" admin "$admin"
  fi

  make_dir /opt/kotl 755 root:root
  make_dir /opt/kotl/bin 755 root:root
  make_dir /var/lib/kotl 750 kotl:kotl
  make_dir /srv/kotl 711 kotl:kotl
  make_dir /srv/kotl/jobs 711 kotl:kotl
  make_dir /srv/kotl/out 711 kotl:kotl

  put_file /etc/sudoers.d/kotl 440 root:root <"$DEPLOY_DIR/sudoers/kotl"
  visudo -cf "$(p /etc/sudoers.d/kotl)" >/dev/null || { remove_file /etc/sudoers.d/kotl; die "sudoers rule failed visudo; removed it"; }

  # shellcheck disable=SC2046
  add_users $(regular_users)
  say "kotl-users: $(regular_users | tr '\n' ' ')"
  say "admin: $admin"
}

undo_all() {
  remove_file /etc/sudoers.d/kotl
  remove_file "$CONF"
  run groupdel "$GROUP" || true
  if [ "${PURGE:-0}" = 1 ]; then
    run userdel --remove kotl || true
    run rm -rf /var/lib/kotl /srv/kotl /opt/kotl /etc/kotl
  else
    say "kept the kotl account and /var/lib/kotl, /srv/kotl, /opt/kotl (add --purge to delete them)"
  fi
}

ACTION="" ADMIN="" PURGE=0 ARGS=()
while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) KOTL_DRY_RUN=1 ;;
    --undo) ACTION=undo ;;
    --purge) PURGE=1 ;;
    --admin) ADMIN=${2:-}; shift ;;
    -h|--help) usage ;;
    install|add-user|remove-user|set-admin|sync) ACTION=$1 ;;
    -*) die "unknown option $1" ;;
    *) ARGS+=("$1") ;;
  esac
  shift
done
[ -n "$ACTION" ] || usage 1
start_mode

case "$ACTION" in
  install) install_all "$ADMIN" ;;
  add-user) [ ${#ARGS[@]} -gt 0 ] || die "add-user needs at least one user"; add_users "${ARGS[@]}" ;;
  remove-user) [ ${#ARGS[@]} -gt 0 ] || die "remove-user needs at least one user"; remove_users "${ARGS[@]}" ;;
  set-admin) [ ${#ARGS[@]} -eq 1 ] || die "set-admin needs exactly one user"; set_admin "${ARGS[0]}" ;;
  # shellcheck disable=SC2046
  sync) add_users $(regular_users) ;;
  undo) undo_all ;;
esac
