# BLAKE3 Snapshot & Differential Rollback Guide

Compart provides fast, hash-based workspace snapshotting and differential file restoration to neutralize rogue file modifications and guarantee workspace immutability between agent turns.

---

## 1. How It Works

1. **Manifest Generation**: Before an agent or tool step executes, `SnapshotManager` scans the workspace directory (excluding build and vendor directories like `node_modules`, `.venv`, `.git`) and computes BLAKE3 hashes for every file.
2. **Execution Tracking**: The agent code runs inside its granted compartment.
3. **Differential Restoration**: `restore()` compares the post-execution workspace against the snapshot manifest:
   - Modified files are restored to their pre-run content.
   - Deleted files are recovered.
   - Newly created untrusted files are purged.

---

## 2. Python SDK Usage

```python
from compart.sandbox.snapshot import SnapshotManager

# Initialize manager for the target worktree
snap = SnapshotManager(
    workdir="/path/to/project",
    snapshot_dir="/tmp/.compart_snapshots"
)

# Take initial snapshot
file_count = snap.snapshot()
print(f"Snapshotted {file_count} files.")

# ... Execute untrusted agent steps ...

# Differential rollback
restored_count = snap.restore()
print(f"Restored {restored_count} changed file(s).")

# Clean up snapshot manifest files
snap.cleanup()
```

---

## 3. Automatic Agent Snapshotting (`AgentCompart`)

When using `AgentCompart`, snapshotting and differential file diff tracking are enabled automatically. Compartment execution results include structured diff data:

```python
from compart import AgentCompart

agent = AgentCompart(workdir=".")
result = agent.run()

# Access tracked file changes
print("Files modified during run:", result.diffs)
```
