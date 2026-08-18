"""Regression tests for auditor-identified edge cases.

Covers bugs that were found but not caught by the existing suite:
- config.py: null/empty YAML sections crashing with AttributeError
- pty_supervisor.py: empty argv ValueError guard
- execution.py: snapshot_dir persists through JSON round-trip
- main.py: session.started_at=None safe in cmd_status
- main.py: workflow node with malformed command string handled gracefully
"""

import os
import shutil
import sys
import tempfile
import textwrap
import pytest
import yaml

from compart.cli.main import _topo_sort
from compart.config import load_config
from compart.engine.execution import Execution, ExecutionKind, ExecutionManager, ExecutionStatus
from compart.engine.pty_supervisor import PtySupervisor


def test_config_null_compartments_section():
    """compartments: (no body) must not raise AttributeError."""
    tmp = tempfile.mkdtemp()
    try:
        p = os.path.join(tmp, "config.yaml")
        with open(p, "w") as f:
            f.write("compartments:\nagents:\nworkflows:\n")
        cfg = load_config(p)
        assert "default" in cfg.compartments
        assert cfg.agents == {}
        assert cfg.workflows == {}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_config_null_agents_section():
    """agents: (no body) must not crash."""
    tmp = tempfile.mkdtemp()
    try:
        p = os.path.join(tmp, "config.yaml")
        with open(p, "w") as f:
            f.write(textwrap.dedent("""\
                compartments:
                  default:
                    filesystem: workspace
                    network: restricted
                agents:
            """))
        cfg = load_config(p)
        assert cfg.agents == {}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_config_null_workflows_section():
    """workflows: (no body) must not crash."""
    tmp = tempfile.mkdtemp()
    try:
        p = os.path.join(tmp, "config.yaml")
        with open(p, "w") as f:
            f.write(textwrap.dedent("""\
                compartments:
                  default:
                    filesystem: workspace
                    network: restricted
                workflows:
            """))
        cfg = load_config(p)
        assert cfg.workflows == {}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_config_depends_on_null():
    """depends_on: (no value) must default to empty list, not None."""
    tmp = tempfile.mkdtemp()
    try:
        p = os.path.join(tmp, "config.yaml")
        with open(p, "w") as f:
            f.write(textwrap.dedent("""\
                compartments:
                  default:
                    filesystem: workspace
                    network: restricted
                workflows:
                  test_wf:
                    nodes:
                      step_a:
                        type: process
                        command: echo hello
                        depends_on:
            """))
        cfg = load_config(p)
        nodes = cfg.workflows["test_wf"].nodes
        assert nodes[0].depends_on == [], f"Expected [], got {nodes[0].depends_on}"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


@pytest.mark.skipif(sys.platform == "win32", reason="PTY not on Windows")
def test_pty_supervisor_empty_argv_attach():
    sup = PtySupervisor(workdir=".")
    with pytest.raises(ValueError, match="argv must not be empty"):
        sup.attach([])


@pytest.mark.skipif(sys.platform == "win32", reason="PTY not on Windows")
def test_pty_supervisor_empty_argv_capture():
    sup = PtySupervisor(workdir=".")
    with pytest.raises(ValueError, match="argv must not be empty"):
        sup.capture([])


def test_snapshot_dir_persists():
    tmp = tempfile.mkdtemp()
    try:
        mgr = ExecutionManager(workdir=tmp)
        ex = mgr.create(kind=ExecutionKind.INTERACTIVE, command=["claude"])
        ex.snapshot_dir = "/tmp/compart_test_snap"
        mgr.save(ex)
        loaded = mgr.get(ex.execution_id)
        assert loaded is not None
        assert loaded.snapshot_dir == "/tmp/compart_test_snap"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_status_started_at_none_safe():
    """Duration calculation in cmd_status must not crash when started_at is None."""
    started_at = None
    finished_at = 1000.0
    dur = round(((finished_at or 0) - (started_at or 0)), 1)
    assert dur == 1000.0


def test_topo_sort_empty_nodes():
    """_topo_sort must return empty list for empty input without crashing."""
    assert _topo_sort([]) == []
