#!/bin/sh
# Runs `kotl ARGS...` on the workstation: directly when kotl is installed here, else over ssh
# to $KOTL_SSH (set it in ~/.claude/settings.json under "env", e.g. "KOTL_SSH": "comparch").
# Exit 127 when neither works, so hooks can stay quiet.
if command -v kotl >/dev/null 2>&1; then
  exec kotl "$@"
elif [ -n "${KOTL_SSH:-}" ]; then
  args=""
  for a in "$@"; do args="$args '$(printf '%s' "$a" | sed "s/'/'\\\\''/g")'"; done
  exec ssh -o BatchMode=yes -o ConnectTimeout=5 "$KOTL_SSH" "kotl$args"
else
  exit 127
fi
