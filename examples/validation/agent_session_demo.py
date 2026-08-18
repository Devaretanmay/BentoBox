"""Flagship Agent Session Demo for Claude Code & CLI Agents.

Demonstrates the Agent Session experience:
- Agent Identity & Task
- Compartment & Permissions
- Activity Log (Allowed vs Blocked actions)
- File Changes & Diff Metrics
"""

import os
from compart.hooks import SandboxRunner

print("================================================================")
print("              COMPART AGENT SESSION #42                         ")
print("================================================================")
print("Agent       : Claude Code (CLI Agent)")
print("Task        : Fix authentication bug")
print("Workflow    : Research -> Build -> Test -> Review")
print("Compartment : Builder")
print("Permissions : [fs_read repo, fs_write src/, fs_exec tests, network blocked]")
print("----------------------------------------------------------------")
print("Activity Log:")

runner = SandboxRunner(workdir=".")

print("  [OK] Read auth.py")

res = runner.run("python3 -c \"open('auth.py', 'w').write('# Fixed auth bug')\"")
print(f"  [OK] Modified auth.py ({len(res.diffs)} file change detected)")

try:
    with open(os.path.expanduser("~/.ssh/id_rsa"), "r") as f:
        print("  [EXPLOIT]: SSH Key leaked!")
except Exception as exc:
    print(f"  [BLOCKED BY KERNEL] Attempted access to ~/.ssh/id_rsa: {exc}")

print("----------------------------------------------------------------")
print(f"Changes     : {res.diffs}")
print("Status      : Complete")
print("================================================================")
