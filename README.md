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

## Multi-SDK Compartment Runtime

All compartment runtime logic — permission enforcement, the command
blocklist, filesystem snapshots, credential proxy routing, and message
routing — is implemented **once in the Rust core** and exposed identically
across three SDKs:

| Capability | Python | Go | TypeScript |
| :--- | :--- | :--- | :--- |
| Permission checks | `SandboxEnforcer` | `CheckPermission` | `runtimeCheckPermission` |
| Command blocklist | `SandboxEnforcer` | `CheckCommand` | `runtimeCheckCommand` |
| Filesystem snapshots | `SnapshotManager` | `Snapshot` / `Restore` | `runtimeSnapshot` / `runtimeRestore` |
| Credential routing | `CredentialProxy` / `RouteConfig` | `CredentialRewrite` / `CredentialResolve` | `runtimeCredentialRewrite` / `runtimeCredentialResolve` |
| Config validation | `BentoBox` / `CompartmentConfig` | `ValidateRuntime` | `runtimeValidate` |
| Message routing | `box.edge()` / `box.run()` | `CanRoute` | `runtimeCanRoute` |
| Opaque runtime handle | `BentoBox` | `NewRuntime` → `Runtime` | `new Runtime(...)` |

**Install:**

```bash
pip install bentoworks                    # Python
npm install @bentobox/sdk                  # TypeScript
go get github.com/Devaretanmay/BentoBox/sdk/go  # Go
```

### 1. Enforcer — permissions & command blocklist

The enforcer makes identical allow/deny decisions in every SDK. The same
permission names are used everywhere: `fs_read`, `fs_write`, `fs_exec`,
`network`, `gpu`, `sys_info`. A read-only compartment cannot write files;
`rm -rf /`, `sudo`, `dd`, `mkfs`, and pipes into shells are blocked even
when `fs_exec` is granted.

**Python**

```python
import os
from bentoworks.sandbox.enforcer import SandboxEnforcer

policy = {"name": "readonly", "permissions": ["fs_read"]}
with SandboxEnforcer(policy):
    data = open("file.txt", "r").read()   # allowed
    open("file.txt", "w").write("x")      # PermissionError: no fs_write
    os.system("rm -rf /")                 # PermissionError: blocked command
```

**Go**

```go
import bentobox "github.com/Devaretanmay/BentoBox/sdk/go"

allowed, err := bentobox.CheckPermission(
    bentobox.CompartmentConfig{Permissions: []string{"fs_read"}},
    "fs_read",
) // allowed == true

blocked, _ := bentobox.CheckCommand("rm -rf /") // blocked == false
```

**TypeScript**

```ts
import * as bentobox from '@bentobox/sdk'

bentobox.runtimeCheckPermission(
  JSON.stringify({ permissions: ['fs_read'] }),
  JSON.stringify(['fs_read']),
) // true

bentobox.runtimeCheckCommand('rm -rf /') // false
```

### 2. Snapshots & rollback

A hash-based snapshot records every file (excluding build/vendor dirs) and
its blake3 hash. `restore()` copies back only the files whose hash changed
— deleted files are recovered, unchanged files are untouched.

**Python**

```python
from bentoworks.sandbox.snapshot import SnapshotManager

snap = SnapshotManager(workdir="/path/project", snapshot_dir="/tmp/.snapshots")
snap.snapshot()          # returns file count
# ... run work that may modify files ...
restored = snap.restore()  # roll back changed files
snap.cleanup()
```

**Go**

```go
n, err := bentobox.Snapshot("/path/project", "/tmp/.snapshots", nil) // n = files
restored, err := bentobox.Restore("/path/project", "/tmp/.snapshots")
```

**TypeScript**

```ts
bentobox.runtimeSnapshot('/path/project', '/tmp/.snapshots') // file count
bentobox.runtimeRestore('/path/project', '/tmp/.snapshots') // files restored
```

### 3. Credential proxy

`RouteConfig` matches a request path prefix and rewrites it to an upstream
base URL, injecting a credential resolved from the environment. In Python
the proxy runs as a real local HTTP server (set `HTTP_PROXY` to route
through it); Go and TypeScript expose the same matching/rewriting decision
logic without the server transport.

**Python**

```python
from bentoworks.sandbox.proxy import CredentialProxy, RouteConfig

proxy = CredentialProxy(routes=[
    RouteConfig(
        prefix="/openai",
        upstream="https://api.openai.com",
        credential_source="env:OPENAI_API_KEY",
    ),
])
proxy.start()
proxy.set_env()  # sets HTTP_PROXY / HTTPS_PROXY to the local proxy
# ... requests to /openai/... are rewritten and get Authorization injected ...
proxy.restore_env()
proxy.stop()
```

**Go**

```go
url, _ := bentobox.CredentialRewrite(
    []bentobox.RouteConfig{{Prefix: "/openai", Upstream: "https://api.openai.com"}},
    "/openai/v1/chat",
) // "https://api.openai.com/v1/chat"

key := bentobox.CredentialResolve("env:OPENAI_API_KEY")
```

**TypeScript**

```ts
bentobox.runtimeCredentialRewrite(
  JSON.stringify([{ prefix: '/openai', upstream: 'https://api.openai.com' }]),
  '/openai/v1/chat',
) // 'https://api.openai.com/v1/chat'

bentobox.runtimeCredentialResolve('env:OPENAI_API_KEY')
```

### 4. Compartment configs & message routing

Each compartment declares its permissions, resource limits, and
communication whitelists. Routing enforces **both** directions: the source's
`allow_outbound_to` and the destination's `allow_inbound_from`. The default
whitelist is `["*"]` (wildcard) — an explicitly empty list denies everything.

**Python**

```python
from bentoworks import BentoBox
from bentoworks.compartments import Compartment, CompartmentConfig

box = BentoBox()
box.add(Compartment(
    name="fetch",
    fn=lambda ctx: {"fetched": True},
    config=CompartmentConfig(
        permissions=["fs_read", "network"],
        allow_outbound_to=["build"],
    ),
))
box.add(Compartment(
    name="build",
    fn=lambda ctx: {"built": True},
    config=CompartmentConfig(
        permissions=["fs_read", "fs_write"],
        allow_inbound_from=["fetch"],
    ),
))
box.edge("fetch", "build")
result = box.run()
```

**Go**

```go
configs := []bentobox.CompartmentConfig{
    {Name: "fetch", Permissions: []string{"fs_read", "network"},
        AllowOutboundTo: []string{"build"}},
    {Name: "build", Permissions: []string{"fs_read", "fs_write"},
        AllowInboundFrom: []string{"fetch"}},
}

valid, _ := bentobox.ValidateRuntime(configs, [][2]string{{"fetch", "build"}})
allowed, _ := bentobox.CanRoute(configs, "fetch", "build")
```

**TypeScript**

```ts
const configs = JSON.stringify({ configs: [
  { name: 'fetch', permissions: ['fs_read', 'network'], allow_outbound_to: ['build'] },
  { name: 'build', permissions: ['fs_read', 'fs_write'], allow_inbound_from: ['fetch'] },
] })

bentobox.runtimeValidate(configs, JSON.stringify([['fetch', 'build']])) // true
bentobox.runtimeCanRoute(configs, 'fetch', 'build') // true
```

### 5. Opaque runtime handle (parse once, route many)

The handle parses compartment configs **once** at construction, so hot-path
routing does not re-parse JSON on every call. The native handle (Go) is
internally mutex-protected and safe to share across goroutines — free it
exactly once, after all threads have finished. The TypeScript class wraps
the same runtime per-isolate (napi objects are not shared across worker
threads).

**Go**

```go
rt, err := bentobox.NewRuntime(configs, [][2]string{{"fetch", "build"}})
if err != nil {
    return err
}
defer rt.Free()

ok, _ := rt.CanRoute("fetch", "build") // true
order, _ := rt.RunOrder("")            // ["fetch", "build"]
```

**TypeScript**

```ts
const rt = new bentobox.Runtime(configs, JSON.stringify([['fetch', 'build']]))
rt.canRoute('fetch', 'build') // true
rt.runOrder()                 // ['fetch', 'build']
rt.names()                    // ['fetch', 'build']
```

---

## Install

```bash
pip install bentoworks
```

Requires Python 3.10+. For Go and TypeScript, see the install commands in
[Multi-SDK Compartment Runtime](#multi-sdk-compartment-runtime).

License: BUSL-1.1
