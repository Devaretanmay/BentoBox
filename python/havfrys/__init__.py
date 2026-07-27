"""HAVFRYS — Engineering infrastructure for AI coding agents.

The core abstraction is a Session — an isolated execution context.
Two session types:
  - ExecutionSession: isolated Git worktree for safe engineering work
  - MaintenanceSession: repository inspection, knowledge accumulation,
    and execution orchestration

The primary API is ``PlanningEngine.execute(goal)`` — it classifies
intent, generates a task graph, executes in an isolated worktree,
verifies results, and applies changes.  All in one call.

Quick start::

    from havfrys import PlanningEngine
    engine = PlanningEngine(workdir=".")
    result = engine.execute("Upgrade httpx to latest")
    print(result["status"])  # "success" | "failed"
    print(result["applied"])  # True | False

For low-level work (custom commands, manual snapshot/rollback)::

    from havfrys import create_session, close_session
    s = create_session("execution")
    s.run("pip install httpx --upgrade")
    s.snapshot("done")
    s.apply()
    close_session(s.session_id)
"""

from .session import (
    ExecutionSession,
    MaintenanceSession,
    get_session,
    create_session,
    close_session,
    list_snapshots,
)
from .planner import PlanningEngine, Plan, TaskNode, TaskType, Intent, classify_intent

__all__ = [
    "ExecutionSession",
    "MaintenanceSession",
    "get_session",
    "create_session",
    "close_session",
    "list_snapshots",
    "PlanningEngine",
    "Plan",
    "TaskNode",
    "TaskType",
    "Intent",
    "classify_intent",
]

__version__ = "0.6.0"
