# BentoBox

**Sandbox any AI agent in seconds.**

Kernel-enforced isolation for AI coding agents — zero setup, zero latency, zero escape.

BentoBox runs any agent — or any command it shells out to — inside compartments enforced directly by your OS kernel: Landlock on Linux, Seatbelt on macOS. Policy is deny-by-default. An agent sees its worktree, read-only system paths, and temp directories — and nothing else, unless a compartment's policy grants it. No containers, no VMs, no daemon, no image pulls, no seconds of startup per run.

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

Agents execute code you did not write and cannot fully predict: shell commands, tests, builds, deploys. Every run is a chance to read credentials, modify files, or touch the network.

Containers and VMs isolate, but they are heavy: images to pull, runtimes to install, seconds of startup per run. Interpreter-level sandboxes are bypassable from inside. BentoBox sits at the OS level instead, where the kernel does the enforcing:

- **Enforced by the kernel, not the interpreter.** A compartment cannot open a file it was not granted — even through a subprocess or a direct syscall.
- **Deny-by-default.** Credential files — SSH keys, cloud configs, git credentials, keychains, browser data — are blocked unless you opt in.
- **Nothing to install.** No daemon, no VM, no container runtime. BentoBox uses what the OS already provides.
- **Zero latency.** A sandbox is a few kernel rules, applied in milliseconds. Enforcement costs nothing at runtime.

## What you get

| | |
| :--- | :--- |
| Kernel-enforced isolation | Landlock (Linux 5.13+) or Seatbelt (macOS) applied at the OS level. Once applied, it cannot be loosened — only tightened. |
| Compartments | Named units of work with their own permissions, resource limits, and message routes. Compose pipelines, not walls. |
| Deny-by-default policy | Worktree read-write, system paths read-only, everything else blocked. |
| Credential protection | SSH keys, cloud configs, git credentials, keychains, and browser data denied by default. |
| Network control | Full access or localhost-only, per box. |
| Snapshots & rollback | Hash-based file snapshots; restore only the files that changed. Deleted files come back. |
| Credential proxy | Route rules rewrite request paths and inject API keys from the environment. |
| Output compression | Long compartment output is compressed before it is stored or returned. |
| One core, two SDKs | Python and TypeScript wrappers over a single Rust core. |

## How it works

The box is the box — the lid is part of it. There are two entry points:

- **`BentoBox`** — just the box. A kernel-level sandbox plus a runtime for the compartments **you** define. Nothing ships predefined: no compartments, no behaviour modules. Opt in with `register_module()`.
- **`AgentBentoBox`** — a box with the lid on. It auto-loads every behaviour module (credential proxy, snapshots, output compression) when it runs, so an agent gets the full insulated runtime.

In both, **compartments are always yours** — create them, wire them with `edge()`, and drop them into either box:

```
BentoBox / AgentBentoBox
|-- Box (kernel-level sandbox — the lid is part of the box)
|   |-- Isolated workspace (.bentoworks/boxes/)
|   |-- File system policy
|   |-- Network policy
|   |-- Process restrictions
|   `-- Insulation (task profile + behaviour modules)
|
`-- Compartment Runtime (you define these)
    |-- Compartment "test"   -> permissions: [fs_read, fs_exec]
    |-- Compartment "build"  -> permissions: [fs_read, fs_write, fs_exec]
    `-- Compartment "deploy" -> permissions: [fs_read, fs_write]
```

The **Box** is the secure execution environment; insulation is folded into it. **Compartments** are isolated units of work with their own policies that you register. The runtime has no opinion about what compartments do. It only coordinates their lifecycle, enforces their policies, and routes messages.

## Use it anywhere

BentoBox is agent-agnostic and process-agnostic. If it runs in a terminal, BentoBox can sandbox it:

- **Coding agents** — Claude Code, Codex, opencode, or any CLI agent. The agent reads your repo and writes code, but cannot touch `~/.ssh`, `~/.aws`, or anything outside its granted paths.
- **Builds & tests** — `npm run build`, `pytest`, `cargo build`, with read-only system paths and no network unless granted.
- **Deploys** — a deploy compartment that can read source and write output, but never reaches credentials.
- **Multi-step pipelines** — fetch → build → deploy, with message passing and routing rules enforced in both directions.

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

The `SandboxEnforcer` blocks any operation that violates the compartment's permission set: a read-only compartment cannot write files; a build compartment cannot reach the network if `network` is missing from its permissions.

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

## The security model

Deny by default. Each compartment declares what it can access:

```python
config = CompartmentConfig(permissions=["fs_read"])  # read-only

with SandboxEnforcer(box._current_policy):
    open("file", "r")  # allowed
    open("file", "w")  # PermissionError - no fs_write
    os.remove("file")  # PermissionError
    subprocess.run(...)  # PermissionError - no fs_exec
```

The enforcer wraps 30+ Python stdlib functions (`builtins.open`, `os.*`, `subprocess.*`, `shutil.*`) and checks the active compartment policy before allowing any operation. On top of path permissions, a command blocklist stops dangerous commands (`rm -rf /`, `sudo`, `dd`, `mkfs`, pipes into shells) even when `fs_exec` is granted.

## Use cases

Real scenarios with working code — sandboxing a CLI coding agent, REPL
execution, credential handling under prompt injection, file rollback, and
fan-out agentic workloads: [`docs/USE_CASES.md`](docs/USE_CASES.md).

## SDKs

One Rust core, two language wrappers. All compartment runtime logic — permission enforcement, the command blocklist, filesystem snapshots, credential proxy routing, and message routing — is implemented **once in Rust** and exposed identically in Python and TypeScript.

| Capability | Python | TypeScript |
| :--- | :--- | :--- |
| Permission checks | `SandboxEnforcer` | `runtimeCheckPermission` |
| Command blocklist | `SandboxEnforcer` | `runtimeCheckCommand` |
| Filesystem snapshots | `SnapshotManager` | `runtimeSnapshot` / `runtimeRestore` |
| Credential routing | `CredentialProxy` / `RouteConfig` | `runtimeCredentialRewrite` / `runtimeCredentialResolve` |
| Config validation | `BentoBox` / `CompartmentConfig` | `runtimeValidate` |
| Message routing | `box.edge()` / `box.run()` | `runtimeCanRoute` |
| Opaque runtime handle | `BentoBox` | `new Runtime(...)` |

```bash
pip install bentoworks                    # Python
npm install @bentwork/sdk                  # TypeScript
```

### Python

The enforcer makes identical allow/deny decisions in every SDK, using the same permission names: `fs_read`, `fs_write`, `fs_exec`, `network`, `gpu`, `sys_info`.

```python
import os
from bentoworks.sandbox.enforcer import SandboxEnforcer

policy = {"name": "readonly", "permissions": ["fs_read"]}
with SandboxEnforcer(policy):
    data = open("file.txt", "r").read()   # allowed
    open("file.txt", "w").write("x")      # PermissionError: no fs_write
    os.system("rm -rf /")                 # PermissionError: blocked command
```

Snapshots & rollback — a hash-based snapshot records every file (excluding build/vendor dirs) and its blake3 hash; `restore()` copies back only the files whose hash changed:

```python
from bentoworks.sandbox.snapshot import SnapshotManager

snap = SnapshotManager(workdir="/path/project", snapshot_dir="/tmp/.snapshots")
snap.snapshot()          # returns file count
# ... run work that may modify files ...
restored = snap.restore()  # roll back changed files
snap.cleanup()
```

Credential proxy — `RouteConfig` matches a request path prefix and rewrites it to an upstream base URL, injecting a credential resolved from the environment. In Python the proxy runs as a real local HTTP server (set `HTTP_PROXY` to route through it); TypeScript exposes the same matching/rewriting decision logic without the server transport.

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

The proxy matches the **path component** of each request, so it handles both origin-form (`GET /openai/v1/chat`) and absolute-form (`GET http://api.example.com/openai/v1/chat`) transparently. Query strings survive the rewrite, and unmatched absolute-form requests pass through untouched.

Compartment configs & message routing — routing enforces **both** directions: the source's `allow_outbound_to` and the destination's `allow_inbound_from`. The default whitelist is `["*"]` (wildcard); an explicitly empty list denies everything.

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

### TypeScript

```ts
import * as bentobox from '@bentwork/sdk'

bentobox.runtimeCheckPermission(
  JSON.stringify({ permissions: ['fs_read'] }),
  JSON.stringify(['fs_read']),
) // true

bentobox.runtimeCheckCommand('rm -rf /') // false

const rt = new bentobox.Runtime(configs, JSON.stringify([['fetch', 'build']]))
rt.canRoute('fetch', 'build') // true
rt.runOrder()                 // ['fetch', 'build']
rt.names()                    // ['fetch', 'build']
```

For the full SDK guide, see [sdk/README.md](sdk/README.md).

## Framework hooks

Run AI-agent code inside kernel-enforced compartments from any major agent
framework. Hooks are dependency-light — each framework is optional and the
hook degrades to a plain duck-typed object when it is absent.

```python
# LangGraph — wrap any node in a sandboxed compartment.
from bentoworks.hooks import BentoBoxGraphNode

def crunch(state, ctx):
    open(f"{ctx.workdir}/out.txt", "w").write(state["value"].upper())
    return {"done": True}

node = BentoBoxGraphNode(crunch, workdir=".")
builder.add_edge(START, node.attach(builder))  # permissions ride on node metadata
```

```python
# LangChain — a Python REPL tool that runs inside BentoBox, not exec().
from bentoworks.hooks import BentoPythonREPLTool
tool = BentoPythonREPLTool(permission=["fs_read", "fs_write", "fs_exec"])
tool.invoke("print(6 * 7)")
```

```python
# CrewAI — replace the Docker code interpreter with a BentoBox one.
from bentoworks.hooks import BentoBoxCodeInterpreterTool
agent = Agent(tools=[BentoBoxCodeInterpreterTool()], ...)
```

```python
# AutoGen — runs each code block in a BentoBox compartment.
from bentoworks.hooks import BentoBoxCodeExecutor, CodeBlock
executor = BentoBoxCodeExecutor()
result = executor.execute_code_blocks([CodeBlock("python", "print('hi')")])
print(result.exit_code, result.output)
```

```python
# Data / RAG agent — isolated workspace, network blocked, no exfiltration.
from bentoworks.hooks import DataScienceSandboxHook
hook = DataScienceSandboxHook()
hook.mount_dataset("customers.csv")
res = hook.run("import pandas as pd; df = pd.read_csv('customers.csv'); print(df.shape)")
print(res.diffs)   # BLAKE3 file diffs the agent caused
```

```python
# Plain CLI coding agent — sandbox any shell command or CLI agent.
from bentoworks.hooks import SandboxRunner
res = SandboxRunner(workdir=".").run("claude -p 'fix the bug'")
print(res.returncode, res.stdout, res.diffs)
```

Every hook returns stdout, stderr, an exit code and BLAKE3 file diffs so the
agent context can react cleanly to what ran.

## Development & Testing

```bash
# from the repository root, installs the package into your venv
python -m venv .venv && source .venv/bin/activate
pip install .

# run the test suite (tests import the installed package)
pytest
```

The test suite imports the **installed** package, not the source tree: the compiled native core (`_core`) ships inside the wheel, so the package must be installed before running tests.

## License

BUSL-1.1. See [CHANGELOG.md](CHANGELOG.md) for release history.
