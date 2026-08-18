# Compart Workspace Activation

## What it is

When you run `compart init`, Compart turns your project directory into a **managed workspace**. You can launch your favorite agent directly or via shell PATH activation.

---

## How it works

```text
compart init
└── creates .compart/
    ├── bin/
    │   ├── claude     <- shim script
    │   ├── codex      <- shim script
    │   └── opencode   <- shim script
    ├── activate       <- source to activate manually
    ├── config.yaml    <- workspace compartment policy
    └── ...

Option A: Direct Launch (Recommended)
  $ compart claude      -> Launches Claude in kernel sandbox

Option B: Shell Activation
  $ source .compart/activate
  $ claude              -> Intercepted by .compart/bin/claude
```

---

## Direct Launch vs Activation

### Option 1: Direct Command (Zero Setup)
```bash
compart claude
compart opencode
```

### Option 2: Session Activation (One-time per shell)
```bash
source .compart/activate

# Or with direnv:
direnv allow

# Now type agent commands normally:
claude
opencode
```

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

Run a declared workflow DAG or workflow file:

```bash
compart run feature-development
```

Or run standalone Python agent scripts:

```bash
compart run my_langgraph.py --compartment builder
```
