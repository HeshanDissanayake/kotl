<!-- managed by kotl (deploy/kotl/install.sh). Read by every Claude Code session on this workstation. -->
# The lab's FPGA boards are shared through Kotl

This workstation's FPGA boards (VCU118 and their PCs, e.g. `vcu118-pc1`) are shared by everyone
through Kotl, a queue. Before anything that uses a board (FireSim `infrasetup`/`runworkload`,
flashing a bitstream, a driver test, ssh to an FPGA PC), go through Kotl:

- `kotl status`: the boards, the queue and who holds each board now.
- `kotl run --eta <estimate> -- <command>`: runs the command with a board, frees it after.
- `kotl lease --eta <estimate>`, then `ssh <board>`; `kotl release` when done.
- `kotl --help`; the full guide is `/opt/kotl/plugin/skills/kotl/SKILL.md` (read it first), and
  each tool has its own: FireSim's is `/opt/kotl/plugin/skills/kotl-firesim/SKILL.md`.
  `kotl setup` adds Kotl's Claude Code plugin and VS Code extension for this person.

Before running a tool on a board, read the lab notes: what worked before on these boards, with
which versions and configs (`kotl notes`, `kotl notes firesim`; the files are in
`/srv/kotl/notes/`). Afterwards add what you learned: `kotl notes add <tool> "..."`.

Never use a board outside Kotl: it can break another person's run, and Kotl can't protect work it
doesn't know about.

If a board looks busy (a FireSim `fsim*` screen or a `FireSim-*` driver on its PC) and it isn't
your Kotl job: it is someone else's work, or work outside Kotl. Don't stop it. Tell the person who
seems to run it and for how long, and that it is outside Kotl. If the person's own run outside
Kotl stopped, check `kotl status` and `kotl history`: a Kotl job may have taken the board.
