#!/bin/sh
# managed by kotl (deploy/kotl/install.sh)
# Slurm runs this every 5 minutes (HealthCheckProgram= in slurm.conf), as root.
# Kotl's checks run as kotl and only record warnings on the boards (kotl board list, kotl top).
# It must always exit 0: a PC problem must never drain the workstation's own Slurm node.
# Slurm runs this with an almost empty environment: no PATH, so set one
PATH=/usr/sbin:/usr/bin:/sbin:/bin
export PATH
[ -x /opt/kotl/launch ] && timeout 120 runuser -u kotl -- /opt/kotl/launch health --quiet >/dev/null 2>&1
exit 0
