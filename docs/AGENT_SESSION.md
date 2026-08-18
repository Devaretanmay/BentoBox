# AgentSession Primitive & Transparent CLI Wrapper (`compart wrap`)

Compart introduces `AgentSession` as a first-class primitive representing an agent's execution session. It captures agent identity, workflow state, permission boundaries, activity logs (`[OK]` vs `[BLOCKED_BY_KERNEL]`), and BLAKE3 workspace diffs.

---

## 1. The `AgentSession` Abstraction

```text
Agent Session #sess_1723635840000
────────────────────────────────────────────────────────────────
Agent       : Claude Code
Task        : Fix authentication bug
Workflow    : Execution
Compartment : WrappedAgent
Permissions : ['fs_read', 'fs_write', 'fs_exec']
Status      : COMPLETED (Exit code: 0)
Duration    : 0.15s
----------------------------------------------------------------
Activity Log:
  [OK] EXECUTE -> python3 -c "open('auth.py', 'w').write('# Fix')"
----------------------------------------------------------------
Changes (1 file(s)):
  MODIFIED: auth.py
================================================================
```

---

## 2. Transparent Agent Wrapper (`compart wrap`)

Govern any CLI agent (Claude Code, Cursor, Codex, custom scripts) transparently without changing how you use your tools:

```bash
# Wrap Claude Code under Compart control
compart wrap --agent "Claude Code" --task "Fix auth bug" -- claude

# Wrap a python agent script
compart wrap --agent "DataAgent" --task "Analyze data" -- python3 agent.py
```

---

## 3. Session Management CLI Commands

### List Agent Sessions
```bash
compart sessions
```

### Inspect an Agent Session
```bash
compart session inspect sess_1723635840000
compart session inspect sess_1723635840000 --json
```

### Roll Back Workspace to Pre-Session State
```bash
compart session rollback sess_1723635840000
```
Restores modified or deleted files and purges untrusted new files created during that session.
