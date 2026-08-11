# Compart CLI Reference & User Guide

The Compart CLI is a declarative runtime manager for isolated agent execution. It provides an Infrastructure-as-Code workflow for configuring, versioning, and materializing kernel sandboxes.

---

## 1. Control-Plane Directory Structure

Running `compart init` creates a hidden `.compart/` control plane in your project directory:

```text
.compart/
├── topology.json    <-- Declarative desired state (versioned in Git)
├── state/          <-- Local workspace runtime state
├── logs/           <-- Execution logs
└── snapshots/      <-- File diff snapshots
```

The `.compart/topology.json` file describes the desired execution state. The actual OS kernel sandbox remains strictly ephemeral and is materialized only when `compart run` is invoked.

---

## 2. Declarative Schema (`topology.json`)

```json
{
  "name": "my_agent_project",
  "compartments": {
    "Research": {
      "permissions": ["fs_read"]
    },
    "Builder": {
      "permissions": ["fs_read", "fs_write", "fs_exec"]
    }
  },
  "connections": [
    ["Research", "Builder"]
  ]
}
```

### Fields:
- **`name`**: Project name (defaults to current directory name).
- **`compartments`**: Object mapping inner compartment names to permission configurations.
  - **`permissions`**: List of permissions (`"fs_read"`, `"fs_write"`, `"fs_exec"`, `"network"`).
- **`connections`**: List of directed communication edges `[source, target]`.

---

## 3. Command Reference

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

---

## 4. Git PR Security Review Workflow

Because `topology.json` is stored as standard JSON inside `.compart/`, you can check it into Git. Pull requests will explicitly show security permission changes in code reviews:

```diff
 "Research": {
-  "permissions": ["fs_read"]
+  "permissions": ["fs_read", "network"]
 }
```
This allows security teams to catch unauthorized permission expansions before code is merged.
