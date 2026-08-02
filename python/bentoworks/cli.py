"""BentoBox CLI - sandbox any AI agent in seconds."""

import argparse
import os
import subprocess
import sys

from bentoworks import __version__
from bentoworks.bentobox import BentoBox, AgentBentoBox, BentoBoxConfig
from bentoworks.compartments import Compartment, CompartmentConfig

BRAND = "BentoBox — Sandbox any AI agent in seconds."


def _bold(text: str) -> str:
    try:
        if os.isatty(sys.stdout.fileno()):
            return f"\033[1m{text}\033[0m"
    except (OSError, ValueError):
        pass
    return text


def _banner() -> str:
    try:
        if os.isatty(sys.stdout.fileno()):
            return _bold(BRAND)
    except (OSError, ValueError):
        pass
    return ""


def cmd_run(args: argparse.Namespace) -> int:
    name = args.name or "task"
    perms = args.permissions or ["fs_read", "fs_exec"]

    def _run_shell(ctx):
        proc = subprocess.run(
            args.cmd if args.cmd else args.goal,
            shell=True, capture_output=True, text=True,
            cwd=ctx.workdir,
        )
        # Return a dict (not CompletedProcess) so cmd_run can print output.
        return {
            "returncode": proc.returncode,
            "stdout": proc.stdout or "",
            "stderr": proc.stderr or "",
        }

    box = AgentBentoBox(config=BentoBoxConfig(
        workdir=args.workdir or ".",
        sandbox=not args.no_sandbox,
        block_network=not args.network,
    ))
    box.add(Compartment(
        name=name,
        fn=_run_shell,
        config=CompartmentConfig(permissions=perms, timeout_s=args.timeout),
    ))
    result = box.run(entry=name)

    banner = _banner()
    if banner:
        print(banner)
        print()

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

    returncode = output.get("returncode") if isinstance(output, dict) else None
    if result.status == "success" and returncode in (None, 0):
        return 0
    return 1


def cmd_why(args: argparse.Namespace) -> int:
    box = BentoBox(workdir=args.workdir or ".")
    result = box.why(args.path)

    banner = _banner()
    if banner:
        print(banner)
        print()

    print(result)
    return 0 if result.startswith("ALLOWED") else 2 if result.startswith("BLOCKED") else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bentoworks",
        description="BentoBox — sandbox any AI agent in seconds. Kernel-enforced "
                    "isolation, deny-by-default, no containers, no VMs.",
    )
    parser.add_argument("--version", action="version",
                        version=f"bentoworks {__version__} — Sandbox any AI agent in seconds.")

    sub = parser.add_subparsers(dest="command")

    run_p = sub.add_parser("run", help="Run any task inside an isolated compartment")
    run_p.add_argument("goal", nargs="?", default="", help="Task description or command")
    run_p.add_argument("--name", default="task", help="Compartment name")
    run_p.add_argument("--cmd", help="Shell command to run (overrides goal)")
    run_p.add_argument("--permissions", nargs="+",
                       default=["fs_read", "fs_exec"],
                       help="Permissions for the compartment")
    run_p.add_argument("--timeout", type=int, default=300,
                       help="Timeout in seconds")
    run_p.add_argument("--workdir", default=".",
                       help="Worktree granted to the sandbox (default: current dir)")
    run_p.add_argument("--network", action="store_true",
                       help="Allow outbound network (default: deny-by-default)")
    run_p.add_argument("--no-sandbox", action="store_true",
                       help="Disable the kernel sandbox (unsafe; debugging only)")
    run_p.set_defaults(func=cmd_run)

    why_p = sub.add_parser("why",
                           help="Explain why a path or network is allowed or blocked")
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
