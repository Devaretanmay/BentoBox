"""Orchestrator — the execution loop."""
from __future__ import annotations

import os
import subprocess
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from havfrys._core import route_and_compress
from havfrys.uncertainty import detect_uncertainty, UncertaintySignal
from havfrys.micro_branch import MicroBranch, BranchBudget, BranchResult, compressed_summary
from havfrys.memory import EngineeringMemory, StrategyOutcome


@dataclass
class ExecutionReport:
    """What the user sees after execution."""

    status: str = "failed"
    output: str = ""
    error: Optional[str] = None
    execution_time_s: float = 0.0
    total_attempts: int = 0
    uncertainty_points: int = 0
    uncertainty_resolved: int = 0
    branches_spawned: int = 0
    branches_killed: int = 0
    token_reduction_pct: float = 0.0
    mode: str = "linear"             # "linear" | "branching"
    winning_fix: str = ""
    branch_summaries: list[str] = field(default_factory=list)
    # Internal tracking
    raw_tokens: int = 0
    compressed_tokens: int = 0


class Orchestrator:
    def __init__(
        self,
        task: str,
        workdir: str,
        *,
        max_linear_retries: int = 3,
        max_uncertainty_points: int = 3,
        branch_budget: Optional[BranchBudget] = None,
        memory: Optional[EngineeringMemory] = None,
        timeout: int = 3600,
        image: str = "",
    ):
        self.task = task
        self.workdir = workdir
        self.max_linear_retries = max_linear_retries
        self.max_uncertainty_points = max_uncertainty_points
        self.branch_budget = branch_budget or BranchBudget()
        self.memory = memory
        self.timeout = timeout
        self.image = image

        self._previous_errors: list[str] = []
        self._report = ExecutionReport()

    def execute(self, command: str) -> ExecutionReport:
        """Execute an engineering task with the linear-first model."""
        start = time.time()
        self._report.mode = "linear"

        attempt = 0
        max_total_attempts = self.max_linear_retries

        while attempt < max_total_attempts:
            # Global timeout check
            if time.time() - start > self.timeout:
                self._report.status = "failed"
                self._report.error = f"Global timeout exceeded: {self.timeout}s"
                break

            attempt += 1
            self._report.total_attempts = attempt

            # --- STEP 1: Execute linearly ---
            exit_code, stdout, stderr = self._run_command(command)

            # Law #1: Compress before reasoning
            raw_len = len(stdout or "") + len(stderr or "")
            self._report.raw_tokens += raw_len // 4

            compressed_out = route_and_compress(stdout) if stdout else ""
            compressed_err = route_and_compress(stderr) if stderr else ""

            if exit_code != 0:
                from havfrys.validator import extract_semantic_failures
                failures_header = extract_semantic_failures((stdout or "") + "\n" + (stderr or ""))
                if failures_header:
                    compressed_err = failures_header + compressed_err

            compressed_len = len(compressed_out) + len(compressed_err)
            self._report.compressed_tokens += compressed_len // 4

            # --- STEP 2: Success? Continue. ---
            if exit_code == 0:
                self._report.status = "success"
                self._report.output = compressed_out
                break

            # Unrecoverable exit codes — fail fast
            if exit_code in (126, 127):
                self._report.status = "failed"
                self._report.error = compressed_err or "Command not found"
                break

            # --- STEP 3: Detect uncertainty ---
            signal = detect_uncertainty(
                error_output=stderr or "",
                exit_code=exit_code,
                attempt_number=attempt,
                previous_errors=self._previous_errors,
            )

            self._previous_errors.append(stderr or "")

            if not signal.is_uncertainty:
                # Not an uncertainty point — retry linearly
                self._report.output = compressed_out
                self._report.error = compressed_err
                continue

            # --- STEP 4: UNCERTAINTY POINT DETECTED ---
            self._report.uncertainty_points += 1
            self._report.mode = "branching"

            if self._report.uncertainty_points > self.max_uncertainty_points:
                self._report.status = "failed"
                self._report.error = f"Max uncertainty points exceeded ({self.max_uncertainty_points})"
                break

            # --- STEP 5: Spawn micro-branches ---
            fix_commands = self._generate_fix_commands(
                command, signal, compressed_err
            )

            branches: list[MicroBranch] = []
            for fix_label, fix_cmd in fix_commands:
                branch = MicroBranch(
                    fix_label=fix_label,
                    command=fix_cmd,
                    source_dir=self.workdir,
                    budget=self.branch_budget,
                )
                branches.append(branch)

            self._report.branches_spawned += len(branches)

            # --- STEP 6: Execute branches (sequential for now) ---
            for branch in branches:
                try:
                    branch.execute()
                except Exception as exc:
                    branch.result.status = "killed"
                    branch.result.kill_reason = str(exc)

                # Record summary for inspect()
                self._report.branch_summaries.append(compressed_summary(branch))

                if branch.result.status == "killed":
                    self._report.branches_killed += 1

                if self.memory:
                    self.memory.record(StrategyOutcome(
                        strategy=branch.fix_label,
                        task_fingerprint=self.task[:50],
                        status=branch.result.status,
                        score=1.0 if branch.result.status == "success" else 0.0,
                        execution_time_s=branch.result.time_used_s,
                        attempts=branch.result.attempts_used,
                        error=branch.result.kill_reason or branch.result.error,
                    ))

            # --- STEP 7: Select winner ---
            winner = self._select_winner(branches)

            if winner and winner.result.status == "success":
                # --- STEP 8: Merge immediately (Invariant #7) ---
                merged = self._merge_winner(winner)
                if not merged:
                    for branch in branches:
                        branch.cleanup()
                    self._report.status = "failed"
                    self._report.error = f"Failed to merge winning branch '{winner.fix_label}' into working tree"
                    break

                self._report.uncertainty_resolved += 1
                self._report.output = winner.result.output
                self._report.winning_fix = winner.fix_label

                # Clean up all branches
                for branch in branches:
                    branch.cleanup()

                self._previous_errors.clear()

                continue

            # All branches failed — report and stop
            for branch in branches:
                branch.cleanup()

            self._report.status = "failed"
            self._report.error = "All micro-branches failed at uncertainty point"
            break

        # Finalize report
        self._report.execution_time_s = time.time() - start

        if self._report.raw_tokens > 0:
            self._report.token_reduction_pct = round(
                100.0 * (1.0 - self._report.compressed_tokens / self._report.raw_tokens), 1
            )
        else:
            self._report.token_reduction_pct = 0.0

        return self._report

    def _select_winner(self, branches: list[MicroBranch]) -> Optional[MicroBranch]:
        """Select the best surviving branch using diff quality scoring.

        Priority:
        1. Successful branch with non-destructive patch (minimal deletions relative to additions)
        2. Smallest line diff (least invasive fix)
        3. Fewest attempts (cheapest fix)
        """
        survivors = [b for b in branches if b.result.status == "success"]

        if not survivors:
            return None

        def _quality_score(b: MicroBranch) -> tuple[int, int, int]:
            diff_lines = b.result.diff_lines
            attempts = b.result.attempts_used
            return (diff_lines, attempts, b.result.tokens_used)

        survivors.sort(key=_quality_score)
        return survivors[0]

    def _merge_winner(self, winner: MicroBranch) -> bool:
        """Apply the winning branch's changes back to the source directory.

        Invariant #7: Merge immediately after a winner is selected.
        Returns True on clean merge, False if patch application fails.
        """
        try:
            diff = subprocess.run(
                ["git", "diff", "HEAD"],
                cwd=winner.workdir,
                capture_output=True,
                text=True,
                timeout=30,
                preexec_fn=os.setsid,
            )
            if diff.returncode != 0:
                return False
            if not diff.stdout.strip():
                return True

            apply = subprocess.run(
                ["git", "apply", "--3way", "-"],
                input=diff.stdout,
                cwd=self.workdir,
                capture_output=True,
                text=True,
                timeout=30,
                preexec_fn=os.setsid,
            )
            if apply.returncode == 0:
                return True

            fallback = subprocess.run(
                ["git", "apply", "--whitespace=nowarn", "-"],
                input=diff.stdout,
                cwd=self.workdir,
                capture_output=True,
                text=True,
                timeout=30,
                preexec_fn=os.setsid,
            )
            return fallback.returncode == 0
        except Exception:
            return False

    def _generate_fix_commands(
        self,
        original_command: str,
        signal: UncertaintySignal,
        error_context: str,
    ) -> list[tuple[str, str]]:
        """Generate fix commands from uncertainty signal.

        Each tuple is (fix_label, shell_command).
        The commands are the original command — micro-branches re-run
        the same task in their isolated worktree. The differentiation
        comes from the worktree isolation, not different commands.
        """
        fixes = []
        for label in signal.suggested_fixes:
            fixes.append((label, original_command))

        if not fixes:
            fixes = [
                ("direct_fix", original_command),
                ("alternative_approach", original_command),
            ]

        return fixes[:4]  # max 4 micro-branches

    def _run_command(self, cmd: str) -> tuple[int, str, str]:
        """Execute a command in the main workdir (or inside Docker container if self.image set)."""
        if self.image:
            from havfrys.backends.docker import DockerBackend
            backend = DockerBackend(
                image=self.image,
                resource_args=["--cpus=2", "--memory=2g"],
                network_args=[],
                timeout=min(300, self.timeout),
                workdir=self.workdir,
            )
            try:
                backend.start()
                code, out, err = backend.execute_cli(cmd, cwd=None, env=None)
                return code, out, err
            except Exception as e:
                return 1, "", f"Docker execution error: {e}"
            finally:
                backend.stop()

        try:
            proc = subprocess.run(
                cmd,
                shell=True,
                cwd=self.workdir,
                capture_output=True,
                text=True,
                timeout=min(300, self.timeout),
                preexec_fn=os.setsid,
            )
            return proc.returncode, proc.stdout, proc.stderr
        except subprocess.TimeoutExpired:
            return 124, "", "Command timed out"
        except Exception as e:
            return 1, "", str(e)
