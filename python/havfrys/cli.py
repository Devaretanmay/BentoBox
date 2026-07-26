"""havfrys — developer CLI."""

import argparse
import sys
from havfrys.server import run_server
from havfrys.installer import run_init_wizard, run_doctor


def cmd_serve(args: argparse.Namespace) -> int:
    run_server(sse=args.sse, host=args.host, port=args.port)
    return 0


def cmd_init(args: argparse.Namespace) -> int:
    run_init_wizard(choice=args.select, auto_all=args.all)
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    run_doctor()
    return 0


def cmd_exe(args: argparse.Namespace) -> int:
    from havfrys.session import ExecutionSession
    workdir = args.workdir or "."
    session = ExecutionSession(workdir=workdir)
    print(f"Execution session {session.session_id} active in worktree: {session.worktree_path}")
    return 0


def cmd_maintain(args: argparse.Namespace) -> int:
    from havfrys.session import MaintenanceSession
    workdir = args.workdir or args.target or "."
    session = MaintenanceSession(workdir=workdir)
    print(f"Maintenance session {session.session_id} active for: {session.target_dir}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="havfrys",
        description="HAVFRYS — Engineering infrastructure for AI coding agents.",
    )
    parser.add_argument(
        "--version", action="version",
        version=f"havfrys {__import__('havfrys').__version__}",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # havfrys exe [--workdir]
    exe_p = sub.add_parser("exe", help="Create an isolated Execution Environment worktree")
    exe_p.add_argument("--workdir", default=".", help="Working directory")
    exe_p.set_defaults(func=cmd_exe)

    # havfrys maintain [--workdir]
    maint_p = sub.add_parser("maintain", help="Create a Maintenance Environment session for repository inspection")
    maint_p.add_argument("--workdir", default=".", help="Target directory")
    maint_p.set_defaults(func=cmd_maintain)

    init_p = sub.add_parser("init", help="Initialize HAVFRYS in workspace (.havfrys/)")
    init_p.add_argument("--select", type=int, default=None)
    init_p.add_argument("--all", "-a", action="store_true")
    init_p.set_defaults(func=cmd_init)

    doctor_p = sub.add_parser("doctor", help="Run environment diagnostics")
    doctor_p.set_defaults(func=cmd_doctor)

    serve_p = sub.add_parser("serve", help="Start HAVFRYS FastMCP server")
    serve_p.add_argument("--sse", action="store_true", help="Use SSE transport")
    serve_p.add_argument("--host", default="0.0.0.0")
    serve_p.add_argument("--port", type=int, default=8080)
    serve_p.set_defaults(func=cmd_serve)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if hasattr(args, "func"):
        return args.func(args)
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
