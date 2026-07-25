"""havfrys — developer CLI for HAVFRYS engineering execution by HAVFRYS Labs."""

from __future__ import annotations

import argparse
import sys
from havfrys.server import run_server
from havfrys.installer import run_init_wizard, run_doctor


def cmd_serve(args: argparse.Namespace) -> int:
    """Start the HAVFRYS MCP server."""
    run_server(sse=args.sse, host=args.host, port=args.port)
    return 0


def cmd_init(args: argparse.Namespace) -> int:
    """Run local-first client installer wizard."""
    run_init_wizard(choice=args.select, auto_all=args.all)
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    """Run HAVFRYS local environment diagnostics."""
    run_doctor()
    return 0


def cmd_maintain(args: argparse.Namespace) -> int:
    """Run automated maintenance across target repository."""
    from havfrys import maintain
    from havfrys.ui import symbol_ok, symbol_err, BOLD, DIM, RESET
    res = maintain(target=args.target, workdir=args.workdir)
    out = res.output or res.error or ""
    if out:
        print(out.strip())
    
    icon = symbol_ok() if res.status in ("success", "cached") else symbol_err()
    print(f"\n{icon} {BOLD}HAVFRYS Maintenance:{RESET} \"{args.target}\"")
    print(f"  {DIM}├─ Status: {res.status.upper()}{RESET}")
    print(f"  {DIM}├─ Strategy: Self-Maintaining Run{RESET}")
    print(f"  {DIM}└─ Latency: {res.execution_time_s:.2f}s ({res.retries + 1} attempt(s)){RESET}\n")
    return 0 if res.status in ("success", "cached") else 1


def cmd_exe(args: argparse.Namespace) -> int:
    """Execute an engineering task via HAVFRYS exe execution layer."""
    from havfrys import exe
    from havfrys.ui import symbol_ok, symbol_err, BOLD, DIM, RESET
    cmd = " ".join(args.command)
    res = exe(cmd, workdir=args.workdir)
    out = res.output or res.error or ""
    if out:
        print(out.strip())
    
    icon = symbol_ok() if res.status in ("success", "cached") else symbol_err()
    mode_text = f"Cached Hit" if res.cached else f"{res.mode.title()} Path"
    print(f"\n{icon} {BOLD}HAVFRYS Execution:{RESET} \"{cmd}\"")
    print(f"  {DIM}├─ Status: {res.status.upper()}{RESET}")
    print(f"  {DIM}├─ Mode: {mode_text}{RESET}")
    print(f"  {DIM}└─ Latency: {res.execution_time_s:.2f}s ({res.retries + 1} attempt(s)){RESET}\n")
    return 0 if res.status in ("success", "cached") else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="havfrys",
        description="HAVFRYS — Maintenance infrastructure for AI-built software by HAVFRYS Labs",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # havfrys exe <command>
    exe_p = sub.add_parser("exe", help="Execute an engineering task via HAVFRYS execution layer")
    exe_p.add_argument("command", nargs="+", help="Engineering task to execute")
    exe_p.add_argument("--workdir", default="", help="Working directory override")
    exe_p.set_defaults(func=cmd_exe)

    # havfrys maintain [target]
    maintain_p = sub.add_parser("maintain", help="Run software maintenance intelligence across target workspace or repository")
    maintain_p.add_argument("target", nargs="?", default=".", help="Target workspace path to maintain")
    maintain_p.add_argument("--workdir", default="", help="Working directory override")
    maintain_p.set_defaults(func=cmd_maintain)

    # havfrys init
    init_p = sub.add_parser("init", help="Initialize HAVFRYS decision layer (.havfrys/hav.md)")
    init_p.add_argument("--select", type=int, default=None, help="Directly select option")
    init_p.add_argument("--all", "-a", action="store_true", help="Auto-configure option")
    init_p.set_defaults(func=cmd_init)

    # havfrys doctor
    doctor_p = sub.add_parser("doctor", help="Run local environment diagnostics")
    doctor_p.set_defaults(func=cmd_doctor)

    # havfrys serve
    serve_p = sub.add_parser("serve", help="Start the HAVFRYS FastMCP server")
    serve_p.add_argument("--sse", action="store_true", help="Use SSE transport")
    serve_p.add_argument("--host", default="0.0.0.0", help="Host for SSE")
    serve_p.add_argument("--port", type=int, default=8080, help="Port for SSE")
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
