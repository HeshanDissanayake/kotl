#!/bin/sh
# SessionStart: give Claude the queue, the boards and your unread Kotl notices (read-only).
# Quiet when Kotl can't be reached; never fails the session.
HERE=$(dirname "$0")
status=$(timeout 15 sh "$HERE/kotl-cmd.sh" status 2>/dev/null) || exit 0
[ -n "$status" ] || exit 0
echo "Kotl (the lab's FPGA board queue): use a board only through kotl run / kotl lease (the kotl skill), and"
echo "never stop board work that isn't this person's Kotl job; report who runs it, how long, outside Kotl."
echo
echo "Kotl right now:"
echo "$status"
notices=$(timeout 10 sh "$HERE/kotl-cmd.sh" notices --peek 2>/dev/null)
case "$notices" in
  ""|"(no notices)") ;;
  *) echo; echo "Unread Kotl notices (shown, not marked read):"; echo "$notices" ;;
esac
exit 0
