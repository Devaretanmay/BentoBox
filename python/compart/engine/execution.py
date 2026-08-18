"""Unified Execution domain primitive.

Every workload Compart governs — interactive agents, workflows, scripts,
MCP servers — is represented as an Execution.  The kernel does not care
which kind it is; the compartment policy is the same abstraction.

Hierarchy
---------
::

    Execution
    ├── kind: INTERACTIVE   claude / codex / opencode (PTY-attached)
    ├── kind: WORKFLOW      LangGraph / CrewAI / custom Python
    ├── kind: PROCESS       pytest / arbitrary shell command
    └── kind: SERVICE       MCP server / long-running daemon
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

_logger = logging.getLogger("compart.engine.execution")


class ExecutionKind:
    INTERACTIVE = "INTERACTIVE"  # Full PTY — claude, codex, opencode
    WORKFLOW = "WORKFLOW"        # Multi-step graph — LangGraph, CrewAI
    PROCESS = "PROCESS"         # One-shot process — pytest, arbitrary shell
    SERVICE = "SERVICE"         # Long-running — MCP server


class ExecutionStatus:
    CREATED = "CREATED"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    APPLIED = "APPLIED"   # change set promoted to workspace baseline
    SKIPPED = "SKIPPED"  # workflow node skipped due to failed dependency


@dataclass
class Execution:
    """First-class domain object representing one governed workload."""

    execution_id: str
    kind: str                           # ExecutionKind constant
    command: List[str]                  # argv, e.g. ["claude"] or ["pytest", "-q"]
    workspace_id: str = "default"
    compartment_id: str = "default"
    lane_id: str = "default"
    session_id: Optional[str] = None
    pid: Optional[int] = None
    status: str = ExecutionStatus.CREATED
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    returncode: Optional[int] = None
    snapshot_dir: Optional[str] = None  # pre-execution worktree snapshot (for undo/restore)
    policy: Dict[str, Any] = field(default_factory=lambda: {"permissions": ["fs_read", "fs_write", "fs_exec"]})
    events: List[Dict[str, Any]] = field(default_factory=list)
    changes: List[Dict[str, Any]] = field(default_factory=list)
    extra_env: Dict[str, str] = field(default_factory=dict)

    def emit(self, name: str, payload: Optional[Dict[str, Any]] = None) -> None:
        """Append a structured lifecycle event."""
        self.events.append({"timestamp": time.time(), "name": name, "payload": payload or {}})

    def start(self, pid: Optional[int] = None) -> None:
        self.status = ExecutionStatus.RUNNING
        self.started_at = time.time()
        self.pid = pid
        self.emit("execution.started", {"command": self.command, "pid": pid})

    def complete(self, returncode: int, changes: Optional[List[Dict[str, Any]]] = None) -> None:
        self.returncode = returncode
        self.finished_at = time.time()
        self.status = ExecutionStatus.COMPLETED if returncode == 0 else ExecutionStatus.FAILED
        if changes:
            self.changes = changes
        self.emit("execution.completed", {"returncode": returncode, "change_count": len(self.changes)})

    def apply(self) -> None:
        """Promote this execution's change set into the workspace baseline."""
        self.status = ExecutionStatus.APPLIED
        self.emit("execution.applied", {"change_count": len(self.changes)})

    def git_trailers(self) -> str:
        """Format Git trailers (RFC 5322 metadata) for this execution."""
        security_status = "clean"
        blocked_count = sum(
            1 for ev in self.events
            if "blocked" in ev.get("name", "").lower() or "denied" in ev.get("name", "").lower()
        )
        if blocked_count > 0:
            security_status = f"{blocked_count} blocked action(s)"

        lines = [
            f"Compart-Execution: {self.execution_id}",
            f"Compart-Agent: {self.agent_name}",
            f"Compart-Compartment: {self.compartment_id}",
            f"Compart-Security: {security_status}",
        ]
        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @property
    def duration_s(self) -> Optional[float]:
        if self.started_at is None:
            return None
        end = self.finished_at or time.time()
        return round(end - self.started_at, 2)

    @property
    def agent_name(self) -> str:
        """Human-readable agent name derived from the command."""
        return self.command[0] if self.command else "unknown"


class ExecutionManager:
    """Persists and retrieves Execution domain objects under .compart/executions/."""

    def __init__(self, workdir: str = ".") -> None:
        self.workdir = os.path.abspath(workdir)
        self.executions_dir = os.path.join(self.workdir, ".compart", "executions")
        os.makedirs(self.executions_dir, exist_ok=True)

    def _path(self, execution_id: str) -> str:
        # Sanitize execution_id to prevent directory traversal
        safe_id = os.path.basename(execution_id)
        if safe_id.endswith(".json"):
            safe_id = safe_id[:-5]
        return os.path.join(self.executions_dir, f"{safe_id}.json")

    def _next_id(self, prefix: str) -> str:
        """Millisecond-timestamp id, disambiguated when created in the same ms."""
        base = f"{prefix}_{int(time.time() * 1000)}"
        candidate = base
        n = 1
        while os.path.exists(self._path(candidate)):
            candidate = f"{base}_{n}"
            n += 1
        return candidate

    def create(
        self,
        kind: str,
        command: List[str],
        compartment_id: str = "default",
        lane_id: str = "default",
        policy: Optional[Dict[str, Any]] = None,
        extra_env: Optional[Dict[str, str]] = None,
    ) -> Execution:
        """Create and persist a new Execution."""
        eid = self._next_id("exec")
        exec_ = Execution(
            execution_id=eid,
            kind=kind,
            command=list(command),
            workspace_id=os.path.basename(self.workdir),
            compartment_id=compartment_id,
            lane_id=lane_id,
            policy=policy or {"permissions": ["fs_read", "fs_write", "fs_exec"]},
            extra_env=extra_env or {},
        )
        exec_.emit("execution.created", {"kind": kind, "command": command})
        self.save(exec_)
        return exec_

    def save(self, execution: Execution) -> None:
        with open(self._path(execution.execution_id), "w", encoding="utf-8") as f:
            json.dump(execution.to_dict(), f, indent=2)

    def get(self, execution_id: str) -> Optional[Execution]:
        path = self._path(execution_id)
        if not os.path.exists(path):
            return None
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            valid = Execution.__dataclass_fields__.keys()
            return Execution(**{k: v for k, v in data.items() if k in valid})
        except Exception as exc:
            _logger.warning("Failed to load execution %s: %s", execution_id, exc)
            return None

    def list_all(self, status_filter: Optional[str] = None) -> List[Execution]:
        results: List[Execution] = []
        if not os.path.exists(self.executions_dir):
            return results
        for fname in sorted(os.listdir(self.executions_dir), reverse=True):
            if not fname.endswith(".json"):
                continue
            ex = self.get(fname[:-5])
            if ex and (status_filter is None or ex.status == status_filter):
                results.append(ex)
        return results

    def list_running(self) -> List[Execution]:
        return self.list_all(status_filter=ExecutionStatus.RUNNING)
