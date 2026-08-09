"""BentoBox CI Step Runner & Wrapper.

Allows 1-word or 1-line execution of CI pipeline steps inside a kernel-enforced
BentoBox compartment. Preserves stdout/stderr and exit codes for CI runners.
"""

import argparse
import os
import subprocess
import sys
from typing import Any, Optional

from bentoworks.bentobox import AgentBentoBox, BentoBoxConfig
from bentoworks.compartments import Compartment, CompartmentConfig


class BentoCIRunner:
    """CI Pipeline Step Runner."""

    def __init__(
        self,
        workdir: str = ".",
        block_network: bool = True,
        timeout_s: int = 600,
        enable_snapshot: bool = True,
        sandbox: bool = True,
    ):
        self.workdir = os.path.abspath(workdir)
        self.block_network = block_network
        self.timeout_s = timeout_s
        self.enable_snapshot = enable_snapshot
        self.sandbox = sandbox

    def run_step(self, cmd: str, name: str = "ci_step") -> dict[str, Any]:
        """Runs a command inside a kernel-enforced BentoBox CI compartment."""
        
        def _exec_cmd(ctx):
            proc = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                cwd=ctx.workdir,
                timeout=self.timeout_s,
            )
            return {
                "returncode": proc.returncode,
                "stdout": proc.stdout or "",
                "stderr": proc.stderr or "",
            }

        perms = ["fs_read", "fs_write", "fs_exec"]
        if not self.block_network:
            perms.append("network")

        box = AgentBentoBox(
            config=BentoBoxConfig(
                workdir=self.workdir,
                sandbox=self.sandbox,
                block_network=self.block_network,
            )
        )
        box.add(
            Compartment(
                name=name,
                fn=_exec_cmd,
                config=CompartmentConfig(
                    permissions=perms,
                    timeout_s=self.timeout_s,
                ),
            )
        )
        result = box.run(entry=name, request=f"CI Step: {cmd}")
        output = result.output.get(name, {})
        
        return {
            "status": result.status,
            "elapsed_s": result.elapsed_s,
            "returncode": output.get("returncode", 1) if isinstance(output, dict) else 1,
            "stdout": output.get("stdout", "") if isinstance(output, dict) else "",
            "stderr": output.get("stderr", "") if isinstance(output, dict) else "",
        }


def run_ci_step(cmd: str, block_network: bool = True, sandbox: bool = True) -> int:
    """Convenience helper to run a CI step and output directly to stdout/stderr."""
    runner = BentoCIRunner(block_network=block_network, sandbox=sandbox)
    res = runner.run_step(cmd)
    
    if res["stdout"]:
        sys.stdout.write(res["stdout"])
        sys.stdout.flush()
    if res["stderr"]:
        sys.stderr.write(res["stderr"])
        sys.stderr.flush()
        
    return res["returncode"]


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="bento",
        description="BentoBox CI Runner - 1-word drop-in kernel sandbox for CI pipeline steps.",
    )
    parser.add_argument("cmd", help="Command line to execute inside kernel sandbox")
    parser.add_argument(
        "--allow-network",
        action="store_true",
        help="Allow outbound network access for this step (default: network blocked)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=600,
        help="Timeout in seconds (default: 600s)",
    )

    args = parser.parse_args(argv)
    block_net = not args.allow_network
    return run_ci_step(args.cmd, block_network=block_net)


if __name__ == "__main__":
    sys.exit(main())
