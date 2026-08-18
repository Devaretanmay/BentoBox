"""compart._exec_shim — entry point called by workspace shim scripts.

Usage (from a .compart/bin/<agent> shim):
    python3 -m compart._exec_shim <agent_name> <workspace_root> [argv...]
"""

import sys
from compart.cli.main import cmd_exec_shim


class _Args:
    def __init__(self, argv):
        self.shim_args = argv


if __name__ == "__main__":
    cmd_exec_shim(_Args(sys.argv[1:]))
