# Compart Quickstart Guide

Get up and running with Compart in under 2 minutes.

---

## 1. Installation

Install Compart via PyPI:

```bash
pip install compart
```

---

## 2. Interactive AI Coding Agents

Run your favorite terminal coding agent inside a kernel-enforced sandbox:

```bash
cd my-project
compart init

# Launch Claude Code, OpenCode, or Codex directly:
compart claude
```

When the agent finishes, inspect changes or rollback if needed:

```bash
compart diff    # Review what the agent changed
compart undo    # Instantly restore if something went wrong
```

---

## 3. Building Multi-Agent Workflows in 3 Steps

Turn your existing Python scripts into a sandboxed, rollback-capable pipeline:

### Step 1: Create a workflow branch
```bash
compart -w document-pipeline
```

### Step 2: Add your scripts
```bash
# Add your folder of scripts in one go:
compart step document-pipeline src/
```

### Step 3: Run the pipeline
```bash
compart run document-pipeline
```

### Step 4: Commit with provenance
```bash
compart commit -m "Automate document pipeline run"
```

---

## 4. Key Security Guarantees

- **Kernel Enforcement**: Built on native OS isolation (macOS Seatbelt / Linux Landlock).
- **Credential Protection**: `~/.ssh`, `~/.aws`, git credentials, and keychains are denied by default.
- **Instant Rollback**: Hash-based file snapshots allow physical restoration of modified and deleted files.
- **Zero Infrastructure**: No Docker, no daemon, no cloud account required.
