"""Kotl: the lab's FPGA job manager."""
import os

__version__ = "1.0.0"

# Written by deploy/kotl/install.sh: VERSION+COMMIT of what is installed. The plugins and the VS Code
# extension carry a copy from the install that gave them to a person, so they can tell when Kotl
# was updated after that (and ask the person to run kotl setup).
BUILD_FILE = "/opt/kotl/BUILD"


def build(path=None):
    """The installed build ('1.0.0+abc1234'), or '' when there is none (a checkout, not installed)."""
    try:
        with open(path or os.environ.get("KOTL_BUILD_FILE", BUILD_FILE)) as f:
            return f.read().strip()
    except OSError:
        return ""
