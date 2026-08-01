# BentoBox

**Kernel-level sandboxing for AI coding agents.**

BentoBox runs agent code inside isolated compartments enforced directly by
the OS kernel: Landlock on Linux, Seatbelt on macOS. Policy is
deny-by-default: an agent sees its worktree, read-only system paths, and
temp directories, and nothing else unless the compartment's policy grants
it. No containers, no VMs, no daemon.

```bash
pip install bentoworks
```

```python
from bentoworks import BentoBox
from bentoworks.compartments import Compartment, CompartmentConfig

box = BentoBox()
box.add(Compartment(
    name="build",
    fn=lambda ctx: {"status": "ok"},
    config=CompartmentConfig(permissions=["fs_read", "fs_exec"]),
))
result = box.run()
print(result.status)  # "success"
```

---

## Why BentoBox?

Agents execute code you did not write and cannot fully predict: shell
commands, tests, builds, deploys. Each run is a chance to read credentials,
modify files, or touch the network.

Containers and VMs isolate, but they are heavy: images to pull, runtimes to
install, seconds of startup per run. Interpreter-level sandboxes are
bypassable from inside. BentoBox sits at the OS level instead:

- **Enforced by the kernel, not the interpreter.** A compartment cannot
  open a file it was not granted, even through a subprocess or a direct
  syscall.
- **Deny-by-default.** Credential files - SSH keys, cloud configs, git
  credentials, keychains, browser data - are blocked unless you opt in.
- **Nothing to install.** No daemon, no VM, no container runtime. The
  sandbox uses what the OS already provides.

## Features

| Capability | What you get |
| :--- | :--- |
| Kernel-enforced isolation | Landlock (Linux 5.13+) or Seatbelt (macOS) applied at the OS level |
| Compartments | Named units of work with their own permissions, resource limits, and message routes |
| Deny-by-default policy | Worktree read-write, system paths read-only, everything else blocked |
| Credential protection | SSH keys, cloud configs, git credentials, keychains, and browser data denied by default |
| Network control | Full access or localhost-only, per box |
| Snapshots & rollback | Hash-based file snapshots; restore only the files that changed |
| Credential proxy | Route rules rewrite request paths and inject API keys from the environment |
| Output compression | Compresses long compartment output before it is stored or returned |
| One core, three SDKs | Python, Go, and TypeScript wrappers over a single Rust core |

## How it works

A BentoBox is one product with two parts: a **Box** (kernel-level sandbox)
and a **Lid** (insulation layer). Inside the box, **compartments** define
what runs, each with its own permissions and resource limits.

```
BentoBox
|-- Box (kernel-level sandbox)
|   |-- Isolated workspace (.bentoworks/boxes/)
|   |-- File system policy
|   |-- Network policy
|   `-- Process restrictions
|
|-- Lid (insulation layer)
|   |-- Task profile classification
|   `-- Behaviour modules (runtime plugins)
|
`-- Compartment Runtime
    |-- Compartment "test"   -> permissions: [fs_read, fs_exec]
    |-- Compartment "build"  -> permissions: [fs_read, fs_write, fs_exec]
    `-- Compartment "deploy" -> permissions: [fs_read, fs_write]
```

The **Box** is the secure execution environment. The **Lid** optimizes that
environment for the task. **Compartments** are isolated units of work with
their own policies. The user sees them as one unified thing: a BentoBox.

The runtime has no opinion about what compartments do. It only coordinates
their lifecycle, enforces their policies, and routes messages.

## Quick Start

Multi-compartment pipeline with message passing:

```python
from bentoworks import BentoBox
from bentoworks.compartments import Compartment, CompartmentConfig

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

The `SandboxEnforcer` blocks any operation that violates the compartment's
permission set: a read-only compartment cannot write files, a build
compartment cannot reach the network if `network` is missing from its
permissions.

### Custom compartments

Subclass `Compartment` and override `run`:

```python
from bentoworks.compartments import Compartment, CompartmentConfig

class SecurityScan(Compartment):
    config = CompartmentConfig(permissions=["fs_read", "network"])

    def run(self, ctx):
        return {"status": "clean"}
```

Requires Python 3.10+.

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

`bentoworks run` captures the command's stdout and stderr and prints them
after the run summary, so you can see exactly what the compartment did:

```
Status: success
Summary: Task completed
Elapsed: 0.1s
Compartments: ['build']

Stdout:
> npm run build
...
```

If the shell command exits non-zero, the CLI itself exits with status `1`
so scripts and CI can react to a failed task.

## Permissions Enforcement

Each compartment declares what it can access:

```python
config = CompartmentConfig(permissions=["fs_read"])  # read-only

with SandboxEnforcer(box._current_policy):
    open("file", "r")  # allowed
    open("file", "w")  # PermissionError - no fs_write
    os.remove("file")  # PermissionError
    subprocess.run(...)  # PermissionError - no fs_exec
```

The enforcer wraps 30+ Python stdlib functions (`builtins.open`, `os.*`,
`subprocess.*`, `shutil.*`) and checks the active compartment policy before
allowing any operation.

## Multi-SDK Compartment Runtime

All compartment runtime logic (permission enforcement, the command
blocklist, filesystem snapshots, credential proxy routing, and message
routing) is implemented **once in the Rust core** and exposed identically
across three SDKs:

| Capability | Python | Go | TypeScript |
| :--- | :--- | :--- | :--- |
| Permission checks | `SandboxEnforcer` | `CheckPermission` | `runtimeCheckPermission` |
| Command blocklist | `SandboxEnforcer` | `CheckCommand` | `runtimeCheckCommand` |
| Filesystem snapshots | `SnapshotManager` | `Snapshot` / `Restore` | `runtimeSnapshot` / `runtimeRestore` |
| Credential routing | `CredentialProxy` / `RouteConfig` | `CredentialRewrite` / `CredentialResolve` | `runtimeCredentialRewrite` / `runtimeCredentialResolve` |
| Config validation | `BentoBox` / `CompartmentConfig` | `ValidateRuntime` | `runtimeValidate` |
| Message routing | `box.edge()` / `box.run()` | `CanRoute` | `runtimeCanRoute` |
| Opaque runtime handle | `BentoBox` | `NewRuntime` -> `Runtime` | `new Runtime(...)` |

**Install:**

```bash
pip install bentoworks                    # Python
npm install @bentobox/sdk                  # TypeScript
go get github.com/Devaretanmay/BentoBox/sdk/go  # Go
```

### 1. Enforcer: permissions & command blocklist

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
its blake3 hash. `restore()` copies back only the files whose hash changed.
Deleted files are recovered; unchanged files are untouched.

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

The Python proxy matches the **path component** of each request, so it
handles both request-target forms transparently:

* **Origin-form**: a client pointed straight at the proxy:
  ``GET /openai/v1/chat``
* **Absolute-form**: a client routing through it via ``HTTP_PROXY``:
  ``GET http://api.example.com/openai/v1/chat``

Query strings survive the rewrite (`/openai/v1/chat?stream=true` becomes
`<upstream>/v1/chat?stream=true`), and unmatched absolute-form requests
pass through untouched.

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
whitelist is `["*"]` (wildcard); an explicitly empty list denies everything.

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
internally mutex-protected and safe to share across goroutines. Free it
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

For the Go and TypeScript SDK setup, see [sdk/README.md](sdk/README.md).

## Development & Testing

```bash
# from the repository root, installs the package into your venv
python -m venv .venv && source .venv/bin/activate
pip install .

# run the test suite (tests import the installed package)
pytest
```

The test suite imports the **installed** package, not the source tree:
the compiled native core (`_core`) ships inside the wheel, so the package
must be installed before running tests.

## License

BUSL-1.1. See [CHANGELOG.md](CHANGELOG.md) for release history.
