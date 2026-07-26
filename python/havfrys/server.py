"""HAVFRYS FastMCP Server — exposes Execution and Maintenance Environment capability tools over MCP."""

import json
import os
import sys
from typing import Any

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    FastMCP = None

from havfrys.installer import ensure_workspace_initialized


def create_server() -> Any:
    """Create and return the HAVFRYS FastMCP server instance."""
    if FastMCP is None:
        print("MCP SDK required: pip install mcp", file=sys.stderr)
        sys.exit(1)

    mcp = FastMCP("HAVFRYS")

    # =========================================================================
    # EXECUTION ENVIRONMENT (`exe.*`)
    # =========================================================================

    @mcp.tool(name="exe")
    def exe(
        repository: str = ".",
    ) -> str:
        """Create a stateful Execution Environment in an isolated Git worktree.

        Args:
            repository: Target repository directory path (default ".").

        Returns:
            JSON with session_id, worktree_path, and execution context.
        """
        ensure_workspace_initialized(repository)
        from havfrys.session import ExecutionSession
        session = ExecutionSession(workdir=repository)
        return json.dumps({
            "status": "success",
            "session_id": session.session_id,
            "worktree_path": session.worktree_path,
            "branch_name": session.branch_name,
            "message": f"Execution Environment active in worktree '{session.worktree_path}'. Use exe.run, exe.diff, exe.snapshot, exe.rollback, exe.apply, exe.exit.",
        }, indent=2)

    @mcp.tool(name="exe_run")
    def exe_run(
        cmd: str,
        session_id: str = "",
        workdir: str = "",
    ) -> str:
        """Execute a command inside the isolated session worktree with automatic output compression.

        Args:
            cmd: Shell command to execute inside worktree.
            session_id: Optional session ID (defaults to active session).
            workdir: Optional workdir path (defaults to current dir).

        Returns:
            JSON with compressed output, exit_code, and execution time.
        """
        from havfrys.session import get_session
        session = get_session(session_id=session_id, workdir=workdir, session_type="execution")
        exit_code, stdout, stderr, elapsed = session.run(cmd)
        return json.dumps({
            "status": "success" if exit_code == 0 else "failed",
            "exit_code": exit_code,
            "output": stdout,
            "error": stderr,
            "execution_time_s": round(elapsed, 2),
        }, indent=2)

    @mcp.tool(name="exe_diff")
    def exe_diff(
        session_id: str = "",
        workdir: str = "",
    ) -> str:
        """Inspect uncommitted git diff inside the isolated session worktree.

        Args:
            session_id: Optional session ID.
            workdir: Optional workdir path.

        Returns:
            Git diff string of uncommitted worktree changes.
        """
        from havfrys.session import get_session
        session = get_session(session_id=session_id, workdir=workdir, session_type="execution")
        return session.diff()

    @mcp.tool(name="exe_snapshot")
    def exe_snapshot(
        name: str,
        session_id: str = "",
        workdir: str = "",
    ) -> str:
        """Create a Git ref snapshot (refs/havfrys/snapshots/<name>) of current worktree state.

        Args:
            name: Label/name for the snapshot.
            session_id: Optional session ID.
            workdir: Optional workdir path.

        Returns:
            Summary with saved Git ref SHA.
        """
        from havfrys.session import get_session
        session = get_session(session_id=session_id, workdir=workdir, session_type="execution")
        return session.snapshot(name)

    @mcp.tool(name="exe_rollback")
    def exe_rollback(
        name: str,
        session_id: str = "",
        workdir: str = "",
    ) -> str:
        """Restore worktree to a named Git ref snapshot.

        Args:
            name: Name of snapshot to restore.
            session_id: Optional session ID.
            workdir: Optional workdir path.

        Returns:
            Status summary.
        """
        from havfrys.session import get_session
        session = get_session(session_id=session_id, workdir=workdir, session_type="execution")
        return session.rollback(name)

    @mcp.tool(name="exe_apply")
    def exe_apply(
        session_id: str = "",
        workdir: str = "",
    ) -> str:
        """Apply worktree changes to the target repository working tree.

        Args:
            session_id: Optional session ID.
            workdir: Optional workdir path.

        Returns:
            Status summary.
        """
        from havfrys.session import get_session
        session = get_session(session_id=session_id, workdir=workdir, session_type="execution")
        return session.apply()

    @mcp.tool(name="exe_exit")
    def exe_exit(
        session_id: str = "",
        workdir: str = "",
    ) -> str:
        """Tear down worktree and close the Execution Environment session.

        Args:
            session_id: Optional session ID.
            workdir: Optional workdir path.

        Returns:
            Teardown confirmation.
        """
        from havfrys.session import get_session
        session = get_session(session_id=session_id, workdir=workdir, session_type="execution")
        return session.exit()

    # =========================================================================
    # MAINTENANCE ENVIRONMENT (`maintain.*`)
    # =========================================================================

    @mcp.tool(name="maintain")
    def maintain(
        repository: str = ".",
    ) -> str:
        """Create a stateful Maintenance Environment session for repository inspection and verification.

        Args:
            repository: Target repository directory path (default ".").

        Returns:
            JSON with session_id, repository context, and summary.
        """
        ensure_workspace_initialized(repository)
        from havfrys.session import MaintenanceSession
        session = MaintenanceSession(workdir=repository)
        return json.dumps({
            "status": "success",
            "session_id": session.session_id,
            "target_dir": session.target_dir,
            "message": "Maintenance Environment active. Use maintain.analyse, maintain.verify, maintain.history, maintain.facts, maintain.exit.",
        }, indent=2)

    @mcp.tool(name="maintain_analyse")
    def maintain_analyse(
        session_id: str = "",
        repository: str = "",
    ) -> str:
        """Deterministic repository inspection (directory structure, manifests, build systems, dependency files, test configuration, language detection).

        Args:
            session_id: Optional maintenance session ID.
            repository: Optional target directory override.

        Returns:
            Project analysis report string.
        """
        from havfrys.session import get_session
        session = get_session(session_id=session_id, workdir=repository, session_type="maintenance")
        return session.analyse()

    @mcp.tool(name="maintain_verify")
    def maintain_verify(
        session_id: str = "",
        repository: str = "",
    ) -> str:
        """Run test suite and build verification checks non-destructively.

        Args:
            session_id: Optional maintenance session ID.
            repository: Optional target directory override.

        Returns:
            JSON with verification results.
        """
        from havfrys.session import get_session
        session = get_session(session_id=session_id, workdir=repository, session_type="maintenance")
        return json.dumps(session.verify(), indent=2)

    @mcp.tool(name="maintain_history")
    def maintain_history(
        session_id: str = "",
        repository: str = "",
    ) -> str:
        """Return recorded maintenance events, verification results, dependency changes, and repository observations from persistent history (.havfrys/runtime/maintenance_graph.json).

        Args:
            session_id: Optional maintenance session ID.
            repository: Optional target directory override.

        Returns:
            JSON with historical maintenance records.
        """
        from havfrys.session import get_session
        session = get_session(session_id=session_id, workdir=repository, session_type="maintenance")
        return json.dumps(session.history(), indent=2)

    @mcp.tool(name="maintain_facts")
    def maintain_facts(
        session_id: str = "",
        repository: str = "",
    ) -> str:
        """Extract deterministic runtime and repository facts (files, build systems, Docker, Git status).

        Args:
            session_id: Optional maintenance session ID.
            repository: Optional target directory override.

        Returns:
            JSON dictionary of deterministic repository facts.
        """
        from havfrys.session import get_session
        session = get_session(session_id=session_id, workdir=repository, session_type="maintenance")
        return json.dumps(session.facts(), indent=2)

    @mcp.tool(name="maintain_exit")
    def maintain_exit(
        session_id: str = "",
        repository: str = "",
    ) -> str:
        """Persist maintenance graph state and close the Maintenance Environment session.

        Args:
            session_id: Optional maintenance session ID.
            repository: Optional target directory override.

        Returns:
            Teardown confirmation.
        """
        from havfrys.session import get_session
        session = get_session(session_id=session_id, workdir=repository, session_type="maintenance")
        return session.exit()

    return mcp


def run_server(*, sse: bool = False, host: str = "0.0.0.0", port: int = 8080) -> None:
    ensure_workspace_initialized(".")
    mcp = create_server()
    if sse:
        mcp.run(transport="sse", host=host, port=port)
    else:
        mcp.run(transport="stdio")
