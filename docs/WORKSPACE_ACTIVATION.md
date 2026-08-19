# Compart Workspace Initialization & Agent Execution

## 1. What It Is

When you run `compart init`, Compart turns your project directory into a **managed agent workspace**. You launch your favorite agent directly inside an isolated kernel sandbox.

---

## 2. How It Works

```text
compart init
└── creates .compart/
    ├── config.yaml    <- workspace compartment policy
    ├── state/         <- runtime state
    ├── snapshots/     <- BLAKE3 worktree diff snapshots
    └── executions/    <- execution records

Direct Execution:
  $ compart claude      -> Launches Claude Code in kernel sandbox
  $ compart opencode    -> Launches OpenCode in kernel sandbox
  $ compart codex       -> Launches Codex in kernel sandbox
  $ compart cursor      -> Launches Cursor in kernel sandbox
  $ compart aider       -> Launches Aider in kernel sandbox
```

---

## 3. Running Interactive Coding Agents

```bash
compart claude
compart opencode
compart codex
compart cursor
compart aider
```

Each interactive agent runs with:
- Full native TUI support (colors, alternate screen, Ctrl+C, Ctrl+D, window resize).
- Hard OS-level kernel isolation (Seatbelt on macOS / Landlock on Linux).
- Deny-by-default credential protection (`~/.ssh`, `~/.aws`, `~/.config/gcloud` blocked).
- Automatic BLAKE3 pre-execution snapshots for physical instant rollback (`compart undo`).

---

## 4. Checking Workspace Health

```bash
compart status
```

```text
COMPART WORKSPACE: billing-service

AGENTS RUNNING
  none

RECENT SESSIONS
  [OK] Claude       lane:default_lane 1 change(s)  (0.5s)

SECURITY
  0 blocked action(s)
  0 credential escapes
```

---

## 5. Running Multi-Agent Workflows

Run a declared workflow DAG:

```bash
compart --run invoice-pipeline
```

Or run standalone Python agent scripts:

```bash
compart exec --compartment research -- python3 scraper.py
```
