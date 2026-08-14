import argparse
import sys
import json
import logging
import os
import shlex
import time

from compart.compart import Compart, AgentCompart, CompartConfig
from compart.compartments import Compartment, CompartmentConfig
from compart.hooks.base import SandboxRunner
from compart.engine.session import SessionManager, AgentSession

_logger = logging.getLogger("compart.cli")

COMPART_DIR = ".compart"
TOPOLOGY_FILE = os.path.join(COMPART_DIR, "topology.json")


def _print_json(data: dict):
    print(json.dumps(data, indent=2))


def _load_topology() -> dict:
    if not os.path.exists(TOPOLOGY_FILE):
        print(f"Error: Not a compart project (missing {TOPOLOGY_FILE}). Run 'compart init' first.")
        sys.exit(1)
    with open(TOPOLOGY_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_topology(topo: dict):
    with open(TOPOLOGY_FILE, "w", encoding="utf-8") as f:
        json.dump(topo, f, indent=2)
        f.write("\n")


def cmd_init(args):
    """Initialize a new declarative compart project."""
    os.makedirs(os.path.join(COMPART_DIR, "state"), exist_ok=True)
    os.makedirs(os.path.join(COMPART_DIR, "logs"), exist_ok=True)
    os.makedirs(os.path.join(COMPART_DIR, "snapshots"), exist_ok=True)
    os.makedirs(os.path.join(COMPART_DIR, "sessions"), exist_ok=True)

    if os.path.exists(TOPOLOGY_FILE):
        print(f"Reinitialized existing Compart project in {os.path.abspath(COMPART_DIR)}")
        return
        
    project_name = os.path.basename(os.path.abspath("."))
    topology = {
        "name": project_name,
        "compartments": {},
        "connections": []
    }
    _save_topology(topology)
    print(f"Initialized empty Compart project '{project_name}' in {os.path.abspath(COMPART_DIR)}")


def cmd_inspect(args):
    """Dump declarative topology and state of the current project."""
    topology = _load_topology()
    if args.json:
        _print_json(topology)
    else:
        print(f"Compart Project: {topology.get('name', 'unnamed')}")
        comps = topology.get("compartments", {})
        conns = topology.get("connections", [])
        
        if not comps and not conns:
            print("Declared Topology: (empty)")
        else:
            print("Declared Topology:")
            print("  Compartments:")
            for name, cfg in comps.items():
                perms = cfg.get("permissions", [])
                print(f"    - {name} (permissions: {perms})")
            print("  Connections:")
            for edge in conns:
                if isinstance(edge, (list, tuple)) and len(edge) >= 2:
                    print(f"    - {edge[0]} -> {edge[1]}")


def cmd_compartment_create(args):
    """Define a new inner compartment in topology.json."""
    topology = _load_topology()
    comps = topology.setdefault("compartments", {})
    
    if args.name in comps:
        print(f"Error: Compartment '{args.name}' already declared.")
        sys.exit(1)
            
    comps[args.name] = {
        "permissions": ["fs_read"]  # Default base permission
    }
    _save_topology(topology)
    print(f"Registered inner compartment '{args.name}'.")


def cmd_connect(args):
    """Establish a directional connection between two inner compartments."""
    topology = _load_topology()
    comps = topology.get("compartments", {})
    
    if args.source not in comps:
        print(f"Error: Source compartment '{args.source}' not declared in topology.json.")
        sys.exit(1)
    if args.target not in comps:
        print(f"Error: Target compartment '{args.target}' not declared in topology.json.")
        sys.exit(1)
        
    conns = topology.setdefault("connections", [])
    edge = [args.source, args.target]
    if edge not in conns:
        conns.append(edge)
        
    _save_topology(topology)
    print(f"Connected '{args.source}' -> '{args.target}'.")


def cmd_run(args):
    """Materialize the declared topology into an ephemeral isolated kernel runtime."""
    topology = _load_topology()
    comps = topology.get("compartments", {})
    if not comps:
        print("Error: No compartments declared in topology.json. Run 'compart compartment create <name>' first.")
        sys.exit(1)
        
    print(f"Materializing declared topology for '{topology.get('name', 'unnamed')}'...")
    
    compart = AgentCompart(workdir=".", verbose=True)
    
    for name, cfg in comps.items():
        perms = cfg.get("permissions", ["fs_read"])
        
        def dummy_fn(ctx, n=name):
            print(f"[{n}] Executing inside kernel sandbox...")
            return {"status": "ok"}
            
        compart.add(Compartment(
            name=name,
            fn=dummy_fn,
            config=CompartmentConfig(permissions=perms)
        ))
        
    for edge in topology.get("connections", []):
        if isinstance(edge, (list, tuple)) and len(edge) >= 2:
            compart.edge(edge[0], edge[1])
        
    result = compart.run()
    if result.status == "error":
        print(f"\nExecution failed: {result.errors}")
        sys.exit(1)
    else:
        print("\nExecution succeeded.")


def cmd_exec(args):
    """Execute a single command in an ephemeral agent compartment."""
    cmd_str = shlex.join(args.cmd)
    print(f"Executing: {cmd_str}")
    
    runner = SandboxRunner(workdir=".", verbose=True)
    result = runner.run(
        cmd_str, 
        permissions=["fs_read", "fs_write", "fs_exec", "network"]
    )
    
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)
        
    if result.returncode != 0:
        print(f"\nExecution failed with code {result.returncode}")
        if result.error:
            print(f"Error: {result.error}")
        sys.exit(result.returncode)
    else:
        print("\nExecution succeeded.")


def cmd_wrap(args):
    """Transparently wrap any CLI agent command in a managed AgentSession under kernel isolation."""
    agent_name = args.agent or "Claude Code"
    task = args.task
    cmd_str = ""
    env_vars = {}

    if args.claude is not None:
        agent_name = "Claude Code"
        raw_task = args.claude.strip()
        if raw_task.startswith("[") and raw_task.endswith("]"):
            raw_task = raw_task[1:-1].strip()
        task = raw_task or task or "Claude Code Execution Task"
        if not args.cmd:
            cmd_str = f"claude -p {shlex.quote(task)}"

    elif getattr(args, "opencode", None) is not None:
        agent_name = "OpenCode"
        raw_task = args.opencode.strip()
        if raw_task.startswith("[") and raw_task.endswith("]"):
            raw_task = raw_task[1:-1].strip()
        task = raw_task or task or "OpenCode Execution Task"

        # Isolate OpenCode XDG directories inside .compart/xdg/
        xdg_base = os.path.abspath(os.path.join(".compart", "xdg"))
        for sub in ["config", "data", "cache", "state"]:
            os.makedirs(os.path.join(xdg_base, sub), exist_ok=True)
        env_vars.update({
            "XDG_CONFIG_HOME": os.path.join(xdg_base, "config"),
            "XDG_DATA_HOME": os.path.join(xdg_base, "data"),
            "XDG_CACHE_HOME": os.path.join(xdg_base, "cache"),
            "XDG_STATE_HOME": os.path.join(xdg_base, "state"),
        })
        if not args.cmd:
            cmd_str = f"opencode run {shlex.quote(task)}" if task else "opencode --help"

    if not cmd_str and args.cmd:
        cmd_str = shlex.join(args.cmd)
        if not task:
            task = cmd_str

    if not cmd_str:
        print("Error: No command or task provided to wrap.")
        print("Usage examples:")
        print("  compart wrap -c \"Fix auth bug\"")
        print("  compart wrap -o \"Fix auth bug\"")
        print("  compart wrap -- opencode run \"explain repo\"")
        sys.exit(1)

    mgr = SessionManager(workdir=".")
    session = mgr.create_session(
        agent_name=agent_name,
        task=task,
        compartment_name="WrappedAgent",
        permissions=["fs_read", "fs_write", "fs_exec"]
    )

    print(f"Compart Agent Session #{session.session_id} active.")
    print(f"Governing agent command under kernel sandbox: {cmd_str}")

    runner = SandboxRunner(workdir=".", verbose=args.verbose)
    result = runner.run(
        cmd_str,
        permissions=["fs_read", "fs_write", "fs_exec"],
        env=env_vars if env_vars else None,
    )

    if result.stdout:
        print("\n--- Agent Output ---")
        print(result.stdout)
        print("--------------------")

    session.log_action("EXECUTE", cmd_str, status="OK" if result.success else "FAILED", details=f"returncode={result.returncode}")
    session.complete(returncode=result.returncode, diffs=result.diffs)
    mgr.save_session(session)

    print("\n" + session.format_ascii_view())


def cmd_sessions(args):
    """List all recorded AgentSessions."""
    mgr = SessionManager(workdir=".")
    sessions = mgr.list_sessions()
    if not sessions:
        print("No recorded agent sessions found. Run 'compart wrap' or 'compart run' first.")
        return
    print(f"Recorded Agent Sessions ({len(sessions)}):")
    for s in sessions:
        duration = round((s.ended_at or time.time()) - s.started_at, 2)
        print(f"  - [{s.session_id}] {s.agent_name} | Task: '{s.task}' | Status: {s.status.upper()} | Diffs: {len(s.diffs)} file(s) ({duration}s)")


def cmd_session_inspect(args):
    """Inspect structured logs and diffs for a given AgentSession."""
    mgr = SessionManager(workdir=".")
    session = mgr.get_session(args.session_id)
    if not session:
        print(f"Error: Session '{args.session_id}' not found.")
        sys.exit(1)
    if args.json:
        _print_json(session.to_dict())
    else:
        print(session.format_ascii_view())


def cmd_session_rollback(args):
    """Roll back workspace state for a given AgentSession."""
    mgr = SessionManager(workdir=".")
    success = mgr.rollback_session(args.session_id)
    if success:
        print(f"Workspace successfully rolled back to state prior to Session #{args.session_id}.")
    else:
        print(f"Error: Failed to roll back Session #{args.session_id}.")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Compart CLI - Control layer for AI agents and workflows"
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # compart init
    subparsers.add_parser("init", help="Initialize a new declarative compart project")

    # compart inspect [--json]
    inspect_parser = subparsers.add_parser("inspect", help="Dump declarative topology and project state")
    inspect_parser.add_argument("--json", action="store_true", help="Output raw JSON topology")

    # compart compartment create <name>
    comp_parser = subparsers.add_parser("compartment", help="Manage declared inner compartments")
    comp_subparsers = comp_parser.add_subparsers(dest="compartment_command")
    comp_create_parser = comp_subparsers.add_parser("create", help="Define a new inner compartment")
    comp_create_parser.add_argument("name", help="Name of the inner compartment")

    # compart connect <source> <target>
    connect_parser = subparsers.add_parser("connect", help="Establish a connection between two declared compartments")
    connect_parser.add_argument("source", help="Source compartment")
    connect_parser.add_argument("target", help="Target compartment")
    
    # compart run
    subparsers.add_parser("run", help="Materialize declared topology into ephemeral runtime")

    # compart exec -- <command>
    exec_parser = subparsers.add_parser("exec", help="Run an ephemeral command inside a sandbox")
    exec_parser.add_argument("cmd", nargs=argparse.REMAINDER, help="Command to run")

    # compart wrap [-c TASK] [-o TASK] [--agent AGENT] [--task TASK] -- <command>
    wrap_parser = subparsers.add_parser("wrap", help="Transparently govern any CLI agent in a managed AgentSession")
    wrap_parser.add_argument("-c", "--claude", nargs="?", const="", help="Claude Code shortcut with task in quotes or [brackets]")
    wrap_parser.add_argument("-o", "--opencode", nargs="?", const="", help="OpenCode shortcut with task in quotes or [brackets]")
    wrap_parser.add_argument("--agent", default="Claude Code", help="Agent name (default: 'Claude Code')")
    wrap_parser.add_argument("--task", default="", help="Task description")
    wrap_parser.add_argument("--verbose", action="store_true", help="Enable lifecycle tracer")
    wrap_parser.add_argument("cmd", nargs=argparse.REMAINDER, help="Agent command to wrap")

    # compart sessions
    subparsers.add_parser("sessions", help="List all recorded agent sessions")

    # compart session inspect/rollback <session_id>
    session_parser = subparsers.add_parser("session", help="Manage and inspect agent sessions")
    session_subparsers = session_parser.add_subparsers(dest="session_command")

    sess_inspect_parser = session_subparsers.add_parser("inspect", help="Inspect an agent session")
    sess_inspect_parser.add_argument("session_id", help="Session ID")
    sess_inspect_parser.add_argument("--json", action="store_true", help="Output raw JSON")

    sess_rollback_parser = session_subparsers.add_parser("rollback", help="Roll back workspace to pre-session state")
    sess_rollback_parser.add_argument("session_id", help="Session ID")

    args = parser.parse_args()

    if args.command == "init":
        cmd_init(args)
    elif args.command == "inspect":
        cmd_inspect(args)
    elif args.command == "run":
        cmd_run(args)
    elif args.command == "exec":
        if args.cmd and args.cmd[0] == "--":
            args.cmd = args.cmd[1:]
        cmd_exec(args)
    elif args.command == "wrap":
        if args.cmd and args.cmd[0] == "--":
            args.cmd = args.cmd[1:]
        cmd_wrap(args)
    elif args.command == "sessions":
        cmd_sessions(args)
    elif args.command == "session":
        scmd = getattr(args, "session_command", None)
        if scmd == "inspect":
            cmd_session_inspect(args)
        elif scmd == "rollback":
            cmd_session_rollback(args)
        else:
            session_parser.print_help()
    elif args.command == "compartment":
        if getattr(args, "compartment_command", None) == "create":
            cmd_compartment_create(args)
        else:
            comp_parser.print_help()
    elif args.command == "connect":
        cmd_connect(args)
    else:
        parser.print_help()


def cli():
    main()


if __name__ == "__main__":
    cli()
