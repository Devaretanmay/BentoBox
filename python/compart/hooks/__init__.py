"""Framework integration hooks for Compart.

This package lets AI agents from Category A (coding assistants) and
Category C (data / RAG agents) run their code inside kernel-enforced
:class:`compart.AgentCompart` compartments.

Hooks are intentionally dependency-light: each framework (LangChain,
LangGraph, CrewAI, AutoGen) is an optional import, and every hook degrades to a
plain duck-typed object when the framework is absent. The only hard
dependency is the Compart runtime itself.

Available hooks:

* :mod:`compart.hooks.langchain` : ``CompartPythonREPLTool``, ``CompartGraphNode``
* :mod:`compart.hooks.crewai` : ``CompartCodeInterpreterTool``, ``CrewAICodeExecutor``
* :mod:`compart.hooks.autogen` : ``CompartCodeExecutor`` (+ ``CodeBlock`` / ``CodeResult``)
* :mod:`compart.hooks.data_agent` : ``DataScienceSandboxHook``, ``DataSandboxConfig``
"""

from __future__ import annotations

from .base import (
    DEFAULT_PERMISSIONS,
    VALID_PERMISSIONS,
    ExecutionResult,
    SandboxRunner,
    diff_trees,
    index_workdir,
    validate_permissions,
)
from .langchain import CompartGraphNode, CompartPythonREPLTool
from .crewai import CompartCodeInterpreterTool, CrewAICodeExecutor
from .autogen import CompartCodeExecutor, CodeBlock, CodeResult
from .data_agent import DataSandboxConfig, DataScienceSandboxHook

__all__ = [
    "VALID_PERMISSIONS",
    "DEFAULT_PERMISSIONS",
    "ExecutionResult",
    "SandboxRunner",
    "validate_permissions",
    "index_workdir",
    "diff_trees",
    "CompartPythonREPLTool",
    "CompartGraphNode",
    "CompartCodeInterpreterTool",
    "CrewAICodeExecutor",
    "CompartCodeExecutor",
    "CodeBlock",
    "CodeResult",
    "DataScienceSandboxHook",
    "DataSandboxConfig",
]