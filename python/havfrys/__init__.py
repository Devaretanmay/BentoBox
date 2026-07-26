"""HAVFRYS — Engineering infrastructure for AI coding agents.

HAVFRYS provides two stateful environments:
  - ExecutionSession: isolated Git worktree for safe engineering work
  - MaintenanceSession: repository inspection and verification context

The LLM owns reasoning, planning, and orchestration.
HAVFRYS owns execution, isolation, persistence, observation, and verification execution.
"""

from .session import ExecutionSession, MaintenanceSession, get_session

__all__ = [
    "ExecutionSession",
    "MaintenanceSession",
    "get_session",
]

__version__ = "0.4.0"
