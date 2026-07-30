# BentoBox

**A kernel-level sandbox with compartmentalized isolated execution for any coding agent.**

```python
from bentoworks import BentoBox
from bentoworks.compartments import Compartment, CompartmentConfig

box = BentoBox()
box.add(Compartment(
    name="build",
    fn=lambda ctx: __import__("os").system("pytest"),
    config=CompartmentConfig(permissions=["fs_read", "fs_exec"]),
))
result = box.run()
print(result.status, result.summary)
```

---

## What is a BentoBox?

A BentoBox is a single product made of two inseparable parts — a **Box** (kernel-level sandbox) and a **Lid** (insulation layer). Inside the box, **compartments** define what runs, each with its own permissions and resource limits.

```
BentoBox
├── Box (kernel-level sandbox)
│   ├── Isolated workspace (.bentoworks/boxes/)
│   ├── File system policy
│   ├── Network policy
│   └── Process restrictions
│
├── Lid (insulation layer)
│   ├── Task profile classification
│   └── Behaviour modules (runtime plugins)
│
└── Compartment Runtime
    ├── Compartment "test"  → permissions: [fs_read, fs_exec]
    ├── Compartment "build" → permissions: [fs_read, fs_write, fs_exec]
    └── Compartment "deploy" → permissions: [fs_read, fs_write]
```

The **Box** is the secure execution environment. The **Lid** optimizes that environment for execution. **Compartments** are isolated units of work with their own policies. The user sees them as one unified thing — a BentoBox.

---

## Quick Start

```bash
pip install bentoworks
```

```python
from bentoworks import BentoBox
from bentoworks.compartments import Compartment, CompartmentConfig

# Single compartment — run a task
box = BentoBox()
box.add(Compartment(
    name="test",
    fn=lambda ctx: __import__("os").system("pytest"),
    config=CompartmentConfig(permissions=["fs_read", "fs_exec"]),
))
result = box.run()
print(f"Status: {result.status}")   # "success"
print(f"Compartments: {result.compartments_completed}")

# Multi-compartment pipeline with message passing
box = BentoBox()
box.add(Compartment(name="fetch", fn=fetch_fn, config=CompartmentConfig(permissions=["fs_read"])))
box.add(Compartment(name="build", fn=build_fn, config=CompartmentConfig(permissions=["fs_read", "fs_write"])))
box.edge("fetch", "build")
result = box.run(entry="fetch", request="Fetch and build")
```

Each compartment gets its own `CompartmentConfig`:
- **permissions**: `fs_read`, `fs_write`, `fs_exec`, `network`, `gpu`, `sys_info`
- **Resource limits**: `timeout_s`, `memory_mb`, `storage_mb`, `cpu_percent`
- **Communication whitelist**: `allow_inbound_from`, `allow_outbound_to`

The `SandboxEnforcer` blocks any operation that violates the compartment's permission set — a read-only compartment cannot write files, a build compartment cannot access the network if omitted from its permissions.

---

## CLI

```bash
# Run a shell command in a compartment
bentoworks run "npm run build" --name build --permissions fs_read fs_write fs_exec

# Diagnose sandbox blocks
bentoworks why ~/.ssh/id_rsa
bentoworks why http://api.example.com

# Trace output (diagnostic)
BENTOWORKS_TRACE=1 bentoworks run "pytest" --name test --permissions fs_read fs_exec
```

---

## Architecture

```
User
  │
  ▼
Create BentoBox
  │
  ├── Box.enter() → sandbox workspace created
  ├── Lid.insulate() → task profiled, modules loaded
  ├── CompartmentRuntime.run()
  │     ├── Compartment A → own config, own permissions
  │     ├── Compartment B → own config, own permissions
  │     └── ... (message passing via edges)
  ├── Lid.release() → modules unloaded
  └── Box.exit() → workspace destroyed
```

The runtime has **no opinion** about what compartments do. It only coordinates their lifecycle, enforces their policies, and routes messages.

---

## Permissions Enforcement

Each compartment declares what it can access:

```python
config = CompartmentConfig(permissions=["fs_read"])  # read-only

with SandboxEnforcer(box._current_policy):
    open("file", "r")  # ✅ allowed
    open("file", "w")  # ❌ PermissionError — no fs_write
    os.remove("file")  # ❌ PermissionError
    subprocess.run(...)  # ❌ PermissionError — no fs_exec
```

The enforcer wraps 30+ Python stdlib functions (`builtins.open`, `os.*`, `subprocess.*`, `shutil.*`) and checks the active compartment policy before allowing any operation.

---

## For Advanced Users

```python
# Access runtime internals
from bentoworks.runtime import Box, Lid, Compartment, CompartmentConfig, CompartmentRuntime
from bentoworks.runtime import EventBus, Tracer

# Create custom compartments as classes
class SecurityScan(Compartment):
    config = CompartmentConfig(permissions=["fs_read", "network"])

    def run(self, ctx):
        # Your logic here
        return {"status": "clean"}
```

---

## Install

```bash
pip install bentoworks
```

Requires Python 3.10+.

License: BUSL-1.1
