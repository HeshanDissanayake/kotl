"""Records which architecture feature each test covers, for tools/status.py refresh.

Tag tests with   @pytest.mark.feature("launcher")   (keys come from docs/status.json)
and board tests also with   @pytest.mark.hw
Results go to .kotl/test-results.json (git-ignored).
"""
import datetime as dt
import json
import os

import pytest

_RESULTS = []


def pytest_configure(config):
    config.addinivalue_line("markers", "feature(key): the architecture feature this test covers")
    config.addinivalue_line("markers", "hw: needs a real board; run only as a Kotl job")


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    rep = outcome.get_result()
    rep.kotl_features = [m.args[0] for m in item.iter_markers("feature") if m.args]
    rep.kotl_hw = item.get_closest_marker("hw") is not None


def pytest_runtest_logreport(report):
    # one entry per test: the call phase, or setup if it failed/skipped there
    if report.when == "call" or (report.when == "setup" and report.outcome != "passed"):
        _RESULTS.append({
            "nodeid": report.nodeid,
            "features": getattr(report, "kotl_features", []),
            "hw": getattr(report, "kotl_hw", False),
            "outcome": report.outcome,
        })


def pytest_sessionfinish(session, exitstatus):
    root = str(session.config.rootpath)
    os.makedirs(os.path.join(root, ".kotl"), exist_ok=True)
    with open(os.path.join(root, ".kotl", "test-results.json"), "w", encoding="utf-8") as f:
        json.dump({"ran_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                   "results": _RESULTS}, f, indent=1)
