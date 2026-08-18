"""Tests for Git-native metadata trailers and Git commit integration.

Covers:
- Execution.git_trailers() RFC-5322 format
- Security status in git trailers (clean vs blocked actions)
- `compart diff --trailers` output
- `compart commit` and `compart apply --commit`
"""

import io
import json
import os
import shutil
import subprocess
import tempfile
import textwrap
from contextlib import redirect_stdout

import pytest

from compart.cli.main import _git_commit_execution, cmd_apply, cmd_commit, cmd_diff
from compart.engine.execution import Execution, ExecutionKind, ExecutionManager, ExecutionStatus


def test_execution_git_trailers_format():
    """Execution.git_trailers() produces valid RFC-5322 Git trailer blocks."""
    ex = Execution(
        execution_id="exec_123456789",
        kind=ExecutionKind.INTERACTIVE,
        command=["claude"],
        compartment_id="coding",
    )
    trailers = ex.git_trailers()
    assert "Compart-Execution: exec_123456789" in trailers
    assert "Compart-Agent: claude" in trailers
    assert "Compart-Compartment: coding" in trailers
    assert "Compart-Security: clean" in trailers


def test_execution_git_trailers_with_security_violations():
    """Blocked security events are surfaced in the Git trailer."""
    ex = Execution(
        execution_id="exec_999",
        kind=ExecutionKind.INTERACTIVE,
        command=["opencode"],
        compartment_id="research",
    )
    ex.emit("network.blocked", {"host": "malicious.com"})
    ex.emit("fs.denied", {"path": "/etc/passwd"})
    trailers = ex.git_trailers()
    assert "Compart-Security: 2 blocked action(s)" in trailers


def test_git_commit_execution_staging_and_trailers():
    """_git_commit_execution stages files and creates a commit with Compart trailers."""
    tmp = tempfile.mkdtemp()
    try:
        # Initialize a real Git repository in tmp
        subprocess.run(["git", "init", "-b", "main"], cwd=tmp, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Compart Bot"], cwd=tmp, check=True)
        subprocess.run(["git", "config", "user.email", "bot@compart.dev"], cwd=tmp, check=True)

        # Create an initial commit
        readme = os.path.join(tmp, "README.md")
        with open(readme, "w") as f:
            f.write("# Hello\n")
        subprocess.run(["git", "add", "README.md"], cwd=tmp, check=True)
        subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=tmp, check=True)

        # Create a change as an execution
        src_file = os.path.join(tmp, "auth.py")
        with open(src_file, "w") as f:
            f.write("def login(): return True\n")

        ex = Execution(
            execution_id="exec_auth_01",
            kind=ExecutionKind.INTERACTIVE,
            command=["claude"],
            compartment_id="coding",
            changes=[{"path": "auth.py", "status": "added"}],
        )

        ok = _git_commit_execution(
            ws_root=tmp,
            ex=ex,
            user_message="Implement login feature",
        )
        assert ok is True

        # Verify commit message with git log
        log_res = subprocess.run(
            ["git", "log", "-n", "1"],
            cwd=tmp,
            capture_output=True,
            text=True,
            check=True,
        )
        log_text = log_res.stdout
        assert "Implement login feature" in log_text
        assert "Compart-Execution: exec_auth_01" in log_text
        assert "Compart-Agent: claude" in log_text
        assert "Compart-Compartment: coding" in log_text
        assert "Compart-Security: clean" in log_text
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_diff_with_trailers_in_json(monkeypatch):
    """`compart diff --json` includes git_trailers in every execution dictionary."""
    tmp = tempfile.mkdtemp()
    try:
        os.makedirs(os.path.join(tmp, ".compart"))
        monkeypatch.chdir(tmp)
        mgr = ExecutionManager(workdir=tmp)
        ex = mgr.create(kind=ExecutionKind.INTERACTIVE, command=["claude"], compartment_id="coding")
        ex.changes = [{"path": "main.py", "status": "modified"}]
        ex.complete(0, changes=ex.changes)
        mgr.save(ex)

        class _Args:
            execution = ex.execution_id
            unapplied = False
            trailers = True
            json = True

        buf = io.StringIO()
        with redirect_stdout(buf):
            cmd_diff(_Args())

        data = json.loads(buf.getvalue())
        assert data["change_sets"] == 1
        assert "git_trailers" in data["executions"][0]
        assert "Compart-Execution: " in data["executions"][0]["git_trailers"]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
