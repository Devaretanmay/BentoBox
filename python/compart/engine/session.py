"""AgentSession Primitive & Session Management Engine.

Represents an agent execution session as a first-class object, capturing:
- Agent Identity & Task
- Compartment & Permissions
- Activity Logs (OK vs BLOCKED_BY_KERNEL vs BLOCKED_BY_POLICY)
- BLAKE3 File Diff Manifests
- Workspace Rollback
"""

from __future__ import annotations

import json
import os
import time

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional
from ..sandbox.snapshot import SnapshotManager

@dataclass
class AgentSessionAction:
    """Single activity log entry within an AgentSession."""
    timestamp: float
    action_type: str
    target: str
    status: str  # "OK", "BLOCKED_BY_KERNEL", "BLOCKED_BY_POLICY"
    details: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

@dataclass
class AgentSession:
    """First-class primitive representing an agent execution session."""
    session_id: str
    agent_name: str
    task: str
    workflow_step: str = "Execution"
    compartment_name: str = "AgentTask"
    permissions: List[str] = field(default_factory=lambda: ["fs_read", "fs_exec"])
    actions: List[Dict[str, Any]] = field(default_factory=list)
    diffs: List[Dict[str, str]] = field(default_factory=list)
    status: str = "running"  # "running", "completed", "failed", "rolled_back"
    started_at: float = field(default_factory=time.time)
    ended_at: Optional[float] = None
    returncode: int = 0
    snapshot_manifest: Optional[str] = None

    def log_action(self, action_type: str, target: str, status: str = "OK", details: str = "") -> None:
        """Record an activity event in the session log."""
        action = AgentSessionAction(
            timestamp=time.time(),
            action_type=action_type,
            target=target,
            status=status,
            details=details,
        )
        self.actions.append(action.to_dict())

    def complete(self, returncode: int = 0, diffs: Optional[List[Dict[str, str]]] = None) -> None:
        """Mark session as completed cleanly."""
        self.returncode = returncode
        self.ended_at = time.time()
        self.status = "completed" if returncode == 0 else "failed"
        if diffs is not None:
            self.diffs = diffs

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def format_ascii_view(self) -> str:
        """Render session details as a structured ASCII view."""
        duration = round((self.ended_at or time.time()) - self.started_at, 2)
        lines = [
            f"================================================================",
            f"              COMPART AGENT SESSION #{self.session_id}          ",
            f"================================================================",
            f"Agent       : {self.agent_name}",
            f"Task        : {self.task}",
            f"Workflow    : {self.workflow_step}",
            f"Compartment : {self.compartment_name}",
            f"Permissions : {self.permissions}",
            f"Status      : {self.status.upper()} (Exit code: {self.returncode})",
            f"Duration    : {duration}s",
            f"----------------------------------------------------------------",
            f"Activity Log:",
        ]

        if not self.actions:
            lines.append("  (No activity logged)")
        else:
            for act in self.actions:
                st = act.get("status", "OK")
                target = act.get("target", "")
                atype = act.get("action_type", "")
                details = act.get("details", "")
                detail_str = f": {details}" if details else ""
                lines.append(f"  [{st}] {atype} -> {target}{detail_str}")

        lines.append("----------------------------------------------------------------")
        lines.append(f"Changes ({len(self.diffs)} file(s)):")
        if not self.diffs:
            lines.append("  (No file changes detected)")
        else:
            for d in self.diffs:
                lines.append(f"  {d.get('status', 'modified').upper()}: {d.get('path', '')}")
        lines.append("================================================================")
        return "\n".join(lines)


class SessionManager:
    """Manages persistence and operations for AgentSessions under .compart/sessions/."""

    def __init__(self, workdir: str = ".") -> None:
        self.workdir = os.path.abspath(workdir)
        self.sessions_dir = os.path.join(self.workdir, ".compart", "sessions")
        os.makedirs(self.sessions_dir, exist_ok=True)

    def _session_file(self, session_id: str) -> str:
        return os.path.join(self.sessions_dir, f"{session_id}.json")

    def create_session(
        self,
        agent_name: str = "Claude Code",
        task: str = "Agent Task",
        compartment_name: str = "AgentTask",
        permissions: Optional[List[str]] = None,
    ) -> AgentSession:
        """Create and persist a new AgentSession."""
        session_id = f"sess_{int(time.time() * 1000)}"
        session = AgentSession(
            session_id=session_id,
            agent_name=agent_name,
            task=task,
            compartment_name=compartment_name,
            permissions=permissions or ["fs_read", "fs_exec"],
        )
        self.save_session(session)
        return session

    def save_session(self, session: AgentSession) -> None:
        """Save session object to JSON file."""
        filepath = self._session_file(session.session_id)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(session.to_dict(), f, indent=2)

    def get_session(self, session_id: str) -> Optional[AgentSession]:
        """Load session object by ID."""
        filepath = self._session_file(session_id)
        if not os.path.exists(filepath):
            return None
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            return AgentSession(**data)
        except Exception:
            return None

    def list_sessions(self) -> List[AgentSession]:
        """List all recorded sessions in reverse chronological order."""
        sessions: List[AgentSession] = []
        if not os.path.exists(self.sessions_dir):
            return sessions

        for filename in sorted(os.listdir(self.sessions_dir), reverse=True):
            if filename.endswith(".json"):
                sid = filename[:-5]
                sess = self.get_session(sid)
                if sess:
                    sessions.append(sess)
        return sessions

    def rollback_session(self, session_id: str) -> bool:
        """Roll back workspace using snapshot manager."""
        session = self.get_session(session_id)
        if not session:
            return False

        snap = SnapshotManager(workdir=self.workdir)
        snap.restore()
        session.status = "rolled_back"
        self.save_session(session)
        return True
