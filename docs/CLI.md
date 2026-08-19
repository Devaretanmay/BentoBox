# Compart CLI Reference & User Guide

Compart is the runtime and control layer for AI coding agents and custom agentic workflows. It layers transparently onto your existing tools with zero configuration.

> **“Git manages your code. Compart manages your agents.”**

---

## The Public CLI Contract

```text
Workspace
  compart init                     Initialize a Compart workspace
  compart status                   Show workspace health & active executions
  compart inspect                  Dump declared compartments & policies

Agents
  compart claude | opencode | codex | cursor | aider
                                   Run coding agent in governed OS sandbox
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

## 1. Workspace Commands

### `compart init`
Initializes a `.compart/` control plane in the current directory:
- Detects installed agents (`claude`, `codex`, `opencode`, `cursor`, `aider`).
- Configures default security compartments (`default`, `research`, `builder`, `network`, `tester`).
- Sets up execution tracking and BLAKE3 snapshot storage.

```bash
compart init
```

---

### `compart status`
Shows live workspace health, active agents, recent executions, and security events.

```bash
compart status
```

---

### `compart inspect`
Dumps declarative topology, active compartments, filesystem permissions, and network policies.

```bash
compart inspect
compart inspect --json
```

---

## 2. Interactive Agent Execution

### Direct Agent Commands (`compart <agent>`)
Launch any interactive coding agent inside an isolated kernel sandbox with full native terminal TUI fidelity (colors, alternate screen, Ctrl+C, Ctrl+D, window resizing):

```bash
compart claude
compart opencode
compart codex
compart cursor
compart aider
```

**Under the Hood:**
1. Resolves genuine binary on system `PATH`.
2. Allocates a pseudo-terminal master/slave pair (`PtySupervisor`).
3. Takes a pre-execution BLAKE3 hash snapshot of the workspace.
4. Applies OS kernel sandboxing (Seatbelt on macOS / Landlock on Linux).
5. Captures file changes upon exit into `compart diff`.

---

### `compart exec`
Runs any arbitrary script, tool, or shell command inside an explicitly selected compartment:

```bash
# Run inside default compartment
compart exec -- python3 script.py

# Run inside 'research' (read-only filesystem, network allowed)
compart exec --compartment research -- python3 scraper.py

# Run inside 'builder' (read-write filesystem, network restricted)
compart exec --compartment builder -- pytest tests/
```

---

## 3. Agentic Workflows (Git-Style Pipelines)

### `compart -w <name>` (or `compart workflow create <name>`)
Creates a new workflow branch in `workflows/<name>.yaml` or `.compart/workflows/<name>.yaml`:

```bash
compart -w invoice-pipeline
```

---

### `compart step <workflow> <target>`
Adds steps to your workflow branch. Point Compart at an individual file, a command, or an entire directory:

```bash
# Add a single script with auto-inferred runner & compartment
compart step invoice-pipeline src/ocr.py

# Ingest an entire directory (scans and auto-chains scripts)
compart step invoice-pipeline src/

# Add a test or shell command
compart step invoice-pipeline "pytest tests/" --compartment tester
```

---

### `compart --run <workflow>` (or `compart run <workflow>`)
Executes the declared workflow DAG under kernel isolation:

```bash
compart --run invoice-pipeline
```

- Topologically sorts the execution graph.
- Executes each step in its designated compartment (`research`, `builder`, `tester`, `reviewer`).
- If an upstream step fails, downstream dependent steps are cleanly `SKIPPED` to prevent cascading data corruption. Independent branches continue running.

---

### `compart workflow show <workflow>`
Inspects and visualizes declared workflow DAG nodes, commands, and dependencies:

```bash
compart workflow show invoice-pipeline
```

---

## 4. Change Management & Git Provenance

### `compart diff`
Review change sets attributed by execution ID and agent name:

```bash
compart diff               # Show all execution change sets
compart diff --unapplied   # Only show pending changes not yet applied
compart diff --trailers    # View formatted RFC-5322 Git metadata trailers
```

---

### `compart apply`
Promotes an execution's recorded change set into the workspace baseline. Detects conflicts if another execution modified the same files.

```bash
compart apply                         # Apply all pending completed executions
compart apply --execution exec_101    # Apply a specific execution
compart apply --force                 # Apply even if changes overlap
```

---

### `compart commit`
Commits applied agent changes to Git, automatically embedding structured RFC-5322 metadata trailers for auditability and compliance:

```bash
compart commit -m "feat(auth): implement token verification"
```

*Commit will contain metadata trailers:*
```text
Compart-Execution: exec_1787082469762
Compart-Agent: claude
Compart-Compartment: builder
Compart-Security: clean
```

---

### `compart undo`
Physically restores the workspace to its exact state before the execution ran using the pre-execution BLAKE3 hash snapshot (restores in ~2 milliseconds):

```bash
compart undo                         # Undo latest execution
compart undo --execution exec_101    # Undo a specific execution
```

---

### `compart restore [session_id]`
Restores workspace files from an Agent Session snapshot checkpoint:

```bash
compart restore                       # Restores latest session checkpoint
compart restore sess_1787082470931    # Restores specific session checkpoint
```
