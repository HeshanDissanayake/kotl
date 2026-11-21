"""Job results: /srv/kotl/out/<user>/<job>/ with status.json, output.log, launcher.log, outputs/.

Owned by kotl, mode 0700: users read their own through the launcher, which checks ownership.
"""
import io
import json
import os
import shutil
import tarfile
import time


def job_dir(out_root, user, job_id, create=False):
    d = os.path.join(out_root, user, str(job_id))
    if create:
        os.makedirs(os.path.join(d, "outputs"), mode=0o700, exist_ok=True)
        for path in (os.path.join(out_root, user), d, os.path.join(d, "outputs")):
            os.chmod(path, 0o700)   # makedirs' mode is cut by umask and skips parents
    return d


def write_status(d, status):
    tmp = os.path.join(d, ".status.json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(status, f, indent=2)
        f.write("\n")
    os.replace(tmp, os.path.join(d, "status.json"))


def read_status(d):
    try:
        with open(os.path.join(d, "status.json"), encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return None


def log(d, text):
    with open(os.path.join(d, "launcher.log"), "a", encoding="utf-8") as f:
        f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + text.rstrip() + "\n")


def tar_bytes(d, job_id):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as t:
        t.add(d, arcname=str(job_id))
    return buf.getvalue()


def purge(out_root, keep_days, now=None):
    """Delete job folders older than keep_days. Returns how many went."""
    now = now or time.time()
    gone = 0
    if not os.path.isdir(out_root):
        return 0
    for user in os.listdir(out_root):
        ud = os.path.join(out_root, user)
        if not os.path.isdir(ud):
            continue
        for job in os.listdir(ud):
            jd = os.path.join(ud, job)
            if os.path.isdir(jd) and now - os.path.getmtime(jd) > keep_days * 86400:
                shutil.rmtree(jd, ignore_errors=True)
                gone += 1
    return gone
