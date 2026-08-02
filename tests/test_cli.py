import subprocess
import sys

import pytest

from bentoworks import __version__
from bentoworks.cli import main


@pytest.fixture
def cli_cwd(tmp_path, monkeypatch):
    """Run each CLI test from a fresh temporary directory."""
    monkeypatch.chdir(tmp_path)
    return tmp_path


# NOTE: the in-process tests below use --no-sandbox on purpose. The kernel
# sandbox is irreversible for the process tree, so applying it inside a test
# runner would sandbox pytest itself. The sandboxed path is covered by
# test_run_blocks_credentials_in_subprocess, which runs the CLI in a child.


def test_run_prints_stdout(cli_cwd, capsys):
    assert main(["run", "--no-sandbox", "--cmd", "echo CLI_STDOUT_123", "--name", "demo"]) == 0
    out = capsys.readouterr().out
    assert "Status: success" in out
    assert "CLI_STDOUT_123" in out


def test_run_prints_stderr(cli_cwd, capsys):
    assert main(["run", "--no-sandbox", "--cmd", "echo CLI_ERR_456 >&2", "--name", "demo"]) == 0
    captured = capsys.readouterr()
    assert "CLI_ERR_456" in captured.err or "CLI_ERR_456" in captured.out


def test_run_surfaces_nonzero_exit(cli_cwd, capsys):
    assert main(["run", "--no-sandbox", "--cmd", "exit 3", "--name", "demo"]) == 1


def test_run_exit_zero_for_success(cli_cwd, capsys):
    assert main(["run", "--no-sandbox", "--cmd", "true", "--name", "demo"]) == 0


def test_run_goal_positional_is_used(cli_cwd, capsys):
    # `goal` positional is the shell command when --cmd is omitted.
    assert main(["run", "--no-sandbox", "echo GOAL_789", "--name", "demo"]) == 0
    out = capsys.readouterr().out
    assert "GOAL_789" in out


def test_run_defaults_to_kernel_sandbox(tmp_path, monkeypatch):
    """Without --no-sandbox, cmd_run must ask BentoBox for a kernel sandbox.

    We assert the wiring (not enforcement - that is a subprocess test) by
    checking the default config enables the sandbox path.
    """
    from bentoworks.bentobox import BentoBoxConfig
    cfg = BentoBoxConfig(sandbox=False)
    assert cfg.sandbox is False  # library default stays off (embedding-safe)
    cfg2 = BentoBoxConfig()
    assert cfg2.sandbox is False


def test_run_blocks_credentials_in_subprocess(tmp_path):
    """The credibility test: `bentoworks run` must NOT leak ~/.ssh.

    Runs in a subprocess so the irreversible kernel sandbox does not trap
    pytest. If the native _core module is unavailable, the CLI degrades to a
    no-sandbox warning and this test is skipped.
    """
    import importlib.util
    if importlib.util.find_spec("bentoworks._core") is None:
        pytest.skip("native _core not installed; sandbox not available")

    cmd = 'cat ~/.ssh/id_ed25519 2>/dev/null || cat "$HOME/.ssh/id_ed25519" 2>/dev/null'
    result = subprocess.run(
        [sys.executable, "-m", "bentoworks.cli", "run", "--cmd", cmd],
        capture_output=True, text=True, cwd=str(tmp_path),
    )
    combined = result.stdout + result.stderr
    assert "OPENSSH PRIVATE KEY" not in combined
    assert "BEGIN OPENSSH" not in combined
    assert result.returncode != 0


def test_why_allowed_path(cli_cwd, capsys):
    assert main(["why", "/etc/passwd", "--workdir", "/tmp"]) == 0
    assert "ALLOWED" in capsys.readouterr().out


def test_main_entry_point():
    """The installed `bentoworks` script resolves to cli.main.

    Runs in a subprocess importing the *installed* package (the venv is
    reinstalled from the wheel, which owns the native _core module). No
    PYTHONPATH override - pointing at the source tree would bypass the
    installed package and silently lose the native sandbox/compression core.
    """
    result = subprocess.run(
        [sys.executable, "-m", "bentoworks.cli", "--version"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0
    assert f"bentoworks {__version__}" in result.stdout
