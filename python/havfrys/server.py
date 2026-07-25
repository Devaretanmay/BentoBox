"""HAVFRYS MCP Server — exposes exe and maintain over MCP."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    FastMCP = None


def create_server() -> Any:
    """Create and return the HAVFRYS FastMCP server instance."""
    if FastMCP is None:
        print("MCP SDK required: pip install mcp", file=sys.stderr)
        sys.exit(1)

    mcp = FastMCP("HAVFRYS")

    @mcp.tool()
    def exe(
        task: str,
        workdir: str = "",
    ) -> str:
        """Execute an engineering problem safely via HAVFRYS execution layer.

        Args:
            task: Engineering task or problem description in plain English or CLI command.
            workdir: Optional working directory override.

        Returns:
            JSON with execution status, outcome summary, token reduction %, and next steps.
        """
        from havfrys.core import exe as _exe
        result = _exe(task=task, workdir=workdir)
        status_text = "completed successfully" if result.status in ("success", "cached") else "failed"
        response: dict[str, Any] = {
            "status": result.status,
            "summary": f"Engineering task {status_text} in {result.execution_time_s:.2f}s.",
            "output": result.output,
            "error": result.error,
            "token_reduction_pct": result.token_reduction_pct,
        }
        return json.dumps(response, indent=2)

    @mcp.tool()
    def maintain(
        target: str = ".",
        workdir: str = "",
    ) -> str:
        """Run automated maintenance across repository dependencies, test suites, and project health.

        Args:
            target: Target workspace directory to maintain (default ".").
            workdir: Optional working directory override.

        Returns:
            JSON with maintenance execution status and outcome summary.
        """
        from havfrys.core import maintain as _maintain
        result = _maintain(target=target, workdir=workdir)
        response = {
            "status": result.status,
            "summary": f"Repository maintenance {result.status} in {result.execution_time_s:.2f}s.",
            "output": result.output,
            "error": result.error,
            "token_reduction_pct": result.token_reduction_pct,
        }
        return json.dumps(response, indent=2)

    return mcp


def run_server(*, sse: bool = False, host: str = "0.0.0.0", port: int = 8080) -> None:
    mcp = create_server()
    if sse:
        mcp.run(transport="sse", host=host, port=port)
    else:
        mcp.run(transport="stdio")


def main() -> int:
    parser = argparse.ArgumentParser(description="HAVFRYS MCP Server")
    parser.add_argument("--sse", action="store_true", help="Use SSE transport")
    parser.add_argument("--host", default="0.0.0.0", help="Host address for SSE")
    parser.add_argument("--port", type=int, default=8080, help="Port for SSE")
    args = parser.parse_args()
    run_server(sse=args.sse, host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    sys.exit(main())
