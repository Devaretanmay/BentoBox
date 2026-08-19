# Compart Quickstart Guide

Get up and running with Compart in under 2 minutes.

> **“Git manages your code. Compart manages your agents.”**

---

## 1. Installation

Install Compart via PyPI:

```bash
pip install --upgrade compart
```

---

## 2. Interactive AI Coding Agents

Run your favorite terminal coding agent inside a kernel-enforced sandbox with full native TUI fidelity:

```bash
cd my-project
compart init

# Launch Claude Code, OpenCode, Codex, Cursor, or Aider directly:
compart claude
```

When the agent finishes, inspect changes or rollback if needed:

```bash
compart diff    # Review what the agent changed
compart commit  # Commit to Git with verified provenance trailers
compart undo    # Instantly restore files if the agent made a mistake
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
# Add a folder of scripts in one go (auto-infers types & chains dependencies):
compart step document-pipeline src/
```

### Step 3: Run the pipeline
```bash
compart --run document-pipeline
```

### Step 4: Commit with provenance
```bash
compart commit -m "Automate document pipeline run"
```

---

## 4. Key Guarantees

- **Kernel Enforcement**: Built on native OS isolation (macOS Seatbelt / Linux Landlock).
- **Credential Protection**: `~/.ssh`, `~/.aws`, `~/.config/gcloud`, git credentials, and keychains are denied by default.
- **Instant Rollback**: Hash-based BLAKE3 file snapshots allow physical restoration of modified and deleted files in 2ms.
- **Zero Infrastructure**: No Docker, no daemon, no cloud account required.
