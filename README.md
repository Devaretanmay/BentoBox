<div align="center">

# Compart

### The Agent Workspace & Execution Engine for Modern Developers

**Run Claude Code, Codex, OpenCode, Aider, and multi-agent pipelines with kernel-level isolation, instant physical rollback, and zero infrastructure.**

[PyPI Package](https://pypi.org/project/compart/) | [Documentation](docs/QUICKSTART.md) | [Rust Core](Cargo.toml) | [License](LICENSE)

<br/>

```text
                     YOUR CODEBASE
                          │
         ┌────────────────┴────────────────┐
         │                                 │
        Git                             Compart
   Source History                   Agent Workspace
   Commits & Diffs                  Sandboxed Executions
   Branching                        BLAKE3 Instant Rollback
   Merging                          Credential Defense Proxy
                                    Token Compression Engines
                                    Multi-Agent DAG Pipelines
                                           │
                        Claude / Codex / OpenCode / Aider
                                           │
                                           ▼
                                   OS Kernel Sandbox
                           (macOS Seatbelt / Linux Landlock)
```

</div>

---

## Why Compart?

AI coding agents are moving from chat interfaces into real codebases, terminals, and continuous integration workflows. They execute shell commands, edit source files, install dependencies, and modify configurations.

Letting an autonomous agent run with raw system access creates critical operational and security risks:

* **Credential Exposure:** Agents can read `~/.ssh`, `~/.aws`, `.env`, and shell history, leaking sensitive tokens directly into external prompt contexts.
* **Destructive File Changes:** When an agent modifies or corrupts dozens of files across a repository, standard `git reset --hard` wipes away uncommitted human work alongside the bad agent mutations.
* **Context Exhaustion & Token Waste:** Verbose compiler logs, test outputs, and unified diffs consume up to 80% of an LLM's context window, increasing API costs and degrading model reasoning.
* **Compliance & Provenance Gaps:** Engineering organizations have no auditable trail to prove which commits were authored by automated agents versus human engineers.

Existing isolation models take the wrong abstractions:
* **Cloud MicroVMs (E2B, Daytona):** High latency, per-second cloud billing, remote hosting, and proprietary code leaving the local machine.
* **Docker Containers:** Heavy image builds, daemon overhead, slow cold starts, and complex filesystem mount management.
* **Interpreter Guards (`exec()` hooks):** Trivial to bypass via C-extensions, background subprocesses, or direct system calls.

**Compart provides native OS kernel-level process isolation, deterministic execution attribution, and sub-millisecond physical rollback on local developer machines with zero infrastructure.**

---

## Quickstart

### 1. Installation
```bash
pip install --upgrade compart
```
*Requires Python 3.10+ on macOS (Apple Silicon / Intel) or Linux (x86_64 / aarch64).*

### 2. Initialize a Workspace
```bash
cd my-project
compart init
```

### 3. Run Any Coding Agent
Launch interactive coding agents inside a governed PTY sandbox with full color, raw input handling, and terminal resize support:
```bash
# Launch interactive coding agents:
compart claude       # Claude Code
compart opencode     # OpenCode
compart codex        # OpenAI Codex
compart aider        # Aider
compart cursor       # Cursor terminal agent

# Or execute arbitrary commands inside an isolated compartment:
compart exec -- pytest tests/
```

### 4. Review, Promote, or Undo
```bash
compart diff         # Review change sets isolated by execution
compart apply        # Promote clean changes to workspace baseline
compart commit -m "Add authentication module"  # Commit to Git with verified metadata trailers
compart undo         # Instant physical rollback to pre-execution snapshot (2ms)
```

---

## Core Capabilities

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│                          THE COMPART PLATFORM                               │
├──────────────────────┬──────────────────────┬───────────────────────────────┤
│ 1. Kernel Sandbox    │ 2. BLAKE3 Rollback   │ 3. Token Compression Engine   │
│    Seatbelt/Landlock │    2ms Physical Undo │    40-70% Token Savings (Rust)│
├──────────────────────┼──────────────────────┼───────────────────────────────┤
│ 4. Credential Proxy  │ 5. Git Provenance    │ 6. Multi-Agent DAG Pipelines  │
│    Zero Secret Leak  │    RFC-5322 Trailers │    Topological Task Runner    │
└──────────────────────┴──────────────────────┴───────────────────────────────┘
```

### 1. Native OS Kernel Isolation
Process boundaries are enforced directly by the operating system kernel via **macOS Seatbelt** and **Linux Landlock**:
* **Deny-by-Default:** Filesystem access is strictly confined to declared workspace paths. System roots and foreign user directories are inaccessible.
* **Network Gating:** Sockets can be completely severed or scoped per compartment.
* **Inherited Confinement:** All spawned child processes, shell subshells, and background tasks automatically inherit isolation boundaries.

### 2. Physical Rollback Engine (BLAKE3)
Before executing an agent task, Compart computes physical BLAKE3 hashes across all workspace files:
* Automatically detects added, modified, and deleted files.
* `compart undo` restores modified files and cleans newly created files in **2 milliseconds**, without affecting untracked Git state.

### 3. High-Speed Output Compression (Rust Core)
Terminal logs, test outputs, and large diffs frequently exhaust LLM context windows. Compart includes 4 specialized Rust compression engines:
* **SmartCrusher:** Tabular and structured JSON compaction that preserves statistical outliers, schema invariants, and query anchors.
* **LogCompressor:** Isolate root-cause stack traces and errors while stripping repetitive progress bars and noisy warnings.
* **DiffCompressor:** Compresses multi-file unified diffs while preserving syntax structure and changed hunk contexts.
* **TextCrusher:** High-throughput extractive text summarization.

### 4. Credential Defense & Local Proxy
* Host SSH keys (`~/.ssh`), cloud configurations (`~/.aws`, `~/.config/gcloud`), git credentials, keychains, and browser caches are blocked by default.
* Outbound API requests can be routed through an internal credential proxy that injects host environment secrets without exposing raw keys to the agent runtime.

### 5. Git Provenance & Compliance Trailers
`compart commit` automatically attaches RFC-5322 metadata trailers to Git commits for regulatory and team auditability:
```text
Commit: 8f3d91a "Refactor authentication cache"
Author: Alex Mercer <alex@company.com>

    Refactor authentication cache to support Redis cluster

    Compart-Execution: exec_7a9f12bc
    Compart-Agent: claude-code-v1.0
    Compart-Compartment: builder
    Compart-Security: clean
```

### 6. Multi-Agent Pipeline Workflows (DAG Runner)
Chain multiple specialized agent steps into dependency-aware pipelines with granular security profiles per step:

```bash
# Create a workflow branch
compart -w vulnerability-scanner

# Add steps with distinct OS security policies
compart step vulnerability-scanner src/fetch_cve.py --compartment research   # Read-only fs, Network allowed
compart step vulnerability-scanner src/apply_patch.py --compartment builder  # Read-write fs, Network blocked
compart step vulnerability-scanner "pytest tests/"   --compartment tester    # Read-only fs, Test execution

# Execute the workflow DAG
compart --run vulnerability-scanner
```

* **Topological Scheduling:** Resolves dependency order automatically.
* **Cascade Skip on Failure:** When an upstream step fails, dependent steps are cleanly skipped to prevent cascading data corruption. Independent branches continue execution.

---

## Python SDK

Integrate Compart into custom agent architectures, LangGraph, CrewAI, AutoGen, or internal Python pipelines:

```python
from compart import Compart, Compartment, CompartmentConfig

# Initialize workspace container
compart = Compart(workdir=".")

# 1. Research step: read-only filesystem, outbound network enabled
compart.add(Compartment(
    name="researcher",
    fn=lambda ctx: print("Fetching external documentation..."),
    config=CompartmentConfig(permissions=["fs_read", "network"]),
))

# 2. Build step: read-write workspace, network strictly blocked
compart.add(Compartment(
    name="builder",
    fn=lambda ctx: print("Executing code modifications with zero exfiltration risk..."),
    config=CompartmentConfig(permissions=["fs_read", "fs_write", "fs_exec"]),
))

# Define execution dependency
compart.edge("researcher", "builder")

# Run pipeline under OS kernel governance
result = compart.run()
print(f"Status: {result.status} (Elapsed: {result.elapsed_s}s)")
```

---

## Framework Integrations

Compart serves as a drop-in execution sandbox across popular agent frameworks:

| Framework | Integration Pattern | Documentation |
| :--- | :--- | :--- |
| **LangGraph / LangChain** | `@compart_tool` sandboxed tool decorator | [Framework Hooks Guide](docs/FRAMEWORK_HOOKS.md) |
| **CrewAI** | Isolated `CompartTask` execution tool | [CrewAI Integration](docs/FRAMEWORK_HOOKS.md#crewai) |
| **AutoGen** | Sandboxed code execution container | [AutoGen Integration](docs/FRAMEWORK_HOOKS.md#autogen) |
| **OpenHands / SWE-bench** | Zero-latency local execution backend | [SWE-bench Harness](docs/USE_CASES.md) |

---

## Architecture Comparison

| Dimension | Compart | Docker Containers | Cloud MicroVMs (E2B) | Raw Host Process |
| :--- | :---: | :---: | :---: | :---: |
| **Startup Overhead** | **< 1 ms** | 2,000 – 10,000 ms | 1,000 – 5,000 ms | 0 ms |
| **Configuration** | **Zero Config** | Dockerfiles & Daemons | Cloud Infrastructure | None |
| **Credential Defense** | **Kernel Deny-by-Default** | Manual mount scoping | Remote isolation | None |
| **Physical Undo** | **2ms BLAKE3 Engine** | Recreate container | VM Snapshots | Manual `git reset` |
| **Interactive Terminal TUI** | **Raw PTY Supervisor** | Complex `-it` forwarding | Headless / API only | Native |
| **Token Output Crushing** | **Native Rust Engines** | None | None | None |
| **Data Privacy** | **100% Local Machine** | Local machine | Cloud hosted | Local machine |

---

## Documentation

* [Quickstart Guide](docs/QUICKSTART.md) - Rapid setup for CLI and Python workflows.
* [CLI Reference](docs/CLI.md) - Command definitions, flags, and options.
* [Interactive Agent Execution](docs/AGENT_EXECUTION.md) - PTY supervision, terminal colors, and raw mode handling.
* [Framework Integration Hooks](docs/FRAMEWORK_HOOKS.md) - Sandboxing LangGraph, CrewAI, AutoGen, and LangChain.
* [Credential Defense & Proxy](docs/CREDENTIAL_PROXY.md) - Secret protection and credential injection.
* [BLAKE3 Snapshots & Rollback](docs/SNAPSHOTS.md) - Fast workspace hashing and restoration.
* [Output Compression & Token Optimization](docs/COMPRESSION.md) - Rust compression engines and performance.
* [Python API Reference](docs/API_REFERENCE.md) - Classes, methods, and configurations.
* [Security Use Cases](docs/USE_CASES.md) - Prompt injection containment and compliance.

---

## License

Compart is licensed under the [Elastic License 2.0 (ELv2)](LICENSE). Free for developers and internal business use.
