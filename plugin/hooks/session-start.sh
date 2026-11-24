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
# Kotl updated since this person's plugins were installed? (BUILD comes with the install)
mine=$(cat "$HERE/../BUILD" 2>/dev/null)
current=$(timeout 10 sh "$HERE/kotl-cmd.sh" version --build 2>/dev/null)
if [ -n "$mine" ] && [ -n "$current" ] && [ "$mine" != "$current" ]; then
  echo
  echo "Kotl was updated ($current; this person's Kotl plugins are from $mine). Tell them once, early:"
  echo "run 'kotl setup' (on their own PC: a new 'kotl client-bundle' and its install.sh), then start a new session."
fi
notices=$(timeout 10 sh "$HERE/kotl-cmd.sh" notices --peek 2>/dev/null)
case "$notices" in
  ""|"(no notices)") ;;
  *) echo; echo "Unread Kotl notices (shown, not marked read):"; echo "$notices" ;;
esac
exit 0
