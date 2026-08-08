# BentoBox Design Partner Program

> Give your enterprise buyers a containment story their security team can audit,
> and let your agents execute at kernel speed instead of container speed.

---

## 1. Executive Summary

Every AI agent runs code the model wrote and that you cannot fully predict. Today
most agent products contain that code with containers or microVMs — secure walls,
but **heavy**: images to pull, runtimes to install, seconds of startup for every
agent step, and a fleet you have to scale, patch, and pay for.

BentoBox flips the trade. It enforces the same boundary that your **operating
system kernel** already provides — Landlock on Linux, Seatbelt on macOS. A
sandbox is a few kernel rules **applied in milliseconds**, with no marginal cost
at runtime: no daemon, no container image, no VM to boot, nothing to install.

Why this matters for a design partner:

- **Latency is margin.** For coding agents, every sandbox cold-start per agent
  step is pure overhead on a per-task basis.
- **Containment is trust.** For enterprise data/RAG agents, the buyer's security
  team blocks deals when they cannot verify the agent "cannot touch what it
  should not." Kernel-enforced, deny-by-default policy is something a security
  engineer can read and believe.
- **Undo is governance.** Instant BLAKE3 file rollback gives you an auditable
  "what did the agent change" trail — the missing proof in governed deployments.

---

## 2. Why Zero-Latency Kernel Sandboxing Beats Heavy Containers

| Dimension | BentoBox (Landlock / Seatbelt) | Docker | MicroVM (Firecracker/Lambda-style) |
| :--- | :--- | :--- | :--- |
| Isolation enforced by | The OS kernel, per syscall | Kernel + daemon + user namespaces | Separate hypervisor (strongest) |
| **Per-step / session startup** | **<1 ms** — apply the rule set | **~2.5 s+** — pull image, daemon, mount | **~125 ms–1 s** — boot from snapshot w/ warm pool |
| Memory/resource overhead | **In-process**; no guest OS, no daemon resident per unit | Per-container overhead + daemon | Full guest kernel + guest memory footprint |
| What must be installed | **Nothing** — the OS ships it | Container runtime + daemon (image lifecycle) | Hypervisor + provisioning/orchestration |
| Bypass surface | Kernel rejects the syscall itself (subprocess included) | Namespace escape is a known attack class | Hardest to escape, heaviest to run |
| Per-user agent scale & cost | Sub-millisecond per compartment | Pay per container creation + daemon | Pay per VM + warm-pool orchestration |

BentoBox does not remove the microVM from your stack — it removes the **need**
to pay for a container/VM on every low-risk step. For genuinely privileged work,
keep the VM **behind the same BentoBox policy**. You get VM-grade isolation where
you actually need it and near-free isolation everywhere else, with fewer moving
parts than running containers for every step.

> **Numbers are representative of real kernel-rule application vs container and
> microVM cold-starts.** We provide a `bench.py` to Design Partners so you can
> measure on your exact hardware and publish real numbers.

---

## 3. What BentoBox Provides

1. **Dedicated maintainers channel.** A private Slack/Discord with the BentoBox
   engineers — a working relationship, not a support ticket queue.

2. **Custom Landlock / Seatbelt policies.** We design the rule sets for *your*
   worktree, *your* file layout, *your* network topology and API endpoints,
   rather than shipping generic defaults.

3. **Zero-cost integration assistance.** Wiring a kernel sandbox into your
   framework (LangChain, LangGraph, CrewAI, AutoGen, or a plain CLI agent) is on
   us. Dedicated implementations for your runtime so the 1-line integration
   actually lands in production.

4. **Co-marketing.** A technical blog post that goes out under both banners
   (your engineers' trust), a spotlight slot in our series, and your logo on our
   website and the GitHub README.

---

## 4. What the Design Partner Agrees To

1. **Production stress-testing.** Point real agent traffic and realistic untrusted
   scenarios at the sandbox. We want the honest weakness list — hard data is the
   highest-value thing you can give.

2. **Feedback sessions.** One recurring 30-minute sync per month
   for the first 12 weeks, with the engineers who will actually ship it, so the
   product reacts to reality.

3. **Public attestation.** A logo, a "sandboxed with BentoBox" badge, and a line
   in the docs noting the integration that handled in pre-production. Low friction,
   honest, and reviewable.

**Duration.** A minimum 12-week design-partner term, renewable. **SLA.** We
guarantee maintainer response within **3 hours** (business hours) for the
duration. Everything is a defensive first-refusal for a future commercial license;
see **§6 Commercial intent**.

---

## 5. Technical Specifications

**Approach:** Apply a `LANDLOCK_*` ruleset on Linux (kernel ≥ 5.13) or a
Seatbelt profile on macOS. Deny by default, then grant only what a compartment
declares. Irreversible in-process once applied — it can only be tightened, never
loosened — which is what makes the invariant achievable.

| Capability | Specification |
| :--- | :--- |
| **Enforcement model** | Kernel-enforced per-syscall; a write/exec/network against a shaded path is denied by the kernel — including from a subprocess. |
| **Permissions (per compartment)** | `fs_read`, `fs_write`, `fs_exec`, `network`, `gpu`, `sys_info`. Compose per unit of work; default is read-only. |
| **Latency** | Rule-set application measured in **<1 ms**; runtime enforcement cost ~0 (the rules live in the kernel, not interpreters). |
| **Memory footprint** | In-process; no guest OS, no per-unit container, negligible per-compartment rule state. |
| **Network control** | Full, localhost-only, or blocked, per box. Default **no outbound exfiltration route**. |
| **Credential proxy** | Route rules `prefix` + `upstream` rewrite the request and inject API keys from env (`credential_source: "env:VAR"`). The agent **never holds a raw secret**; a localhost reverse-proxy strips hop-by-hop headers. |
| **Snapshots & rollback** | BLAKE3 content-addressed index of the worktree before execution; **roll back only the files that changed**; deleted files are restored from a snapshot index. Auditable per agent run. |
| **Framework hooks (1-line)** | `BentoPythonREPLTool` (LangChain), `BentoBoxGraphNode` (LangGraph), `BentoBoxCodeInterpreterTool` (CrewAI), `BentoBoxCodeExecutor` (AutoGen), `DataScienceSandboxHook` (data/RAG). |
| **SDKs** | Python and TypeScript over a single Rust core. |
| **Compression** | Long compartment output is compressed before it is stored or returned. |
| **License** | BUSL‑1.1, with a no-change commercial conversion clause for design partners on a private bench. |

---

## 5.1 How to wire it in practice

The production path for a coding agent: run the agent through a
`SandboxRunner` with a credential proxy into the model API — the agent cannot
read `~/.ssh`, `~/.aws`, or write outside its worktree, and it never touches a
raw API key:

```
from bentoworks.hooks import SandboxRunner
from bentoworks.sandbox.proxy import RouteConfig

SandboxRunner(workdir=".", block_network=True,
              credential_rules=[RouteConfig(
                  prefix="/v1",
                  upstream="https://api.anthropic.com",
                  credential_source="env:ANTHROPIC_API_KEY",
              )]).run("claude -p 'fix the bug'")
```

For a data agent: mount only the datasets the agent may see into an
isolated workspace, block egress, and read the BLAKE3 diff to see exactly what
changed:

```
hook = DataScienceSandboxHook()
hook.mount_dataset("customers.csv")          # only this is visible
res = hook.run("df = pd.read_csv('customers.csv'); df.to_parquet('out.parquet')")
print(res.diffs)                             # audited agent mutations
```

---

## 5.2 Why this is different from what you run today

- **E2B / Modal / Firecracker sandboxes** — remote execution: every safe step
  crosses a network boundary to a remote VM, billing per-VM-second and shipping
  data out of process. BentoBox stays **colocated with your agent**, no network
  hop per step, no per-VM cost per user.
- **Interpreter-level sandboxes** — clean API surface but **bypassable from
  inside**: every dangerous call must be re-checked, and a C-extension escape
  defeats the gate. BentoBox's kernel does the rejecting, including for
  subprocesses.
- **Docker** — the same isolation behavior you are used to seeing in a stack,
  but in milliseconds, with nothing to install and no daemon to run.

If your buyer's security team currently answers "we will never let agents touch
our warehouse" with a no, BentoBox is the technical step up to turn that into a
reason. Hand them the kernel rules to inspect, and let the agent be audited.

---

## 6. Commercial intent

Design-partner today, commercial license conversion when you ship in revenue.
BUSL‑1.1 source today; a conversion option + SLA under YOUR account. No catch;
we want partners that become customers when the numbers are real.

---

## 7. Next step

Send your founder/CTO and an engineering lead to **design-partner@bentoworks.dev**
and we send back a **Day‑1 packet**: a wrapped microbenchmark, a test policy set
writing for your worktree, an empty integration ticket — 30 minutes to first
results. No sales call, no long questionnaire: ship, and tell us what breaks.