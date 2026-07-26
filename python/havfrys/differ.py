"""diff() primitive — show changes in a worktree vs source."""

import os
import subprocess
import uuid
from dataclasses import dataclass
from typing import Optional


@dataclass
class DiffResult:
    status: str = "success"
    lines_changed: int = 0
    files_changed: int = 0
    files: list = None
    summary: str = ""
    diff: str = ""
    error: Optional[str] = None
    operation_id: str = ""


def diff(worktree_id: str, path: str = "", source_dir: str = "") -> DiffResult:
    op_id = f"df_{uuid.uuid4().hex[:8]}"

    from havfrys.worktree import resolve_wt
    wt_info, _resolved = resolve_wt(worktree_id, source_dir)

    if not wt_info:
        return DiffResult(
            status="error", error=f"Worktree not found: {worktree_id}", operation_id=op_id,
        )

    wt_path = wt_info["path"]
    if not os.path.isdir(wt_path):
        return DiffResult(
            status="error", error=f"Worktree path not found: {wt_path}", operation_id=op_id,
        )

    try:
        diff_cmd = ["git", "diff", "HEAD", "--"] + ([path] if path else [])
        proc = subprocess.run(
            diff_cmd, cwd=wt_path, capture_output=True, text=True, timeout=30,
        )
        diff_out = proc.stdout or ""

        numstat = subprocess.run(
            ["git", "diff", "--numstat", "HEAD"] + ([path] if path else []),
            cwd=wt_path, capture_output=True, text=True, timeout=10,
        )
        lines_changed = 0
        files_changed = 0
        files = []
        for line in numstat.stdout.strip().splitlines():
            parts = line.split("\t")
            if len(parts) >= 2:
                files_changed += 1
                try:
                    lines_changed += int(parts[0]) + int(parts[1])
                except ValueError:
                    pass

        for line in diff_out.strip().splitlines():
            if line.startswith("diff --git"):
                fname = line.split()[-1].lstrip("b/")
                files.append(fname)

        summary = f"{files_changed} files, {lines_changed} lines changed"
        return DiffResult(
            status="success",
            lines_changed=lines_changed,
            files_changed=files_changed,
            files=files[:20],
            summary=summary,
            diff=diff_out[:2000],
            operation_id=op_id,
        )
    except Exception as e:
        return DiffResult(
            status="error", error=str(e), operation_id=op_id,
        )
