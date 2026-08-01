import subprocess
import sys

import pytest

from bentoworks.cli import main


@pytest.fixture
def cli_cwd(tmp_path, monkeypatch):
    """Run each CLI test from a fresh temporary directory."""
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_run_prints_stdout(cli_cwd, capsys):
    assert main(["run", "--cmd", "echo CLI_STDOUT_123", "--name", "demo"]) == 0
    out = capsys.readouterr().out
    assert "Status: success" in out
    assert "CLI_STDOUT_123" in out


def test_run_prints_stderr(cli_cwd, capsys):
    assert main(["run", "--cmd", "echo CLI_ERR_456 >&2", "--name", "demo"]) == 0
    captured = capsys.readouterr()
    assert "CLI_ERR_456" in captured.err or "CLI_ERR_456" in captured.out


def test_run_surfaces_nonzero_exit(cli_cwd, capsys):
    assert main(["run", "--cmd", "exit 3", "--name", "demo"]) == 1


def test_run_exit_zero_for_success(cli_cwd, capsys):
    assert main(["run", "--cmd", "true", "--name", "demo"]) == 0


def test_run_goal_positional_is_used(cli_cwd, capsys):
    # `goal` positional is the shell command when --cmd is omitted.
    assert main(["run", "echo GOAL_789", "--name", "demo"]) == 0
    out = capsys.readouterr().out
    assert "GOAL_789" in out


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
    assert "bentoworks 0.9.1" in result.stdout
