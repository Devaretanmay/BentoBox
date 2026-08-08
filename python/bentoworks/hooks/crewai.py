"""CrewAI code-execution hook.

Provides a :class:`BentoBoxCodeInterpreterTool` that plugs into CrewAI agents
in place of the Docker-based ``CodeInterpreterTool``. The agent-supplied
Python code runs inside a kernel-enforced
:class:`bentoworks.AgentBentoBox` compartment: deny-by-default filesystem,
blocked outbound network, per-execution BLAKE3 file diffs, and stdout/stderr
returned cleanly to the agent context.

CrewAI itself is an optional dependency. The tool is duck-typed against both
the ``crewai_tools.BaseTool`` and ``crewai.tools.BaseTool`` surfaces, so it
works with no CrewAI installation and can be handed to ``Agent(tools=[...])``
when CrewAI is present.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Sequence

from .base import ExecutionResult, SandboxRunner, validate_permissions
from ..sandbox.proxy import RouteConfig

try:  # pragma: no cover - exercised only when crewai-tools is installed
    from crewai_tools.tools.base_tool import BaseTool as _CrewaiBaseTool

    _HAS_CREWAI_TOOL = True
except Exception:  # pragma: no cover - duck-typed fallback
    _CrewaiBaseTool = object  # type: ignore[assignment]
    _HAS_CREWAI_TOOL = False

__all__ = [
    "BentoBoxCodeInterpreterTool",
    "CrewAICodeExecutor",
]


class BentoBoxCodeInterpreterTool(_CrewaiBaseTool):  # type: ignore[misc]
    """CrewAI-compatible tool that runs Python inside a BentoBox sandbox.

    Accepts the same inputs as ``crewai_tools.CodeInterpreterTool`` (``code``
    and optional ``libraries_used``) but executes inside a kernel-enforced
    compartment instead of a Docker container or bare host ``exec``.

    Parameters
    ----------
    workdir
        Worktree granted to the sandbox.
    permission
        Compartment permissions for executions.
    sandbox
        Apply the kernel sandbox (disable only for tests / debug).
    block_network
        Deny outbound network.
    credential_rules
        Optional proxy routes injecting credentials.
    timeout_s
        Per-execution timeout in seconds.
    """

    name: str = "bento_code_interpreter"
    description: str = (
        "Execute Python code in an isolated, kernel-enforced sandbox. "
        "Input should be the code to run as a string (param 'code'). "
        "Optionally pass 'libraries_used' as a list of pip package names. "
        "Returns stdout and stderr of the execution."
    )

    def __init__(
        self,
        workdir: str = ".",
        permission: Sequence[str] = ("fs_read", "fs_write", "fs_exec"),
        sandbox: bool = True,
        block_network: bool = True,
        credential_rules: Optional[Sequence[RouteConfig]] = None,
        timeout_s: int = 300,
    ) -> None:
        super().__init__()
        self._runner = SandboxRunner(
            workdir=workdir,
            credential_rules=credential_rules,
            sandbox=sandbox,
            block_network=block_network,
        )
        self._permissions = validate_permissions(permission)
        self._timeout_s = timeout_s

    def _run(
        self,
        code: str,
        libraries_used: Optional[list[str]] = None,
        **kwargs: Any,
    ) -> str:
        """Execute ``code`` in the sandbox and return its output.

        Parameters
        ----------
        code
            Python source to execute.
        libraries_used
            Optional list of pip packages to pre-install before running.
        **kwargs
            Ignored extra arguments (CrewAI tool-call surface).

        Returns
        -------
        str
            Combined stdout/stderr, or a ``ERROR:`` line when installation or
            execution failed so the agent can react gracefully.
        """
        result = self._execute(code, libraries_used)
        if result.error is not None:
            return f"ERROR: {result.error}"
        return result.output

    def _execute(
        self,
        code: str,
        libraries_used: Optional[list[str]] = None,
    ) -> ExecutionResult:
        """Run the code with optional pre-installation of libraries."""
        if libraries_used:
            install_cmd = " ".join(f"'{p}'" for p in libraries_used)
            install = self._runner.run(
                f"python3 -m pip install --quiet {install_cmd}",
                permissions=self._permissions,
                timeout_s=self._timeout_s,
            )
            if install.returncode != 0:
                return ExecutionResult(
                    returncode=install.returncode,
                    stderr=f"library install failed: {install.stderr[:500]}",
                )
        return self._runner.run_code(code, permissions=self._permissions, timeout_s=self._timeout_s)

    def __call__(self, *args: Any, **kwargs: Any) -> str:
        """Make the tool directly callable (CrewAI/llamaindex tool contract)."""
        code = kwargs.get("code") or (args[0] if args else "")
        return self._run(str(code), kwargs.get("libraries_used"))


class CrewAICodeExecutor:
    """Imperative execution helper for CrewAI flows that want to call code directly.

    Wraps :class:`~bentoworks.hooks.base.SandboxRunner` behind a small
    ``run`` / ``execute`` surface so a Crew as a whole can execute a step
    without routing through an Agent tool.

    Parameters
    ----------
    workdir
        Worktree granted to the sandbox.
    permission
        Compartment permissions.
    sandbox
        Apply the kernel sandbox.
    block_network
        Deny outbound network.
    credential_rules
        Optional proxy routes.
    timeout_s
        Per-execution timeout.
    """

    def __init__(
        self,
        workdir: str = ".",
        permission: Sequence[str] = ("fs_read", "fs_write", "fs_exec"),
        sandbox: bool = True,
        block_network: bool = True,
        credential_rules: Optional[Sequence[RouteConfig]] = None,
        timeout_s: int = 300,
    ) -> None:
        self._runner = SandboxRunner(
            workdir=workdir,
            credential_rules=credential_rules,
            sandbox=sandbox,
            block_network=block_network,
        )
        self._permissions = validate_permissions(permission)
        self._timeout_s = timeout_s

    def run(self, code: str, language: str = "python") -> ExecutionResult:
        """Execute ``code`` and return an :class:`ExecutionResult`.

        Parameters
        ----------
        code
            Source to execute.
        language
            ``"python"`` or a shell language (``"bash"``/``"sh"``).

        Returns
        -------
        ExecutionResult
        """
        if language in {"bash", "shell", "sh"}:
            return self._runner.run(code, permissions=self._permissions, timeout_s=self._timeout_s)
        return self._runner.run_code(code, permissions=self._permissions, timeout_s=self._timeout_s)

    def execute(self, code: str, language: str = "python") -> Dict[str, Any]:
        """Dict-returning convenience wrapper over :meth:`run`.

        Parameters
        ----------
        code
            Source to execute.
        language
            ``"python"`` or a shell language.

        Returns
        -------
        dict[str, Any]
            :meth:`~bentoworks.hooks.base.ExecutionResult.as_dict` payload.
        """
        return self.run(code, language).as_dict()