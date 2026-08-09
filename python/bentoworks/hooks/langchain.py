"""LangChain / LangGraph integration hooks.

Two entry points:

* :class:`BentoPythonREPLTool` — a drop-in replacement for ``PythonREPLTool``
  that executes the code snippet inside a kernel-enforced BentoBox
  compartment instead of ``exec()`` in the caller's process.
* :class:`BentoBoxGraphNode` — wraps any LangGraph execution node so its body
  runs inside an :class:`bentoworks.AgentBentoBox` compartment, with
  permissions drawn from node metadata or an explicit override.

``langchain`` and ``langgraph`` are optional dependencies. Every integration
here degrades gracefully: when ``langchain_core`` is importable the tool
subclasses :class:`~langchain_core.tools.BaseTool`; otherwise it still exposes
the same ``name`` / ``description`` / ``_run`` / ``_arun`` surface so agents
built against either API can use it.
"""

from __future__ import annotations

from typing import Any, Callable, Mapping, Optional, Sequence

from ..compartments import Compartment, CompartmentConfig
from ..sandbox.proxy import RouteConfig
from .base import SandboxRunner, validate_permissions

try:  # pragma: no cover - exercised only when langchain is installed
    from langchain_core.tools import BaseTool

    _HAS_BASETOOL = True
except Exception:  # pragma: no cover - import-less fallback
    BaseTool = object  # type: ignore[assignment]
    _HAS_BASETOOL = False

__all__ = [
    "BentoPythonREPLTool",
    "BentoBoxGraphNode",
]


def _tool_may_parse(query: str) -> str:
    """Strip fenced-code fences and stray ``python`` markers.

    Parameters
    ----------
    query
        Raw tool input.

    Returns
    -------
        str
            A cleaned Python code string.
    """
    text = query.strip()
    if text.startswith("```"):
        text = text.strip("`").strip("`").strip()
        if text.startswith("python"):
            text = text[len("python"):].lstrip("\n")
    return text


class BentoPythonREPLTool(BaseTool):  # type: ignore[misc]
    """A LangChain tool that runs Python inside a kernel-enforced compartment.

    Subclasses :class:`~langchain_core.tools.BaseTool` when ``langchain_core``
    is installed; otherwise it is a plain object implementing the identical
    ``name`` / ``description`` / ``_run`` / ``_arun`` surface.

    Parameters
    ----------
    workdir
        Worktree granted to the sandbox (the subprocess runs here).
    permission
        Compartment permissions used for each execution.
    timeout_s
        Per-call execution timeout in seconds.
    sandbox
        Apply the kernel sandbox (disable only for tests / debug).
    block_network
        Deny outbound network unless ``network`` is in ``permission``.
    credential_rules
        Proxy routes injecting credentials from the environment.
    sanitize_input
        Strip markdown fenced-code wrappers / ``python`` markers from input.
    """

    name: str = "bento_python_repl"
    description: str = (
        "A Python shell. Use this to execute python commands. "
        "Input should be a valid python command. If you want to see the output "
        "of a value, you should print it out with `print(...)`. "
        "Runs inside a kernel-enforced BentoBox sandbox."
    )
    sanitize_input: bool = True

    def __init__(
        self,
        workdir: str = ".",
        permission: Sequence[str] = ("fs_read", "fs_write", "fs_exec"),
        timeout_s: int = 300,
        sandbox: bool = True,
        block_network: bool = True,
        credential_rules: Optional[Sequence[RouteConfig]] = None,
        sanitize_input: bool = True,
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
        self.sanitize_input = sanitize_input

    def _run(self, query: str, run_manager: Any = None) -> str:
        """Execute ``query`` inside the sandbox and return its output.

        Parameters
        ----------
        query
            The Python code to execute.
        run_manager
            Optional LangChain callback manager (interface parity).

        Returns
        -------
        str
            Combined stdout/stderr of the sandboxed execution.
        """
        code = _tool_may_parse(query) if self.sanitize_input else query
        result = self._runner.run_code(
            code, permissions=self._permissions, timeout_s=self._timeout_s,
        )
        return result.output

    async def _arun(self, query: str, run_manager: Any = None) -> Any:
        """Asynchronous variant delegating to :meth:`_run`."""
        return self._run(query, run_manager)

    def invoke(self, *args: Any, **kwargs: Any) -> Any:
        """Runnable-compatible synchronous invocation."""
        tool_input = args[0] if args else kwargs.pop("tool_input", kwargs.get("input", ""))
        return self._run(str(tool_input))

    async def ainvoke(self, *args: Any, **kwargs: Any) -> Any:
        """Runnable-compatible asynchronous invocation."""
        tool_input = args[0] if args else kwargs.pop("tool_input", kwargs.get("input", ""))
        return self._run(str(tool_input))


class BentoBoxGraphNode:
    """Wrap a function so it runs inside a BentoBox compartment.

    Turns any callable into a LangGraph node that executes within a
    kernel-enforced :class:`bentoworks.AgentBentoBox`. The wrapped node calls
    ``fn(state, ctx)`` where ``ctx`` exposes ``workdir``, ``box_dir`` and the
    resolved compartment configuration.

    Parameters
    ----------
    fn
        Underlying graph-node function: ``fn(state, ctx) -> state_update``.
    workdir
        Worktree granted to the sandbox.
    permission
        Optional explicit compartment permissions (overrides metadata).
    sandbox
        Apply the kernel sandbox.
    block_network
        Deny outbound network.
    credential_rules
        Optional proxy credential routes.
    timeout_s
        Per-invocation timeout in seconds.
    """

    def __init__(
        self,
        fn: Callable[[dict[str, Any], Any], dict[str, Any]],
        *,
        workdir: str = ".",
        permission: Optional[Sequence[str]] = None,
        sandbox: bool = True,
        block_network: bool = True,
        credential_rules: Optional[Sequence[RouteConfig]] = None,
        timeout_s: int = 300,
    ) -> None:
        self._fn = fn
        self._permission_override = (
            None if permission is None else validate_permissions(permission)
        )
        self._runner = SandboxRunner(
            workdir=workdir,
            credential_rules=credential_rules,
            sandbox=sandbox,
            block_network=block_network,
        )
        self._timeout_s = timeout_s

    def _permissions_from(self, metadata: Optional[Mapping[str, Any]]) -> tuple[str, ...]:
        """Resolve permissions from an explicit override, then metadata."""
        if self._permission_override is not None:
            return self._permission_override
        if metadata:
            listed = metadata.get("permissions") or metadata.get("bentobox_permissions")
            if listed:
                return validate_permissions(listed)  # type: ignore[arg-type]
        return ("fs_read", "fs_write", "fs_exec")

    def as_node(
        self,
        *,
        name: str = "bento_node",
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> Callable[[dict[str, Any], Any], dict[str, Any]]:
        """Return a LangGraph-compatible node function.

        Registration-time ``metadata`` supplies the effective permission set
        when no explicit permission override was given.

        Parameters
        ----------
        name
            Node name used for diagnostics and compartment naming.
        metadata
            Graph node metadata; may carry ``permissions``.

        Returns
        -------
        Callable[[dict[str, Any], Any], dict[str, Any]]
            ``node(state, config=None) -> state_update``.
        """
        perms = self._permissions_from(metadata)
        runner = self._runner
        fn = self._fn
        timeout_s = self._timeout_s

        def node(state: dict[str, Any], config: Any = None) -> dict[str, Any]:
            """Execute ``fn`` inside a compartment, returning a state update."""
            holder: dict[str, Any] = {}

            def exploit(ctx: Any) -> dict[str, Any]:
                try:
                    holder["result"] = fn(state, ctx)
                except Exception as exc:  # noqa: BLE001 - surfaced to the graph
                    holder["error"] = str(exc)
                return dict(holder)

            box = runner._box()
            box.add(Compartment(
                name=name,
                fn=exploit,
                config=CompartmentConfig(permissions=list(perms), timeout_s=timeout_s),
            ))
            outcome = box.run(entry=name)
            payload = outcome.output.get(name, {})
            if not isinstance(payload, dict):
                payload = {}
            if "error" in payload or "error" in holder:
                return {"error": payload.get("error") or holder.get("error")}
            result = holder.get("result") or payload.get("result") or {}
            return result if isinstance(result, dict) else {"result": result}

        return node

    def attach(
        self,
        builder: Any,
        *,
        name: Optional[str] = None,
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> str:
        """Register this node on a LangGraph ``StateGraph`` builder.

        The permissions are embedded into the node ``metadata`` so they are
        available to downstream graph inspection tooling.

        Parameters
        ----------
        builder
            An instance of ``langgraph.graph.StateGraph``.
        name
            Node name (defaults to the wrapped function's ``__name__``).
        metadata
            Node metadata; ``permissions`` here drive sandbox permissions.

        Returns
        -------
        str
            The name the node was registered under.

        Raises
        ------
        TypeError
            If ``langgraph`` is not installed (``builder`` is ``None``).
        """
        if builder is None:
            raise TypeError(
                "BentoBoxGraphNode.attach requires langgraph; install it with"
                " 'pip install langgraph'."
            )
        node_name = name or getattr(self._fn, "__name__", "bento_node")
        permission_metadata = dict(metadata or {})
        permission_metadata["permissions"] = list(
            self._permissions_from(permission_metadata)
        )
        builder.add_node(
            node_name,
            self.as_node(name=node_name, metadata=permission_metadata),
            metadata=permission_metadata,
        )
        return node_name