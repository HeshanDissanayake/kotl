#!/usr/bin/env python3
"""Keep docs/architecture (architecture.json + status.json) in step with the code.

  python3 tools/status.py check            consistency + coverage of all tracked files
  python3 tools/status.py check --staged   same, plus pre-commit rules for staged files
  python3 tools/status.py refresh          fold the last test run into status.json
  python3 tools/status.py refresh --results PATH   (e.g. results copied back from a board job)

Exit code 1 means "fix these problems first"; each problem says what to do.
Standard library only.
"""
import argparse
import datetime as dt
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARCH = os.path.join(ROOT, "docs", "architecture", "architecture.json")
STATUS = os.path.join(ROOT, "docs", "architecture", "status.json")
STATUS_REL = "docs/architecture/status.json"
RESULTS = os.path.join(ROOT, ".kotl", "test-results.json")

VALID = {"planned", "in_progress", "built", "tested", "failing", "blocked", "later", "parked"}
AGENT_SET = {"planned", "in_progress", "built", "blocked", "later", "parked"}  # tested/failing come from refresh only


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def git(*args):
    try:
        out = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True)
        return out.stdout
    except (OSError, subprocess.CalledProcessError):
        return None


def covered(path, prefixes):
    return any(path == p or (p.endswith("/") and path.startswith(p)) for p in prefixes)


def node_key(n):
    return n.get("detail") or n["id"]


def check(staged_only):
    problems = []
    try:
        arch = load(ARCH)
    except Exception as e:  # noqa: BLE001
        return [f"architecture.json does not load: {e}"]
    try:
        status = load(STATUS)
    except Exception as e:  # noqa: BLE001
        return [f"status.json does not load: {e}"]

    nodes = arch.get("nodes", [])
    edges = arch.get("edges", [])
    details = arch.get("details", {})
    files = arch.get("files", {})
    feats = status.get("features", {})
    milestones = status.get("milestones", {})

    # ids unique
    ids = [n["id"] for n in nodes]
    for i in sorted({i for i in ids if ids.count(i) > 1}):
        problems.append(f"node id '{i}' is used twice in architecture.json")
    eids = [e["id"] for e in edges]
    for i in sorted({i for i in eids if eids.count(i) > 1}):
        problems.append(f"edge id '{i}' is used twice in architecture.json")
    idset, keyset = set(ids), {node_key(n) for n in nodes}

    # every box has details; every non-user box has a status entry
    for n in nodes:
        k = node_key(n)
        if k not in details:
            problems.append(f"box '{n['id']}' has no details entry '{k}' in architecture.json")
        if n.get("owner") != "user" and k not in feats:
            problems.append(f"box '{n['id']}' has no status entry '{k}' in status.json (add one)")
        if n.get("owner") not in {"user", "kotl", "slurm", "outside", "hardware"}:
            problems.append(f"box '{n['id']}' has an unknown owner '{n.get('owner')}'")

    # every drawn feature has a box
    for k, f in feats.items():
        if f.get("drawn", True) and k not in keyset:
            problems.append(f"status entry '{k}' has no box in architecture.json (add a node, or set \"drawn\": false)")
        st = f.get("status")
        if st not in VALID:
            problems.append(f"status entry '{k}' has unknown status '{st}'")
        if st in {"tested", "failing"} and not ((f.get("tests") or {}).get("unit") or (f.get("tests") or {}).get("hardware")):
            problems.append(f"status entry '{k}' says '{st}' but has no test results: only 'refresh' may set that")
        if f.get("milestone") and f["milestone"] not in milestones:
            problems.append(f"status entry '{k}' uses milestone '{f['milestone']}' that isn't in milestones")

    # edges point at real boxes
    for e in edges:
        for end in ("from", "to"):
            if e.get(end) not in idset:
                problems.append(f"edge '{e['id']}' {end} '{e.get(end)}' is not a box id")

    # flows reference real boxes and edges
    eidset = set(eids)
    for fk, flow in arch.get("flows", {}).items():
        for i, s in enumerate(flow.get("steps", []), 1):
            for nid in s.get("nodes", []):
                if nid not in idset:
                    problems.append(f"flow '{fk}' step {i} names unknown box '{nid}'")
            for eid in s.get("edges", []):
                if eid not in eidset:
                    problems.append(f"flow '{fk}' step {i} names unknown edge '{eid}'")

    # file cards exist
    for k, d in details.items():
        for fk in d.get("files", []) or []:
            if fk not in files:
                problems.append(f"details '{k}' lists file card '{fk}' that isn't in files")

    # geometry: inside the canvas, no overlapping boxes
    cw, ch = arch["canvas"]["w"], arch["canvas"]["h"]
    for n in nodes:
        if n["x"] < 0 or n["y"] < 0 or n["x"] + n["w"] > cw or n["y"] + n["h"] > ch:
            problems.append(f"box '{n['id']}' sticks out of the canvas ({cw}x{ch}); grow the canvas instead")
    for i, a in enumerate(nodes):
        for b in nodes[i + 1:]:
            if a.get("inside") == b["id"] or b.get("inside") == a["id"]:
                continue
            if a["x"] < b["x"] + b["w"] and b["x"] < a["x"] + a["w"] and a["y"] < b["y"] + b["h"] and b["y"] < a["y"] + a["h"]:
                problems.append(f"boxes '{a['id']}' and '{b['id']}' overlap; put the new one in free space")

    # code coverage: every file under the watched folders belongs to a feature
    watch = status.get("watch", [])
    shared = status.get("shared", [])
    all_code = [p for f in feats.values() for p in f.get("code", [])]
    listing = git("diff", "--cached", "--name-only", "--diff-filter=ACMR") if staged_only else git("ls-files")
    if listing is not None:
        paths = [p for p in listing.splitlines() if p]
        for p in paths:
            if os.path.basename(p) == "__init__.py":
                continue  # package markers belong to no one
            if covered(p, watch) and not covered(p, shared) and not covered(p, all_code):
                problems.append(f"'{p}' belongs to no feature: add its path to a feature's \"code\" in status.json (or a new feature and box)")
        if staged_only:
            touched = sorted({k for k, f in feats.items() for p in paths if covered(p, f.get("code", []))})
            if touched and STATUS_REL not in paths:
                problems.append(f"code for {', '.join(touched)} changed but status.json isn't staged: update their status, now and log")
    return problems


def refresh(results_path, use_git):
    status = load(STATUS)
    feats = status["features"]
    if os.path.exists(results_path):
        res = load(results_path)
        ran_at = res.get("ran_at")
        agg = {}
        untagged = []
        for r in res.get("results", []):
            if not r.get("features"):
                untagged.append(r["nodeid"])
            for k in r.get("features", []):
                kind = "hardware" if r.get("hw") else "unit"
                a = agg.setdefault(k, {}).setdefault(kind, {"passed": 0, "failed": 0, "ran_at": ran_at})
                if r["outcome"] == "passed":
                    a["passed"] += 1
                elif r["outcome"] == "failed":
                    a["failed"] += 1
        for k, kinds in agg.items():
            if k not in feats:
                print(f"warning: tests tagged '{k}' but status.json has no such feature", file=sys.stderr)
                continue
            tests = feats[k].setdefault("tests", {"unit": None, "hardware": None})
            tests.update(kinds)
            f = feats[k]
            if f.get("status") in {"built", "tested", "failing"}:
                u, h = tests.get("unit"), tests.get("hardware")
                failed = (u and u["failed"]) or (h and h["failed"])
                passed = (u and u["passed"]) or (h and h["passed"])
                if failed:
                    f["status"] = "failing"
                elif passed:
                    f["status"] = "tested"
        for n in untagged:
            print(f"warning: test has no @pytest.mark.feature(...): {n}", file=sys.stderr)
    else:
        print(f"no test results at {results_path}; run pytest first (only commit info refreshed)", file=sys.stderr)

    if use_git:
        head = git("rev-parse", "HEAD")
        status["repo_commit"] = head.strip() if head else None
        for f in feats.values():
            code = [p for p in f.get("code", []) if os.path.exists(os.path.join(ROOT, p))]
            if not code:
                continue
            out = git("log", "-1", "--format=%H%x1f%s%x1f%cI", "--", *code)
            if out and out.strip():
                h, s, d = out.strip().split("\x1f")
                f["last_commit"] = {"hash": h, "message": s, "date": d}
    status["updated"] = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with open(STATUS, "w", encoding="utf-8") as fh:
        json.dump(status, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    print("status.json refreshed")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("--staged", action="store_true", help="pre-commit mode: look at staged files only")
    r = sub.add_parser("refresh")
    r.add_argument("--results", default=RESULTS)
    r.add_argument("--no-git", action="store_true")
    a = ap.parse_args()
    if a.cmd == "check":
        probs = check(a.staged)
        for p in probs:
            print("✗ " + p)
        if probs:
            print(f"\n{len(probs)} problem(s). Code, status.json and architecture.json must agree.")
            sys.exit(1)
        print("✓ code, status.json and architecture.json agree")
    else:
        refresh(a.results, not a.no_git)


if __name__ == "__main__":
    main()
