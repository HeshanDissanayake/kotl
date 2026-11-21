"""The launcher (board lease) and job results, with a fake Slurm."""
import io
import json
import os
import tarfile
import time

import pytest

from kotl.core import results
from kotl.core.config import Config, parse_duration
from kotl.core.launcher import Launcher, Refused, time_limit_seconds

from .fakes import FakeSlurm


@pytest.fixture
def env(tmp_path):
    for d in ("var/lib/kotl", "srv/kotl/out", "srv/kotl/jobs", "etc/kotl"):
        (tmp_path / d).mkdir(parents=True)
    (tmp_path / "etc/kotl/kotl.conf").write_text("admin = boss\n")
    cfg = Config(prefix=str(tmp_path))
    fs = FakeSlurm()

    def make(who):
        L = Launcher(cfg, slurm=fs, who=who)
        L.spawn_watcher = lambda job: None
        return L

    make("kotl").reg.add_board("vcu118-pc1", "vcu118-pc1", "vcu118")
    return cfg, fs, make


def status_of(cfg, user, job):
    return results.read_status(results.job_dir(cfg.out, user, job))


@pytest.mark.feature("launcher")
def test_start_claims_and_writes_status(env):
    cfg, fs, make = env
    fs.add(7, "alice")
    b = make("alice").start(7, "run", command="sleep 5")
    assert b["name"] == "vcu118-pc1"
    st = status_of(cfg, "alice", 7)
    assert st["state"] == "running" and st["board"] == "vcu118-pc1"
    assert st["eta_s"] == 1800 and st["max_s"] == 3600            # max defaults to 2x ETA
    assert oct(os.stat(results.job_dir(cfg.out, "alice", 7)).st_mode & 0o777) == "0o700"


@pytest.mark.feature("launcher")
@pytest.mark.parametrize("who,setup,msg", [
    ("bob", dict(user="alice"), "belongs to alice"),
    ("alice", dict(user="alice", state="PENDING"), "not running"),
    ("alice", dict(user="alice", licenses="(null)"), "no vcu118 license"),
])
def test_start_refusals(env, who, setup, msg):
    cfg, fs, make = env
    fs.add(7, **setup)
    with pytest.raises(Refused, match=msg):
        make(who).start(7, "run")


@pytest.mark.feature("launcher")
def test_start_unknown_job_and_twice(env):
    cfg, fs, make = env
    with pytest.raises(Refused, match="no job"):
        make("alice").start(99, "run")
    fs.add(7, "alice")
    make("alice").start(7, "run")
    with pytest.raises(Refused, match="already started"):
        make("alice").start(7, "run")


@pytest.mark.feature("launcher")
def test_second_job_gets_no_board(env):
    cfg, fs, make = env
    fs.add(7, "alice"); fs.add(8, "bob")
    make("alice").start(7, "run")
    with pytest.raises(Refused, match="no idle vcu118 board"):
        make("bob").start(8, "run")


@pytest.mark.feature("launcher")
def test_end_frees_board_once(env):
    cfg, fs, make = env
    fs.add(7, "alice")
    L = make("alice")
    L.start(7, "run")
    assert L.end(7, rc=0) == "succeeded"
    assert L.reg.board("vcu118-pc1")["state"] == "idle"
    st = status_of(cfg, "alice", 7)
    assert st["state"] == "done" and st["result"] == "succeeded" and st["rc"] == 0
    assert L.end(7, rc=1) == "succeeded"                     # safe to run twice
    assert make("kotl").end(7, epilog=True) == "succeeded"   # the epilog changes nothing


@pytest.mark.feature("launcher")
@pytest.mark.parametrize("mode,kw,expect", [
    ("run", dict(rc=3), "failed"),
    ("run", dict(signal=True), "cancelled"),
    ("lease", dict(signal=True), "released"),
])
def test_end_results(env, mode, kw, expect):
    cfg, fs, make = env
    fs.add(7, "alice")
    L = make("alice")
    L.start(7, mode)
    assert L.end(7, **kw) == expect


@pytest.mark.feature("launcher")
def test_epilog_catches_a_killed_job(env):
    cfg, fs, make = env
    fs.add(7, "alice")
    make("alice").start(7, "run")
    assert make("kotl").end(7, epilog=True) == "killed"
    assert make("kotl").reg.board("vcu118-pc1")["state"] == "idle"
    assert make("kotl").end(12345, epilog=True) is None     # not a Kotl job: nothing to do


@pytest.mark.feature("launcher")
def test_others_cannot_end_or_read(env):
    cfg, fs, make = env
    fs.add(7, "alice")
    make("alice").start(7, "run")
    for call in (lambda L: L.end(7, rc=0), lambda L: L.logs(7, out=io.BytesIO()),
                 lambda L: L.fetch(7, out=io.BytesIO())):
        with pytest.raises(Refused, match="belongs to alice"):
            call(make("bob"))
    make("boss").logs(7, out=io.BytesIO())                  # the admin may


@pytest.mark.feature("launcher")
@pytest.mark.parametrize("kw,reason", [(dict(max_=60), "over_max"), (dict(idle=60), "idle")])
def test_guards_cancel_and_record_why(env, kw, reason):
    cfg, fs, make = env
    fs.add(7, "alice")
    make("alice").start(7, "run", **kw)
    t0 = time.time()
    clock = iter([t0 + 10, t0 + 120, t0 + 130])

    def sleep(_):
        if len(fs.cancelled) and fs.jobs[7]["JobState"] == "RUNNING":
            fs.jobs[7]["JobState"] = "COMPLETED"
    os.utime(os.path.join(results.job_dir(cfg.out, "alice", 7)), (t0, t0))
    W = Launcher(cfg, slurm=fs, who="kotl", clock=lambda: next(clock), sleep=sleep)
    W.watch(7)
    assert fs.cancelled == [7]
    assert W.end(7, signal=True) == reason                  # the guard's reason, not "cancelled"


@pytest.mark.feature("launcher")
def test_watch_only_by_kotl(env, monkeypatch):
    cfg, fs, make = env
    monkeypatch.setenv("SUDO_USER", "alice")
    with pytest.raises(Refused):
        make("alice").watch(7)


@pytest.mark.feature("launcher")
def test_logs_and_history(env):
    cfg, fs, make = env
    fs.add(7, "alice")
    L = make("alice")
    L.start(7, "run")
    L.append_log(7, io.BytesIO(b"hello\n"))
    out = io.BytesIO()
    L.logs(7, out=out)
    assert out.getvalue() == b"hello\n"
    L.end(7, rc=0)
    assert "succeeded" in L.history() and "7" in L.history()
    assert "7 " not in make("bob").history().split("\n", 1)[-1]


@pytest.mark.feature("launcher")
def test_time_limits():
    assert time_limit_seconds("30:00") == 1800
    assert time_limit_seconds("1:00:00") == 3600
    assert time_limit_seconds("1-02:00:00") == 93600
    assert time_limit_seconds("UNLIMITED") is None


@pytest.mark.feature("results")
def test_fetch_is_a_tarball(env):
    cfg, fs, make = env
    fs.add(7, "alice")
    L = make("alice")
    L.start(7, "run")
    L.end(7, rc=0)
    out = io.BytesIO()
    L.fetch(7, out=out)
    names = tarfile.open(fileobj=io.BytesIO(out.getvalue())).getnames()
    assert {"7/status.json", "7/launcher.log", "7/outputs"} <= set(names)


@pytest.mark.feature("results")
def test_status_json_fields(env):
    cfg, fs, make = env
    fs.add(7, "alice")
    L = make("alice")
    L.start(7, "run", command="./t.sh")
    L.end(7, rc=0)
    st = json.loads(open(os.path.join(results.job_dir(cfg.out, "alice", 7), "status.json")).read())
    assert {"job", "user", "mode", "board", "result", "rc", "started", "ended", "command"} <= set(st)
    assert st["command"] == "./t.sh" and st["ended"] >= st["started"]


@pytest.mark.feature("results")
def test_purge_after_30_days(tmp_path):
    old = tmp_path / "alice" / "1"; new = tmp_path / "alice" / "2"
    old.mkdir(parents=True); new.mkdir()
    t = time.time() - 31 * 86400
    os.utime(old, (t, t))
    assert results.purge(str(tmp_path), 30) == 1
    assert not old.exists() and new.exists()


@pytest.mark.feature("cli")
@pytest.mark.parametrize("text,secs", [("90", 5400), ("45m", 2700), ("2h", 7200), ("1h30m", 5400), ("1d", 86400)])
def test_durations(text, secs):
    assert parse_duration(text) == secs


@pytest.mark.feature("cli")
def test_bad_duration():
    with pytest.raises(ValueError):
        parse_duration("soon")


@pytest.mark.feature("launcher")
def test_watcher_starts_without_sudo_vars(env, monkeypatch):
    cfg, fs, make = env
    seen = {}
    monkeypatch.setenv("SUDO_USER", "alice")
    monkeypatch.setattr("subprocess.Popen", lambda args, **kw: seen.update(args=args, env=kw["env"]))
    Launcher(cfg, slurm=fs, who="alice").spawn_watcher(7)
    assert seen["args"][-2:] == ["watch", "7"]
    assert not any(k.startswith("SUDO_") for k in seen["env"])


@pytest.mark.feature("cli")
def test_short_durations_show_seconds():
    from kotl.core.config import fmt_duration
    assert fmt_duration(15) == "15s" and fmt_duration(120) == "2m" and fmt_duration(5400) == "1h30m"


@pytest.mark.feature("launcher")
def test_no_exit_plan_is_refused(env):
    cfg, fs, make = env
    fs.add(7, "alice", time_limit="UNLIMITED")
    with pytest.raises(Refused, match="exit plan"):
        make("alice").start(7, "run")
    assert make("kotl").reg.board("vcu118-pc1")["state"] == "idle"


@pytest.mark.feature("launcher")
def test_lease_always_has_idle_guard(env):
    cfg, fs, make = env
    fs.add(7, "alice", name="kotl-lease")
    make("alice").start(7, "lease")
    assert make("kotl").reg.job(7)["idle"] == 1800             # kotl.conf idle (default 30m)


@pytest.mark.feature("launcher")
def test_lease_idle_means_nothing_running_on_the_pc(env):
    cfg, fs, make = env
    fs.add(7, "alice", name="kotl-lease")
    make("alice").start(7, "lease", idle=120)
    t0 = time.time()
    answers = iter([True, False, False, False])                 # busy at first, then nothing runs
    clock = iter([t0 + 10, t0 + 70, t0 + 130, t0 + 190, t0 + 250])
    W = Launcher(cfg, slurm=fs, who="kotl", clock=lambda: next(clock),
                 sleep=lambda _: fs.cancelled and fs.jobs[7].update(JobState="COMPLETED"))
    W.pc_busy = lambda j: next(answers)
    W.watch(7)
    assert fs.cancelled == [7] and W.end(7, signal=True) == "idle"


@pytest.mark.feature("launcher")
@pytest.mark.parametrize("text,rc,expect", [
    (b"boot\nKOTL RESULT: PASS\n", 0, "passed"),
    (b"KOTL RESULT: PASS\nKOTL RESULT: FAIL\n", 0, "failed"),
    (b"no marker\n", 0, "succeeded"),
    (b"no marker\n", 2, "failed"),
])
def test_result_marker(env, text, rc, expect):
    cfg, fs, make = env
    fs.add(7, "alice")
    L = make("alice")
    L.start(7, "run")
    L.append_log(7, io.BytesIO(text))
    assert L.end(7, rc=rc) == expect
