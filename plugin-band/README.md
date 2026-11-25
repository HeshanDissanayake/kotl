# kotl-band

A live Kotl line above the Claude Code prompt: each FPGA board and its state, who holds it and
for how long against their ETA, how many jobs are waiting, your own running jobs, unread notices
and board warnings. Every second it reads the Kotl daemon's status file (on your own PC, or when
the daemon is down: `kotl status --json`, directly or over `ssh $KOTL_SSH`, every 5 s). It never
starts or stops anything.

Collapsed (the default) it is one line: the boards, how many wait, your next job, unread
notices. Expanded it adds your jobs and everyone waiting, in order (who, kind, ETA, estimated
start, why), and each board's warnings. Switch with the ▸/▾ button at its start (or `k` once the
band has the focus: a click, or ctrl+x tab), or `/kotl-band expand` / `/kotl-band collapse`; the
choice is kept for your next session.

`/kotl-band` refreshes it now, `/kotl-band hide` hides it, `/kotl-band show` brings it back.

Install (on the workstation): `claude plugin marketplace add /opt/kotl` and
`claude plugin install kotl-band@kotl`.
