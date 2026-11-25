"""Lab notes: what the lab knows about running each tool on its boards, kept by Kotl.

  /srv/kotl/notes/INDEX.md               what's here (written by Kotl: don't edit)
  /srv/kotl/notes/general/               Kotl-wide: setup.md, notes.md
  /srv/kotl/notes/<adapter>/             one folder per enabled adapter (e.g. firesim/):
      setup.md       what the boards' PCs have for this tool (curated: kotl notes set)
      compatible.md  known-good and known-bad combinations (curated: kotl notes set)
      runs.md        one line per finished run, added by Kotl at the end step (newest last)
      notes.md       free notes, dated and signed (kotl notes add)

The paths never change, so skills and CLAUDE.md can name them. Everything is readable by
everyone on the workstation (0755 folders, 0644 files); only the launcher (as kotl) writes, so
every change has a date and an author. `kotl notes set` keeps the page it replaces in
<tool>/.history/. runs.md keeps its last MAX_RUNS lines; older ones move to runs-old.md.
"""
import os
import re
import time

GENERAL = "general"
CURATED = ("setup.md", "compatible.md")
TOOL_PAGES = ("setup.md", "compatible.md", "runs.md", "notes.md")
GENERAL_PAGES = ("setup.md", "notes.md")
MAX_SET = 64 * 1024
MAX_ADD = 2000
MAX_RUNS = 500
SHOW_RUNS = 15
FACT = re.compile(r"^([a-z][a-z0-9_]{0,29})=(.{1,200})$")
FACT_LINE = re.compile(rb"KOTL FACT: ([a-z][a-z0-9_]{0,29})=([^\r\n]{1,200})")
MAX_FACTS = 30
# results worth a line in runs.md: the run happened and finished (or hung); not cancelled/released
RECORDED = {"passed": "ok", "succeeded": "ok", "failed": "FAIL", "over_max": "FAIL", "idle": "FAIL"}

TEMPLATES = {
    "setup.md": "# {title}: setup\n\nWhat the boards' PCs have for this, and what a run needs. Nobody has written it yet:\n"
                "`kotl notes set {tool} setup.md < file` (the old page is kept in .history/).\n",
    "compatible.md": "# {title}: what works together\n\nKnown-good and known-bad combinations. Nobody has written it "
                     "yet: `kotl notes set {tool} compatible.md < file`. The latest runs are in runs.md.\n",
    "runs.md": "# {title}: runs\n\nAdded by Kotl when a run ends (newest last): ok/FAIL, date, job, who, board, time, "
               "result, then what the run reported (versions, config, workload) and its command.\n\n",
    "notes.md": "# {title}: notes\n\nFree notes, dated and signed: `kotl notes add {tool} \"text\"`.\n\n",
}


class NotesError(Exception):
    """A notes request that can't be done; the message says why."""


def clean(text, limit):
    """Printable text only (newlines and tabs kept), cut at limit."""
    text = "".join(ch for ch in text if ch in "\n\t" or (ch.isprintable()))
    return text[:limit]


class Notes:
    def __init__(self, root, adapters=(), clock=time.time):
        self.root = root
        self.adapters = list(adapters)
        self.clock = clock

    # --- layout
    def tools(self):
        return [GENERAL] + [a.name for a in self.adapters]

    def pages(self, tool):
        return GENERAL_PAGES if tool == GENERAL else TOOL_PAGES

    def adapter(self, tool):
        return next((a for a in self.adapters if a.name == tool), None)

    def check_tool(self, tool):
        if tool not in self.tools():
            raise NotesError(f"no notes for '{tool}' (there are: {', '.join(self.tools())})")

    def check_page(self, tool, page):
        self.check_tool(tool)
        if page not in self.pages(tool):
            raise NotesError(f"{tool} has no page '{page}' (it has: {', '.join(self.pages(tool))})")

    def path(self, tool=None, page=None):
        parts = [self.root] + ([tool] if tool else []) + ([page] if page else [])
        return os.path.join(*parts)

    def stamp(self):
        return time.strftime("%Y-%m-%d %H:%M", time.localtime(self.clock()))

    def _write(self, path, text):
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(text)
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)

    def _append(self, path, text):
        with open(path, "a", encoding="utf-8") as f:
            f.write(text)
        os.chmod(path, 0o644)

    def ensure(self):
        """Every folder and page exists (pages an adapter seeds start from its text), and INDEX.md."""
        os.makedirs(self.root, exist_ok=True)
        os.chmod(self.root, 0o755)
        for tool in self.tools():
            d = self.path(tool)
            os.makedirs(d, exist_ok=True)
            os.chmod(d, 0o755)
            seeds = getattr(self.adapter(tool), "notes_seed", None) or {}
            title = "Kotl" if tool == GENERAL else (getattr(self.adapter(tool), "title", "") or tool)
            for page in self.pages(tool):
                p = self.path(tool, page)
                if not os.path.exists(p):
                    self._write(p, seeds.get(page) or TEMPLATES[page].format(title=title, tool=tool))
        self.write_index()

    # --- reading
    def last_run(self, tool, ok=True):
        try:
            with open(self.path(tool, "runs.md"), encoding="utf-8") as f:
                rows = [l.rstrip("\n") for l in f if l.startswith("- ")]
        except FileNotFoundError:
            return None
        want = "- ok " if ok else "- FAIL "
        return next((r for r in reversed(rows) if r.startswith(want)), None)

    def changed(self, path):
        try:
            return time.strftime("%Y-%m-%d %H:%M", time.localtime(os.path.getmtime(path)))
        except FileNotFoundError:
            return "-"

    def write_index(self):
        out = ["# Lab notes (Kotl)", "",
               "What the lab knows about running each tool on its boards. Read the tool's pages before a run;",
               "add what you learn. Kotl writes this index: don't edit it.", "",
               "    kotl notes [TOOL [PAGE]]           read (TOOL alone: every page, the latest runs)",
               "    kotl notes add TOOL \"text\"         a dated, signed line in TOOL/notes.md",
               "    kotl notes set TOOL PAGE < file    replace setup.md or compatible.md (the old one is kept)",
               "    kotl notes history TOOL            earlier versions of the curated pages", ""]
        for tool in self.tools():
            what = "Kotl itself, the boards and their PCs" if tool == GENERAL else f"the {tool} adapter"
            out += [f"## {tool}/ ({what})", ""]
            for page in self.pages(tool):
                p = self.path(tool, page)
                out.append(f"- {p} (changed {self.changed(p)})")
            if tool != GENERAL:
                good = self.last_run(tool)
                out.append(f"- last good run: {good[2:] if good else 'none recorded yet'}")
            out.append("")
        self._write(self.path(page="INDEX.md"), "\n".join(out))

    def show(self, tool=None, page=None):
        """The index, one tool's pages (the last SHOW_RUNS runs), or one page whole."""
        self.ensure()
        if not tool:
            return self.read(self.path(page="INDEX.md"))
        if page:
            self.check_page(tool, page)
            return self.read(self.path(tool, page))
        self.check_tool(tool)
        parts = []
        for pg in self.pages(tool):
            text = self.read(self.path(tool, pg))
            if pg == "runs.md":
                lines = text.splitlines()
                head = [l for l in lines if not l.startswith("- ")]
                rows = [l for l in lines if l.startswith("- ")]
                text = "\n".join(head).rstrip() + "\n\n" + (
                    (f"(the last {SHOW_RUNS} of {len(rows)}; all: kotl notes {tool} runs.md)\n" if len(rows) > SHOW_RUNS else "")
                    + "\n".join(rows[-SHOW_RUNS:]) if rows else "(no runs recorded yet)") + "\n"
            parts.append(f"===== {self.path(tool, pg)} =====\n{text.rstrip()}\n")
        return "\n".join(parts)

    @staticmethod
    def read(path):
        with open(path, encoding="utf-8") as f:
            return f.read()

    def history(self, tool):
        self.check_tool(tool)
        d = self.path(tool, ".history")
        names = sorted(os.listdir(d)) if os.path.isdir(d) else []
        if not names:
            return f"(no earlier versions of {tool}'s pages)"
        return "\n".join(os.path.join(d, n) for n in names)

    # --- writing
    def add(self, tool, who, text):
        self.ensure()
        self.check_tool(tool)
        text = clean(text, MAX_ADD).strip()
        if not text:
            raise NotesError("the note is empty")
        body = text.replace("\n", "\n  ")
        self._append(self.path(tool, "notes.md"), f"- {self.stamp()} {who}: {body}\n")
        self.write_index()

    def set(self, tool, page, who, text):
        self.ensure()
        self.check_page(tool, page)
        if page not in CURATED:
            raise NotesError(f"only {' and '.join(CURATED)} can be replaced; add to notes.md with kotl notes add")
        if len(text.encode("utf-8")) > MAX_SET:
            raise NotesError(f"too long (at most {MAX_SET // 1024} KB)")
        text = clean(text, MAX_SET)
        if not text.strip():
            raise NotesError("the new page is empty; nothing changed")
        p = self.path(tool, page)
        hd = self.path(tool, ".history")
        os.makedirs(hd, exist_ok=True)
        os.chmod(hd, 0o755)
        when = time.strftime("%Y%m%d-%H%M%S", time.localtime(self.clock()))
        old = os.path.join(hd, f"{page}.{when}.{who}")
        self._write(old, self.read(p))
        self._write(p, text if text.endswith("\n") else text + "\n")
        self.write_index()
        return old

    def record(self, tool, job, result, facts):
        """One line in tool/runs.md for a finished run. Returns the line, or None if not recorded."""
        mark = RECORDED.get(job.get("result") if result is None else result)
        if not mark or tool not in self.tools() or tool == GENERAL:
            return None
        self.ensure()
        took = int((job.get("ended") or self.clock()) - job["started"]) if job.get("started") else None
        took = f"{took // 60}m" if took is not None and took >= 60 else (f"{took}s" if took is not None else "-")
        res = result or job.get("result")
        if job.get("reason") and job["reason"] not in (res,):
            res += f" ({job['reason']})"
        cmd = " ".join((job.get("command") or "").split())
        cmd = cmd if len(cmd) <= 160 else cmd[:157] + "..."
        shown = " ".join(f"{k}={v}" for k, v in facts.items() if k != "tool")
        line = (f"- {mark} {self.stamp()} · job {job['job_id']} · {job['user']} · {job.get('board') or '-'} · "
                f"{took} · {res}" + (f" · {shown}" if shown else "") + (f" · cmd: {cmd}" if cmd else "") + "\n")
        p = self.path(tool, "runs.md")
        self._append(p, line)
        self.trim(p)
        self.write_index()
        return line

    def trim(self, p):
        with open(p, encoding="utf-8") as f:
            lines = f.readlines()
        rows = [i for i, l in enumerate(lines) if l.startswith("- ")]
        if len(rows) <= MAX_RUNS:
            return
        cut = rows[len(rows) - MAX_RUNS]
        old = [l for l in lines[:cut] if l.startswith("- ")]
        self._append(os.path.join(os.path.dirname(p), "runs-old.md"), "".join(old))
        self._write(p, "".join([l for l in lines[:cut] if not l.startswith("- ")] + lines[cut:]))


def parse_facts(text):
    """key=value lines (what an adapter's facts script prints) -> dict; odd lines are skipped."""
    out = {}
    for line in (text or "").splitlines():
        m = FACT.match(clean(line, 240).strip())
        if m and len(out) < MAX_FACTS:
            out[m.group(1)] = m.group(2).strip()
    return out


def output_facts(data):
    """'KOTL FACT: key=value' lines a command printed (bytes of output.log) -> dict."""
    out = {}
    for m in FACT_LINE.finditer(data or b""):
        if len(out) < MAX_FACTS:
            out[m.group(1).decode()] = clean(m.group(2).decode("utf-8", "replace"), 200).strip()
    return out
