# kotl-band

A live Kotl line above the Claude Code prompt: each FPGA board and its state, who holds it and
for how long against their ETA, how many jobs are waiting, your own running jobs, unread notices
and board warnings. It reads `kotl status --json` every 30 seconds (on the workstation directly,
on your own PC over `ssh $KOTL_SSH`) and never starts or stops anything.

`/kotl-band` refreshes it now, `/kotl-band hide` hides it, `/kotl-band show` brings it back.

Install (on the workstation): `claude plugin marketplace add /opt/kotl` and
`claude plugin install kotl-band@kotl`.
