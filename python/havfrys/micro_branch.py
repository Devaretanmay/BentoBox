"""Micro-Branch — tiny, budget-constrained execution branches.

HAVFRYS Invariant #3: Branches are tiny and short-lived.
HAVFRYS Invariant #6: Kill branches aggressively.

A micro-branch is NOT a full trajectory. It is:
- A single fix attempt in an isolated worktree
- Constrained by a hard budget (tokens, attempts, time)
- Monitored by BranchLoopDetector for internal loops
- Killed the instant it exceeds budget or loops

From the orchestrator's perspective, a micro-branch is disposable.
Spawn 3, kill 2, merge 1, move on.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from havfrys._core import route_and_compress
from havfrys.branch_loop import BranchLoopDetector, AttemptSignature, LoopVerdict, hash_output


@dataclass
class BranchBudget:
    """Hard limits for a micro-branch. Exceeded = KILL."""

    max_tokens: int = 2000
    max_attempts: int = 5
    max_seconds: float = 180.0   # 3 minutes
    max_checkpoints: int = 3


@dataclass
class BranchResult:
    """Outcome of a micro-branch execution."""

    branch_id: str = ""
    fix_label: str = ""
    status: str = "pending"       # "pending" | "running" | "success" | "failed" | "killed"
    kill_reason: str = ""
    output: str = ""
    error: Optional[str] = None
    exit_code: int = -1
    attempts_used: int = 0
    tokens_used: int = 0
    time_used_s: float = 0.0
    diff_lines: int = 0
    loop_verdict: Optional[LoopVerdict] = None


class MicroBranch:
    """A tiny, budget-constrained execution branch.

    Each micro-branch gets its own git worktree (or temp copy),
    runs the fix command under budget constraints, and is monitored
    for internal loops. The moment it exceeds budget or loops, it dies.
    """

    def __init__(
        self,
        fix_label: str,
        command: str,
        source_dir: str,
        *,
        budget: Optional[BranchBudget] = None,
    ):
        self.id = f"mb-{uuid.uuid4().hex[:6]}"
        self.fix_label = fix_label
        self.command = command
        self.source_dir = source_dir
        self.budget = budget or BranchBudget()

        self._loop_detector = BranchLoopDetector(
            stagnation_threshold=min(3, self.budget.max_attempts),
        )

        # Prune stale worktrees from previous runs
        try:
            subprocess.run(
                ["git", "worktree", "prune"],
                cwd=self.source_dir,
                capture_output=True,
                timeout=5,
            )
        except Exception:
            pass

        # Create isolated worktree
        self.workdir = self._create_worktree()
        self._is_git_worktree = False

        self.result = BranchResult(
            branch_id=self.id,
            fix_label=fix_label,
        )

    def execute(self) -> BranchResult:
        """Execute the fix command under budget constraints.

        Runs up to budget.max_attempts times. Each attempt is:
        1. Run command
        2. Compress output (Law #1)
        3. Check internal loops
        4. Check budget
        5. If exceeded or looping → KILL
        """
        self.result.status = "running"
        start_time = time.time()

        for attempt_idx in range(1, self.budget.max_attempts + 1):
            # Budget check: time
            elapsed = time.time() - start_time
            if elapsed >= self.budget.max_seconds:
                return self._kill(f"Time budget exceeded: {elapsed:.1f}s >= {self.budget.max_seconds}s")

            # Execute command
            exit_code, stdout, stderr = self._run_command(self.command)

            # Law #1: Compress before reasoning
            compressed_out = route_and_compress(stdout) if stdout else ""
            compressed_err = route_and_compress(stderr) if stderr else ""

            tokens_this_attempt = (len(compressed_out) + len(compressed_err)) // 4
            tokens_this_attempt = int(tokens_this_attempt * 1.5)
            self.result.tokens_used += tokens_this_attempt

            if self.result.tokens_used > self.budget.max_tokens:
                return self._kill(
                    f"Token budget exceeded: {self.result.tokens_used} > {self.budget.max_tokens}"
                )

            # Measure diff
            diff_lines = self._measure_diff()

            # Record attempt for loop detection
            sig = AttemptSignature(
                index=attempt_idx,
                exit_code=exit_code,
                output_hash=hash_output(compressed_out),
                error_hash=hash_output(compressed_err),
                diff_lines=diff_lines,
                tokens_spent=tokens_this_attempt,
            )
            verdict = self._loop_detector.record(sig)

            # Loop detected → KILL
            if verdict.should_kill:
                self.result.loop_verdict = verdict
                return self._kill(f"Internal loop: {verdict.reason}")

            self.result.attempts_used = attempt_idx
            self.result.exit_code = exit_code
            self.result.output = compressed_out
            self.result.error = compressed_err if exit_code != 0 else None
            self.result.diff_lines = diff_lines

            # Success!
            if exit_code == 0:
                self.result.status = "success"
                self.result.time_used_s = time.time() - start_time
                return self.result

        # Exhausted all attempts without success
        self.result.status = "failed"
        self.result.time_used_s = time.time() - start_time
        return self.result

    def _kill(self, reason: str) -> BranchResult:
        """Kill this branch."""
        self.result.status = "killed"
        self.result.kill_reason = reason
        self.result.time_used_s = 0.0  # killed branches report 0
        return self.result

    def cleanup(self) -> None:
        try:
            if self.workdir and os.path.exists(self.workdir):
                if self._is_git_worktree:
                    subprocess.run(
                        ["git", "worktree", "remove", "--force", self.workdir],
                        cwd=self.source_dir,
                        capture_output=True,
                        timeout=30,
                    )
                else:
                    shutil.rmtree(self.workdir, ignore_errors=True)
        except Exception:
            pass
        finally:
            try:
                subprocess.run(
                    ["git", "worktree", "prune"],
                    cwd=self.source_dir,
                    capture_output=True,
                    timeout=5,
                )
            except Exception:
                pass
            try:
                subprocess.run(
                    ["git", "branch", "-D", f"havfrys/{self.id}"],
                    cwd=self.source_dir,
                    capture_output=True,
                    timeout=5,
                )
            except Exception:
                pass

    def _run_command(self, cmd: str) -> tuple[int, str, str]:
        try:
            proc = subprocess.run(
                cmd,
                shell=True,
                cwd=self.workdir,
                capture_output=True,
                text=True,
                timeout=min(60, int(self.budget.max_seconds)),
                preexec_fn=os.setsid,
            )
            return proc.returncode, proc.stdout, proc.stderr
        except subprocess.TimeoutExpired:
            return 124, "", "Command timed out"
        except Exception as e:
            return 1, "", str(e)

    def _measure_diff(self) -> int:
        """Measure lines changed in the worktree since branch creation."""
        try:
            proc = subprocess.run(
                ["git", "diff", "--numstat"],
                cwd=self.workdir,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if proc.returncode != 0:
                return 0
            total = 0
            for line in proc.stdout.strip().splitlines():
                parts = line.split("\t")
                if len(parts) >= 2:
                    try:
                        total += int(parts[0]) + int(parts[1])
                    except ValueError:
                        continue
            return total
        except Exception:
            return 0

    def _create_worktree(self) -> str:
        """Create isolated working directory for this micro-branch."""
        worktree_base = os.path.join(tempfile.gettempdir(), "havfrys_branches")
        os.makedirs(worktree_base, exist_ok=True)

        # Try git worktree (fast, zero-copy)
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--is-inside-work-tree"],
                cwd=self.source_dir,
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                worktree_dir = os.path.join(worktree_base, self.id)
                branch_name = f"havfrys/{self.id}"
                subprocess.run(
                    ["git", "worktree", "add", "-b", branch_name, worktree_dir],
                    cwd=self.source_dir,
                    capture_output=True,
                    timeout=30,
                    check=True,
                )
                self._is_git_worktree = True
                return worktree_dir
        except Exception:
            pass

        # Fallback: shallow copy
        copy_dir = os.path.join(worktree_base, self.id)
        shutil.copytree(
            self.source_dir,
            copy_dir,
            ignore=shutil.ignore_patterns(
                ".git", "__pycache__", "node_modules", ".venv", "venv",
                "target", "dist", "build",
            ),
            dirs_exist_ok=True,
        )
        return copy_dir


def compressed_summary(branch: MicroBranch) -> str:
    """Generate a compressed summary of a branch for the orchestrator.

    Instead of 56k raw logs, the orchestrator sees ~30-40 tokens:

        Branch A: Attempts: 5 | Status: killed | Tests improved: 0
        Diff: 3 LOC | Tokens: 1.9k | Kill: A-B-A-B oscillation
    """
    r = branch.result
    parts = [
        f"Branch {branch.fix_label}:",
        f"Attempts: {r.attempts_used}",
        f"Status: {r.status}",
        f"Diff: {r.diff_lines} LOC",
        f"Tokens: {r.tokens_used}",
    ]
    if r.kill_reason:
        parts.append(f"Kill: {r.kill_reason}")
    if r.exit_code >= 0:
        parts.append(f"Exit: {r.exit_code}")
    return " | ".join(parts)
