# Compart Agent Execution

## What it is

When you run `compart init`, Compart turns your project directory into a **managed agent workspace**. You launch your favorite agent directly inside an isolated kernel sandbox.

---

## How it works

```text
compart init
└── creates .compart/
    ├── config.yaml    <- workspace compartment policy
    ├── state/         <- runtime state
    ├── snapshots/     <- BLAKE3 worktree diff snapshots
    └── executions/    <- execution records

Direct Execution:
  $ compart claude      -> Launches Claude in kernel sandbox
  $ compart opencode    -> Launches OpenCode in kernel sandbox
  $ compart codex       -> Launches Codex in kernel sandbox
```

---

## Running Interactive Coding Agents

```bash
compart claude
compart opencode
compart codex
```

Each interactive agent runs with:
- Full native TUI support (colors, alternate screen, Ctrl+C, Ctrl+D, window resize).
- Hard OS-level kernel isolation (Seatbelt on macOS / Landlock on Linux).
- Deny-by-default credential protection (`~/.ssh`, `~/.aws`, git credentials blocked).
- Automatic BLAKE3 pre-execution snapshots for physical instant rollback (`compart undo`).

---

## Checking Workspace Status

```bash
compart status
```

```text
COMPART WORKSPACE: my-project

AGENTS RUNNING
  * claude      default      pid:12345   0 change(s)  (4s)

LANES
  auth-fix    Claude Code   COMPLETED   1 file(s)

SECURITY
  2 blocked action(s)
```

---

## Running Multi-Agent Workflows

Run a declared workflow DAG:

```bash
compart run feature-development
```

Or run standalone Python agent scripts:

```bash
compart run my_langgraph.py --compartment builder
```
