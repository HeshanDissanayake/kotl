"""Who on the workstation is connected to a board's PC right now: work outside Kotl.

Every SSH connection to an FPGA PC starts on the workstation, under the account of the person
who opened it, and the kernel's connection table (/proc/net/tcp, readable by everyone) names
that account. Kotl uses it to say *who* runs work on a PC outside Kotl; it never acts on it.
"""
import ipaddress
import pwd

TABLES = ("/proc/net/tcp", "/proc/net/tcp6")
ESTABLISHED = "01"


def _hex_v4(address):
    return "".join(f"{b:02X}" for b in reversed(ipaddress.IPv4Address(address).packed))


def connected_users(address, port=22, tables=TABLES, skip=("kotl", "root")):
    """{account: open connections} to address:port, from the workstation's connection table."""
    try:
        v4 = _hex_v4(address)
    except ValueError:
        return {}
    want = {f"{v4}:{port:04X}", f"0000000000000000FFFF0000{v4}:{port:04X}"}
    found = {}
    for table in tables:
        try:
            lines = open(table).read().splitlines()[1:]
        except OSError:
            continue
        for line in lines:
            f = line.split()
            if len(f) > 7 and f[2] in want and f[3] == ESTABLISHED:
                try:
                    name = pwd.getpwuid(int(f[7])).pw_name
                except (KeyError, ValueError):
                    name = f"uid {f[7]}"
                if name not in skip:
                    found[name] = found.get(name, 0) + 1
    return found


def describe(users):
    """'alice (2 connections), bob' or ''."""
    return ", ".join(u + (f" ({n} connections)" if n > 1 else "") for u, n in sorted(users.items()))


def duration(seconds):
    s = int(seconds)
    if s < 60:
        return f"{s}s"
    if s < 3600:
        return f"{s // 60}m"
    return f"{s // 3600}h {s % 3600 // 60}m"
