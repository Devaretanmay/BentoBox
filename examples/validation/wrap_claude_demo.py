"""Validation Test for Phase 3 & 4: AgentSession & Transparent Agent Wrapper (`compart wrap`).

Demonstrates:
- Creating and persisting an AgentSession primitive.
- Executing an agent task under OS kernel sandbox isolation.
- Formatted AgentSession ASCII view with activity logs and BLAKE3 file diffs.
"""

from compart.engine.session import SessionManager

print("=== Compart Control Layer Demo: AgentSession & Transparent Wrapper ===")

mgr = SessionManager(workdir=".")

# 1. Create a managed AgentSession
session = mgr.create_session(
    agent_name="Claude Code",
    task="Fix authentication bug in auth.py",
    compartment_name="Builder",
    permissions=["fs_read", "fs_write", "fs_exec"]
)

# 2. Log activity actions
session.log_action("READ", "src/auth.py", status="OK")
session.log_action("EXECUTE", "pytest tests/test_auth.py", status="OK", details="14 passed")
session.log_action("EXECUTE", "curl http://external-eval.com", status="BLOCKED_BY_KERNEL", details="network egress denied")

# 3. Complete session with mock diff
session.complete(returncode=0, diffs=[{"path": "src/auth.py", "status": "modified"}])
mgr.save_session(session)

print(session.format_ascii_view())

print("\nListing recorded sessions:")
for s in mgr.list_sessions():
    print(f"  - [{s.session_id}] {s.agent_name} | Task: {s.task} | Status: {s.status}")
