"""CLI for BentoBox — run compartments from the command line."""

import argparse
import os
import subprocess
import sys

from bentoworks.bentobox import BentoBox
from bentoworks.compartments import Compartment, CompartmentConfig


def _bold(text: str) -> str:
    try:
        if os.isatty(sys.stdout.fileno()):
            return f"\033[1m{text}\033[0m"
    except (OSError, ValueError):
        pass
    return text


def cmd_run(args: argparse.Namespace) -> int:
    name = args.name or "task"
    perms = args.permissions or ["fs_read", "fs_exec"]

    def _run_shell(ctx):
        return subprocess.run(
            args.cmd if args.cmd else args.goal,
            shell=True, capture_output=True, text=True,
            cwd=ctx.workdir,
        )

    box = BentoBox()
    box.add(Compartment(
        name=name,
        fn=_run_shell,
        config=CompartmentConfig(permissions=perms, timeout_s=args.timeout),
    ))
    result = box.run(entry=name)

    print(f"Status: {result.status}")
    print(f"Summary: {result.summary}")
    print(f"Elapsed: {result.elapsed_s}s")
    print(f"Compartments: {result.compartments_completed}")

    output = result.output.get(name, {})
    if isinstance(output, dict):
        if output.get("stdout"):
            print(f"\nStdout:\n{output['stdout'][:2000]}")
        if output.get("stderr"):
            print(f"\nStderr:\n{output['stderr'][:1000]}")
    return 0 if result.status == "success" else 1


def cmd_why(args: argparse.Namespace) -> int:
    box = BentoBox(workdir=args.workdir or ".")
    result = box.why(args.path)
    print(result)
    return 0 if result.startswith("ALLOWED") else 2 if result.startswith("BLOCKED") else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bentoworks")
    parser.add_argument("--version", action="version", version="bentoworks 0.9.1")

    sub = parser.add_subparsers(dest="command")

    # ── run ────────────────────────────────────────────────────────────
    run_p = sub.add_parser("run", help="Run a task inside a single compartment")
    run_p.add_argument("goal", nargs="?", default="", help="Task description or command")
    run_p.add_argument("--name", default="task", help="Compartment name")
    run_p.add_argument("--cmd", help="Shell command to run (overrides goal)")
    run_p.add_argument("--permissions", nargs="+",
                       default=["fs_read", "fs_exec"],
                       help="Permissions for the compartment")
    run_p.add_argument("--timeout", type=int, default=300,
                       help="Timeout in seconds")
    run_p.set_defaults(func=cmd_run)

    # ── why ────────────────────────────────────────────────────────────
    why_p = sub.add_parser("why",
                           help="Diagnose why a path or network would be blocked")
    why_p.add_argument("path", help="File path or network address")
    why_p.add_argument("--workdir", default=".",
                       help="Project directory to resolve sandbox worktree")
    why_p.set_defaults(func=cmd_why)

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
