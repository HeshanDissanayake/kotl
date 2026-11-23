"""Board registry: one SQLite file. Boards are claimed and released atomically.

Board states: down -> idle -> busy -> draining -> maintenance (setting_up arrives with M3).
"""
import os
import sqlite3
import time

STATES = ("down", "idle", "setting_up", "busy", "draining", "maintenance")

SCHEMA = """
CREATE TABLE IF NOT EXISTS boards (
  name TEXT PRIMARY KEY, host TEXT NOT NULL, type TEXT NOT NULL,
  state TEXT NOT NULL DEFAULT 'idle', job_id INTEGER, bitstream TEXT,
  driver_version TEXT, last_healthy TEXT, power_watts REAL, warnings TEXT
);
CREATE TABLE IF NOT EXISTS jobs (
  job_id INTEGER PRIMARY KEY, user TEXT NOT NULL, mode TEXT NOT NULL, board TEXT,
  eta INTEGER, max INTEGER, idle INTEGER, started REAL, ended REAL,
  reason TEXT, result TEXT, rc INTEGER, command TEXT, pc_address TEXT
);
CREATE TABLE IF NOT EXISTS notices (
  id INTEGER PRIMARY KEY AUTOINCREMENT, user TEXT NOT NULL, at REAL NOT NULL,
  text TEXT NOT NULL, read INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS notified (
  key TEXT PRIMARY KEY, at REAL NOT NULL, value TEXT
);
"""


class RegistryError(RuntimeError):
    pass


class Registry:
    def __init__(self, path):
        self.path = path
        new = not os.path.exists(path)
        self.db = sqlite3.connect(path, timeout=30, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        cols = {r["name"] for r in self.db.execute("PRAGMA table_info(jobs)")}
        if "pc_address" not in cols:   # added in M3
            self.db.execute("ALTER TABLE jobs ADD COLUMN pc_address TEXT")
        bcols = {r["name"] for r in self.db.execute("PRAGMA table_info(boards)")}
        if "warnings" not in bcols:    # added with the first health check
            self.db.execute("ALTER TABLE boards ADD COLUMN warnings TEXT")
        if new:
            os.chmod(path, 0o600)

    # --- boards
    def add_board(self, name, host, type_, state="idle"):
        if state not in STATES:
            raise RegistryError(f"unknown state {state}")
        # a new board starts in `state`; re-adding a known one (every install does) only updates
        # its host and type, and never touches its state, job or health
        self.db.execute("INSERT INTO boards(name, host, type, state) VALUES (?,?,?,?) "
                        "ON CONFLICT(name) DO UPDATE SET host=excluded.host, type=excluded.type",
                        (name, host, type_, state))

    def boards(self):
        return [dict(r) for r in self.db.execute("SELECT * FROM boards ORDER BY name")]

    def board(self, name):
        r = self.db.execute("SELECT * FROM boards WHERE name=?", (name,)).fetchone()
        return dict(r) if r else None

    def set_state(self, name, state):
        if state not in STATES:
            raise RegistryError(f"unknown state {state}")
        if self.db.execute("UPDATE boards SET state=? WHERE name=?", (state, name)).rowcount != 1:
            raise RegistryError(f"no board {name}")

    def claim(self, job_id, type_):
        """Atomically take one idle board of this type for the job. Returns its row, or None."""
        self.db.execute("BEGIN IMMEDIATE")
        try:
            held = self.db.execute("SELECT * FROM boards WHERE job_id=?", (job_id,)).fetchone()
            if held:
                self.db.execute("COMMIT")
                return dict(held)
            row = self.db.execute("SELECT name FROM boards WHERE state='idle' AND type=? "
                                  "AND job_id IS NULL ORDER BY name LIMIT 1", (type_,)).fetchone()
            if not row:
                self.db.execute("COMMIT")
                return None
            self.db.execute("UPDATE boards SET state='busy', job_id=? WHERE name=? AND state='idle'",
                            (job_id, row["name"]))
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise
        return self.board(row["name"])

    def release(self, job_id):
        """Free whatever board the job holds. A draining board goes to maintenance, not idle."""
        self.db.execute("BEGIN IMMEDIATE")
        self.db.execute("UPDATE boards SET state = CASE state WHEN 'draining' THEN 'maintenance' "
                        "ELSE 'idle' END, job_id=NULL WHERE job_id=?", (job_id,))
        self.db.execute("COMMIT")

    def set_warnings(self, name, warnings, healthy_at=None):
        """Health check results: a list of warnings ([] = healthy); healthy_at when it answered."""
        import json
        self.db.execute("UPDATE boards SET warnings=? WHERE name=?", (json.dumps(warnings), name))
        if healthy_at is not None:
            self.db.execute("UPDATE boards SET last_healthy=? WHERE name=?",
                            (time.strftime("%Y-%m-%d %H:%M", time.localtime(healthy_at)), name))

    def warnings(self, name):
        import json
        b = self.board(name)
        return json.loads(b["warnings"]) if b and b.get("warnings") else []

    def drain(self, name):
        """Busy -> draining (freed into maintenance); idle -> maintenance at once."""
        b = self.board(name)
        if not b:
            raise RegistryError(f"no board {name}")
        self.set_state(name, "draining" if b["job_id"] else "maintenance")

    # --- notices (the notifier and the health check write; each user reads their own)
    def notify(self, user, text, at=None):
        self.db.execute("INSERT INTO notices(user, at, text) VALUES (?,?,?)", (user, at or time.time(), text))

    def notices(self, user, unread_only=False, limit=50):
        q = "SELECT * FROM notices WHERE user=?" + (" AND read=0" if unread_only else "")
        return [dict(r) for r in self.db.execute(q + " ORDER BY id DESC LIMIT ?", (user, limit))]

    def mark_read(self, user):
        self.db.execute("UPDATE notices SET read=1 WHERE user=? AND read=0", (user,))

    def once(self, key, value=None, at=None):
        """True the first time a key is seen (or when its stored value changes): 'notify once'."""
        row = self.db.execute("SELECT value FROM notified WHERE key=?", (key,)).fetchone()
        if row and (value is None or row["value"] == str(value)):
            return False
        self.db.execute("INSERT OR REPLACE INTO notified(key, at, value) VALUES (?,?,?)",
                        (key, at or time.time(), None if value is None else str(value)))
        return True

    def remembered(self, key):
        row = self.db.execute("SELECT value, at FROM notified WHERE key=?", (key,)).fetchone()
        return dict(row) if row else None

    def forget(self, key):
        self.db.execute("DELETE FROM notified WHERE key=?", (key,))

    # --- jobs
    def start_job(self, job_id, user, mode, board, eta, max_, idle, command=""):
        try:
            self.db.execute("INSERT INTO jobs(job_id,user,mode,board,eta,max,idle,started,command) "
                            "VALUES (?,?,?,?,?,?,?,?,?)",
                            (job_id, user, mode, board, eta, max_, idle, time.time(), command))
        except sqlite3.IntegrityError:
            raise RegistryError(f"job {job_id} already started") from None

    def job(self, job_id):
        r = self.db.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()
        return dict(r) if r else None

    def set_address(self, job_id, address):
        self.db.execute("UPDATE jobs SET pc_address=? WHERE job_id=?", (address, job_id))

    def set_reason(self, job_id, reason):
        """First reason wins: a guard that trips sets why, and a later cancel doesn't overwrite it."""
        self.db.execute("UPDATE jobs SET reason=? WHERE job_id=? AND reason IS NULL", (reason, job_id))

    def finish(self, job_id, result, rc):
        """Mark ended once. Returns False if it had already ended."""
        cur = self.db.execute("UPDATE jobs SET ended=?, result=?, rc=? WHERE job_id=? AND ended IS NULL",
                              (time.time(), result, rc, job_id))
        return cur.rowcount == 1

    def jobs(self, user=None, limit=20):
        q, args = "SELECT * FROM jobs", ()
        if user:
            q, args = q + " WHERE user=?", (user,)
        return [dict(r) for r in self.db.execute(q + " ORDER BY job_id DESC LIMIT ?", (*args, limit))]
