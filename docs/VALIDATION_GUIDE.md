# Product Validation Guide: Testing Compart with Your AI Agents

This guide provides a 60-second test suite for validating Compart as the control layer for your AI agents and workflows.

---

## The 3 Validation Scenarios

```text
WITHOUT COMPART
Agent -> Tools -> OS / Credentials / Network (Unmonitored)

WITH COMPART
Agent -> COMPART (Topology, Policies, Proxy, Snapshots) -> OS (Kernel Enforced)
```

---

## 1. Test Scenario 1: CLI Coding Agent (Claude Code / Shell Agent)

Validate that an AI agent reading your repo and executing bash commands is blocked from reading `~/.ssh` or `~/.aws` credentials while executing workspace tasks cleanly.

```bash
python3 examples/validation/1_claude_code_cli_agent.py
```

### What You Observe:
- Host SSH credential access is blocked by the OS kernel.
- Workspace file modifications are tracked with BLAKE3 file diffs.

---

## 2. Test Scenario 2: Multi-Agent Workflow (LangGraph / CrewAI)

Validate multi-compartment permission routing where a Research Agent has read-only access and a Builder Agent has write access.

```bash
python3 examples/validation/2_langgraph_crewai_workflow.py
```

### What You Observe:
- Inter-compartment communication flows only along authorized edges.
- Read-only agent compartments cannot write or modify workspace files.

---

## 3. Test Scenario 3: Custom Agent & MCP Tools (Credential Proxy)

Validate in-memory secret proxying for outbound API calls without exposing raw API keys to agent code or LLM prompts.

```bash
python3 examples/validation/3_mcp_tools_and_proxy.py
```

### What You Observe:
- Local proxy intercepts `/openai` requests and injects Authorization headers in memory.
- Agent environment remains isolated from raw host secrets.

---

## The Validation Question for Testers

After running these 3 validation scenarios on your codebase, answer this single question:

> **"Would you run your agents without this?"**
