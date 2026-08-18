# Compart v1.0.3

[![PyPI version](https://img.shields.io/pypi/v/compart.svg)](https://pypi.org/project/compart/)
[![License: ELv2](https://img.shields.io/badge/License-ELv2-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://pypi.org/project/compart/)

> **Works with your existing workflows and agents.  
> Zero configuration required. It simply layers onto your current workflow.**

Compart is the **kernel-enforced control, isolation, and provenance layer for AI coding agents and multi-agent workflows**.

```text
Claude Code ────┐
OpenCode ───────┤
Codex / Cursor ─┤
LangGraph ──────┼───► COMPART ───► OS Kernel (Seatbelt / Landlock)
CrewAI ─────────┤        │
Custom Python ──┘        ├── PTY Supervisor (Native TUI)
                         ├── Dynamic Multi-Agent Workflows
                         ├── Deny-by-Default Credential Guard
                         ├── BLAKE3 Snapshot Rollback (undo)
                         └── Git Provenance Trailers (commit)
```

---

## Why Compart?

AI agents are moving from chat interfaces into real codebases, terminals, and production pipelines. They execute code, edit files, and run shell commands you did not write and cannot predict.

Existing isolation platforms take a narrow approach:
- **Cloud VMs / MicroVMs (E2B, Daytona):** High latency (80–150ms+ boot), remote hosting, per-second cloud billing, data leaves the local machine.
- **Docker Containers:** Heavy image builds, daemon dependencies, slow cold starts, complex file mounting.
- **Interpreter Guards (`exec()` hooks):** Bypassable via C-extensions, subprocesses, or direct system calls.

**Compart gives you instant, native OS kernel-level control on your local machine with zero infrastructure.**

---

## Two Core Workflows

### 1. Interactive Coding Agents (Terminal TUI)
Run your favorite interactive coding agent inside an isolated kernel sandbox with full native TUI support (colors, alternate screen, Ctrl+C, window resizing):

```bash
cd my-project
compart init

# Launch Claude Code, OpenCode, or Codex directly:
compart claude
compart opencode
compart codex
```

When the agent finishes, review what changed or rollback instantly:
```bash
compart diff      # Inspect files created or modified by the agent
compart commit    # Commit changes to Git with verified RFC-5322 provenance trailers
compart undo      # Instantly restore files from BLAKE3 pre-execution snapshot
```

---

### 2. Custom Multi-Agent Workflows & Pipelines
Turn existing Python scripts, LangChain chains, CrewAI agents, and AutoGen loops into sandboxed, dependency-chained DAG pipelines:

```bash
# 1. Create a workflow branch
compart -w invoice-pipeline

# 2. Ingest your scripts (scans directory, auto-infers types & compartments)
compart step invoice-pipeline src/

# 3. Run the workflow DAG under kernel isolation
compart run invoice-pipeline
```

- **Topological DAG Runner:** Sequences steps and isolates each step in its designated compartment (`research`, `builder`, `network`, `tester`).
- **Cascade Skip on Failure:** If an upstream step fails, dependent steps are cleanly `SKIPPED` to prevent cascading data corruption.
- **Zero-Config Auto-Provisioning:** Standard compartments are automatically provisioned at runtime.

---

## Key Capabilities & Subsystems

| Subsystem | Guarantee | Mechanism |
| :--- | :--- | :--- |
| **OS Kernel Sandbox** | Hard OS Process Isolation | Applied natively via macOS Seatbelt / Linux Landlock. Sub-millisecond startup, deny-by-default on system paths, child processes strictly inherit boundaries. |
| **PTY Supervisor** | Full Native TUI Experience | Bridges pseudo-terminals, forwards window resize (`TIOCGWINSZ`), Ctrl+C (`SIGINT`), Ctrl+D (`EOF`), raw mode. |
| **Credential Defense** | Deny-by-Default Protection | Host SSH keys (`~/.ssh`), cloud credentials (`~/.aws`, `~/.config/gcloud`), git credentials, keychains, and browser data are blocked by default. |
| **BLAKE3 Snapshot Engine** | Physical Instant Rollback | Computes 16-byte BLAKE3 hashes across all workspace files before execution. `compart undo` restores modified/deleted files instantly. |
| **Git Provenance Engine** | Auditability & Compliance | `compart commit` automatically attaches RFC-5322 metadata trailers (`Compart-Execution`, `Compart-Agent`, `Compart-Compartment`, `Compart-Security: clean`). |
| **Credential Proxy** | Safe API Secret Routing | Rewrites requests and injects LLM API tokens (OpenAI, Anthropic) from host environment without exposing raw secrets to the agent. |
| **Token Compression** | High-Speed Output Crushing | Rust compression engines (`SmartCrusher`, `LogCompressor`, `DiffCompressor`, `TextCrusher`) optimize context before returning outputs. |

---

## Installation

Install Compart via PyPI:

```bash
pip install compart
```

*Requires Python 3.10+ on macOS (Apple Silicon / Intel) or Linux (x86_64 / aarch64).*

---

## Quickstart in 60 Seconds

```bash
# 1. Initialize your project workspace
compart init

# 2. Run an agent or ephemeral command
compart exec -- python3 -c "print('Running safely inside kernel sandbox')"

# 3. Build a multi-step pipeline
compart -w market-research
compart step market-research src/fetch_data.py --compartment research
compart step market-research src/analyze_data.py --compartment builder
compart run market-research

# 4. Review and commit
compart diff
compart commit -m "Complete market analysis"
```

---

## Python SDK Example

Integrate Compart directly into your AI application:

```python
from compart import Compart, Compartment, CompartmentConfig

compart = Compart(workdir=".")

# Add an isolated research step (read-only filesystem, network allowed)
compart.add(Compartment(
    name="researcher",
    fn=lambda ctx: print("Researching data..."),
    config=CompartmentConfig(permissions=["fs_read", "network"]),
))

# Add an isolated build step (read-write workspace, network blocked)
compart.add(Compartment(
    name="builder",
    fn=lambda ctx: print("Building application..."),
    config=CompartmentConfig(permissions=["fs_read", "fs_write", "fs_exec"]),
))

# Wire execution flow
compart.edge("researcher", "builder")

result = compart.run()
print(f"Status: {result.status}")
```

---

## Language SDKs & Bindings

| Language / SDK | Package | Status | Capabilities |
| :--- | :--- | :--- | :--- |
| **Python** | `compart` | **Live on PyPI (`v1.0.3`)** | Full CLI, Kernel Sandbox, PTY Supervisor, Snapshot Manager, Framework Hooks, Workflow Runner. |
| **TypeScript / Node.js** | `@compart/sdk` | **Upcoming NPM Release** | Native NAPI-RS bindings for permission verification, command blocklist, and snapshot management. |

---

## Documentation Map

- **[Quickstart Guide](docs/QUICKSTART.md)**: 2-minute quickstart guide for CLI and Python workflows.
- **[CLI Reference Guide](docs/CLI.md)**: Complete reference for all Compart CLI commands.
- **[Agent Execution Guide](docs/AGENT_EXECUTION.md)**: Details on PTY supervision, terminal TUI agents, and isolation boundaries.
- **[Framework Integration Hooks](docs/FRAMEWORK_HOOKS.md)**: Drop-in sandboxing for LangGraph, LangChain, CrewAI, and AutoGen.
- **[Credential Proxy & Secret Masking](docs/CREDENTIAL_PROXY.md)**: Safe API key injection and request routing.
- **[BLAKE3 Snapshots & Rollback](docs/SNAPSHOTS.md)**: Fast workspace hashing, diff tracking, and physical restoration.
- **[Output Compression & Token Crushing](docs/COMPRESSION.md)**: High-performance Rust engines for token optimization.
- **[API Reference](docs/API_REFERENCE.md)**: Python SDK classes, methods, and configuration options.
- **[Use Cases & Working Examples](docs/USE_CASES.md)**: Real-world security scenarios, prompt injection defense, and REPL sandboxing.

---

## License

Compart is licensed under the [Elastic License 2.0 (ELv2)](LICENSE).
