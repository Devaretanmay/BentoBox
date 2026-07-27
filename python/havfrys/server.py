"""HAVFRYS FastMCP Server — session-oriented API for AI coding agents.

The server exposes a minimal set of tools:

  1. execute           — one-shot goal execution (plan → run → verify → apply)
  2. create_session    — allocate an isolated context (exe | maintain)
  3. session_close     — tear down
  4. session_run       — shell command inside execution worktree
  5. session_diff      — worktree diff
  6. session_snapshot  — save named restore point
  7. session_rollback  — restore named snapshot
  8. session_apply     — patch main repository
  9. session_analyse   — inspect repository structure
  10. session_verify   — run test suite
  11. session_observe  — store a named observation
  12. session_knowledge— retrieve accumulated observations
  13. session_history  — maintenance event log

``execute`` is the primary tool for goal-based work — it creates a
session, runs the plan, applies changes on success, and tears down.
The ``session_*`` tools are for low-level access when you need to
control the session lifecycle yourself.
"""

import json
import sys
from typing import Any

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    FastMCP = None

from havfrys.installer import ensure_workspace_initialized


# ---------------------------------------------------------------------------
# Guard helpers
# ---------------------------------------------------------------------------

def _require_session(session_id: str) -> Any:
    """Look up a session by ID or raise a clear error."""
    from havfrys.session import _SESSION_INSTANCES
    session = _SESSION_INSTANCES.get(session_id)
    if not session:
        raise ValueError(
            f"No active session with ID '{session_id}'. "
            "Create one with create_session first."
        )
    return session


def _require_exe(session_id: str) -> Any:
    """Look up execution session or error."""
    session = _require_session(session_id)
    if not session.session_id.startswith("exe_"):
        raise ValueError(
            f"Session '{session_id}' is not an Execution session. "
            "Operations like run/diff/snapshot/rollback/apply require type='exe'."
        )
    return session


def _require_maintain(session_id: str) -> Any:
    """Look up maintenance session or error."""
    session = _require_session(session_id)
    if not session.session_id.startswith("maint_"):
        raise ValueError(
            f"Session '{session_id}' is not a Maintenance session. "
            "Operations like analyse/verify/history/observe require type='maintain'."
        )
    return session


# ---------------------------------------------------------------------------
# Server factory
# ---------------------------------------------------------------------------

def create_server() -> Any:
    """Create and return the HAVFRYS FastMCP server instance."""
    if FastMCP is None:
        print("MCP SDK required: pip install mcp", file=sys.stderr)
        sys.exit(1)

    mcp = FastMCP("HAVFRYS")

    # =====================================================================
    # SESSION LIFECYCLE
    # =====================================================================

    @mcp.tool(name="create_session")
    def create_session_tool(
        type: str = "exe",
        repository: str = ".",
    ) -> str:
        """Create an isolated session for safe engineering work.

        Two session types:
          - exe (execution):    isolated Git worktree. Run commands, edit
                                files, snapshot, rollback, apply.
                                Short-lived (minutes to hours).
          - maintain:           repository inspection and verification.
                                Analyse structure, run tests, observe.
                                No worktree, no side effects.
                                Can be long-lived.

        Args:
            type: Session type — "exe" or "maintain" (default "exe").
            repository: Target repository directory path (default ".").

        Returns:
            JSON with session_id, type, and context-specific details.
        """
        ensure_workspace_initialized(repository)
        from havfrys.session import create_session as factory

        session = factory(session_type=type, workdir=repository)

        resp = {
            "status": "success",
            "session_id": session.session_id,
            "type": type,
            "target_dir": session.target_dir,
        }

        if type == "exe":
            resp["worktree_path"] = session.worktree_path
            resp["branch_name"] = session.branch_name
            resp["message"] = (
                "Execution session active. Use session_run, "
                "session_snapshot, session_diff, "
                "session_rollback, session_apply, session_close."
            )
        else:
            resp["message"] = (
                "Maintenance session active. Use session_analyse, "
                "session_verify, session_observe, session_knowledge, "
                "session_history, session_close."
            )

        return json.dumps(resp, indent=2)

    @mcp.tool(name="session_close")
    def session_close_tool(session_id: str) -> str:
        """Close a session. Tears down worktree (exe) or persists state (maintain).

        Args:
            session_id: ID of the session to close.

        Returns:
            Teardown confirmation.
        """
        from havfrys.session import close_session as closer
        return closer(session_id)

    # =====================================================================
    # ONE-SHOT GOAL EXECUTION
    # =====================================================================

    @mcp.tool(name="execute")
    def execute_tool(
        goal: str,
        repository: str = ".",
    ) -> str:
        """Execute a goal end-to-end: plan → execute → verify → apply.

        The planning engine classifies the goal, generates a task graph,
        creates an isolated worktree session, runs each step
        transactionally, applies changes on success, and cleans up.

        This is the primary tool for goal-based work.  Use the
        session_* tools only when you need fine-grained control.

        Args:
            goal: What to accomplish (e.g. "Upgrade httpx to latest").
            repository: Target repository directory path (default ".").

        Returns:
            JSON with status, results per node, and apply status.
        """
        ensure_workspace_initialized(repository)
        from havfrys.planner import PlanningEngine
        engine = PlanningEngine(workdir=repository)
        result = engine.execute(goal)
        return json.dumps(result, indent=2)

    # =====================================================================
    # EXECUTION SESSION OPERATIONS
    # =====================================================================

    @mcp.tool(name="session_run")
    def session_run_tool(
        session_id: str,
        cmd: str,
    ) -> str:
        """Execute a shell command inside an execution session's isolated worktree.

        Only valid for sessions created with type='exe'.

        For intent-driven work prefer ``execute``:
        it handles planning, verification, and apply in one call.

        Args:
            session_id: Session ID from create_session.
            cmd: Shell command to execute inside the worktree.

        Returns:
            JSON with exit_code, output, error, and execution time.
        """
        session = _require_exe(session_id)
        exit_code, stdout, stderr, elapsed = session.run(cmd)
        return json.dumps({
            "status": "success" if exit_code == 0 else "failed",
            "exit_code": exit_code,
            "output": stdout,
            "error": stderr,
            "execution_time_s": round(elapsed, 2),
        }, indent=2)

    @mcp.tool(name="session_diff")
    def session_diff_tool(session_id: str) -> str:
        """Show uncommitted git diff inside an execution session's worktree."""
        session = _require_exe(session_id)
        return session.diff()

    @mcp.tool(name="session_snapshot")
    def session_snapshot_tool(session_id: str, name: str) -> str:
        """Save current worktree state as a named Git ref snapshot.
        Restorable with session_rollback.

        Only valid for sessions created with type='exe'.

        Args:
            session_id: Session ID from create_session.
            name: Label for the snapshot (e.g. "before_fix", "trial_1").

        Returns:
            Summary with saved Git ref SHA.
        """
        session = _require_exe(session_id)
        return session.snapshot(name)

    @mcp.tool(name="session_rollback")
    def session_rollback_tool(session_id: str, name: str) -> str:
        """Restore execution session worktree to a named snapshot.

        Also supports cross-session rollback via ``session_id/name``.

        Only valid for sessions created with type='exe'.

        Args:
            session_id: Session ID from create_session.
            name: Snapshot name to restore.

        Returns:
            Status summary.
        """
        session = _require_exe(session_id)
        return session.rollback(name)

    @mcp.tool(name="session_apply")
    def session_apply_tool(session_id: str) -> str:
        """Apply execution session worktree changes to the main repository.
        Runs a dry-run check first; only applies if clean.

        Only valid for sessions created with type='exe'.

        Args:
            session_id: Session ID from create_session.

        Returns:
            Status summary.
        """
        session = _require_exe(session_id)
        return session.apply()

    # =====================================================================
    # MAINTENANCE SESSION OPERATIONS
    # =====================================================================

    @mcp.tool(name="session_analyse")
    def session_analyse_tool(session_id: str) -> str:
        """Deterministic repository inspection: language, build system,
        test framework, directory structure, file count.

        Only valid for sessions created with type='maintain'.

        Args:
            session_id: Session ID from create_session.

        Returns:
            JSON with language, framework, build_system, test_framework,
            test_command, docker, is_git_repo, files_count, structure,
            subprojects.
        """
        session = _require_maintain(session_id)
        return session.analyse()

    @mcp.tool(name="session_verify")
    def session_verify_tool(session_id: str) -> str:
        """Run test suite and return structured pass/fail results.
        Discovers test command automatically from project manifests.

        Only valid for sessions created with type='maintain'.

        Args:
            session_id: Session ID from create_session.

        Returns:
            JSON with passed, summary, failures, command_used.
        """
        session = _require_maintain(session_id)
        return json.dumps(session.verify(), indent=2)

    @mcp.tool(name="session_observe")
    def session_observe_tool(session_id: str, key: str, value: str) -> str:
        """Store a named observation in the maintenance session.
        Observations accumulate across calls and are returned by
        session_knowledge.

        This is how maintenance builds a model of the repository
        over time.

        Only valid for sessions created with type='maintain'.

        Args:
            session_id: Session ID from create_session.
            key: Observation name (e.g. "dependency_count").
            value: Observation value (e.g. "42").

        Returns:
            Confirmation message.
        """
        session = _require_maintain(session_id)
        return session.observe(key, value)

    @mcp.tool(name="session_knowledge")
    def session_knowledge_tool(session_id: str) -> str:
        """Return all accumulated observations for a maintenance session.

        Only valid for sessions created with type='maintain'.

        Args:
            session_id: Session ID from create_session.

        Returns:
            JSON with session_id and observations dict.
        """
        session = _require_maintain(session_id)
        return json.dumps(session.knowledge(), indent=2)

    @mcp.tool(name="session_history")
    def session_history_tool(session_id: str) -> str:
        """Return recorded maintenance events and observations from
        persistent store.

        Only valid for sessions created with type='maintain'.

        Args:
            session_id: Session ID from create_session.

        Returns:
            JSON with historical maintenance records.
        """
        session = _require_maintain(session_id)
        return json.dumps(session.history(), indent=2)

    return mcp


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run_server(*, sse: bool = False, host: str = "0.0.0.0", port: int = 8080) -> None:
    """Start the HAVFRYS MCP server."""
    ensure_workspace_initialized(".")

    if FastMCP is None:
        print("MCP SDK required: pip install mcp", file=sys.stderr)
        sys.exit(1)

    mcp = create_server()

    if sse:
        print(f"HAVFRYS MCP server listening on http://{host}:{port}/sse", flush=True)
        mcp.run(transport="sse", host=host, port=port)
    else:
        mcp.run(transport="stdio")
