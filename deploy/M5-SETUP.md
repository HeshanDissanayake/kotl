# M5 setup: the Kotl plugin for Claude Code

## 1. Publish it on the workstation (sudo)

`deploy/kotl/install.sh` now also copies the plugin to `/opt/kotl/plugin`, with a marketplace
file at `/opt/kotl/.claude-plugin/marketplace.json`, readable by everyone.

```sh
sudo deploy/kotl/install.sh --board vcu118-pc1=vcu118@vcu118-pc1
```

## 2. Each user, once

On the workstation:

```sh
claude plugin marketplace add /opt/kotl
claude plugin install kotl@kotl
```

(In Claude Code the same is `/plugin marketplace add /opt/kotl`, then `/plugin install kotl@kotl`.)

On a user's own PC: copy `/opt/kotl/plugin` and `/opt/kotl/.claude-plugin` there (or install
from the GitHub repo once it's reachable), add it the same way, and set the workstation's ssh
name in `~/.claude/settings.json`:

```json
{ "env": { "KOTL_SSH": "comparch" } }
```

## 3. Try it

Start a new Claude Code session anywhere and ask, for example:
"run hostname on the FPGA board through kotl and tell me the result".
