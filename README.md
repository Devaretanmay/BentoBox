# Compart v1.0.4

[![PyPI version](https://img.shields.io/pypi/v/compart.svg)](https://pypi.org/project/compart/)
[![License: ELv2](https://img.shields.io/badge/License-ELv2-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://pypi.org/project/compart/)

> **Git manages your code. Compart manages your agents.**  
> *The agent workspace for developers. Zero configuration required.*

---

```text
                     YOUR PROJECT

             Git                 Compart
              │                     │
        Source history       Agent workspace
        Branches             Executions
        Commits              Compartments
        Diffs                Policies
                             Checkpoints
                             Workflows

                  Claude / Codex / OpenCode
                              │
                              ▼
                             OS
```

---

## Why Compart?

AI coding agents are moving from chat windows into real codebases, terminals, and production pipelines. They execute code, edit files, and run shell commands you did not write and cannot predict.

Existing approaches take the wrong abstractions:
- **Cloud VMs / MicroVMs (E2B, Daytona):** High latency, per-second cloud billing, remote hosting, data leaves your machine.
- **Docker Containers:** Heavy image builds, daemon dependencies, slow cold starts, complex file mounts.
- **Interpreter Guards (`exec()` hooks):** Bypassable via C-extensions, subprocesses, or direct system calls.

**Compart gives you instant, native OS kernel-level process isolation, execution attribution, and instant rollback on your local machine with zero infrastructure.**

---

## Two Core Workflows

### 1. Normal Coding Agents (Simple Path)

You run your favorite interactive coding agent directly inside Compart. No new framework, no manual session setup. Compart sits underneath:

```bash
cd my-project
compart init

# Launch Claude Code, OpenCode, Codex, Cursor, or Aider directly:
compart claude
compart opencode
compart codex
```

```text
create workspace
      ↓
create execution
      ↓
create compartment
      ↓
apply OS kernel boundary (Seatbelt / Landlock)
      ↓
launch real agent via raw PTY bridge
      ↓
Native Agent TUI (full color, Ctrl+C, resize)
      ↓
agent exits → capture changes → release compartment
```

When the agent finishes, review what changed or rollback instantly:
```bash
compart diff      # Review change sets attributed by agent execution
compart apply     # Promote changes to workspace baseline
compart commit    # Commit to Git with RFC-5322 metadata trailers
compart undo      # Instantly restore files from BLAKE3 pre-execution snapshot
```

---

### 2. Custom Multi-Agent Workflows (Advanced Path)

Build dependency-chained, multi-step DAG pipelines where every step runs in its own isolated compartment:

```bash
# 1. Create a workflow branch
compart -w invoice-pipeline

# 2. Add steps (point to scripts, commands, or directories)
compart step invoice-pipeline src/ocr.py --compartment research
compart step invoice-pipeline src/build.py --compartment builder
compart step invoice-pipeline "pytest tests/" --compartment tester

# 3. Execute the workflow DAG
compart --run invoice-pipeline
```

```text
                 invoice-pipeline
                        │
                        ▼
                    Extract
                 [research]  (read-only fs, network allowed)
                        │
                        ▼
                     Build
                  [builder]   (read-write fs, network restricted)
                        │
                        ▼
                     Test
                  [tester]    (read-only fs, test execution)
                        │
                        ▼
                    Review
                  [research]  (read-only fs, audit mode)
```

- **Topological DAG Runner:** Sequences steps and executes each step in its designated compartment.
- **Cascade Skip on Failure:** If an upstream step fails, dependent steps are cleanly `SKIPPED` to prevent cascading data corruption. Independent branches continue running.

---

## The Public CLI Contract

```text
Workspace
  compart init                     Initialize a Compart workspace
  compart status                   Show workspace health & active executions
  compart inspect                  Dump declared compartments & policies

Agents
  compart claude                   Run Claude Code in governed OS sandbox
  compart opencode                 Run OpenCode in governed OS sandbox
  compart codex                    Run Codex in governed OS sandbox
  compart cursor                   Run Cursor in governed OS sandbox
  compart aider                    Run Aider in governed OS sandbox
  compart exec -- <cmd>            Run arbitrary command inside a compartment

Workflows
  compart -w <name>                Create a new workflow branch
  compart step <workflow> <target> Add a step with auto-inferred properties
  compart --run <workflow>         Execute declared workflow DAG

Changes
  compart diff                     Review change sets attributed by agent
  compart apply                    Promote changes to workspace baseline
  compart commit -m <msg>          Commit to Git with RFC-5322 metadata trailers
  compart undo                     Instant physical snapshot rollback
  compart restore                  Restore from session checkpoint
```

---

## Key Subsystems & Guarantees

| Subsystem | Guarantee | Mechanism |
| :--- | :--- | :--- |
| **OS Kernel Sandbox** | Hard OS Process Isolation | Applied natively via macOS Seatbelt / Linux Landlock. Sub-millisecond startup, deny-by-default on system paths, child processes strictly inherit boundaries. |
| **PTY Supervisor** | Full Native TUI Experience | Bridges pseudo-terminals, forwards window resize (`TIOCGWINSZ`), Ctrl+C (`SIGINT`), Ctrl+D (`EOF`), raw mode. |
| **Credential Defense** | Deny-by-Default Protection | Host SSH keys (`~/.ssh`), cloud credentials (`~/.aws`, `~/.config/gcloud`), git credentials, keychains, and browser data are blocked by default. |
| **BLAKE3 Snapshot Engine** | Physical Instant Rollback | Computes 16-byte BLAKE3 hashes across all workspace files before execution. `compart undo` restores modified/deleted files in 2ms. |
| **Git Provenance Engine** | Auditability & Compliance | `compart commit` automatically attaches RFC-5322 metadata trailers (`Compart-Execution`, `Compart-Agent`, `Compart-Compartment`, `Compart-Security: clean`). |
| **Credential Proxy** | Safe API Secret Routing | Rewrites requests and injects LLM API tokens from host environment without exposing raw secrets to the agent. |
| **Token Compression** | High-Speed Output Crushing | Rust compression engines (`SmartCrusher`, `LogCompressor`, `DiffCompressor`, `TextCrusher`) optimize context before returning outputs. |

---

## Installation

```bash
pip install --upgrade compart
```

*Requires Python 3.10+ on macOS (Apple Silicon / Intel) or Linux (x86_64 / aarch64).*

---

## Python SDK Example

Integrate Compart directly into your custom agent systems:

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

## Documentation Map

- **[Quickstart Guide](docs/QUICKSTART.md)**: 2-minute quickstart guide for CLI and Python workflows.
- **[CLI Reference Guide](docs/CLI.md)**: Complete guide to the frozen public CLI contract.
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
