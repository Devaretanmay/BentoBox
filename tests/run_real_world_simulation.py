import os
import sys
import shutil
import subprocess
import tempfile
import time

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_DIR, "python"))

from compart.cli.main import (
    cmd_init, cmd_status, cmd_diff, cmd_apply, cmd_commit, cmd_undo, cmd_restore,
    _launch_agent, _resolve_real_binary, _write_shims
)
from compart.engine.execution import ExecutionManager, ExecutionKind, ExecutionStatus, Execution
from compart.config import load_config
from compart.sandbox.snapshot import SnapshotManager

print("======================================================================", flush=True)
print("     REAL-WORLD COMPART LIFECYCLE & MULTI-AGENT WORKSPACE SIMULATION   ", flush=True)
print("======================================================================", flush=True)
print(flush=True)

tmp_project = tempfile.mkdtemp(prefix="compart_demo_project_")
print(f"[1] Setting up new repository: {tmp_project}", flush=True)
subprocess.run(["git", "init", "-b", "main"], cwd=tmp_project, check=True, capture_output=True)
subprocess.run(["git", "config", "user.name", "Dev User"], cwd=tmp_project, check=True)
subprocess.run(["git", "config", "user.email", "dev@example.com"], cwd=tmp_project, check=True)

with open(os.path.join(tmp_project, "main.py"), "w") as f:
    f.write('def app():\n    return "v1.0"\n')
subprocess.run(["git", "add", "main.py"], cwd=tmp_project, check=True)
subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=tmp_project, check=True)

old_cwd = os.getcwd()
os.chdir(tmp_project)

print("\n[2] Initializing workspace (`compart init`)...", flush=True)
class EmptyArgs: pass
cmd_init(EmptyArgs())

print("\n[3] Simulating Agent 1 (Claude Code) in 'builder' compartment...", flush=True)
exec_mgr = ExecutionManager(workdir=tmp_project)

snap_claude = os.path.join(tmp_project, ".compart", "snapshots", "exec_claude_auth")
SnapshotManager(workdir=tmp_project, snapshot_dir=snap_claude).snapshot()

with open(os.path.join(tmp_project, "auth.py"), "w") as f:
    f.write('def authenticate(token):\n    return token == "secret-token"\n')

ex_claude = exec_mgr.create(
    kind=ExecutionKind.INTERACTIVE,
    command=["claude", "-p", "implement token auth"],
    compartment_id="builder",
)
ex_claude.snapshot_dir = snap_claude
ex_claude.changes = [{"path": "auth.py", "status": "added"}]
ex_claude.complete(returncode=0, changes=ex_claude.changes)
exec_mgr.save(ex_claude)
print(f"    [OK] Agent 1 completed: Execution #{ex_claude.execution_id} (1 file created)", flush=True)

print("\n[4] Simulating Agent 2 (OpenCode) in 'tester' compartment...", flush=True)
snap_opencode = os.path.join(tmp_project, ".compart", "snapshots", "exec_opencode_tests")
SnapshotManager(workdir=tmp_project, snapshot_dir=snap_opencode).snapshot()

with open(os.path.join(tmp_project, "test_auth.py"), "w") as f:
    f.write('from auth import authenticate\n\ndef test_auth():\n    assert authenticate("secret-token") is True\n    assert authenticate("wrong") is False\n')

ex_opencode = exec_mgr.create(
    kind=ExecutionKind.INTERACTIVE,
    command=["opencode", "run", "add unit tests for auth"],
    compartment_id="tester",
)
ex_opencode.snapshot_dir = snap_opencode
ex_opencode.changes = [{"path": "test_auth.py", "status": "added"}]
ex_opencode.complete(returncode=0, changes=ex_opencode.changes)
exec_mgr.save(ex_opencode)
print(f"    [OK] Agent 2 completed: Execution #{ex_opencode.execution_id} (1 test file created)", flush=True)

print("\n[5] Checking workspace status (`compart status`)...", flush=True)
cmd_status(EmptyArgs())

print("\n[6] Reviewing change sets and RFC-5322 Git Trailers (`compart diff --trailers`)...", flush=True)
class DiffArgs:
    execution = None
    unapplied = True
    trailers = True
    json = False
cmd_diff(DiffArgs())

print("\n[7] Applying and Committing both agent changes to Git (`compart commit --all`)...", flush=True)
class CommitArgs:
    message = "feat(auth): add token authentication and test suite"
    execution = None
    all = True
    force = False
try:
    cmd_commit(CommitArgs())
except SystemExit:
    pass

print("\n[8] Verifying Git commit history (`git log -n 2`):", flush=True)
log_output = subprocess.run(["git", "log", "-n", "2"], cwd=tmp_project, capture_output=True, text=True).stdout
print(log_output, flush=True)

print("[9] Simulating a rogue agent making breaking changes...", flush=True)
snap_rogue = os.path.join(tmp_project, ".compart", "snapshots", "exec_rogue_99")
SnapshotManager(workdir=tmp_project, snapshot_dir=snap_rogue).snapshot()

with open(os.path.join(tmp_project, "main.py"), "w") as f:
    f.write("# CORRUPTED: SYNTAX ERROR %%%!!!\n")
with open(os.path.join(tmp_project, "auth.py"), "w") as f:
    f.write("# DELETED AUTH LOGIC\n")

ex_rogue = exec_mgr.create(kind=ExecutionKind.PROCESS, command=["malicious_agent"], compartment_id="default")
ex_rogue.snapshot_dir = snap_rogue
ex_rogue.changes = [{"path": "main.py", "status": "modified"}, {"path": "auth.py", "status": "modified"}]
ex_rogue.complete(returncode=0, changes=ex_rogue.changes)
ex_rogue.apply()
exec_mgr.save(ex_rogue)

print(f"    -> Rogue Execution #{ex_rogue.execution_id} applied corrupted code.", flush=True)
with open(os.path.join(tmp_project, "main.py")) as f:
    print(f"    -> main.py on disk: {f.read().strip()}", flush=True)

print("\n[10] Executing `compart undo` to rollback disk files...", flush=True)
class UndoArgs:
    execution = ex_rogue.execution_id
try:
    cmd_undo(UndoArgs())
except SystemExit:
    pass

with open(os.path.join(tmp_project, "main.py")) as f:
    restored_main = f.read().strip()
with open(os.path.join(tmp_project, "auth.py")) as f:
    restored_auth = f.read().strip()

print(f"    -> main.py AFTER undo: {restored_main}", flush=True)
print(f"    -> auth.py AFTER undo: {restored_auth}", flush=True)
assert "def app():" in restored_main, "main.py failed to restore!"
assert "def authenticate" in restored_auth, "auth.py failed to restore!"

os.chdir(old_cwd)
shutil.rmtree(tmp_project, ignore_errors=True)

print("\n======================================================================", flush=True)
print("     ALL REAL-WORLD SIMULATION STEPS COMPLETED SUCCESSFULLY!          ", flush=True)
print("======================================================================", flush=True)
