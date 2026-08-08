"""Framework integration hooks for BentoBox.

This package lets AI agents from Category A (coding assistants) and
Category C (data / RAG agents) run their code inside kernel-enforced
:class:`bentoworks.AgentBentoBox` compartments.

Hooks are intentionally dependency-light: each framework (LangChain,
LangGraph, CrewAI, AutoGen) is an optional import, and every hook degrades to a
plain duck-typed object when the framework is absent. The only hard
dependency is the BentoBox runtime itself.

Available hooks:

* :mod:`bentoworks.hooks.langchain` — ``BentoPythonREPLTool``, ``BentoBoxGraphNode``
* :mod:`bentoworks.hooks.crewai` — ``BentoBoxCodeInterpreterTool``, ``CrewAICodeExecutor``
* :mod:`bentoworks.hooks.autogen` — ``BentoBoxCodeExecutor`` (+ ``CodeBlock`` / ``CodeResult``)
* :mod:`bentoworks.hooks.data_agent` — ``DataScienceSandboxHook``, ``DataSandboxConfig``
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
from .langchain import BentoBoxGraphNode, BentoPythonREPLTool
from .crewai import BentoBoxCodeInterpreterTool, CrewAICodeExecutor
from .autogen import BentoBoxCodeExecutor, CodeBlock, CodeResult
from .data_agent import DataSandboxConfig, DataScienceSandboxHook

__all__ = [
    # base
    "VALID_PERMISSIONS",
    "DEFAULT_PERMISSIONS",
    "ExecutionResult",
    "SandboxRunner",
    "validate_permissions",
    "index_workdir",
    "diff_trees",
    # langchain / langgraph
    "BentoPythonREPLTool",
    "BentoBoxGraphNode",
    # crewai
    "BentoBoxCodeInterpreterTool",
    "CrewAICodeExecutor",
    # autogen
    "BentoBoxCodeExecutor",
    "CodeBlock",
    "CodeResult",
    # data agents
    "DataScienceSandboxHook",
    "DataSandboxConfig",
]