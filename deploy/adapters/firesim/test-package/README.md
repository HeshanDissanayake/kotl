# Kotl FireSim test

Boots Linux on the lab's VCU118 FPGA through Kotl, then powers it off. Everything it needs is in
this folder: the FireSim driver and its libraries, the bitstream and a Linux workload. You don't
need Chipyard, FireSim, conda or any setup beyond a Kotl account.

## Run it

From any folder you can write to (results go to `./firesim-test-results/<job>/`):

```sh
kotl run --eta 15m -- @PACKAGE@/run.sh
```

- It waits in Kotl's queue for a board, then flashes the FPGA, boots Linux and waits for it to
  power off (a few minutes).
- `kotl status` or `kotl top` shows where it is. `kotl attach` shows the live console.
- The last line says **`KOTL RESULT: PASS`** when Linux booted and powered off.
- The board is freed as soon as it finishes, whatever the result.

## For Claude

When the person asks to test FireSim, the FPGA or Kotl with this package:

1. Run `kotl run --eta 15m --no-wait -- <this folder>/run.sh` from a writable folder (not this
   one), and note the job number it prints.
2. Follow it with `kotl logs <job> -f` in the background, or check `kotl status` now and then.
   The steps are numbered `1/6` to `6/6`.
3. When it ends: `kotl fetch <job>`, read `kotl-results/<job>/status.json` (`result`), and the
   `firesim-test-results/<job>/uartlog` in the folder it ran from.
4. Report: PASS or FAIL, how long it took against the 15 minute ETA, and for a FAIL the step it
   stopped at and the last uartlog lines.

If step 1 says FireSim is already running outside Kotl, stop there: don't stop that run and
don't retry around it. Report what it printed (how long it has run, who is connected) and that it
is outside Kotl, and suggest asking that person to use `kotl run` or `kotl lease`.

Common failures, from step 1: XDMA loaded without `poll_mode=1`, or a board account without
passwordless sudo. These are board setup problems for the admin, not something to work around.
Never run FireSim or ssh to the FPGA PC outside `kotl run`.

## Settings

| Variable | Default | Meaning |
| --- | --- | --- |
| `KOTL_TEST_TIMEOUT` | 900 | seconds to wait for Linux to power off |
| `KOTL_TEST_KEEP` | 0 | 1 keeps the copy on the PC afterwards |
| `KOTL_TEST_OUT` | `./firesim-test-results/<job>` | where the uartlog goes |

`MANIFEST` lists where each file came from and its checksum.
