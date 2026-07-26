"""snapshot() primitive — git-reflog-backed checkpointing."""

import json
import os
import subprocess
import time
import uuid
from dataclasses import dataclass
from typing import Optional


@dataclass
class SnapshotResult:
    status: str = "success"
    snapshot_id: str = ""
    ref: str = ""
    changes_staged: str = ""
    error: Optional[str] = None
    operation_id: str = ""


@dataclass
class SnapshotListResult:
    status: str = "success"
    snapshots: list = None
    operation_id: str = ""


_REF_PREFIX = "refs/havfrys/snapshots/"


def save(label: str = "", path: str = ".") -> SnapshotResult:
    op_id = f"sn_{uuid.uuid4().hex[:8]}"
    base = os.path.abspath(path)
    snapshot_id = label or op_id
    ref_name = f"{_REF_PREFIX}{snapshot_id}"

    if not os.path.exists(os.path.join(base, ".git")):
        try:
            subprocess.run(["git", "init"], cwd=base, capture_output=True, timeout=10)
            subprocess.run(
                ["git", "add", "-A"], cwd=base, capture_output=True, timeout=30,
            )
            subprocess.run(
                ["git", "commit", "-m", f"HAVFRYS snapshot: {snapshot_id}"],
                cwd=base, capture_output=True, timeout=30,
            )
        except Exception as e:
            return SnapshotResult(
                status="error", error=f"Git init/commit failed: {e}", operation_id=op_id,
            )

    try:
        subprocess.run(
            ["git", "add", "-A"], cwd=base, capture_output=True, timeout=30,
        )
        result = subprocess.run(
            ["git", "stash", "push", "-m", f"HAVFRYS snapshot: {snapshot_id}"],
            cwd=base, capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0 and "No local changes" not in result.stderr:
            return SnapshotResult(
                status="error", error=f"Stash failed: {result.stderr[:200]}",
                operation_id=op_id,
            )

        subprocess.run(
            ["git", "update-ref", ref_name, "HEAD"],
            cwd=base, capture_output=True, timeout=10,
        )

        subprocess.run(
            ["git", "stash", "pop"], cwd=base, capture_output=True, timeout=30,
        )
    except Exception as e:
        return SnapshotResult(
            status="error", error=f"Snapshot failed: {e}", operation_id=op_id,
        )

    return SnapshotResult(
        status="success",
        snapshot_id=snapshot_id,
        ref=ref_name,
        changes_staged=f"State saved at {ref_name}",
        operation_id=op_id,
    )


def restore(label: str, path: str = ".") -> SnapshotResult:
    op_id = f"sr_{uuid.uuid4().hex[:8]}"
    base = os.path.abspath(path)
    ref_name = f"{_REF_PREFIX}{label}" if not label.startswith("refs/") else label

    try:
        result = subprocess.run(
            ["git", "show-ref", "--verify", ref_name],
            cwd=base, capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return SnapshotResult(
                status="error", error=f"Snapshot not found: {label}", operation_id=op_id,
            )

        subprocess.run(
            ["git", "read-tree", "-m", "-u", ref_name],
            cwd=base, capture_output=True, timeout=30,
        )
        return SnapshotResult(
            status="success",
            snapshot_id=label,
            ref=ref_name,
            changes_staged=f"Restored to {ref_name}",
            operation_id=op_id,
        )
    except Exception as e:
        return SnapshotResult(
            status="error", error=f"Restore failed: {e}", operation_id=op_id,
        )


def list_snapshots(path: str = ".") -> SnapshotListResult:
    op_id = f"sl_{uuid.uuid4().hex[:8]}"
    base = os.path.abspath(path)

    try:
        result = subprocess.run(
            ["git", "for-each-ref", "--format=%(refname:short)|%(creatordate:iso8601)", _REF_PREFIX],
            cwd=base, capture_output=True, text=True, timeout=10,
        )
        snapshots = []
        for line in result.stdout.strip().splitlines():
            if "|" in line:
                refname, date = line.split("|", 1)
                snapshots.append({"ref": refname, "created": date.strip()})
        return SnapshotListResult(
            status="success", snapshots=snapshots, operation_id=op_id,
        )
    except Exception as e:
        return SnapshotListResult(
            status="success", snapshots=[], operation_id=op_id,
        )
