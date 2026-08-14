# Compart CLI Reference & User Guide

The Compart CLI is the control layer manager for AI agents and workflows. It provides a transparent wrapper and declarative workspace topology manager for kernel-enforced agent execution.

---

## 1. Control-Plane Directory Structure

Running `compart init` creates a hidden `.compart/` control plane in your project directory:

```text
.compart/
├── topology.json    <-- Declarative workspace topology (versioned in Git)
├── sessions/        <-- Persisted AgentSession objects
├── state/           <-- Local workspace runtime state
├── logs/            <-- Execution logs
└── snapshots/       <-- BLAKE3 file diff snapshots
```

---

## 2. Transparent Agent Wrapper Commands

### `compart wrap`
Transparently govern any CLI agent (Claude Code, Cursor, Codex, custom scripts) in a managed `AgentSession` under OS kernel sandbox isolation.

```bash
compart wrap --agent "Claude Code" --task "Fix auth bug" -- claude -p "fix the bug"
```

### `compart sessions`
List all recorded agent sessions in the workspace.

```bash
compart sessions
```

### `compart session inspect <session_id>`
Inspect structured activity logs and BLAKE3 file diffs for a given session.

```bash
compart session inspect sess_1723635840000
compart session inspect sess_1723635840000 --json
```

### `compart session rollback <session_id>`
Roll back the workspace files to the exact state prior to that session.

```bash
compart session rollback sess_1723635840000
```

---

## 3. Declarative Topology Commands

### `compart init`
Initialize a new `.compart/` project directory and default `topology.json`.

```bash
compart init
```

### `compart compartment create <name>`
Declare a new inner compartment in `topology.json`.

```bash
compart compartment create Research
compart compartment create Builder
```

### `compart connect <source> <target>`
Declare a directed communication path between two compartments in `topology.json`.

```bash
compart connect Research Builder
```

### `compart inspect [--json]`
Display the declared topology. Pass `--json` to output raw JSON for `jq` or CI scripts.

```bash
compart inspect
compart inspect --json
```

### `compart run`
Materializes `topology.json` into an ephemeral isolated OS kernel sandbox (macOS Seatbelt / Linux Landlock), executes the configured compartments, and releases the runtime.

```bash
compart run
```

### `compart exec -- <command>`
Execute a single command inside an ephemeral kernel sandbox without initializing a project file.

```bash
compart exec -- python3 script.py
```
