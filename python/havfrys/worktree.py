"""worktree() primitive — isolated git worktree lifecycle."""

import json
import os
import shutil
import subprocess
import tempfile
import time
import uuid
from dataclasses import dataclass
from typing import Optional


_WORKTREE_BASE = os.path.join(tempfile.gettempdir(), "havfrys_worktrees")
_DEFAULT_TTL = 3600  # 1 hour


@dataclass
class WorktreeResult:
    status: str = "success"
    worktree_id: str = ""
    path: str = ""
    changes_summary: str = ""
    error: Optional[str] = None
    operation_id: str = ""


@dataclass
class WorktreeListResult:
    status: str = "success"
    worktrees: list = None
    operation_id: str = ""


def _registry_path(source_dir: str) -> str:
    return os.path.join(source_dir, ".havfrys", "runtime", "registry.json")


def _load_registry(source_dir: str) -> dict:
    rp = _registry_path(source_dir)
    if os.path.exists(rp):
        try:
            return json.load(open(rp))
        except Exception:
            pass
    return {"worktrees": {}}


def _save_registry(source_dir: str, registry: dict) -> None:
    rp = _registry_path(source_dir)
    os.makedirs(os.path.dirname(rp), exist_ok=True)
    with open(rp, "w") as f:
        json.dump(registry, f, indent=2)


def _worktree_dir(wt_id: str) -> str:
    return os.path.join(_WORKTREE_BASE, wt_id)


def create(source_dir: str = ".", ttl: int = _DEFAULT_TTL) -> WorktreeResult:
    op_id = f"wt_{uuid.uuid4().hex[:8]}"
    wt_id = op_id
    source = os.path.abspath(source_dir)

    if not os.path.isdir(source):
        return WorktreeResult(
            status="error", error=f"Source directory not found: {source}", operation_id=op_id,
        )

    os.makedirs(_WORKTREE_BASE, exist_ok=True)
    wt_path = _worktree_dir(wt_id)
    is_git_worktree = False

    try:
        result = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=source, capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            branch_name = f"havfrys/{wt_id}"
            subprocess.run(
                ["git", "worktree", "add", "-b", branch_name, wt_path],
                cwd=source, capture_output=True, timeout=30, check=True,
            )
            is_git_worktree = True
    except Exception:
        pass

    if not is_git_worktree:
        try:
            shutil.copytree(
                source, wt_path,
                ignore=shutil.ignore_patterns(
                    ".git", "__pycache__", "node_modules", ".venv", "venv",
                    "target", "dist", "build",
                ),
                dirs_exist_ok=True,
            )
        except Exception as e:
            return WorktreeResult(
                status="error", error=f"Failed to create worktree: {e}", operation_id=op_id,
            )

    registry = _load_registry(source)
    registry["worktrees"][wt_id] = {
        "path": wt_path,
        "source": source,
        "created": time.time(),
        "ttl": ttl,
        "is_git_worktree": is_git_worktree,
    }
    _save_registry(source, registry)

    try:
        with open(os.path.join(wt_path, ".havfrys_source"), "w") as f:
            f.write(source)
    except Exception:
        pass

    return WorktreeResult(
        status="success",
        worktree_id=wt_id,
        path=wt_path,
        changes_summary=f"Worktree created at {wt_path}",
        operation_id=op_id,
    )


def resolve_wt(wt_id: str, source_dir: str = "") -> tuple[dict, str]:
    """Look up a worktree by ID. Tries: explicit source_dir, .havfrys_source in worktree dir, registry scan."""
    wt_path = _worktree_dir(wt_id)
    source_file = os.path.join(wt_path, ".havfrys_source")
    if os.path.exists(source_file):
        try:
            with open(source_file) as f:
                inferred_source = f.read().strip()
            registry = _load_registry(inferred_source)
            info = registry.get("worktrees", {}).get(wt_id)
            if info:
                return info, inferred_source
        except Exception:
            pass

    if source_dir:
        registry = _load_registry(source_dir)
        info = registry.get("worktrees", {}).get(wt_id)
        if info:
            return info, source_dir

    for candidate in [os.getcwd(), "."]:
        if not os.path.isdir(candidate):
            continue
        registry = _load_registry(candidate)
        info = registry.get("worktrees", {}).get(wt_id)
        if info:
            return info, os.path.abspath(candidate)

    return None, ""


def merge(wt_id: str, source_dir: str = "") -> WorktreeResult:
    op_id = f"mg_{uuid.uuid4().hex[:8]}"
    wt_info, resolved_source = resolve_wt(wt_id, source_dir)

    if not wt_info:
        return WorktreeResult(
            status="error", error=f"Worktree not found: {wt_id}", operation_id=op_id,
        )

    wt_path = wt_info["path"]
    source = resolved_source or wt_info["source"]

    if not os.path.isdir(wt_path):
        return WorktreeResult(
            status="error", error=f"Worktree path not found: {wt_path}", operation_id=op_id,
        )

    try:
        diff = subprocess.run(
            ["git", "diff", "HEAD"],
            cwd=wt_path, capture_output=True, text=True, timeout=30,
        )
        if diff.returncode != 0:
            return WorktreeResult(
                status="error", error="Failed to compute diff", operation_id=op_id,
            )
        if not diff.stdout.strip():
            summary = "No changes to merge"
            _cleanup_worktree(wt_id, source)
            return WorktreeResult(
                status="success", worktree_id=wt_id,
                changes_summary=summary, operation_id=op_id,
            )

        apply = subprocess.run(
            ["git", "apply", "--3way", "-"],
            input=diff.stdout, cwd=source,
            capture_output=True, text=True, timeout=30,
        )
        if apply.returncode != 0:
            fallback = subprocess.run(
                ["git", "apply", "--whitespace=nowarn", "-"],
                input=diff.stdout, cwd=source,
                capture_output=True, text=True, timeout=30,
            )
            if fallback.returncode != 0:
                return WorktreeResult(
                    status="error", error=f"Merge conflict: {fallback.stderr[:200]}",
                    operation_id=op_id,
                )

        numstat = subprocess.run(
            ["git", "diff", "--numstat", "HEAD"],
            cwd=wt_path, capture_output=True, text=True, timeout=10,
        )
        lines_changed = sum(
            abs(int(p[0])) + abs(int(p[1]))
            for line in numstat.stdout.strip().splitlines()
            if line and (p := line.split("\t")) and len(p) >= 2
            and p[0].isdigit() and p[1].isdigit()
        )
        summary = f"Merged: {lines_changed} lines changed"
    except Exception as e:
        return WorktreeResult(
            status="error", error=f"Merge failed: {e}", operation_id=op_id,
        )

    _cleanup_worktree(wt_id, source)
    return WorktreeResult(
        status="success", worktree_id=wt_id,
        changes_summary=summary, operation_id=op_id,
    )


def discard(wt_id: str, source_dir: str = "") -> WorktreeResult:
    op_id = f"dc_{uuid.uuid4().hex[:8]}"
    wt_info, resolved_source = resolve_wt(wt_id, source_dir)

    if not wt_info:
        return WorktreeResult(
            status="error", error=f"Worktree not found: {wt_id}", operation_id=op_id,
        )

    source = resolved_source or wt_info["source"]
    _cleanup_worktree(wt_id, source)
    return WorktreeResult(
        status="success", worktree_id=wt_id,
        changes_summary="Discarded", operation_id=op_id,
    )


def list_worktrees(source_dir: str = ".") -> WorktreeListResult:
    op_id = f"wl_{uuid.uuid4().hex[:8]}"
    source = os.path.abspath(source_dir)
    registry = _load_registry(source)

    now = time.time()
    active = []
    for wt_id, info in registry.get("worktrees", {}).items():
        age = now - info.get("created", now)
        ttl = info.get("ttl", _DEFAULT_TTL)
        expired = age > ttl
        active.append({
            "id": wt_id,
            "path": info.get("path", ""),
            "age_s": int(age),
            "expired": expired,
        })

    return WorktreeListResult(
        status="success",
        worktrees=active,
        operation_id=op_id,
    )


def _cleanup_worktree(wt_id: str, source_dir: str) -> None:
    wt_path = _worktree_dir(wt_id)

    try:
        if os.path.isdir(wt_path):
            subprocess.run(
                ["git", "worktree", "remove", "--force", wt_path],
                cwd=source_dir, capture_output=True, timeout=30,
            )
        if os.path.isdir(wt_path):
            shutil.rmtree(wt_path, ignore_errors=True)
    except Exception:
        pass

    try:
        subprocess.run(
            ["git", "branch", "-D", f"havfrys/{wt_id}"],
            cwd=source_dir, capture_output=True, timeout=5,
        )
    except Exception:
        pass

    try:
        subprocess.run(
            ["git", "worktree", "prune"],
            cwd=source_dir, capture_output=True, timeout=5,
        )
    except Exception:
        pass

    registry = _load_registry(source_dir)
    registry.get("worktrees", {}).pop(wt_id, None)
    _save_registry(source_dir, registry)


def cleanup_expired(source_dir: str = ".") -> int:
    """Remove expired worktrees. Returns count removed."""
    source = os.path.abspath(source_dir)
    registry = _load_registry(source)
    now = time.time()
    expired = [
        wt_id for wt_id, info in registry.get("worktrees", {}).items()
        if now - info.get("created", now) > info.get("ttl", _DEFAULT_TTL)
    ]
    for wt_id in expired:
        _cleanup_worktree(wt_id, source)
    return len(expired)
