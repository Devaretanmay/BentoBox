import argparse
import sys
import json
import logging
import os
import shlex

from compart.compart import Compart, AgentCompart, CompartConfig
from compart.compartments import Compartment, CompartmentConfig
from compart.hooks.base import SandboxRunner

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
    
    # Materialize declared topology into an ephemeral AgentCompart
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


def main():
    parser = argparse.ArgumentParser(
        description="Compart CLI - Declarative runtime manager for isolated agent execution"
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # compart init
    init_parser = subparsers.add_parser("init", help="Initialize a new declarative compart project")

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
    run_parser = subparsers.add_parser("run", help="Materialize declared topology into ephemeral runtime")

    # compart exec -- <command>
    exec_parser = subparsers.add_parser("exec", help="Run an ephemeral command inside a sandbox")
    exec_parser.add_argument("cmd", nargs=argparse.REMAINDER, help="Command to run")

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
