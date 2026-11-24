"""kotl client-bundle: everything a user's own PC needs, as a tar on stdout.

  ssh <workstation> kotl client-bundle > kotl-client.tar && tar xf kotl-client.tar
  ./kotl-client/install.sh            (deploy/client/install.sh: plugins, extension, KOTL_SSH)

The bundle is read from /opt/kotl (published by deploy/kotl/install.sh).
"""
import io
import os
import socket
import sys
import tarfile

OPT = "/opt/kotl"
PARTS = {"plugin": "plugin", "plugin-band": "plugin-band", ".claude-plugin": ".claude-plugin",
         "kotl-status.vsix": "kotl-status.vsix", "client/install.sh": "install.sh"}


def bundle(opt=OPT, workstation=None):
    """The tar's bytes. Raises FileNotFoundError naming what /opt/kotl is missing."""
    missing = [p for p in PARTS if not os.path.exists(os.path.join(opt, p))]
    if missing:
        raise FileNotFoundError(f"{opt} lacks {', '.join(missing)}: the admin runs deploy/kotl/install.sh")
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as t:
        for src, dst in PARTS.items():
            t.add(os.path.join(opt, src), arcname=f"kotl-client/{dst}")
        name = (workstation or socket.getfqdn() or socket.gethostname()).encode() + b"\n"
        info = tarfile.TarInfo("kotl-client/workstation")
        info.size, info.mode = len(name), 0o644
        t.addfile(info, io.BytesIO(name))
    return buf.getvalue()


def main(out=None):
    out = out or sys.stdout.buffer
    if out.isatty() if hasattr(out, "isatty") else False:
        print("kotl client-bundle writes a tar: ssh <workstation> kotl client-bundle > kotl-client.tar", file=sys.stderr)
        return 2
    try:
        out.write(bundle())
    except FileNotFoundError as e:
        print(f"kotl: {e}", file=sys.stderr)
        return 1
    out.flush()
    return 0
