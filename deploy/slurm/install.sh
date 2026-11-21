#!/usr/bin/env bash
# Slurm on the workstation, as a single node, with accounting in MariaDB. Run as root,
# after accounts.sh install.
#
#   slurm/install.sh             install packages, write configs, start services, add the
#                                kotl cluster, account, QOS (urgent, maint) and every kotl-users member
#   slurm/install.sh --undo      stop Slurm and remove Kotl's configs (packages and data stay)
#   slurm/install.sh --undo --purge   also remove the packages, the accounting database and Slurm's state
#
# Add --dry-run to preview without changing anything. Safe to re-run: it keeps the
# database password and only adds what is missing.
source "$(dirname "$0")/../lib.sh"

PKGS="slurm-wlm slurmdbd munge mariadb-server expect"
HERE="$DEPLOY_DIR/slurm"
HOST=$(hostname -s)
CPUS=$(nproc)

usage() { sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'; exit "${1:-0}"; }

render() {  # render TEMPLATE  -> stdout, with @HOST@ @CPUS@ @DBPASS@ filled in
  sed -e "s|@HOST@|$HOST|g" -e "s|@CPUS@|$CPUS|g" -e "s|@DBPASS@|$DBPASS|g" "$HERE/$1"
}

db_password() {  # keep the one already in slurmdbd.conf, or make a new one
  local f old
  f=$(p /etc/slurm/slurmdbd.conf)
  old=$(sed -n 's/^StoragePass=//p' "$f" 2>/dev/null || true)
  if [ -n "$old" ]; then printf '%s' "$old"; else od -An -N24 -tx1 /dev/urandom | tr -d ' \n'; fi
}

has() {  # has KIND NAME   (cluster, account, qos, user) already in Slurm accounting?
  [ "$KOTL_DRY_RUN" = 1 ] && return 1
  [ -n "$(sacctmgr -n -P show "$1" "$2" format=name 2>/dev/null)" ]
}

wait_dbd() {
  [ "$KOTL_DRY_RUN" = 1 ] && return 0
  local i
  for i in $(seq 1 30); do sacctmgr -n show cluster >/dev/null 2>&1 && return 0; sleep 1; done
  die "slurmdbd did not answer within 30 s; see /var/log/slurm/slurmdbd.log"
}

install_all() {
  if [ "$KOTL_DRY_RUN" != 1 ]; then
    getent group kotl-users >/dev/null || die "run accounts.sh install first"
  fi
  local admin u members
  admin=$(get_conf /etc/kotl/kotl.conf admin)

  run apt-get install -y $PKGS

  # munge: Slurm's local authentication. The package normally creates the key.
  if [ "$KOTL_DRY_RUN" = 1 ] || [ ! -s /etc/munge/munge.key ]; then
    run sh -c 'test -s /etc/munge/munge.key || dd if=/dev/urandom bs=1 count=1024 of=/etc/munge/munge.key status=none'
    run chown munge:munge /etc/munge/munge.key
    run chmod 400 /etc/munge/munge.key
  fi
  run systemctl enable --now munge mariadb

  # accounting database
  DBPASS=$(db_password)
  run mysql -e "CREATE DATABASE IF NOT EXISTS slurm_acct_db;
    CREATE USER IF NOT EXISTS 'slurm'@'localhost' IDENTIFIED BY '$DBPASS';
    ALTER USER 'slurm'@'localhost' IDENTIFIED BY '$DBPASS';
    GRANT ALL ON slurm_acct_db.* TO 'slurm'@'localhost';"

  make_dir /var/spool/slurmctld 755 slurm:slurm
  make_dir /var/spool/slurmd 755 root:root
  make_dir /var/log/slurm 755 slurm:slurm
  render slurm.conf.in | put_file /etc/slurm/slurm.conf 644 root:root
  render cgroup.conf.in | put_file /etc/slurm/cgroup.conf 644 root:root
  render slurmdbd.conf.in | put_file /etc/slurm/slurmdbd.conf 600 slurm:slurm

  # Kotl's hooks that slurm.conf names; placeholders until M2 (end step) and M4 (health)
  make_dir /opt/kotl 755 root:root
  put_file /opt/kotl/epilog.sh 755 root:root <"$DEPLOY_DIR/epilog.sh"
  put_file /opt/kotl/health.sh 755 root:root <"$DEPLOY_DIR/health.sh"

  run systemctl enable --now slurmdbd
  run systemctl restart slurmdbd
  wait_dbd

  has cluster kotl || run sacctmgr -i add cluster kotl
  has account kotl || run sacctmgr -i add account kotl cluster=kotl Description="Kotl users"
  has qos urgent || run sacctmgr -i add qos urgent Priority=500 Description="admin-granted"
  has qos maint || run sacctmgr -i add qos maint Priority=1000 Description="board maintenance"
  members=$({ getent group kotl-users || true; } | cut -d: -f4 | tr ',' ' ')
  [ -n "$members" ] || say "kotl-users has no members yet (run accounts.sh install first)"
  for u in $members; do
    has user "$u" || run sacctmgr -i add user name="$u" account=kotl
  done
  if [ -n "$admin" ]; then run sacctmgr -i modify user name="$admin" set qos+=urgent,maint; fi

  run systemctl enable --now slurmctld slurmd
  run systemctl restart slurmctld slurmd
  run scontrol update nodename="$HOST" state=resume || true

  say "Slurm is set up on $HOST ($CPUS CPUs, license vcu118:1)."
  say "check: sinfo; scontrol show license; sacctmgr show qos format=name,priority"
}

undo_all() {
  run systemctl disable --now slurmctld slurmd slurmdbd || true
  remove_file /etc/slurm/slurm.conf
  remove_file /etc/slurm/cgroup.conf
  remove_file /etc/slurm/slurmdbd.conf
  remove_file /opt/kotl/epilog.sh
  remove_file /opt/kotl/health.sh
  if [ "${PURGE:-0}" = 1 ]; then
    run mysql -e "DROP DATABASE IF EXISTS slurm_acct_db; DROP USER IF EXISTS 'slurm'@'localhost';" || true
    run apt-get purge -y $PKGS
    run rm -rf /var/spool/slurmctld /var/spool/slurmd /var/log/slurm
  else
    say "kept the packages, the accounting database and Slurm's state (add --purge to remove them)"
  fi
}

ACTION=install PURGE=0
while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) KOTL_DRY_RUN=1 ;;
    --undo) ACTION=undo ;;
    --purge) PURGE=1 ;;
    -h|--help) usage ;;
    *) die "unknown option $1" ;;
  esac
  shift
done
start_mode
if [ "$ACTION" = undo ]; then undo_all; else install_all; fi
