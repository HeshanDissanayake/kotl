"""The ETA notifier: once-only notices at ETA and 2x ETA, start-estimate slips (fake Slurm)."""
import pytest

from kotl.core import notifier
from kotl.core.registry import Registry

pytestmark = pytest.mark.feature("notifier")


class Q:
    def __init__(self):
        self.running, self.pending = {}, {}

    def running_times(self):
        return self.running

    def pending_starts(self):
        return self.pending


@pytest.fixture
def reg(tmp_path):
    return Registry(str(tmp_path / "kotl.db"))


def texts(reg, user):
    return [n["text"] for n in reversed(reg.notices(user))]


def test_nothing_before_eta(reg):
    q = Q(); q.running = {41: ("alice", 600, 1800)}
    assert notifier.run(reg, q, admin="boss") == 0 and texts(reg, "alice") == []


def test_eta_then_2x_eta_once_each(reg):
    q = Q(); q.running = {41: ("alice", 1900, 1800)}
    notifier.run(reg, q, admin="boss")
    notifier.run(reg, q, admin="boss")                          # every minute: still one notice
    assert texts(reg, "alice") == ["job 41 passed its ETA (30m); nothing is stopped. Your --max guard ends it if it hangs."]
    q.running = {41: ("alice", 3700, 1800)}
    notifier.run(reg, q, admin="boss")
    assert "past 2x its ETA" in texts(reg, "alice")[-1] and "kotl logs 41" in texts(reg, "alice")[-1]
    assert texts(reg, "boss") == ["job 41 of alice is at 1h01m, past 2x its ETA (30m)."]


def test_admin_own_job_gets_one_notice(reg):
    q = Q(); q.running = {7: ("boss", 4000, 1800)}
    notifier.run(reg, q, admin="boss")
    assert len(texts(reg, "boss")) == 2                           # ETA + 2x ETA, not doubled


def test_start_slip(reg):
    q = Q(); q.pending = {42: ("bob", 1_000_000)}
    notifier.run(reg, q)
    assert texts(reg, "bob") == []                                # first estimate: just remember it
    q.pending = {42: ("bob", 1_000_000 + 5 * 60)}
    notifier.run(reg, q)
    assert texts(reg, "bob") == []                                # a small slip isn't worth a notice
    q.pending = {42: ("bob", 1_000_000 + 20 * 60)}
    notifier.run(reg, q)
    assert len(texts(reg, "bob")) == 1 and "now expects to start at" in texts(reg, "bob")[0]


def test_notices_read_and_unread(reg):
    reg.notify("alice", "one"); reg.notify("alice", "two"); reg.notify("bob", "x")
    assert [n["text"] for n in reg.notices("alice", unread_only=True)] == ["two", "one"]
    reg.mark_read("alice")
    assert reg.notices("alice", unread_only=True) == [] and len(reg.notices("alice")) == 2
    assert len(reg.notices("bob", unread_only=True)) == 1
