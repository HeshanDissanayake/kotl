#!/bin/sh
# managed by kotl (deploy/kotl/install.sh)
# Slurm runs this as root after every job (Epilog= in slurm.conf): Kotl's end step again,
# as a backup in case job.sh was killed. It does nothing for jobs that aren't Kotl's.
# It must always exit 0, or Slurm drains the node.
# Slurm runs this with an almost empty environment: no PATH, so set one
PATH=/usr/sbin:/usr/bin:/sbin:/bin
export PATH
[ -x /opt/kotl/launch ] && runuser -u kotl -- /opt/kotl/launch end "${SLURM_JOB_ID:-0}" --epilog >/dev/null 2>&1
exit 0
