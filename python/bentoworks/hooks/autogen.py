"""AutoGen code-executor hook.

Implements a :class:`BentoBoxCodeExecutor` that satisfies AutoGen's
``CodeExecutor`` interface (both the synchronous ``autogen`` 0.2 API and the
async ``autogen_core`` API) while executing every code block inside a
kernel-enforced :class:`bentoworks.AgentBentoBox` compartment. This replaces
AutoGen's default ``LocalCommandLineCodeExecutor`` / Docker executor with
BentoBox isolation: deny-by-default filesystem, blocked network, and BLAKE3
file diffs surfaced back into the agent's result.

AutoGen itself is an optional dependency. :class:`CodeBlock` and
:class:`CodeResult` are lightweight data models mirroring AutoGen's shapes so
the executor is usable, and testable, with no AutoGen installation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable, List, Optional, Sequence

from .base import ExecutionResult, SandboxRunner, validate_permissions
from ..sandbox.proxy import RouteConfig

__all__ = [
    "CodeBlock",
    "CodeResult",
    "BentoBoxCodeExecutor",
]


@dataclass
class CodeBlock:
    """A single code block to execute, matching ``autogen.coding.CodeBlock``.

    Attributes
    ----------
    language
        The language this block is written in (``"python"`` or ``"bash"``).
    code
        The raw source of the block.
    """

    language: str
    code: str


@dataclass
class CodeResult:
    """Result of executing code blocks, matching ``autogen.coding.CodeResult``.

    Attributes
    ----------
    exit_code
        ``0`` on success, non-zero on failure.
    output
        Combined stdout/stderr text.
    diffs
        BLAKE3 file diffs observed across the execution.
    """

    exit_code: int = 0
    output: str = ""
    diffs: List[dict[str, str]] = field(default_factory=list)

    def __bool__(self) -> bool:
        """True when the execution succeeded."""
        return self.exit_code == 0


class BentoBoxCodeExecutor:
    """Execute AutoGen code blocks inside a BentoBox compartment.

    Parameters
    ----------
    workdir
        Worktree granted to the sandbox (code runs here).
    permission
        Permissions granted to the execution compartment.
    sandbox
        Apply the kernel sandbox (disable only for tests / debug).
    block_network
        Deny outbound network by default.
    credential_rules
        Optional proxy routes injecting credentials.
    timeout_s
        Per-execution timeout in seconds.
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

    @property
    def code_extractor(self) -> Any:
        """Return a Markdown code extractor used by AutoGen orchestration.

        The returned object exposes ``extract_code_blocks(text) -> list[CodeBlock]``,
        mirroring ``autogen.coding.MarkdownCodeExtractor``.
        """

        def extract_code_blocks(text: str, **kwargs: Any) -> List[CodeBlock]:
            pattern = r"```([a-zA-Z0-9_-]*)\n(.*?)```"
            matches = re.findall(pattern, text, re.DOTALL)
            blocks: List[CodeBlock] = []
            for lang, code in matches:
                blocks.append(CodeBlock(language=lang.strip() or "python", code=code.strip()))
            return blocks

        return type("MarkdownCodeExtractor", (), {"extract_code_blocks": staticmethod(extract_code_blocks)})()

    def run_code(self, code: str, language: str = "python") -> ExecutionResult:
        """Run a single code string in the sandbox.

        Parameters
        ----------
        code
            Source to execute.
        language
            ``"python"`` or ``"bash"``/``"sh"``.

        Returns
        -------
        ExecutionResult
        """
        if language in {"bash", "shell", "sh", "pwsh", "powershell", "ps1"}:
            return self._runner.run(code, permissions=self._permissions, timeout_s=self._timeout_s)
        return self._runner.run_code(code, language=language, permissions=self._permissions, timeout_s=self._timeout_s)

    def execute_code_blocks(
        self,
        code_blocks: Iterable[CodeBlock],
        cancellation_token: Any = None,
    ) -> CodeResult:
        """Execute a sequence of code blocks and return a result.

        Concatenates all code and runs it as a single sandboxed script so
        shared state persists across blocks within one execution.

        Parameters
        ----------
        code_blocks
            The blocks to execute, in order.
        cancellation_token
            Optional AutoGen cancellation token (set to None when absent).

        Returns
        -------
        CodeResult
        """
        segments: list[str] = []
        language: str = "python"
        for block in code_blocks if code_blocks is not None else []:
            if isinstance(block, str):
                segments.append(block)
                continue
            language = getattr(block, "language", "python") or language
            segments.append(getattr(block, "code", block))
        if not segments:
            return CodeResult(exit_code=0, output="")
        result = self.run_code("\n".join(segments), language=language)
        return CodeResult(
            exit_code=result.returncode if result.error is None else 1,
            output=result.output,
            diffs=result.diffs,
        )

    async def aexecute_code_blocks(
        self,
        code_blocks: Iterable[CodeBlock],
        cancellation_token: Any = None,
    ) -> CodeResult:
        """Async variant of :meth:`execute_code_blocks` (autogen_core API)."""
        return self.execute_code_blocks(code_blocks, cancellation_token)

    def restart(self) -> None:
        """Reset executor state (AutoGen lifecycle hook; no-op for stateless)."""