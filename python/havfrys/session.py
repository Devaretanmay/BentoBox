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
        """Execute command in the isolated worktree.

        Args:
            cmd: Shell command to execute.

        Returns:
            (exit_code, stdout, stderr, elapsed_seconds)
        """
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

        # Compress large outputs automatically (threshold ~5KB).
        should_compress = (len(proc.stdout or "") > 5120 or len(proc.stderr or "") > 5120)

        if should_compress:
            out_compressed = route_and_compress(proc.stdout) if proc.stdout else ""
            err_compressed = route_and_compress(proc.stderr) if proc.stderr else ""
        else:
            out_compressed = proc.stdout or ""
            err_compressed = proc.stderr or ""

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
                _append_global_snapshot(self.target_dir, self.session_id, name, ref_name, commit_sha)
                self.save()
                return f"Snapshot '{name}' saved to ref {ref_name} ({commit_sha[:7]})"
        return f"Failed to create snapshot '{name}'"

    def rollback(self, name: str) -> str:
        """Restore worktree to a named snapshot.

        Supports:
          - Local session snapshots (plain name)
          - Cross-session snapshots via "session_id/name" syntax
          - Automatic global index lookup if not found locally
        """
        ref = self.state.snapshots.get(name)
        if not ref:
            # Fallback: search global snapshot index
            snapshots = list_snapshots(self.target_dir)
            for snap in snapshots:
                if name == snap["name"] or name == f"{snap['session_id']}/{snap['name']}":
                    ref = snap["ref"]
                    break
        if not ref:
            return f"Error: Snapshot '{name}' not found. Use list_snapshots() to see all available."
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

        # Dry-run check first
        check_res = subprocess.run(
            ["git", "apply", "--check"],
            cwd=self.target_dir,
            input=diff_text,
            capture_output=True,
            text=True,
        )
        if check_res.returncode != 0:
            return f"Patch does not apply cleanly:\n{check_res.stderr.strip()}"

        # Apply patch
        apply_res = subprocess.run(
            ["git", "apply"],
            cwd=self.target_dir,
            input=diff_text,
            capture_output=True,
            text=True,
        )
        if apply_res.returncode == 0:
            self.state.operations.append({"type": "apply", "status": "success"})
            self.save()
            return "Successfully applied session worktree changes to main repository."
        else:
            return f"Failed to apply patch cleanly: {apply_res.stderr.strip() or 'conflict'}"

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
        # Validate that state was written successfully
        if not os.path.exists(state_file) or os.path.getsize(state_file) == 0:
            raise RuntimeError(f"Failed to persist Execution session state to {state_file}")


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

    # ------------------------------------------------------------------
    # Knowledge persistence
    # ------------------------------------------------------------------
    _OBSERVATIONS_DIR = "observations"

    def _observations_file(self) -> str:
        return os.path.join(self.session_dir, self._OBSERVATIONS_DIR, "knowledge.json")

    def observe(self, key: str, value: Any) -> str:
        """Store a named observation that persists for the session lifetime.

        Observations accumulate and are returned by ``knowledge()``.
        This is how maintenance builds a model of the repository over
        multiple calls.
        """
        obs_file = self._observations_file()
        os.makedirs(os.path.dirname(obs_file), exist_ok=True)
        data: dict[str, Any] = {}
        if os.path.exists(obs_file):
            try:
                with open(obs_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                pass
        data[key] = {"value": value, "timestamp": time.time()}
        with open(obs_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        self.state.operations.append({"type": "observe", "key": key})
        self.save()
        return f"Observation '{key}' recorded."

    def knowledge(self) -> dict[str, Any]:
        """Return all accumulated observations for this session.

        Includes both explicit observations and session metadata.
        """
        obs_file = self._observations_file()
        observations: dict[str, Any] = {}
        if os.path.exists(obs_file):
            try:
                with open(obs_file, "r", encoding="utf-8") as f:
                    observations = json.load(f)
            except Exception:
                pass
        return {
            "session_id": self.session_id,
            "observations": observations,
            "operations": len(self.state.operations),
        }

    def create_execution(self, goal: str = "") -> Any:
        """Spawn a child execution session from this maintenance session.

        The execution session uses the same target directory and can be
        used to implement fixes that maintenance discovered.  Returns
        an ``ExecutionSession`` ready for ``run()`` / ``execute()`` /
        ``snapshot()`` / ``apply()``.

        This is how maintenance orchestrates execution.
        """
        import havfrys.session as _s  # deferred to avoid circular import
        exe = _s.create_session(session_type="execution", workdir=self.target_dir)
        self.observe("spawned_execution", {
            "session_id": exe.session_id,
            "goal": goal,
        })
        return exe

    def analyse(self) -> str:
        """Deterministic repository inspection: language, build system,
        test framework, directory structure.
        """
        from .analyzer import analyse
        res = analyse(path=self.target_dir)
        return json.dumps({
            "language": res.language,
            "framework": res.framework,
            "build_system": res.build_system,
            "test_framework": res.test_framework,
            "test_command": res.test_command,
            "docker": res.docker,
            "is_git_repo": res.is_git_repo,
            "files_count": res.files_count,
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
        # Validate that state was written successfully
        if not os.path.exists(state_file) or os.path.getsize(state_file) == 0:
            raise RuntimeError(f"Failed to persist Maintenance session state to {state_file}")


# Global Snapshot Index — cross-session persistent registry
_SNAPSHOT_INDEX_FILE = os.path.join(".havfrys", "runtime", "snapshots_index.json")


def _global_snapshot_index_path(target_dir: str) -> str:
    """Path to the cross-session snapshot registry."""
    return os.path.join(os.path.abspath(target_dir), _SNAPSHOT_INDEX_FILE)


def _append_global_snapshot(
    target_dir: str,
    session_id: str,
    name: str,
    ref: str,
    commit: str,
) -> None:
    """Append a snapshot to the global registry (visible across sessions)."""
    index_file = _global_snapshot_index_path(target_dir)
    os.makedirs(os.path.dirname(index_file), exist_ok=True)
    index: list[dict[str, Any]] = []
    if os.path.exists(index_file):
        try:
            with open(index_file, "r", encoding="utf-8") as f:
                index = json.load(f)
        except Exception:
            pass
    entry = {
        "session_id": session_id,
        "name": name,
        "ref": ref,
        "commit": commit,
        "created_at": time.time(),
    }
    # Replace if same session_id/name pair exists
    for i, snap in enumerate(index):
        if snap.get("session_id") == session_id and snap.get("name") == name:
            index[i] = entry
            break
    else:
        index.append(entry)
    with open(index_file, "w", encoding="utf-8") as f:
        json.dump(index, f, indent=2)


def list_snapshots(target_dir: str = ".") -> list[dict[str, Any]]:
    """List all snapshots across all sessions from the global index.

    Args:
        target_dir: Repository root (default ".").

    Returns:
        List of {session_id, name, ref, commit, created_at} dicts.
    """
    index_file = _global_snapshot_index_path(target_dir)
    if os.path.exists(index_file):
        try:
            with open(index_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return []


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
    """Look up an existing session by ID or active session for workdir.
    Falls back to auto-creating a new session if none found (legacy path).
    """
    sid = session_id or get_active_session_id(workdir, session_type)
    if sid and sid in _SESSION_INSTANCES:
        return _SESSION_INSTANCES[sid]
    
    # Auto-create active session if none exists
    target = workdir or os.getcwd()
    if session_type == "execution":
        return ExecutionSession(workdir=target)
    else:
        return MaintenanceSession(workdir=target)


def create_session(session_type: str = "execution", workdir: str = ".") -> Any:
    """Explicitly create a new session.

    Args:
        session_type: "execution" (or "exe") for isolated Git worktree,
                      "maintenance" (or "maintain") for inspection.
        workdir: Target repository path.

    Returns:
        ExecutionSession or MaintenanceSession instance.
    """
    type_map = {
        "execution": "execution",
        "exe": "execution",
        "maintenance": "maintenance",
        "maintain": "maintenance",
    }
    resolved = type_map.get(session_type)
    if not resolved:
        raise ValueError(
            f"Unknown session type: {session_type}. "
            "Use 'execution'/'exe' or 'maintenance'/'maintain'."
        )
    target = os.path.abspath(workdir)
    if resolved == "execution":
        return ExecutionSession(workdir=target)
    else:
        return MaintenanceSession(workdir=target)


def close_session(session_id: str) -> str:
    """Close a session by ID. Tears down worktree, persists state, cleans up."""
    session = _SESSION_INSTANCES.get(session_id)
    if not session:
        return f"Error: No active session with ID '{session_id}'."
    return session.exit()
