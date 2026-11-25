"""Kotl's settings and paths.

Settings come from /etc/kotl/kotl.conf ("key = value" lines). Paths can be moved under a
prefix for tests; the installed launcher always uses the real ones.
"""
import os
import pwd
from dataclasses import dataclass, field

DEFAULTS = {"lockdown": "soft", "admin": "", "pc_account": "virtex-host", "idle": "30m",
            "board_type": "vcu118", "keep_days": "30", "adapters": ""}


def read_conf(path):
    conf = dict(DEFAULTS)
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.split("#", 1)[0].strip()
                if "=" in line:
                    k, v = (s.strip() for s in line.split("=", 1))
                    conf[k] = v
    except FileNotFoundError:
        pass
    return conf


@dataclass
class Config:
    prefix: str = ""
    settings: dict = field(default_factory=dict)

    def path(self, p):
        return self.prefix + p

    @property
    def conf_file(self): return self.path("/etc/kotl/kotl.conf")
    @property
    def db(self): return self.path("/var/lib/kotl/kotl.db")
    @property
    def jobs(self): return self.path("/srv/kotl/jobs")
    @property
    def out(self): return self.path("/srv/kotl/out")
    @property
    def notes(self): return self.path("/srv/kotl/notes")
    @property
    def run_dir(self): return self.path("/run/kotl")
    @property
    def status_file(self): return self.path("/run/kotl/status.json")

    def get(self, key):
        if not self.settings:
            self.settings = read_conf(self.conf_file)
        return self.settings.get(key, DEFAULTS.get(key, ""))


def caller():
    """Who asked: the sudo caller, or the account we run as (kotl, or root from the epilog)."""
    return os.environ.get("SUDO_USER") or pwd.getpwuid(os.geteuid()).pw_name


def parse_duration(text):
    """'90' (minutes), '45m', '2h', '1h30m', '1d', '30s' -> seconds. Raises ValueError."""
    import re
    t = str(text).strip().lower()
    if not t:
        raise ValueError("empty duration")
    if t.isdigit():
        return int(t) * 60
    parts = re.fullmatch(r"(?:(\d+)d)?(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?", t)
    if not parts or not any(parts.groups()):
        raise ValueError(f"can't read duration '{text}' (try 45m, 2h, 1h30m)")
    d, h, m, s = (int(x or 0) for x in parts.groups())
    return ((d * 24 + h) * 60 + m) * 60 + s


def fmt_duration(seconds):
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    h, rem = divmod(seconds, 3600)
    m = rem // 60
    return f"{h}h{m:02d}m" if h else f"{m}m"
