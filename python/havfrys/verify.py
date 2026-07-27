"""Execute verification suites, return structured results. LLM determines pass/fail."""

import os
import shutil
import subprocess
import time
import uuid
from dataclasses import dataclass
from typing import Optional


@dataclass
class VerifyResult:
    status: str = "success"
    passed: bool = False
    type: str = "test"
    summary: str = ""
    failures: list = None
    counts: dict = None
    command_used: str = ""
    execution_time_ms: int = 0
    operation_id: str = ""


_FAILURE_KEYWORDS = [
    "FAILED ", "FAIL ", "FAILURES", "error[E", "ModuleNotFoundError:",
    "ImportError:", "SyntaxError:", "ERR!", "FATAL", "Exception:",
]


def _discover_test_command(target: str) -> str:
    manifests = [
        ("pyproject.toml", "python -m pytest --tb=short -q"),
        ("pytest.ini", "python -m pytest --tb=short -q"),
        ("setup.cfg", "python -m pytest --tb=short -q"),
        ("Cargo.toml", "cargo test"),
        ("package.json", "npm test --if-present 2>/dev/null || true"),
        ("go.mod", "go test ./..."),
    ]
    for mf, cmd in manifests:
        if os.path.exists(os.path.join(target, mf)):
            py = _resolve_python(target)
            if py and ("python" in cmd or "pytest" in cmd):
                return cmd.replace("python", py)
            return cmd
    return ""


def _resolve_python(workdir: str) -> str:
    for venv_dir in (".venv", "venv", ".env", "env"):
        # Unix
        candidate = os.path.join(workdir, venv_dir, "bin", "python")
        if os.path.exists(candidate):
            return candidate
        # Windows
        candidate_win = os.path.join(workdir, venv_dir, "Scripts", "python.exe")
        if os.path.exists(candidate_win):
            return candidate_win
    # Fallback: use available python command
    for name in ("python3", "python"):
        found = shutil.which(name)
        if found:
            return found
    return ""


def _extract_failures(output: str, max_lines: int = 10) -> list[str]:
    if not output:
        return []
    lines = []
    for line in output.splitlines():
        stripped = line.strip()
        if any(kw in stripped for kw in _FAILURE_KEYWORDS):
            lines.append(stripped)
            if len(lines) >= max_lines:
                break
    return lines


def verify(
    checks: list[str] = None,
    target: str = ".",
    worktree: Optional[str] = None,
) -> VerifyResult:
    if checks is None:
        checks = ["tests"]
    op_id = f"vr_{uuid.uuid4().hex[:8]}"
    start = time.time()

    run_dir = worktree if worktree and os.path.isdir(worktree) else os.path.abspath(target)

    results = {}
    overall_passed = True
    all_failures = []

    for check in checks:
        if check == "tests":
            cmd = _discover_test_command(run_dir)
            if not cmd:
                elapsed = int((time.time() - start) * 1000)
                return VerifyResult(
                    status="failure",
                    passed=False,
                    type="tests",
                    summary="No test framework detected",
                    command_used="",
                    execution_time_ms=elapsed,
                    operation_id=op_id,
                )

            try:
                proc = subprocess.run(
                    cmd, shell=True, cwd=run_dir,
                    capture_output=True, text=True,
                    timeout=300, start_new_session=True,
                )
            except subprocess.TimeoutExpired:
                elapsed = int((time.time() - start) * 1000)
                return VerifyResult(
                    status="failure",
                    passed=False,
                    type="tests",
                    summary=f"Tests timed out (>300s)",
                    command_used=cmd,
                    execution_time_ms=elapsed,
                    operation_id=op_id,
                )
            except Exception as e:
                elapsed = int((time.time() - start) * 1000)
                return VerifyResult(
                    status="error",
                    passed=False,
                    type="tests",
                    summary=str(e),
                    command_used=cmd,
                    execution_time_ms=elapsed,
                    operation_id=op_id,
                )

            stdout = proc.stdout or ""
            stderr = proc.stderr or ""
            output = stdout + "\n" + stderr
            failures = _extract_failures(output)

            passed = proc.returncode == 0
            last_line = [l for l in output.strip().splitlines() if l][-1] if output.strip() else ""
            summary = f"{'PASSED' if passed else 'FAILED'}: {last_line}" if last_line else f"{'Passed' if passed else 'Failed'} (exit {proc.returncode})"

            results["tests"] = {
                "passed": passed,
                "exit_code": proc.returncode,
                "failures": failures,
            }
            if not passed:
                overall_passed = False
                all_failures.extend(failures)

    elapsed = int((time.time() - start) * 1000)
    return VerifyResult(
        status="success" if overall_passed else "failure",
        passed=overall_passed,
        type="+".join(checks),
        summary=f"{'All checks passed' if overall_passed else f'{len(all_failures)} failures'}",
        failures=all_failures if all_failures else None,
        counts=results,
        command_used=_discover_test_command(run_dir),
        execution_time_ms=elapsed,
        operation_id=op_id,
    )
