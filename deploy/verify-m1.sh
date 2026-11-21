#!/usr/bin/env bash
# Checks that M1 works, end to end, and writes results that tools/status.py can read.
# Run on the workstation as root, from your own account (sudo keeps your name as the job owner):
#
#   sudo deploy/verify-m1.sh [--pc vcu118-pc1] [--results /tmp/kotl-m1-results.json]
#   python3 tools/status.py refresh --results /tmp/kotl-m1-results.json
#
# It submits two tiny test jobs (sleep) through Slurm, tries to cancel one as another
# user (must be refused), and logs in to the PC as kotl. It changes no settings.
set -uo pipefail

PC=vcu118-pc1 OUT=/tmp/kotl-m1-results.json
while [ $# -gt 0 ]; do
  case "$1" in
    --pc) PC=$2; shift ;;
    --results) OUT=$2; shift ;;
    *) echo "unknown option $1" >&2; exit 2 ;;
  esac
  shift
done
[ "$(id -u)" = 0 ] || { echo "run as root: sudo $0" >&2; exit 2; }
OWNER=${SUDO_USER:-}
[ -n "$OWNER" ] && [ "$OWNER" != root ] || { echo "run it with sudo from your own account" >&2; exit 2; }
OTHER=$(getent group kotl-users | cut -d: -f4 | tr ',' '\n' | grep -vx "$OWNER" | head -n 1)

RESULTS=() fails=0
result() {  # result FEATURE HW NAME OK [DETAIL]
  local outcome=passed
  [ "$4" = 1 ] || { outcome=failed; fails=$((fails + 1)); }
  printf '%-6s %-8s %-40s %s\n' "$([ "$outcome" = passed ] && echo PASS || echo FAIL)" "$1" "$3" "${5:-}"
  RESULTS+=("{\"nodeid\": \"deploy/verify-m1.sh::$3\", \"features\": [\"$1\"], \"hw\": $2, \"outcome\": \"$outcome\"}")
}
ok() { if "$@" >/dev/null 2>&1; then echo 1; else echo 0; fi; }
as() { local u=$1; shift; runuser -u "$u" -- "$@"; }
state() { squeue -h -j "$1" -o %T 2>/dev/null; }
wait_state() {  # wait_state JOB STATE SECONDS
  local i; for i in $(seq 1 "$3"); do [ "$(state "$1")" = "$2" ] && return 0; sleep 1; done; return 1
}

# --- accounts, folders, sudoers (os)
result os false kotl_account "$(ok getent passwd kotl)"
result os false kotl_users_group "$(ok sh -c "getent group kotl-users | grep -qw $OWNER")" "owner $OWNER"
result os false sudoers_rule_valid "$(ok visudo -cf /etc/sudoers.d/kotl)"
result os false kotl_conf_admin "$(ok grep -q '^admin *= *[a-z]' /etc/kotl/kotl.conf)"
result os false kotl_folders "$(ok test -d /var/lib/kotl -a -d /srv/kotl/jobs -a -d /srv/kotl/out)"

# --- Slurm config (queue, runner, acct)
result queue false license_vcu118_is_1 "$(ok sh -c 'scontrol show license vcu118 | grep -q "Total=1"')"
result queue false qos_urgent_and_maint "$(ok sh -c 'q=$(sacctmgr -n -P show qos format=name); echo "$q" | grep -qx urgent && echo "$q" | grep -qx maint')"
result queue false over_time_never_kills "$(ok sh -c 'scontrol show config | grep -Eq "OverTimeLimit += UNLIMITED"')"
result runner false health_program_set "$(ok sh -c 'scontrol show config | grep -q "HealthCheckProgram.*/opt/kotl/health.sh"')"
result runner false node_not_drained "$(ok sh -c '! sinfo -h -o %t | grep -Eq "drain|down|fail"')" "$(sinfo -h -o %t | head -n 1)"
result acct false accounting_answers "$(ok sacctmgr -n show cluster kotl)"

# --- jobs through Slurm (starter, queue, acct)
A=$(as "$OWNER" sbatch --parsable -o /dev/null -L vcu118:1 --time=2 -J kotl-m1-a --wrap 'sleep 90' 2>&1)
B=$(as "$OWNER" sbatch --parsable -o /dev/null -L vcu118:1 --time=2 -J kotl-m1-b --wrap 'sleep 3' 2>&1)
result starter false job_starts "$(ok wait_state "$A" RUNNING 30)" "job $A"
sleep 3
result queue false second_job_waits_for_board "$( [ "$(state "$B")" = PENDING ] && squeue -h -j "$B" -o %r | grep -q Licenses && echo 1 || echo 0)" "job $B: $(squeue -h -j "$B" -o '%T %r')"
if [ -n "$OTHER" ]; then
  as "$OTHER" scancel "$A" >/dev/null 2>&1
  sleep 2
  result starter false other_user_cannot_cancel "$( [ "$(state "$A")" = RUNNING ] && echo 1 || echo 0)" "tried as $OTHER"
else
  echo "SKIP   other_user_cannot_cancel (no second kotl-users member)"
fi
as "$OWNER" scancel "$A"
result starter false owner_can_cancel "$(ok wait_state "$A" "" 30)"
for i in $(seq 1 60); do [ -z "$(state "$B")" ] && break; sleep 1; done
sleep 2
result acct false history_shows_completed "$(ok sh -c "sacct -n -X -j $B -o State | grep -q COMPLETED")" "job $B: $(sacct -n -X -j "$B" -o State | tr -s ' ')"
result acct false history_shows_cancelled "$(ok sh -c "sacct -n -X -j $A -o State | grep -q CANCELLED")"

# --- the PC, as kotl (key, pc1, firesim): these touch the board's PC, so they count as hardware
pc() { as kotl ssh "$PC" "$1" 2>/dev/null; }
result key true kotl_ssh_login "$( [ -n "$(pc hostname)" ] && echo 1 || echo 0)" "$(pc hostname)"
result pc1 true xilinx_card_on_pci "$( [ -n "$(pc 'lspci -d 10ee:')" ] && echo 1 || echo 0)" "$(pc 'lspci -d 10ee: | head -n 1')"
ACCOUNT=$(sed -n 's/^pc_account *= *//p' /etc/kotl/kotl.conf | head -n 1)
result firesim true pc_account_exists "$( [ -n "$(pc "getent passwd ${ACCOUNT:-virtex-host}")" ] && echo 1 || echo 0)" "${ACCOUNT:-virtex-host}"
result firesim true xdma_driver_loaded "$( [ -n "$(pc 'lsmod | grep -w xdma')" ] && echo 1 || echo 0)"

{
  printf '{"ran_at": "%s", "results": [\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  ( IFS=$'\n'; printf '%s' "${RESULTS[*]}" | sed '$!s/$/,/' )
  printf '\n]}\n'
} >"$OUT"
chown "$OWNER" "$OUT" 2>/dev/null || true
echo
echo "$fails failed. Results: $OUT"
echo "Next: python3 tools/status.py refresh --results $OUT"
exit $((fails > 0))
