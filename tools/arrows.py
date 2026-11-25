"""Arrow checks for the architecture map.

The view routes its arrows live (docs/router.js). This routes them the same way in
every fold state (through node, tools/arrows-check.js) and checks, independently of the router:
every arrow is drawn, has its own start point and its own end point, no two arrows run along the
same line, and no arrow passes through a box. Arrows may cross. Used by tools/status.py check:

  python3 tools/arrows.py        list every problem
"""
import shutil
import subprocess
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARCH = os.path.join(ROOT, "docs", "architecture.json")
NEAR = 6        # two endpoints closer than this count as the same point
GAP = 5         # parallel segments closer than this count as the same line


def points(d):
    pts, x, y = [], 0.0, 0.0
    for c, p, q in re.findall(r"([MHV])\s*(-?[\d.]+)(?:\s*,\s*(-?[\d.]+))?", d):
        if c == "M":
            x, y = float(p), float(q)
        elif c == "H":
            x = float(p)
        else:
            y = float(p)
        pts.append((x, y))
    return pts


def segments(d):
    pts = points(d)
    return [(pts[i - 1], pts[i]) for i in range(1, len(pts))]


def overlap(s, t):
    """Length two axis-aligned segments run along the same line."""
    (a1, a2), (b1, b2) = s, t
    if a1[1] == a2[1] and b1[1] == b2[1] and abs(a1[1] - b1[1]) < GAP:          # both horizontal
        lo, hi = max(min(a1[0], a2[0]), min(b1[0], b2[0])), min(max(a1[0], a2[0]), max(b1[0], b2[0]))
        return hi - lo
    if a1[0] == a2[0] and b1[0] == b2[0] and abs(a1[0] - b1[0]) < GAP:          # both vertical
        lo, hi = max(min(a1[1], a2[1]), min(b1[1], b2[1])), min(max(a1[1], a2[1]), max(b1[1], b2[1]))
        return hi - lo
    return 0


def through_box(d, boxes):
    for b in boxes:
        for (x1, y1), (x2, y2) in segments(d):
            if max(x1, x2) > b["x"] + 1 and min(x1, x2) < b["x"] + b["w"] - 1 and max(y1, y2) > b["y"] + 1 and min(y1, y2) < b["y"] + b["h"] - 1:
                return b["id"]
    return None


def check_states():
    """Problems across every fold state, or a note if node isn't available."""
    if not shutil.which("node"):
        return [], "node not found: arrow routes not checked"
    r = subprocess.run(["node", os.path.join(ROOT, "tools", "arrows-check.js"), os.path.dirname(ARCH)],
                       capture_output=True, text=True, timeout=300)
    if r.returncode:
        return [f"arrow router failed: {r.stderr.strip()[-300:]}"], None
    out = []
    for st in json.loads(r.stdout):
        where = "with " + (", ".join(sorted(st["folded"])) or "nothing") + " folded"
        out += [f"arrow '{f}' has no clean route {where}" for f in st["failed"]]
        drawn = [e for e in st["edges"] if e["d"]]
        out += [f"{p} {where}" for p in problems({"edges": drawn})]
        for e in drawn:
            b = through_box(e["d"], [x for x in st["boxes"]])
            if b:
                out.append(f"arrow '{e['id']}' runs through box '{b}' {where}")
    return sorted(set(out)), None


def problems(arch):
    edges = arch.get("edges", [])
    out = []
    for i, e in enumerate(edges):
        pe = points(e["d"])
        for f in edges[i + 1:]:
            pf = points(f["d"])
            for name, p, q in (("start", pe[0], pf[0]), ("end", pe[-1], pf[-1]), ("start/end", pe[0], pf[-1]), ("end/start", pe[-1], pf[0])):
                if abs(p[0] - q[0]) < NEAR and abs(p[1] - q[1]) < NEAR:
                    out.append(f"arrows '{e['id']}' and '{f['id']}' share a {name} point {p}")
            worst = max((overlap(s, t) for s in segments(e["d"]) for t in segments(f["d"])), default=0)
            if worst > 2:
                out.append(f"arrows '{e['id']}' and '{f['id']}' run along the same line for {worst:.0f}px")
    return out


if __name__ == "__main__":
    probs, note = check_states()
    print("\n".join(probs) or note or "every fold state: each arrow its own start and end, no shared lines, no arrow through a box")
    sys.exit(1 if probs else 0)
