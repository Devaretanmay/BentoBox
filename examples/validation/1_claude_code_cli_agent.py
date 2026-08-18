"""Validation Test 1: CLI Coding Agent (e.g. Claude Code / Shell Agent) under Compart Control.

Demonstrates:
- WITHOUT COMPART: Shell command has unmonitored access to ~/.ssh and host files.
- WITH COMPART: OS kernel enforces deny-by-default on ~/.ssh while allowing worktree read/write and capturing file diffs.
"""

import os
from compart.hooks import SandboxRunner

print("=== Compart Control Layer Demo: CLI Coding Agent ===")

runner = SandboxRunner(workdir=".")

print("\n[Step 1] Agent attempts to read SSH credentials (~/.ssh/id_rsa)...")
try:
    with open(os.path.expanduser("~/.ssh/id_rsa"), "r") as f:
        print("  [EXPLOIT]: SSH Key leaked!")
except Exception as exc:
    print(f"  [BLOCKED BY KERNEL]: {exc}")

print("\n[Step 2] Agent executes safe build task in workspace...")
res = runner.run("python3 -c \"open('build_output.txt', 'w').write('Built by Agent')\"")
print(f"  Return code: {res.returncode}")
print(f"  File Diffs: {res.diffs}")
