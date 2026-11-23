#!/bin/sh
# Claude Code UserPromptSubmit hook (set up in .claude/settings.local.json): prints what is new in
# .kotl/next.log since the last prompt, so Claude sees what the user ran with deploy/next.sh.
cd "$(dirname "$0")/.." || exit 0
LOG=.kotl/next.log
SEEN=.kotl/next.log.seen
[ -f "$LOG" ] || exit 0
size=$(wc -c <"$LOG")
seen=$(cat "$SEEN" 2>/dev/null || echo 0)
[ "$size" -lt "$seen" ] && seen=0          # the log was cleared or replaced
[ "$size" -gt "$seen" ] || exit 0
echo "New in .kotl/next.log since the last message (what the user ran with deploy/next.sh):"
tail -c +"$((seen + 1))" "$LOG" | sed 's/\x1b\[[0-9;?]*[A-Za-z]//g; s/\r$//' | tail -n 200
echo "$size" >"$SEEN"
