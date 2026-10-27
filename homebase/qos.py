"""The batch children the app's services start -- backtests, heat-map cells, exports, tick refreshes, research
runs -- run at the utility QoS on macOS, so they never compete with the desk, the charts and the Lab's runner,
which launchd runs Interactive (deploy/*.plist.template, ProcessType). taskpolicy's clamp is inherited by every
process the child starts (its pools too). Anywhere else (the VPS, Linux) the command is left as it is."""
from __future__ import annotations

import os
import sys

TASKPOLICY = "/usr/sbin/taskpolicy"
DARWIN = sys.platform == "darwin"


def utility(argv: list) -> list:
    """argv as a command clamped to the utility QoS. taskpolicy execs the program: the same pid (stop, kill and
    process groups work as before), the same open fds, stdout/stderr and exit code. Only for a program that is
    there and executable: a missing one is left to Popen, which raises the same OSError as before (taskpolicy
    would start, print "posix_spawn: ..." and exit 66 instead)."""
    # shortcut: a bare name (PATH lookup) is left unclamped; every caller passes an absolute python or sandbox-exec
    prog = str(argv[0]) if argv else ""
    if (DARWIN and os.access(TASKPOLICY, os.X_OK) and os.path.isabs(prog) and os.path.isfile(prog)
            and os.access(prog, os.X_OK)):
        return [TASKPOLICY, "-c", "utility", *argv]
    return list(argv)
