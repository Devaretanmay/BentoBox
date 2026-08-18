# Compart CLI Reference & User Guide

Compart is the runtime and control layer for AI coding agents and custom agentic workflows. It layers transparently onto your existing tools with zero configuration.

---

## 1. Quick Workspace Setup

```bash
compart init
```

Initializes a `.compart/` control plane in the current directory:
- Detects installed agents (Claude, Codex, OpenCode, Cursor, Aider).
- Generates safe default policies in `.compart/config.yaml`.
- Prepares execution tracking and snapshot storage.

---

## 2. Interactive Agent Execution

### Direct Agent Shortcut
Launch any interactive coding agent inside an isolated kernel sandbox with full native TUI support (colors, Ctrl+C, interactive prompts):

```bash
compart claude
compart opencode
compart codex
```

### Transparent PATH Activation (Optional)
If you prefer running agents without typing `compart`, activate your shell session:

```bash
source .compart/activate
# or use direnv: direnv allow

claude    # automatically governed by Compart
```

---

## 3. Agentic Workflows (Git-Style)

### `compart -w <name>`
Create a new workflow branch in `workflows/<name>.yaml`:

```bash
compart -w invoice-pipeline
```

### `compart step <workflow> <target>`
Add steps to your workflow. Point Compart at an individual file, a command, or an entire directory:

```bash
# Add a single script with auto-inferred compartment
compart step invoice-pipeline src/ocr_scrape.py

# Add an entire directory (scans and auto-chains scripts)
compart step invoice-pipeline src/

# Add a test or shell command
compart step invoice-pipeline "pytest tests/" --compartment tester
```

### `compart run <name>`
Execute the declared workflow DAG under kernel isolation:

```bash
compart run invoice-pipeline
```

---

## 4. Change Management & Review Surface

### `compart diff`
Inspect file changes made across agent executions:

```bash
compart diff
compart diff --unapplied
compart diff --execution exec_1787056334504
```

### `compart commit [-m "message"]`
Promote and commit agent execution changes to Git with structured RFC-5322 metadata trailers:

```bash
compart commit -m "Process batch invoices"
```

### `compart undo`
Physically restore the workspace to its exact state before the execution ran:

```bash
compart undo
```

### `compart status`
Display live workspace status, active executions, virtual lanes, and security events:

```bash
compart status
```

---

## 5. Ephemeral Execution (`compart exec`)

Run any arbitrary command inside a governed compartment:

```bash
compart exec -- python3 script.py
compart exec --compartment network -- curl https://api.example.com
```
