"""Session & Worktree Management Layer — stateful execution and maintenance contexts.

HAVFRYS LAW: HAVFRYS owns metadata (.havfrys/runtime/sessions/), Git owns source code (worktrees & refs).
"""

import json
import os
import shutil
import subprocess
import time
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Optional


@dataclass
class SessionState:
    session_id: str
    session_type: str  # "execution" | "maintenance"
    workdir: str
    target_dir: str
    worktree_path: str
    branch_name: str
    created_at: float = field(default_factory=time.time)
    active: bool = True
    snapshots: dict[str, str] = field(default_factory=dict)  # name -> git_ref
    operations: list[dict[str, Any]] = field(default_factory=list)


class ExecutionSession:
    """Manages an isolated execution context using Git worktrees and snapshot refs."""

    def __init__(self, workdir: str = "."):
        self.target_dir = os.path.abspath(workdir or os.getcwd())
        self.session_id = f"exe_{uuid.uuid4().hex[:8]}"
        self.havfrys_dir = os.path.join(self.target_dir, ".havfrys")
        self.session_dir = os.path.join(self.havfrys_dir, "runtime", "sessions", self.session_id)
        
        os.makedirs(self.session_dir, exist_ok=True)
        self._ensure_git_repo()

        self.branch_name = f"havfrys-session-{self.session_id}"
        self.worktree_path = os.path.join(self.session_dir, "worktree")

        # Create isolated Git worktree
        self._create_worktree()

        self.state = SessionState(
            session_id=self.session_id,
            session_type="execution",
            workdir=self.target_dir,
            target_dir=self.target_dir,
            worktree_path=self.worktree_path,
            branch_name=self.branch_name,
        )
        self.save()
        _register_active_session(self.target_dir, self.session_id, "execution")
        _SESSION_INSTANCES[self.session_id] = self

    def _ensure_git_repo(self) -> None:
        if not os.path.exists(os.path.join(self.target_dir, ".git")):
            subprocess.run(["git", "init"], cwd=self.target_dir, capture_output=True, text=True)
            subprocess.run(["git", "add", "-A"], cwd=self.target_dir, capture_output=True, text=True)
            subprocess.run(
                ["git", "commit", "-m", "Initial commit by HAVFRYS"],
                cwd=self.target_dir,
                capture_output=True,
                text=True,
                env={
                    **os.environ,
                    "GIT_AUTHOR_NAME": "HAVFRYS",
                    "GIT_AUTHOR_EMAIL": "agent@havfrys.local",
                    "GIT_COMMITTER_NAME": "HAVFRYS",
                    "GIT_COMMITTER_EMAIL": "agent@havfrys.local",
                },
            )

    def _create_worktree(self) -> None:
        res = subprocess.run(
            ["git", "worktree", "add", "-b", self.branch_name, self.worktree_path, "HEAD"],
            cwd=self.target_dir,
            capture_output=True,
            text=True,
        )
        if res.returncode != 0:
            # Fallback if branch exists or detached HEAD
            res = subprocess.run(
                ["git", "worktree", "add", "--detach", self.worktree_path, "HEAD"],
                cwd=self.target_dir,
                capture_output=True,
                text=True,
            )

    def run(self, cmd: str) -> tuple[int, str, str, float]:
        """Execute command in the isolated worktree."""
        from havfrys._core import route_and_compress
        start = time.time()

        proc = subprocess.run(
            cmd,
            shell=True,
            cwd=self.worktree_path,
            capture_output=True,
            text=True,
            timeout=300,
        )
        elapsed = time.time() - start

        out_compressed = route_and_compress(proc.stdout) if proc.stdout else ""
        err_compressed = route_and_compress(proc.stderr) if proc.stderr else ""

        self.state.operations.append({
            "type": "run",
            "command": cmd,
            "exit_code": proc.returncode,
            "elapsed_s": round(elapsed, 2),
            "timestamp": time.time(),
        })
        self.save()
        return proc.returncode, out_compressed, err_compressed, elapsed

    def diff(self) -> str:
        """Return uncommitted diff in session worktree."""
        res = subprocess.run(
            ["git", "diff", "HEAD"],
            cwd=self.worktree_path,
            capture_output=True,
            text=True,
        )
        return res.stdout or "No uncommitted modifications in worktree."

    def snapshot(self, name: str) -> str:
        """Create a Git ref snapshot of current worktree state."""
        ref_name = f"refs/havfrys/snapshots/{self.session_id}/{name}"
        
        # Stage current worktree changes
        subprocess.run(["git", "add", "-A"], cwd=self.worktree_path, capture_output=True)
        res = subprocess.run(
            ["git", "write-tree"],
            cwd=self.worktree_path,
            capture_output=True,
            text=True,
        )
        tree_sha = res.stdout.strip()
        if tree_sha:
            commit_res = subprocess.run(
                ["git", "commit-tree", tree_sha, "-p", "HEAD", "-m", f"HAVFRYS Snapshot: {name}"],
                cwd=self.worktree_path,
                capture_output=True,
                text=True,
                env={
                    **os.environ,
                    "GIT_AUTHOR_NAME": "HAVFRYS",
                    "GIT_AUTHOR_EMAIL": "agent@havfrys.local",
                    "GIT_COMMITTER_NAME": "HAVFRYS",
                    "GIT_COMMITTER_EMAIL": "agent@havfrys.local",
                },
            )
            commit_sha = commit_res.stdout.strip()
            if commit_sha:
                subprocess.run(["git", "update-ref", ref_name, commit_sha], cwd=self.target_dir, capture_output=True)
                self.state.snapshots[name] = ref_name
                self.state.operations.append({"type": "snapshot", "name": name, "ref": ref_name, "commit": commit_sha})
                self.save()
                return f"Snapshot '{name}' saved to ref {ref_name} ({commit_sha[:7]})"
        return f"Failed to create snapshot '{name}'"

    def rollback(self, name: str) -> str:
        """Restore worktree to a named snapshot."""
        if name not in self.state.snapshots:
            return f"Error: Snapshot '{name}' not found. Available: {list(self.state.snapshots.keys())}"
        
        ref = self.state.snapshots[name]
        res = subprocess.run(
            ["git", "reset", "--hard", ref],
            cwd=self.worktree_path,
            capture_output=True,
            text=True,
        )
        self.state.operations.append({"type": "rollback", "name": name, "ref": ref})
        self.save()
        return f"Worktree rolled back to snapshot '{name}' ({ref})"

    def apply(self) -> str:
        """Apply worktree changes to the target repository."""
        # Stage worktree
        subprocess.run(["git", "add", "-A"], cwd=self.worktree_path, capture_output=True)
        diff_res = subprocess.run(["git", "diff", "HEAD"], cwd=self.worktree_path, capture_output=True, text=True)
        diff_text = diff_res.stdout

        if not diff_text.strip():
            return "No changes in session worktree to apply."

        # Apply diff to main target_dir
        patch_proc = subprocess.Popen(["git", "apply", "--check"], cwd=self.target_dir, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        _, err = patch_proc.communicate(input=diff_text)

        patch_apply = subprocess.Popen(["git", "apply"], cwd=self.target_dir, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        out, err = patch_apply.communicate(input=diff_text)

        if patch_apply.returncode == 0:
            self.state.operations.append({"type": "apply", "status": "success"})
            self.save()
            return "Successfully applied session worktree changes to main repository."
        else:
            return f"Failed to apply patch cleanly: {err or 'conflict'}"

    def exit(self) -> str:
        """Tear down worktree and close session."""
        self.state.active = False
        self.save()

        # Remove git worktree
        subprocess.run(["git", "worktree", "remove", "--force", self.worktree_path], cwd=self.target_dir, capture_output=True)
        subprocess.run(["git", "branch", "-D", self.branch_name], cwd=self.target_dir, capture_output=True)

        _unregister_active_session(self.target_dir, "execution")
        _SESSION_INSTANCES.pop(self.session_id, None)
        return f"Execution session '{self.session_id}' closed and worktree cleaned up."

    def save(self) -> None:
        state_file = os.path.join(self.session_dir, "state.json")
        with open(state_file, "w", encoding="utf-8") as f:
            json.dump(asdict(self.state), f, indent=2)


class MaintenanceSession:
    """Manages a stateful maintenance context for repository inspection and verification."""

    def __init__(self, workdir: str = "."):
        self.target_dir = os.path.abspath(workdir or os.getcwd())
        self.session_id = f"maint_{uuid.uuid4().hex[:8]}"
        self.havfrys_dir = os.path.join(self.target_dir, ".havfrys")
        self.session_dir = os.path.join(self.havfrys_dir, "runtime", "sessions", self.session_id)

        os.makedirs(self.session_dir, exist_ok=True)
        self.state = SessionState(
            session_id=self.session_id,
            session_type="maintenance",
            workdir=self.target_dir,
            target_dir=self.target_dir,
            worktree_path=self.target_dir,
            branch_name="main",
        )
        self.save()
        _register_active_session(self.target_dir, self.session_id, "maintenance")
        _SESSION_INSTANCES[self.session_id] = self

    def analyse(self) -> str:
        """Deterministic repository inspection: directory structure, manifests, build systems, dependency files, test configuration, language detection."""
        from .analyzer import analyse
        res = analyse(path=self.target_dir)
        return json.dumps({
            "language": res.language,
            "framework": res.framework,
            "build_system": res.build_system,
            "test_framework": res.test_framework,
            "structure": res.structure,
            "subprojects": res.subprojects,
        }, indent=2)

    def verify(self) -> dict[str, Any]:
        """Execute verification suite, return structured results (LLM determines pass/fail)."""
        from .verify import verify
        res = verify(target=self.target_dir)
        return {
            "status": res.status,
            "passed": res.passed,
            "summary": res.summary,
            "failures": res.failures,
            "command_used": res.command_used,
        }

    def history(self) -> dict[str, Any]:
        """Return recorded maintenance events, verification results, dependency changes, and repository observations from persistent history."""
        graph_file = os.path.join(self.target_dir, ".havfrys", "runtime", "maintenance_graph.json")
        if os.path.exists(graph_file):
            try:
                with open(graph_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {"nodes": [], "edges": [], "summary": "No historical maintenance graph found"}

    def facts(self) -> dict[str, Any]:
        from .context import resolve_context
        ctx = resolve_context(self.target_dir)
        return {
            "context_type": ctx.context_type,
            "files_count": ctx.files_count,
            "is_git_repo": ctx.is_git_repo,
            "has_test_suite": ctx.has_test_suite,
            "has_build_system": ctx.has_build_system,
            "is_docker": ctx.is_docker,
            "summary": ctx.summary,
        }

    def exit(self) -> str:
        self.state.active = False
        self.save()
        _unregister_active_session(self.target_dir, "maintenance")
        _SESSION_INSTANCES.pop(self.session_id, None)
        return f"Maintenance session '{self.session_id}' closed."

    def save(self) -> None:
        state_file = os.path.join(self.session_dir, "state.json")
        with open(state_file, "w", encoding="utf-8") as f:
            json.dump(asdict(self.state), f, indent=2)


# Active Session Registry Helpers
_ACTIVE_SESSIONS: dict[str, dict[str, str]] = {}
_SESSION_INSTANCES: dict[str, Any] = {}


def _register_active_session(workdir: str, session_id: str, session_type: str) -> None:
    workdir_abs = os.path.abspath(workdir)
    if workdir_abs not in _ACTIVE_SESSIONS:
        _ACTIVE_SESSIONS[workdir_abs] = {}
    _ACTIVE_SESSIONS[workdir_abs][session_type] = session_id


def _unregister_active_session(workdir: str, session_type: str) -> None:
    workdir_abs = os.path.abspath(workdir)
    if workdir_abs in _ACTIVE_SESSIONS and session_type in _ACTIVE_SESSIONS[workdir_abs]:
        del _ACTIVE_SESSIONS[workdir_abs][session_type]


def get_active_session_id(workdir: str = "", session_type: str = "execution") -> Optional[str]:
    workdir_abs = os.path.abspath(workdir or os.getcwd())
    return _ACTIVE_SESSIONS.get(workdir_abs, {}).get(session_type)


def get_session(session_id: str = "", workdir: str = "", session_type: str = "execution") -> Any:
    sid = session_id or get_active_session_id(workdir, session_type)
    if sid and sid in _SESSION_INSTANCES:
        return _SESSION_INSTANCES[sid]
    
    # Auto-create active session if none exists
    target = workdir or os.getcwd()
    if session_type == "execution":
        return ExecutionSession(workdir=target)
    else:
        return MaintenanceSession(workdir=target)
