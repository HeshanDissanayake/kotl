# Next: what Claude needs from you

This file always holds only the current steps. Copy commands from here.

## 0. What runs as virtex-host on the PC? (read-only)

The health check warns "something runs as virtex-host on the PC with no Kotl job holding the
board". This shows what it is:

```sh
ssh virtex-host@192.168.1.2 'ps -u virtex-host -o pid,etime,cmd --sort=start_time'
```

Your own `ssh` login shows up too (sshd, bash, ps). Anything else, such as `screen`,
`FireSim-xilinx_vcu118`, or a VS Code server, is what the warning means.

M4 is installed and the health check runs by itself every 5 minutes. Three live tests are left.

## 1. Say "ok PC" so Claude may run these two itself

- **ETA notice:** `kotl run --eta 1m -- sleep 100`. It passes its 1-minute ETA, and the
  notifier should tell Claude within a minute. Holds the board about 2 minutes; adds and removes a
  job key on the PC.
- **Console attach:** a short `kotl lease`, then `kotl attach`. With no FireSim running it should
  say there's no fsim0 console and list the PC's screens. Then `kotl release`. About 30 seconds.

## 2. The driver-failure test (you, sudo on the PC), when nobody is running FireSim

This unloads the XDMA driver on purpose. Kotl's next health check (within 5 minutes) should try
one reload, find the driver back, and keep the board up.

```sh
ssh -t virtex-host@192.168.1.2 'sudo modprobe -r xdma && lsmod | grep -c "^xdma " ; echo unloaded'
```

Then tell Claude. It watches `kotl board list` for the reload note and the driver coming back.
If the reload can't bring the driver back, the board goes down, queued jobs wait, and you get
a notice. That's the other half of the test, and the fix is `sudo modprobe xdma` on the PC.

Skip step 2 if you'd rather not break the driver now.
