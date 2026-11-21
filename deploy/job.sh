#!/bin/bash
# managed by kotl (deploy/kotl/install.sh)
# What Slurm runs for every Kotl job, as the submitting user, inside their job:
#   1) a fresh SSH key for this job is made as you (the private half never leaves your account);
#      the launcher (as kotl) checks the job is yours, claims a board, adds the public half
#      on the board's PC, and starts the guards
#   2) your command runs as you, with an ssh-agent holding only the job key and
#      KOTL_JOB, KOTL_BOARD, KOTL_PC (user@address) set; its output goes to output.log
#   3) the end step: frees the board and writes status.json (Slurm's epilog repeats it)
# Settings come from the kotl CLI: KOTL_MODE (run|lease), KOTL_MAX and KOTL_IDLE (seconds).
set -u
JOB=${SLURM_JOB_ID:?not inside a Slurm job}
read -r -a LAUNCH <<<"${KOTL_LAUNCH:-sudo -n -u kotl /opt/kotl/launch}"

# the job key: /tmp/kotl-keys-<you>/job-<JOB>, linked as /tmp/kotl-keys-<you>/<board> for ssh
KEYDIR=${KOTL_KEYDIR:-/tmp/kotl-keys-$(id -un)}
[ -d "$KEYDIR" ] || mkdir -m 700 "$KEYDIR" || exit 1
if [ -L "$KEYDIR" ] || [ ! -O "$KEYDIR" ] || [ "$(stat -c %a "$KEYDIR")" != 700 ]; then
  echo "kotl: $KEYDIR must be a folder only you can use; remove it and retry" >&2
  exit 1
fi
KEY="$KEYDIR/job-$JOB"
rm -f "$KEY" "$KEY.pub"
ssh-keygen -q -t ed25519 -N '' -C "kotl-job-$JOB" -f "$KEY" || exit 1

out=$("${LAUNCH[@]}" start "$JOB" --mode "${KOTL_MODE:-run}" \
  ${KOTL_MAX:+--max "$KOTL_MAX"} ${KOTL_IDLE:+--idle "$KOTL_IDLE"} --command "$*" \
  --pubkey "$(cut -d' ' -f1,2 "$KEY.pub")") || { rm -f "$KEY" "$KEY.pub"; exit 1; }
board=$(sed -n 's/^board=//p' <<<"$out")
pc=$(sed -n 's/^pc=//p' <<<"$out")
[ -n "$board" ] && ln -sfn "$KEY" "$KEYDIR/$board"
export KOTL_JOB="$JOB" KOTL_BOARD="$board" KOTL_PC="$pc"
# any tool that uses ssh (FireSim included) gets the job key through this agent
if command -v ssh-agent >/dev/null; then
  eval "$(ssh-agent -s)" >/dev/null && ssh-add -q "$KEY" 2>/dev/null
fi

stopping=0 pid=""
on_stop() { stopping=1; [ -n "$pid" ] && kill -TERM "$pid" 2>/dev/null; }
trap on_stop TERM INT HUP

# your command's output goes through a pipe to the launcher, which owns the log file
fifo=$(mktemp -u "${TMPDIR:-/tmp}/kotl-$JOB.XXXXXX")
mkfifo -m 600 "$fifo"
"${LAUNCH[@]}" log "$JOB" <"$fifo" &
logpid=$!
"$@" >"$fifo" 2>&1 &
pid=$!
rc=0
while :; do
  wait "$pid"; rc=$?
  kill -0 "$pid" 2>/dev/null || break   # wait returns early when a signal arrives
done
# let the log writer drain (at most 10 s, in case something still holds the pipe open)
for _ in $(seq 1 50); do kill -0 "$logpid" 2>/dev/null || break; sleep 0.2; done
kill "$logpid" 2>/dev/null; wait "$logpid" 2>/dev/null
rm -f "$fifo"

if [ "$stopping" = 1 ]; then
  "${LAUNCH[@]}" end "$JOB" --signal
else
  "${LAUNCH[@]}" end "$JOB" --rc "$rc"
fi
[ -n "${SSH_AGENT_PID:-}" ] && ssh-agent -k >/dev/null 2>&1
[ -n "$board" ] && [ "$(readlink "$KEYDIR/$board")" = "$KEY" ] && rm -f "$KEYDIR/$board"
rm -f "$KEY" "$KEY.pub"
exit "$rc"
