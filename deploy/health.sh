#!/bin/sh
# managed by kotl (deploy/kotl/install.sh)
# Slurm runs this every 5 minutes (HealthCheckProgram= in slurm.conf), as root.
# Kotl's checks run as kotl and only record warnings on the boards (kotl board list, kotl top).
# It must always exit 0: a PC problem must never drain the workstation's own Slurm node.
[ -x /opt/kotl/launch ] && timeout 120 runuser -u kotl -- /opt/kotl/launch health --quiet >/dev/null 2>&1
exit 0
