"""run() primitive — execute shell commands, auto-compress output, structured results."""

import os
import subprocess
import time
import uuid
from dataclasses import dataclass
from typing import Optional


@dataclass
class RunResult:
    status: str = "success"
    output: str = ""
    error: Optional[str] = None
    exit_code: int = 0
    compressed: bool = False
    tokens_saved: int = 0
    execution_time_ms: int = 0
    operation_id: str = ""


def run(
    command: str,
    worktree: Optional[str] = None,
    sandbox: bool = False,
    timeout: int = 120,
) -> RunResult:
    op_id = f"run_{uuid.uuid4().hex[:8]}"
    start = time.time()

    cmd = command.strip()
    if not cmd:
        return RunResult(status="error", error="No command provided", operation_id=op_id)

    run_dir = worktree if worktree and os.path.isdir(worktree) else os.getcwd()

    try:
        proc = subprocess.run(
            cmd,
            shell=True,
            cwd=run_dir,
            capture_output=True,
            text=True,
            timeout=timeout,
            preexec_fn=os.setsid,
        )
    except subprocess.TimeoutExpired:
        elapsed = int((time.time() - start) * 1000)
        return RunResult(
            status="error",
            error=f"Command timed out after {timeout}s",
            exit_code=124,
            execution_time_ms=elapsed,
            operation_id=op_id,
        )
    except Exception as e:
        elapsed = int((time.time() - start) * 1000)
        return RunResult(
            status="error",
            error=str(e),
            exit_code=1,
            execution_time_ms=elapsed,
            operation_id=op_id,
        )

    stdout = proc.stdout or ""
    stderr = proc.stderr or ""

    try:
        from havfrys._core import route_and_compress
        raw_len = len(stdout) + len(stderr)
        c_out = route_and_compress(stdout) if stdout else ""
        c_err = route_and_compress(stderr) if stderr else ""
        compressed = True
        tokens_saved = max(0, (raw_len - len(c_out) - len(c_err)) // 4)
    except Exception:
        c_out, c_err = stdout, stderr
        compressed = False
        tokens_saved = 0

    elapsed = int((time.time() - start) * 1000)
    return RunResult(
        status="success" if proc.returncode == 0 else "failure",
        output=c_out,
        error=c_err if proc.returncode != 0 else None,
        exit_code=proc.returncode,
        compressed=compressed,
        tokens_saved=tokens_saved,
        execution_time_ms=elapsed,
        operation_id=op_id,
    )
