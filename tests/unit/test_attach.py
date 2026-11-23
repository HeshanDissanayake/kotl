"""kotl attach: the ssh command for a running job's console, with the job key only."""
import pytest

from kotl.core import attach

pytestmark = pytest.mark.feature("attach")
RUNNING = {"state": "running", "pc_address": "192.168.1.2", "pc_user": "virtex-host"}


def test_attach_uses_only_the_job_key(tmp_path):
    (tmp_path / "job-41").write_text("key")
    argv, why = attach.argv_for(RUNNING, "alice", 41, keydir=str(tmp_path))
    assert why is None
    assert argv[:2] == ["ssh", "-t"] and "IdentitiesOnly=yes" in argv and "IdentityAgent=none" in argv
    assert argv[argv.index("-i") + 1] == str(tmp_path / "job-41")
    assert argv[-2] == "virtex-host@192.168.1.2" and "screen -x fsim0" in argv[-1]


@pytest.mark.parametrize("status,msg", [
    (None, "isn't running"), (dict(RUNNING, state="done"), "isn't running"),
    (dict(RUNNING, pc_address=None), "no PC access"), (RUNNING, "no job key"),
])
def test_attach_explains_why_not(tmp_path, status, msg):
    argv, why = attach.argv_for(status, "alice", 41, keydir=str(tmp_path))
    assert argv is None and msg in why
