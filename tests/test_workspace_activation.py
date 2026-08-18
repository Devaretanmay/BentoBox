"""Tests for workspace activation hardening (M0-M2).

Covers:
- real-binary resolution that skips the workspace's own .compart/bin shim dir
  (prevents shim self-recursion when the workspace is activated),
- the COMPART_EXECUTION_ID shim bypass so an agent launched by an agent
  inherits the parent execution boundary instead of being wrapped again,
- the deterministic nested-workspace rule (innermost .compart wins),
- PtySupervisor resolving real binaries past the shim dir.
"""

import os
import shutil
import subprocess
import sys
import tempfile

import pytest

from compart.cli.main import _SHIM_TEMPLATE, _resolve_real_binary
from compart.config import find_workspace_root
from compart.engine.pty_supervisor import PtySupervisor

REPO_PYTHON_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "python"
)


def _write_executable(path: str, content: str) -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    os.chmod(path, 0o755)
    return path


def _render_shim(workspace: str, agent: str, real_path: str) -> str:
    """Write a rendered shim script into workspace/.compart/bin/<agent>."""
    shim_path = os.path.join(workspace, ".compart", "bin", agent)
    os.makedirs(os.path.dirname(shim_path), exist_ok=True)
    with open(shim_path, "w", encoding="utf-8") as f:
        f.write(_SHIM_TEMPLATE.format(agent=agent, real_path=real_path))
    os.chmod(shim_path, 0o755)
    return shim_path


def _real_binary_script(marker_path: str) -> str:
    return (
        "#!/usr/bin/env bash\n"
        f'echo "ran" > "{marker_path}"\n'
        "exit 0\n"
    )


# ── Real-binary resolution ────────────────────────────────────────────────


def test_resolve_real_binary_skips_workspace_shim_dir(tmp_path, monkeypatch):
    """When activated, .compart/bin shadows PATH; the shim must be skipped."""
    shim_dir = tmp_path / ".compart" / "bin"
    real_dir = tmp_path / "realbin"
    _write_executable(str(shim_dir / "claude"), "#!/usr/bin/env bash\n")
    real = _write_executable(str(real_dir / "claude"), "#!/usr/bin/env bash\n")

    monkeypatch.setenv("PATH", f"{shim_dir}:{real_dir}:/usr/bin:/bin")

    resolved = _resolve_real_binary("claude", str(tmp_path))
    assert resolved == real


def test_resolve_real_binary_returns_none_when_only_shim_present(tmp_path, monkeypatch):
    """If the only match on PATH is our own shim, resolution must fail cleanly."""
    shim_dir = tmp_path / ".compart" / "bin"
    _write_executable(str(shim_dir / "claude"), "#!/usr/bin/env bash\n")

    monkeypatch.setenv("PATH", f"{shim_dir}:/usr/bin:/bin")

    assert _resolve_real_binary("claude", str(tmp_path)) is None


def test_resolve_real_binary_ignores_other_workspace_shims(tmp_path, monkeypatch):
    """Only the governing workspace's shim dir is excluded, not other projects'."""
    shim_dir = tmp_path / ".compart" / "bin"
    other_shim_dir = tmp_path / "other-project" / ".compart" / "bin"
    _write_executable(str(shim_dir / "claude"), "#!/usr/bin/env bash\n")
    other = _write_executable(str(other_shim_dir / "claude"), "#!/usr/bin/env bash\n")

    monkeypatch.setenv("PATH", f"{shim_dir}:{other_shim_dir}:/usr/bin:/bin")

    assert _resolve_real_binary("claude", str(tmp_path)) == other


# ── Shim script behavior (real bash execution) ────────────────────────────


@pytest.mark.skipif(sys.platform == "win32", reason="shims are bash scripts")
def test_shim_bypasses_when_execution_marker_set(tmp_path):
    """An agent launched by another agent inherits the boundary: no re-wrap."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / ".compart").mkdir(parents=True)

    marker = tmp_path / "ran.out"
    real_path = _write_executable(
        str(workspace / "realagent"), _real_binary_script(str(marker))
    )
    shim = _render_shim(str(workspace), "compart_test_agent", real_path)

    env = {
        **os.environ,
        "COMPART_EXECUTION_ID": "exec_123",
        "COMPART_TEST_MARKER": str(marker),
    }
    result = subprocess.run(
        ["bash", shim, "--some", "args"],
        cwd=str(workspace),
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert marker.exists(), "real binary should run directly when marker is set"


@pytest.mark.skipif(sys.platform == "win32", reason="shims are bash scripts")
def test_shim_runs_real_binary_outside_workspace(tmp_path):
    """Outside any workspace, the shim is transparent: real binary runs."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / ".compart").mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()

    marker = tmp_path / "ran.out"
    real_path = _write_executable(
        str(workspace / "realagent"), _real_binary_script(str(marker))
    )
    shim = _render_shim(str(workspace), "compart_test_agent", real_path)

    env = {**os.environ, "COMPART_TEST_MARKER": str(marker)}
    result = subprocess.run(
        ["bash", shim],
        cwd=str(outside),
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert marker.exists(), "real binary should run outside a workspace"


@pytest.mark.skipif(sys.platform == "win32", reason="shims are bash scripts")
def test_shim_delegates_to_exec_shim_inside_workspace(tmp_path):
    """Inside a workspace without a marker, the shim delegates to _exec_shim.

    The fake agent name is unresolvable, so _exec_shim fails fast (exit 127)
    and the real binary is never reached.
    """
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / ".compart").mkdir(parents=True)

    marker = tmp_path / "ran.out"
    real_path = _write_executable(
        str(workspace / "realagent"), _real_binary_script(str(marker))
    )
    shim = _render_shim(str(workspace), "compart_fake_agent_xyz", real_path)

    env = {
        **os.environ,
        "PYTHONPATH": REPO_PYTHON_DIR + os.pathsep + os.environ.get("PYTHONPATH", ""),
        "COMPART_TEST_MARKER": str(marker),
    }
    result = subprocess.run(
        ["bash", shim],
        cwd=str(workspace),
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 127, result.stderr
    assert "Could not find agent binary" in (result.stdout + result.stderr)
    assert not marker.exists(), "real binary must not run when _exec_shim governs"


# ── Nested workspace rule ─────────────────────────────────────────────────


def test_find_workspace_root_innermost_wins(tmp_path):
    """A workspace nested inside another resolves to the innermost root."""
    (tmp_path / ".compart").mkdir()
    inner = tmp_path / "inner"
    (inner / ".compart").mkdir(parents=True)
    deep = inner / "src" / "deep"
    deep.mkdir(parents=True)

    assert find_workspace_root(str(deep)) == str(inner)
    assert find_workspace_root(str(tmp_path)) == str(tmp_path)


# ── PtySupervisor resolution ──────────────────────────────────────────────


@pytest.mark.skipif(sys.platform == "win32", reason="PTY not available on Windows")
def test_pty_supervisor_resolve_skips_shim_dir(tmp_path, monkeypatch):
    """Standalone PtySupervisor must not launch the workspace's own shim."""
    shim_dir = tmp_path / ".compart" / "bin"
    _write_executable(str(shim_dir / "echo"), "#!/usr/bin/env bash\n")

    monkeypatch.setenv("PATH", f"{shim_dir}:/usr/bin:/bin")

    sup = PtySupervisor(workdir=str(tmp_path))
    resolved = sup._resolve("echo")
    assert os.path.basename(resolved) == "echo"
    assert os.path.abspath(resolved) != os.path.abspath(str(shim_dir / "echo"))
    assert os.path.isfile(resolved)
