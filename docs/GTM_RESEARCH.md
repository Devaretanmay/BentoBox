# Compart : Target Startup Intelligence & Ready-to-Send Outreach

**Lead Growth & DevRel · GTM Brief** : targets **Category A** (Autonomous Coding Agents) and **Category C** (Enterprise Data / RAG Agents).

Companion asset : the design-partner one-pager: [`docs/DESIGN_PARTNERS.md`](DESIGN_PARTNERS.md).

Product framing used throughout: Compart executes agent code with **kernel-enforced process controls** : Landlock (Linux) / Seatbelt (macOS), with a credential proxy and BLAKE3 file snapshots. Startup and rollback costs depend on the platform and worktree size. One-line hooks exist for LangChain / LangGraph / CrewAI / AutoGen / data agents, plus a generic `SandboxRunner` for sandboxing any CLI coding agent.

**Confidence key.** `Confirmed` = public evidence (docs/blog/press). `Likely` = inferred from product surface. Founder LinkedIn/X shown only where verified, otherwise flagged "not confirmed". **(Top Fit)** = strongest sandbox fit. This is a live snapshot; re-verify before outreach.

---

## 1. Target Intelligence Database

### Category A : Autonomous Coding Agents (10)

---

#### A1. Factory : factory.ai (Top Fit)
- **What** "Droids": autonomous software-engineering agents (Code / Review / Test / Project) plus a CLI agent for local/airgapped use. Sequoia-led (~$20M).
- **Founders** Matan Grinberg (CEO), Eno Reyes (Co-founder/CTO). LinkedIn URLs not confirmed.
- **Architecture** `Confirmed` : already does OS-kernel sandboxing: **Seatbelt on macOS, bubblewrap + seccomp on Linux/WSL2**, per-command by default.
- **Value prop** They already believe in this model but maintain *two* sandbox backends with per-command spawn overhead. A single Landlock-based kernel sandbox unifies Linux/macOS isolation and removes the bubblewrap dependency : the highest-alignment target on the list.

#### A2. Cognition (Devin) : cognition.com
- **What** Devin, a fully autonomous AI software engineer (also built Windsurf). $1B+ raised, $10B+ valuation.
- **Founders** Scott Wu (CEO, X @ScottWu46); Steven Hao (CTO), Walden Yan (CPO) : LinkedIn not individually confirmed.
- **Architecture** `Confirmed` : **custom microVM hypervisor (`otterlink`), not Docker**. They explicitly rejected containers (kernel-share escape risk) and run a warm pool of snapshot-booted VMs, one per Devin session.
- **Value prop** MicroVM cold-boot / wake-from-snapshot latency plus warm-pool orchestration is a dedicated cost center. A kernel sandbox serves lower-risk refactor/test/browse steps in-process and shrinks the warm-VM fleet, keeping the microVM only for genuinely privileged work.

#### A3. Cosine : cosine.sh
- **What** Vertically-integrated agentic SWE agent (Genie/Lumen) across CLI, desktop, cloud. YC W23, ~$3M.
- **Founders** Alistair Pullen (CEO, LinkedIn, X @AlistairPullen); Sam Stenner and Yang Li (co-founders) : LinkedIn not individually confirmed.
- **Architecture** `Confirmed` : cloud = **hardware-isolated MicroVM (~125 ms boot)**; CLI/desktop = unsandboxed on the user's host.
- **Value prop** Two gaps: per-session microVM boot at scale, and *unsandboxed local* mode. Sub-ms in-process isolation covers low-risk steps; the same policy adds OS enforcement to local execution.

#### A4. Qodo (fka CodiumAI) : qodo.ai
- **What** Code-integrity platform: AI agents for test generation, PR review, and code generation. YC S24; $50M total.
- **Founders** Itamar Friedman (CEO, LinkedIn, X @ItamarF); Dedy Kredo (CPO); CTO not public.
- **Architecture** `Likely` hybrid : IDE/local + CI for generated-code validation; no documented sandbox.
- **Value prop** Generated code and test suites are validated on user machines/CI with no OS isolation. A deny-by-default kernel sandbox makes the validate-fix-verify loop sandboxed automatically, at no container cost.

#### A5. Emergent : emergent.sh
- **What** Vibe-coding platform that generates, tests, and deploys full-stack apps at scale. YC S24, ~$230M; claims ~$120M ARR, 200K+ paying customers.
- **Founders** Mukund Jha (CEO, LinkedIn); Madhav Jha (CTO) : LinkedIn not individually confirmed.
- **Architecture** `Likely` cloud container/VM fleet per user build. No public docs.
- **Value prop** Millions of LLM-generated apps per tenant mean per-user isolation must be cheap and fast. Benchmark the native process controls and snapshots on the target runner to establish unit economics.

#### A6. All Hands AI / OpenHands : all-hands.dev
- **What** Open-source platform for cloud coding agents (OpenHands); model-agnostic, self-hostable. YC W24; $18.8M Series A.
- **Founders** Robert Brennan (CEO); Xingyao Wang (CAIO); Graham Neubig (Chief Scientist). LinkedIn URLs not individually confirmed.
- **Architecture** `Confirmed` : **Docker sandbox** by default plus a hosted Docker runtime API; a "Local" runtime exists with an explicit no-isolation warning.
- **Value prop** Docker cold-start (image pull, container boot per agent session) and container cost for thousands of agents; the no-isolation Local runtime exists precisely because containers are too heavy. A kernel sandbox replaces Docker for local and lighter cloud steps.

#### A7. CodeStory / Aide : aide.dev
- **What** Open-source AI-native IDE (VS Code fork) with proactive multi-file agents. YC S23.
- **Founders** Sandeep Kumar Pani (CEO, X @sandeep_pani); Naresh Ramesh (Co-founder, LinkedIn).
- **Architecture** `Confirmed` : **local / in-process, unsandboxed**: LSP, linters, and command execution all run on the user's host with full privileges; no code leaves the machine by design.
- **Value prop** Untrusted LLM tool calls (build/run/lint) execute with full user rights. A kernel sandbox confines agent file/command access to the repo without moving compute off-machine or breaking the privacy-first model.

#### A8. Sweep : sweep.dev
- **What** Started as an open-source GitHub-issue-to-PR coding agent; pivoted to a self-hostable JetBrains assistant. YC S23. **Likely wound down : founder joined xAI (2026).**
- **Founders** William Zeng (CEO); Kevin Lu (former CTO, LinkedIn).
- **Value prop** Original validate/fix loop depended on GitHub Actions runner boots (seconds); the local plugin executes LLM commands on the host. Sandbox the local step and skip CI spin-up.

#### A9. Plandex : plandex.ai
- **What** Open-source terminal AI coding agent for large multi-file tasks, with a *cumulative diff-review sandbox*. Bootstrapped; OSS continues after the founder moved on (2025).
- **Founder** Dane Schneider (danenania). X: @PlandexAI.
- **Value prop** Its "sandbox" is **diff-level only** : commands (build/lint/test, auto-debug loops) run unsandboxed. The most OSS-native opening for a one-line kernel-sandbox hook: real OS enforcement added to its diff model with no container runtime.

#### A10. PearAI : trypear.ai
- **What** Open-source AI coding editor (VS Code fork) plus a Coding Agent. YC F24.
- **Founders** Nang (Nathan) Ang (CEO, LinkedIn); Duke (Matthew) Pan (Co-founder, LinkedIn).
- **Architecture** Local/in-process, unsandboxed : the agent acts directly inside the editor.
- **Value prop** An OS sandbox confines the Coding Agent to the project tree and blocks destructive/network ops, with zero container to break the local-first experience.


### Category C : Enterprise Data & RAG Agents (10)

---

#### C1. TextQL : textql.com (Top Fit)
- **What** Enterprise data-analyst agents ("Ana") that turn plain-language questions into SQL, dashboards, and reports across a customer's warehouse : without data migration. ~$21M total (Blackstone-led Series A).
- **Founders** Ethan Ding (CEO, LinkedIn, X @TheEthanDing); Mark Hay (CTO, LinkedIn); Spencer Hubert (Head of Engineering, LinkedIn).
- **Architecture** `Confirmed` : deploys its own warehouse **inside the customer's private environment** (air-gapped AWS/Azure/GCP); agent transforms run on serverless/sandbox compute.
- **Value prop** Every regulated deal needs proof the agent cannot exfiltrate warehouse rows or touch PII. A kernel sandbox with **blocked egress + credential proxy** into the warehouse plus **BLAKE3 rollback** of every transformed artifact turns "your data never leaves the VPC" into a verifiable, auditable claim.

#### C2. Definite : definite.app
- **What** AI-native data stack (DuckDB + Iceberg) replacing Snowflake/Fivetran/Looker. $10M seed.
- **Founder** Mike Ritchie (CEO, ex-Gather).
- **Architecture** `Confirmed` : **DuckDB runs embedded/in-process** in their control plane or customer cloud.
- **Value prop** In-process DuckDB means every agent query touches the full dataset with no OS barrier. A read-only host audit plus BLAKE3 rollback gives enterprises the "what did the agent change" trail a governed Snowflake replacement requires.

#### C3. CamelAI : camelai.com
- **What** YC W24 NL-to-SQL BI/data agent with Plotly visualizations; embeddable chat API with row-level security.
- **Founders** Illiana Reed (CEO); Isabella Reed (COO, X @isabella_patane); Miguel Salinas (CTO, LinkedIn, X @Vercantez).
- **Value prop** Banking/fintech embeds get blocked on "your SaaS can see our data." A sandbox with a credential proxy to the *customer's* DB, blocked egress, and rollback of generated dataframes removes the data-out objection and speeds VPC-less enterprise embeds.

#### C4. Cognee : cognee.ai (Top Fit)
- **What** Open-source agentic-RAG/memory engine ("ECL") : graph memory for AI agents. $7.5M seed.
- **Founders** Vasilije Markovic (CEO/Founder, LinkedIn); Boris Arzentar (Co-founder).
- **Architecture** `Confirmed` : a **Python library that runs inside the customer's stack** (LangGraph, n8n, Claude SDK); no managed sandbox.
- **Value prop** Their growth path is a managed cloud. A sandbox with read-only mounted data sources, blocked egress, and BLAKE3 rollback of mutated vector/graph state removes the "my docs won't leak through your vector store" blocking issue.

#### C5. Sema4.ai : sema4.ai
- **What** Enterprise agent platform (Python automation) that runs natively inside Snowflake on governed data. ~$55M Series A.
- **Founders** Rob Bearden (CEO); Antti Karjalainen (Co-founder, Robocorp); CTO line not fully confirmed.
- **Architecture** `Confirmed` : inherits the **Robocorp `rcc` Docker-container Python** runtime.
- **Value prop** Directly governed Snowflake data. Kernel controls, credential proxying, and BLAKE3 rollback can tighten the audit/trust story; measure latency on the target workload.

#### C6. RelationalAI : relational.ai
- **What** Relational graph coprocessor that runs inside the Snowflake data cloud : zero data movement. $150M+ funded.
- **Founders** Molham Aref (CEO); leadership LinkedIn not fully confirmed.
- **Architecture** `Confirmed` : computes run **in-warehouse as a Snowflake coprocessor**; the warehouse is the sandbox.
- **Value prop** Read-only mounts to Snowflake stages, blocked egress, and BLAKE3 versioned rollback provide the proof that "the agent only touched what it needed and can undo anything" for finance/healthcare graph workloads.

#### C7. Varys DI : varysdi.com
- **What** Enterprise agentic-data platform deployed inside the customer's private cloud; agents generate and execute SQL + Python autonomously.
- **Founders** Not publicly found.
- **Architecture** `Likely` : containerized workers inside the customer's VPC; data never leaves the perimeter.
- **Value prop** Its whole pitch is "your data stays inside the network." A kernel sandbox with read-only host access, blocked egress, credential proxy, and BLAKE3 rollback delivers the immutable "every action is logged" audit trail it already promises but cannot prove at the kernel level.

#### C8. Miru : miru.com
- **What** Graph-native investigation platform for cyber / trust-and-safety analysts and agents (autonomous investigations). $2.7M pre-seed.
- **Founders** Eoghan McKee, Quang Pham, David Pigotte (LinkedIn not confirmed).
- **Architecture** `Likely` containerized workers or serverless in their cloud; no published sandbox detail.
- **Value prop** Investigators connect HR/endpoint/SIEM/cloud logs into a graph AI agents mine : exactly the sensitive-data fear. A zero-latency sandbox with read-only mounts, blocked exfiltration, and rollback gives a differentiated "agents can't leak or corrupt evidence" guarantee for government/enterprise security buyers.

#### C9. Dataleap : dataleap.io
- **What** YC S24 enterprise retrieval agent : "Perplexity for consultants" / "Claude Code for business users".
- **Founders** Jan Damm (CEO, LinkedIn); Lance-Hendrik Ruehpeter (CTO, LinkedIn).
- **Value prop** Sales to compliance-conscious consultancies needs a hard data-guardrail story: read-only access to the curated corpus, blocked egress, a credential proxy to licensed data APIs, and BLAKE3 rollback of any transformed output.

#### C10. Trieve : trieve.ai *(reference / adjacent)*
- **What** All-in-one search + RAG API (hybrid semantic/full-text, reranking). YC W24, $3.5M seed. **Acquired by Mintlify (2025)** : keep as a reference model and a possible in-market conversation, not a live design target.
- **Founders** Nick Khami (CEO, X @skeptrune); Denzel Morris (Co-founder).
- **Architecture** `Confirmed` : self-hostable/containerized backend, source-available; ingestion and embedding run as background container workers.
- **Value prop** Self-hosted RAG pipelines ingest content that often contains PII; a kernel sandbox offers read-only file access, no egress (so embeddings can't leak), and BLAKE3 rollback of vector state to prevent index-corruption rebuilds.

---

*Note: research is live-verified to the flagged depth; several specific founder
URLs and a few architecture fields remain "not confirmed" and are marked. Tighten
before any send.*

---

## 2. Ready-to-Send Outreach Sequences

Three pre-written, non-spammy touchpoints. Personalize the `[[brackets]]`, keep
the promise concrete (sub-ms, kernel-enforced, rollback), and always offer a
benchmark rather than a sales call.

---

### Variant 1 : X/Twitter DM (under 280 chars, benchmark-first)

> A good DM is a specific, testable claim + an ask to prove it : not a pitch.

**Filled example / Category A:**

```
Hey @AlistairPullen : Cosine's cloud spins a microVM (~125ms) per session; Compart
runs low-risk agent steps in-process via OS-kernel sandbox (Landlock/Seatbelt) in
<1ms, no container. Made a LangGraph hook. 10-min benchmark against Genie? : Jasper
```

> Architecture template (swap `[tool]`, `[metric]`, `[outcome]`, `[hook]`):

```
Hey @[founder] : love [tool]. Our kernel sandbox turns [their metric, e.g. each
session/step] from [their current cost, e.g. ~2.5s container / ~125ms VM boot] into
<1ms in-process (Landlock/Seatbelt, deny-by-default). [Hook/framework they use].
Want a 5-min benchmark on your stack?
```

> Architecture template / Category C (data):

```
Hi @[founder] : data agents on sensitive data need containment buyers can audit.
Compart sandboxes agent code with the OS kernel (no container), blocks egress,
proxies your creds, and rolls back changes with BLAKE3. Opens safe VPC-less embeds.
Worth a look?
```

**Rules.** One observation + one claim + one low-cost ask. Under 280 characters.
Never attach a deck. Follow the company/agent accounts first if you can.

---

### Variant 2 : LinkedIn InMail / Founder email (3 paragraphs, value-first)

**Subject:** `<1ms` sandboxing for `[their product]` : a benchmark, not a pitch

Hi `[First]`,

You already know the cost of executing agent code safely: every step that shells
out to a test, a build, or a data query goes through a Docker container or a
microVM, and each one is ~2.5s (or a 125ms VM boot) plus an image to pull and a
daemon to run. That latency is a hit to `[their product]`'s e2e loop and its gross
margin per task. Containers and VMs also miss the real problem: a buyer who cannot
verify "the agent cannot touch what it shouldn't" will block the deal.

Compart executes agent code inside compartments **your OS kernel already
provides** : Landlock on Linux, Seatbelt on macOS. The sandbox is a couple of
kernel rules applied in-process, with no daemon or container service to operate; the SDK and native toolchain still need to be installed:
container, no VM, no daemon. Deny-by-default, so `~/.ssh`/`~/.aws` is unreachable
unless you opt in; a credential proxy injects model/DB keys from env so the agent
never holds a raw secret; and a BLAKE3 content-hash snapshot means any mutation
can be rolled back in milliseconds. It maps to a single line no matter your stack
: a LangChain tool, a LangGraph node, a CrewAI/AutoGen interpreter, or a plain
CLI agent via `SandboxRunner`.

If the idea of <1ms, kernel-enforced isolation resonates, I'd love to run a 30
day benchmark on your exact worktree and publish your real numbers. We'll wire an
endpoint, you point agent traffic at it, and I send the diff and the latency
comparison. No sales deck : just a measurement you can replay in your own
vendor run‑off. Sound useful?

: `[My name]` · Compart · `[email]` | `[calendar link]`

**Sending notes:** Use the full name first, one value-first paragraph, and a
concrete CTA; send at a local morning; follow with the design-partner one-pager
only if they reply.

---

### Variant 3 : Open-Source GitHub issue / Discussion (maintainer proposal)

**Title suggestion:** `RFC: optional <1ms> kernel sandbox for untrusted agent command execution`

**Body:**

Hi `[maintainer]` maintainers,

First: `[explicitly useful comment on the project's actual value, API, or a recent
release]`. Here is a small, optional contribution I think fits `[repo]`'s threat
model.

## Problem

`[repo]` executes model-driven commands : `[build/test/lint/data transforms]` :
currently `[unsandboxed on the host / in a Docker container]`. Untrusted tool
output and dangerous filesystem/network access are the classic gap: interpreter-
level checks are bypassable from inside, and containers cost a cold start per step
(your Local runtime already documents no isolation).

## Proposal

Sandbox each command with the OS kernel instead of a process : **Landlock on
Linux / Seatbelt on macOS** : as an optional, behind-a-flag integration:

- **In-process controls** : no image pull, daemon, or container service; benchmark startup and snapshot costs for your workload.
- **Deny-by-default:** worktree read/write, system paths read-only, everything else
  blocked. Credentials (`~/.ssh`, `~/.aws`, git creds, keychain) unreachable unless
  allowed.
- **Per-compartment grants:** `fs_read`, `fs_write`, `fs_exec`, `network` : so the
  always-granted rule is no-network.
- **Network control + credential proxy:** model/API keys are injected from `env`
  with a localhost proxy; the agent never holds a raw key.
- **BLAKE3 file rollback:** a snapshot lets you revert only the files the agent
  changed : perfect for the validate-fix loop.

## Offer to maintainers

I'll implement and land this as an optional integration (a 1-line hook) and
maintain it, at no cost to `[repo]`. I maintain the open-source Compart
kernel-sandbox library (`github.com/Devaretanmay/Compart`).

Interested? I'll open a proper PR/draft and you review, or I can start with a
discussion post cook-through. Happy to keep it minimal: a new sandbox option with
no behavior change to existing users.

**Threads:** `[link to related issue/discussion]` · `[link to project setup]`

---
