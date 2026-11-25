"""The lab notes (/srv/kotl/notes): layout, reading, adding, replacing with history, and the run
lines the launcher adds at the end step. No board involved."""
import io
import json
import os
import stat
import subprocess
from pathlib import Path

import pytest

from kotl.adapters.firesim import FACTS, FireSim
from kotl.core import notes as nm
from kotl.core import results
from kotl.core.config import Config
from kotl.core.launcher import Launcher

from .fakes import FakeSlurm

pytestmark = pytest.mark.feature("notes")
ROOT = Path(__file__).resolve().parents[2]
NOW = 1764000000.0


@pytest.fixture
def notes(tmp_path):
    return nm.Notes(str(tmp_path / "notes"), [FireSim(here="2.39")], clock=lambda: NOW)


def mode(p):
    return stat.S_IMODE(os.stat(p).st_mode)


def test_layout_is_fixed_and_readable_by_everyone(notes):
    notes.ensure()
    root = Path(notes.root)
    for p in ("INDEX.md", "general/setup.md", "general/notes.md", "firesim/setup.md",
              "firesim/compatible.md", "firesim/runs.md", "firesim/notes.md"):
        assert (root / p).is_file() and mode(root / p) == 0o644, p
    assert mode(root) == 0o755 and mode(root / "firesim") == 0o755
    assert "XDMA" in (root / "firesim/setup.md").read_text()            # the adapter's seed
    index = (root / "INDEX.md").read_text()
    assert str(root / "firesim/runs.md") in index and "last good run: none recorded yet" in index
    (root / "firesim/setup.md").write_text("ours\n")
    notes.ensure()                                                        # never overwrites a page
    assert (root / "firesim/setup.md").read_text() == "ours\n"


def test_add_is_dated_signed_and_append_only(notes):
    notes.add("firesim", "alice", "use poll_mode=1\nor the driver hangs")
    notes.add("general", "bob", "pc1 reboots slowly")
    text = Path(notes.path("firesim", "notes.md")).read_text()
    assert "- 20" in text and " alice: use poll_mode=1\n  or the driver hangs\n" in text
    assert "bob: pc1 reboots slowly" in Path(notes.path("general", "notes.md")).read_text()
    with pytest.raises(nm.NotesError, match="empty"):
        notes.add("firesim", "alice", "  \x07 ")
    with pytest.raises(nm.NotesError, match="no notes for 'vivado'"):
        notes.add("vivado", "alice", "x")


def test_set_keeps_the_old_page_and_only_curated_pages(notes):
    notes.ensure()
    seed = Path(notes.path("firesim", "compatible.md")).read_text()
    old = notes.set("firesim", "compatible.md", "alice", "# good\n- chipyard 1.13 + vcu118\n")
    assert Path(old).read_text() == seed and old.endswith(".alice")
    assert Path(notes.path("firesim", "compatible.md")).read_text().startswith("# good")
    assert old in notes.history("firesim")
    for page, msg in (("runs.md", "only setup.md and compatible.md"), ("notes.md", "only"),
                      ("x.md", "no page 'x.md'")):
        with pytest.raises(nm.NotesError, match=msg):
            notes.set("firesim", page, "alice", "x")
    with pytest.raises(nm.NotesError, match="too long"):
        notes.set("firesim", "setup.md", "alice", "x" * (nm.MAX_SET + 1))
    with pytest.raises(nm.NotesError, match="empty"):
        notes.set("firesim", "setup.md", "alice", "\n")


def job(result, **kw):
    j = {"job_id": 71, "user": "alice", "board": "vcu118-pc1", "started": NOW - 125, "ended": NOW,
         "result": result, "reason": None, "command": "/pkg/run.sh"}
    j.update(kw)
    return j


def test_record_a_line_per_finished_run(notes):
    assert notes.record("firesim", job("passed"), None, {"tool": "firesim", "chipyard": "3021ed6c77"})
    notes.record("firesim", job("over_max", reason="over_max", job_id=72), None, {})
    assert notes.record("firesim", job("cancelled"), None, {}) is None     # nothing ran to the end
    assert notes.record("general", job("passed"), None, {}) is None        # runs belong to a tool
    rows = [l for l in Path(notes.path("firesim", "runs.md")).read_text().splitlines() if l.startswith("- ")]
    assert rows[0].startswith("- ok ") and "job 71 · alice · vcu118-pc1 · 2m · passed · chipyard=3021ed6c77 · cmd: /pkg/run.sh" in rows[0]
    assert "tool=" not in rows[0]
    assert rows[1].startswith("- FAIL ") and "job 72" in rows[1]
    assert "last good run: ok" in Path(notes.path(page="INDEX.md")).read_text()
    shown = notes.show("firesim")
    assert "job 71" in shown and "===== " + notes.path("firesim", "setup.md") in shown


def test_runs_keep_the_latest_and_move_older_ones(notes, monkeypatch):
    monkeypatch.setattr(nm, "MAX_RUNS", 3)
    for i in range(5):
        notes.record("firesim", job("passed", job_id=i), None, {})
    runs = Path(notes.path("firesim", "runs.md")).read_text()
    old = Path(notes.path("firesim", "runs-old.md")).read_text()
    assert [("job %d " % i) in runs for i in range(5)] == [False, False, True, True, True]
    assert "job 0 " in old and "job 1 " in old
    assert runs.startswith("# FireSim: runs")


def test_show_limits_the_runs(notes):
    for i in range(nm.SHOW_RUNS + 2):
        notes.record("firesim", job("passed", job_id=100 + i), None, {})
    shown = notes.show("firesim")
    assert "job 100 " not in shown and f"job {100 + nm.SHOW_RUNS + 1} " in shown
    assert "all: kotl notes firesim runs.md" in shown
    assert "job 100 " in notes.show("firesim", "runs.md")


def test_facts_are_checked():
    assert nm.parse_facts("tool=firesim\nBad=1\nx\nchipyard=abc+changes\n") == {"tool": "firesim", "chipyard": "abc+changes"}
    out = b"hi\nKOTL FACT: bitstream=ref-1\nKOTL FACT: Nope=1\nKOTL FACT: workload=linux \x1b[31m\n"
    assert nm.output_facts(out) == {"bitstream": "ref-1", "workload": "linux [31m"}


# ---- the launcher: facts at the end of a run, a line in runs.md

@pytest.fixture
def env(tmp_path):
    for d in ("var/lib/kotl", "srv/kotl/out", "etc/kotl"):
        (tmp_path / d).mkdir(parents=True)
    cfg = Config(prefix=str(tmp_path))
    fs = FakeSlurm()

    def make(who):
        L = Launcher(cfg, slurm=fs, who=who, adapters=[FireSim(here="2.39")])
        L.spawn_watcher = lambda job: None
        return L

    make("kotl").reg.add_board("vcu118-pc1", "vcu118-pc1", "vcu118")
    return cfg, fs, make


def runs(cfg):
    p = Path(cfg.notes) / "firesim/runs.md"
    return [l for l in p.read_text().splitlines() if l.startswith("- ")] if p.exists() else []


def test_a_firesim_run_gets_its_line_with_what_it_used(env):
    cfg, fs, make = env
    fs.add(7, "alice")
    L = make("alice")
    L.start(7, "run", command="sh -c firesim infrasetup && firesim runworkload")
    assert "echo tool=firesim" in L.facts_script(7)
    L.save_facts(7, io.BytesIO(b"tool=firesim\nchipyard=3021ed6c77\nhw_config=rocket\n"))
    L.end(7, rc=0)
    [line] = runs(cfg)
    assert line.startswith("- ok ") and "chipyard=3021ed6c77 hw_config=rocket" in line
    assert "notes: added to firesim/runs.md" in (Path(L.dir_for(L.reg.job(7))) / "launcher.log").read_text()


def test_a_command_that_describes_itself_wins(env):
    cfg, fs, make = env
    fs.add(7, "alice")
    L = make("alice")
    L.start(7, "run", command="/shared/pkg/run.sh")      # no 'firesim' in it: its own facts say so
    assert L.facts_script(7) == ""
    with open(os.path.join(L.dir_for(L.reg.job(7)), "output.log"), "wb") as f:
        f.write(b"KOTL FACT: tool=firesim\nKOTL FACT: bitstream=ref-1\nKOTL RESULT: PASS\n")
    L.end(7, rc=0)
    [line] = runs(cfg)
    assert "passed · bitstream=ref-1" in line


@pytest.mark.parametrize("mode,command,kw", [
    ("run", "make test", dict(rc=0)),                 # not a tool's run
    ("lease", "sleep infinity", dict(signal=True)),   # leases: Claude or the person adds a note
    ("run", "firesim runworkload", dict(signal=True)),  # cancelled
])
def test_no_line_for_other_jobs(env, mode, command, kw):
    cfg, fs, make = env
    fs.add(7, "alice")
    L = make("alice")
    L.start(7, mode, command=command)
    L.end(7, **kw)
    assert runs(cfg) == []


def test_the_notes_never_break_the_end_step(env, monkeypatch):
    cfg, fs, make = env
    fs.add(7, "alice")
    L = make("alice")
    L.start(7, "run", command="firesim runworkload")
    monkeypatch.setattr(nm.Notes, "record", lambda *a, **k: 1 / 0)
    assert L.end(7, rc=0) == "succeeded"
    assert L.reg.board("vcu118-pc1")["state"] == "idle"
    assert "notes: could not record the run" in (Path(L.dir_for(L.reg.job(7))) / "launcher.log").read_text()


def test_only_the_owner_saves_facts(env):
    cfg, fs, make = env
    fs.add(7, "alice")
    make("alice").start(7, "run", command="firesim runworkload")
    from kotl.core.launcher import Refused
    with pytest.raises(Refused, match="belongs to alice"):
        make("bob").save_facts(7, io.BytesIO(b"tool=firesim\n"))
    with pytest.raises(Refused, match="belongs to alice"):
        make("bob").facts_script(7)


# ---- the FireSim adapter's facts, on a fake Chipyard (git, configs): read-only

def git(cwd, *args):
    subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True,
                   env=dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t",
                            GIT_COMMITTER_EMAIL="t@t"))


def test_firesim_facts_read_the_users_firesim(tmp_path):
    fsd = tmp_path / "firesim"
    dep = fsd / "deploy"
    dep.mkdir(parents=True)
    (dep / "firesim").write_text("#!/bin/sh\n")
    (dep / "firesim").chmod(0o755)
    (dep / "config_runtime.yaml").write_text("target_config:\n    default_hw_config: hw_a  # default\nworkload:\n    workload_name: 'linux.json'\n")
    (dep / "mine.yaml").write_text("target_config:\n    default_hw_config: hw_b\nworkload:\n    workload_name: br-base.json\n")
    (dep / "config_hwdb.yaml").write_text("hw_a:\n    bitstream_tar: file:///x/results-build/ref-a/firesim.tar.gz\n"
                                         "hw_b:\n    deploy_quintuplet_override: null\n    bitstream_tar: file:///x/results-build/ref-b/firesim.tar.gz\n")
    git(fsd, "init", "-q"); git(fsd, "add", "."); git(fsd, "commit", "-qm", "x")
    (dep / "config_runtime.yaml").write_text((dep / "config_runtime.yaml").read_text() + "# edited\n")

    def facts(command):
        r = subprocess.run(["bash", "-c", FACTS], capture_output=True, text=True, cwd=str(dep),
                           env=dict(os.environ, PATH=f"{dep}:{os.environ['PATH']}", KOTL_COMMAND=command))
        return nm.parse_facts(r.stdout)

    f = facts("sh -c firesim infrasetup && firesim runworkload")
    assert f["tool"] == "firesim" and f["firesim"].endswith("+changes") and "chipyard" not in f
    assert (f["hw_config"], f["workload"], f["bitstream"]) == ("hw_a", "linux.json", "ref-a")
    f = facts(f"sh -c firesim runworkload -c {dep / 'mine.yaml'}")
    assert (f["hw_config"], f["bitstream"], f["runtime_config"]) == ("hw_b", "ref-b", str(dep / "mine.yaml"))
    r = subprocess.run(["bash", "-c", FACTS], capture_output=True, text=True, env=dict(os.environ, PATH="/usr/bin:/bin"))
    assert nm.parse_facts(r.stdout) == {"tool": "firesim"}             # no FireSim on PATH: just the tool


# ---- the CLI and job.sh

def test_kotl_notes_passes_words_to_the_launcher(tmp_path, monkeypatch, capsys):
    from kotl.cli import main as cli
    log = tmp_path / "calls"
    fake = tmp_path / "launch"
    fake.write_text(f'#!/bin/sh\necho "$*" >> {log}\ncat >> {log}\n')
    fake.chmod(0o755)
    monkeypatch.setenv("KOTL_LAUNCH", str(fake))
    assert cli.main(["notes"]) == 0
    assert cli.main(["notes", "firesim", "runs.md"]) == 0
    assert cli.main(["notes", "add", "firesim", "-c", "works", "with", "poll_mode=1"]) == 0
    assert cli.main(["notes", "history", "firesim"]) == 0
    calls = log.read_text()
    assert "notes show\n" in calls and "notes show firesim runs.md\n" in calls
    assert "notes add firesim\n-c works with poll_mode=1" in calls and "notes history firesim\n" in calls
    with pytest.raises(SystemExit):
        cli.main(["notes", "add", "firesim"])


def test_job_sh_saves_the_runs_facts_before_the_end_step(tmp_path):
    calls, facts = tmp_path / "calls", tmp_path / "facts"
    fake = tmp_path / "launch"
    fake.write_text(f"""#!/bin/bash
echo "$*" >> {calls}
case "$1" in
  start) echo board=vcu118-pc1; echo pc=u@1.2.3.4 ;;
  log) cat >/dev/null ;;
  facts-script) echo 'echo cmd="$KOTL_COMMAND"; echo dir=$PWD' ;;
  facts) cat > {facts} ;;
esac
""")
    fake.chmod(0o755)
    env = dict(os.environ, SLURM_JOB_ID="42", KOTL_LAUNCH=str(fake), KOTL_KEYDIR=str(tmp_path / "keys"))
    r = subprocess.run(["bash", str(ROOT / "deploy/job.sh"), "firesim", "runworkload"], env=env, cwd=str(tmp_path),
                       capture_output=True, text=True)
    c = calls.read_text().splitlines()
    assert c[-3:] == ["facts-script 42", "facts 42", f"end 42 --rc {r.returncode}"]
    assert facts.read_text() == f"cmd=firesim runworkload\ndir={tmp_path}\n"


# ---- the daemon keeps the notes there

def test_daemon_makes_the_notes(tmp_path):
    from kotl.core import daemon as kd
    for d in ("var/lib/kotl", "run/kotl", "etc/kotl"):
        (tmp_path / d).mkdir(parents=True)
    (tmp_path / "etc/kotl/kotl.conf").write_text("adapters = firesim\n")
    cfg = Config(prefix=str(tmp_path))
    d = kd.Daemon(cfg, slurm=FakeSlurm(), tasks=[kd.NotesTask])
    d.step()
    assert d.errors["notes"] is None
    assert (Path(cfg.notes) / "firesim/runs.md").exists() and (Path(cfg.notes) / "INDEX.md").exists()
