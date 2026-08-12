# Compart v1.0.0

[![PyPI version](https://img.shields.io/pypi/v/compart.svg)](https://pypi.org/project/compart/)
[![License: ELv2](https://img.shields.io/badge/License-ELv2-blue.svg)](LICENSE)

**Compart is the control layer for AI agents and workflows.**

*Compart lets you define, isolate, control, and observe what agents and workflows can access and do.*

> **AI agents are moving from chat into real workflows, tools, codebases, and production systems. Compart gives developers a control layer to run them safely.**

Don't replace your existing agent stack (Claude Code, Cursor, Codex, LangGraph, CrewAI, MCP tools). **Put it under Compart.**

```text
Claude Code ─────┐
Codex ───────────┤
Cursor ──────────┤
LangGraph ───────┼──→ COMPART ──→ OS
CrewAI ──────────┤       │
MCP Tools ───────┤       ├── Topology
Custom Agents ───┘       ├── Policies
                         ├── Compartments
                         ├── Credentials
                         ├── Network
                         └── Behaviour
```

```python
from compart import Compart
from compart.compartments import Compartment, CompartmentConfig

compart = Compart()
compart.add(Compartment(
    name="build",
    fn=lambda ctx: {"status": "ok"},
    config=CompartmentConfig(permissions=["fs_read", "fs_exec"]),
))
result = compart.run()
print(result.status)  # "success"
```

---

## Why Compart?

Every developer and team is starting to run AI agents: Claude Code, Cursor, AutoGen, custom scripts, or MCP tool runners. But as agents move from simple chat into real codebases and production systems, they execute code and shell commands you did not write and cannot predict.

Existing isolation platforms take a narrow approach:

```text
E2B / Daytona / Cloud VMs
        ↓
"Give my agent an isolated environment."

Compart
        ↓
"Give me control over my agents and workflows."
```

*The kernel sandbox is what makes that control trustworthy.*

Compart sits directly between your AI agents and your operating system kernel:

- **Define, isolate, control, and observe.** Manage agent topology, credentials, filesystem boundaries, network access, and execution traces.
- **Enforced by the kernel, not the interpreter.** A compartment cannot open a file it was not granted: even through a subprocess or direct syscall.
- **Deny-by-default credential protection.** SSH keys (`~/.ssh`), cloud configs (`~/.aws`), git credentials, keychains, and browser data are blocked by default.
- **Sub-millisecond kernel enforcement.** Sandboxing rules are applied natively on your OS kernel (Landlock on Linux, Seatbelt on macOS) without virtualization overhead.
- **Declarative topology.** Manage permissions as code in `.compart/topology.json` so security rules are reviewable in Git PRs.

## What you get

| | |
| :--- | :--- |
| Kernel-enforced isolation | Landlock (Linux 5.13+) or Seatbelt (macOS) applied at the OS level. Once applied, it cannot be loosened : only tightened. |
| Compartments | Named units of work with their own permissions, resource limits, and message routes. Compose pipelines, not walls. |
| Deny-by-default policy | Worktree read-write, system paths read-only, everything else blocked. |
| Credential protection | SSH keys, cloud configs, git credentials, keychains, and browser data denied by default. |
| Network control | Full access or localhost-only, per compartment. |
| Snapshots & rollback | Hash-based file snapshots; restore only the files that changed. Deleted files come back. |
| Credential proxy | Route rules rewrite request paths and inject API keys from the environment. |
| Output compression | Long compartment output is compressed before it is stored or returned. |
| One core, two SDKs | Python and TypeScript wrappers over a single Rust core. |

## Agent Workspace & Product Experience

Compart presents your agent stack as a structured **Agent Workspace**:

```text
COMPART
   │
   ├── Agents & Workflows (Claude Code, Cursor, LangGraph, CrewAI, MCP)
   ├── Workspace Topology (.compart/topology.json)
   ├── Permissions & Boundaries (File, Network, Credentials)
   └── OS Kernel Sandbox (Landlock on Linux / Seatbelt on macOS)
```

### The Agent Session View

When an agent runs under Compart, execution is tracked as an **Agent Session**:

```text
Agent Session #42
────────────────────────────────────────────────────────────────
Agent       : Claude Code
Task        : Fix authentication bug
Workflow    : Research -> Build -> Test -> Review
Compartment : Builder
Permissions : [fs_read repo, fs_write src/, fs_exec tests, network blocked]
Activity    :
  [OK] Read auth.py
  [OK] Modified auth.py
  [OK] Executed pytest (14 passed)
  [BLOCKED BY KERNEL] Attempted network request to external host
Changes     : +42 / -18 lines
Status      : Complete
```

---

## Security Model & Boundary Definitions

Compart enforces security at three distinct, explicit layers:

| Layer | Type | Scope | Description |
| :--- | :--- | :--- | :--- |
| **Kernel Boundary** | **OS Process Sandbox** | Hard OS Boundary | Applied via Linux Landlock or macOS Seatbelt directly at the OS kernel. Restricts process syscalls, filesystem paths, and network access across the process and all child subprocesses. |
| **Compartment Policy** | **Workflow Boundary** | Logical Topology | Defines granular permissions (`fs_read`, `fs_write`, `fs_exec`, `network`) and allowed communication edges between inner workflow steps. |
| **Python Enforcer** | **Interpreter Guard** | Application Level | Intercepts Python stdlib calls (`builtins.open`, `os.*`, `subprocess.*`) inside Python-based compartment functions. |

---

## Declarative Agent Workspace CLI

Manage your agent workspace topology as code:

```bash
# 1. Initialize an agent workspace
compart init

# 2. Define workflow compartments
compart compartment create Research
compart compartment create Builder

# 3. Wire agent communication edges
compart connect Research Builder

# 4. Inspect workspace topology
compart inspect

# 5. Run agent workspace under kernel isolation
compart run
```

Your workspace configuration is stored in `.compart/topology.json`, making security permission changes reviewable in Git PRs (`git diff`).

```python
config = CompartmentConfig(permissions=["fs_read"])  # read-only

with SandboxEnforcer(compart._current_policy):
    open("file", "r")  # allowed
    open("file", "w")  # PermissionError - no fs_write
    os.remove("file")  # PermissionError
    subprocess.run(...)  # PermissionError - no fs_exec
```

The enforcer wraps 30+ Python stdlib functions (`builtins.open`, `os.*`, `subprocess.*`, `shutil.*`) and checks the active compartment policy before allowing any operation. On top of path permissions, a command blocklist stops dangerous commands (`rm -rf /`, `sudo`, `dd`, `mkfs`, pipes into shells) even when `fs_exec` is granted.

## Use cases

Real scenarios with working code : sandboxing a CLI coding agent, REPL
execution, credential handling under prompt injection, file rollback, and
fan-out agentic workloads: [`docs/USE_CASES.md`](docs/USE_CASES.md).

## SDKs

One Rust core, two language wrappers. All compartment runtime logic (permission enforcement, the command blocklist, filesystem snapshots, credential proxy routing, and message routing) is implemented once in Rust and exposed identically in Python and TypeScript.

| Capability | Python | TypeScript |
| :--- | :--- | :--- |
| Permission checks | `SandboxEnforcer` | `runtimeCheckPermission` |
| Command blocklist | `SandboxEnforcer` | `runtimeCheckCommand` |
| Filesystem snapshots | `SnapshotManager` | `runtimeSnapshot` / `runtimeRestore` |
| Credential routing | `CredentialProxy` / `RouteConfig` | `runtimeCredentialRewrite` / `runtimeCredentialResolve` |
| Config validation | `Compart` / `CompartmentConfig` | `runtimeValidate` |
| Message routing | `compart.edge()` / `compart.run()` | `runtimeCanRoute` |
| Opaque runtime handle | `Compart` | `new Runtime(...)` |

```bash
pip install compart                    # Python; native wheels depend on platform
npm install @compart/sdk                  # TypeScript; publish platform addons first
```

### Python

The enforcer makes identical allow/deny decisions in every SDK, using the same permission names: `fs_read`, `fs_write`, `fs_exec`, `network`, `gpu`, `sys_info`.

```python
import os
from compart.sandbox.enforcer import SandboxEnforcer

policy = {"name": "readonly", "permissions": ["fs_read"]}
with SandboxEnforcer(policy):
    data = open("file.txt", "r").read()   # allowed
    open("file.txt", "w").write("x")      # PermissionError: no fs_write
    os.system("rm -rf /")                 # PermissionError: blocked command
```

Snapshots & rollback: a hash-based snapshot records every file (excluding build/vendor dirs) and its blake3 hash; `restore()` copies back only the files whose hash changed:

```python
from compart.sandbox.snapshot import SnapshotManager

snap = SnapshotManager(workdir="/path/project", snapshot_dir="/tmp/.snapshots")
snap.snapshot()          # returns file count
# ... run work that may modify files ...
restored = snap.restore()  # roll back changed files
snap.cleanup()
```

Credential proxy: `RouteConfig` matches a request path prefix and rewrites it to an upstream base URL, injecting a credential resolved from the environment. In Python the proxy runs as a real local HTTP server (set `HTTP_PROXY` to route through it); TypeScript exposes the same matching/rewriting decision logic without the server transport.

```python
from compart.sandbox.proxy import CredentialProxy, RouteConfig

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

Compartment configs & message routing: routing enforces both directions: the source's `allow_outbound_to` and the destination's `allow_inbound_from`. The default whitelist is `["*"]` (wildcard); an explicitly empty list denies everything.

```python
from compart import Compart
from compart.compartments import Compartment, CompartmentConfig

compart = Compart()
compart.add(Compartment(
    name="fetch",
    fn=lambda ctx: {"fetched": True},
    config=CompartmentConfig(
        permissions=["fs_read", "network"],
        allow_outbound_to=["build"],
    ),
))
compart.add(Compartment(
    name="build",
    fn=lambda ctx: {"built": True},
    config=CompartmentConfig(
        permissions=["fs_read", "fs_write"],
        allow_inbound_from=["fetch"],
    ),
))
compart.edge("fetch", "build")
result = compart.run()
```

### TypeScript

```ts
import * as compart from '@compart/sdk'

compart.runtimeCheckPermission(
  JSON.stringify({ permissions: ['fs_read'] }),
  JSON.stringify(['fs_read']),
) // true

compart.runtimeCheckCommand('rm -rf /') // false

const rt = new compart.Runtime(configs, JSON.stringify([['fetch', 'build']]))
rt.canRoute('fetch', 'build') // true
rt.runOrder()                 // ['fetch', 'build']
rt.names()                    // ['fetch', 'build']
```

For the full SDK guide, see [sdk/README.md](sdk/README.md) and [`docs/TYPESCRIPT_SDK.md`](docs/TYPESCRIPT_SDK.md).

## Documentation Map

- **[Product Validation Guide](docs/VALIDATION_GUIDE.md)**: 60-second test suite comparing agent execution with and without Compart.
- **[Quickstart Guide](docs/QUICKSTART.md)**: 2-minute setup guide for CLI and Python SDK.
- **[Declarative CLI Guide](docs/CLI.md)**: Infrastructure-as-Code workflow, `.compart/topology.json` schema, and Git PR security reviews.
- **[Framework Integration Hooks](docs/FRAMEWORK_HOOKS.md)**: Drop-in sandboxing for LangChain, LangGraph, CrewAI, AutoGen, and Data/RAG agents.
- **[Zero-Trust Credential Proxy](docs/CREDENTIAL_PROXY.md)**: Path rewriting and secret masking for outbound LLM API requests.
- **[BLAKE3 Snapshots & Worktree Rollback](docs/SNAPSHOTS.md)**: Fast workspace hashing, diff tracking, and differential file restoration.
- **[Output Crusher & Token Compression](docs/COMPRESSION.md)**: Log crushing, JSON array compaction, and LLM token reduction.
- **[TypeScript & Node.js SDK](docs/TYPESCRIPT_SDK.md)**: Native NAPI-RS bindings and TypeScript API reference.
- **[CI/CD Security & Acceleration](docs/CI_INTEGRATION.md)**: GitHub Actions and CI runner security integration.
- **[Real-World Use Cases](docs/USE_CASES.md)**: Security scenarios and agent sandboxing patterns.

## Framework hooks

Run AI-agent code inside kernel-enforced compartments from any major agent framework. Hooks are dependency-light: each framework is optional and the hook degrades to a plain duck-typed object when it is absent.

```python
# LangGraph : wrap any node in a sandboxed compartment.
from compart.hooks import CompartGraphNode

def crunch(state, ctx):
    open(f"{ctx.workdir}/out.txt", "w").write(state["value"].upper())
    return {"done": True}

node = CompartGraphNode(crunch, workdir=".")
builder.add_edge(START, node.attach(builder))  # permissions ride on node metadata
```

```python
# LangChain : a Python REPL tool that runs inside Compart, not exec().
from compart.hooks import CompartPythonREPLTool
tool = CompartPythonREPLTool(permission=["fs_read", "fs_write", "fs_exec"])
tool.invoke("print(6 * 7)")
```

```python
# CrewAI : replace the Docker code interpreter with a Compart one.
from compart.hooks import CompartCodeInterpreterTool
agent = Agent(tools=[CompartCodeInterpreterTool()], ...)
```

```python
# AutoGen : runs each code block in a Compart compartment.
from compart.hooks import CompartCodeExecutor, CodeBlock
executor = CompartCodeExecutor()
result = executor.execute_code_blocks([CodeBlock("python", "print('hi')")])
print(result.exit_code, result.output)
```

```python
# Data / RAG agent : isolated workspace, network blocked, no exfiltration.
from compart.hooks import DataScienceSandboxHook
hook = DataScienceSandboxHook()
hook.mount_dataset("customers.csv")
res = hook.run("import pandas as pd; df = pd.read_csv('customers.csv'); print(df.shape)")
print(res.diffs)   # BLAKE3 file diffs the agent caused
```

```python
# Plain CLI coding agent : sandbox any shell command or CLI agent.
from compart.hooks import SandboxRunner
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

ELv2 (Elastic License 2.0). See [CHANGELOG.md](CHANGELOG.md) for release history.
