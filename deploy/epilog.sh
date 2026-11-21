#!/bin/sh
# managed by kotl (deploy/slurm/install.sh)
# Slurm runs this as root after every job (Epilog= in slurm.conf).
# M1 placeholder: it does nothing. In M2 it becomes the end step's backup:
#   exec runuser -u kotl -- /opt/kotl/launch end "$SLURM_JOB_ID"
# It must always exit 0, or Slurm drains the node.
exit 0
