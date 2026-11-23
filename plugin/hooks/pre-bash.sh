#!/bin/sh
# PreToolUse (Bash): a FireSim command that uses the board, run outside Kotl, could clash with
# someone's job. Ask the person first, and say how to run it through Kotl. Anything else: no opinion.
python3 -c '
import json, re, sys
try:
    cmd = json.load(sys.stdin).get("tool_input", {}).get("command", "")
except Exception:
    sys.exit(0)
board = re.search(r"\bfiresim\s+(infrasetup|runworkload|kill|runcheck)\b", cmd)
through_kotl = re.search(r"\bkotl\s+(run|lease)\b", cmd) or "KOTL_JOB" in cmd
if board and not through_kotl:
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "ask",
        "permissionDecisionReason": (
            "firesim " + board.group(1) + " uses the FPGA board outside Kotl, so it may clash with "
            "a queued job. Run it through the queue instead: kotl run --eta <estimate> -- <this command> "
            "(the board is freed when it ends), or hold a board first with kotl lease --eta <estimate>.")}}))
'
exit 0
