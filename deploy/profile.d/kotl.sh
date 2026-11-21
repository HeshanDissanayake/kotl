# managed by kotl (deploy/kotl/install.sh). Installed as /etc/profile.d/kotl.sh.
# Puts Kotl's commands (kotl, and the firesim wrapper) first on PATH. FireSim's own
# sourceme-manager.sh adds its deploy/ folder at the end, so the wrapper is found first.
case ":$PATH:" in
  *:/opt/kotl/bin:*) ;;
  *) PATH="/opt/kotl/bin:$PATH" ;;
esac
export PATH
