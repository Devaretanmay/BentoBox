"""Tests for config.py — YAML workspace config loader."""

import os
import shutil
import tempfile
import textwrap
import pytest

from compart.config import (
    load_config,
    is_compart_workspace,
    find_workspace_root,
    _default_config,
)


def test_load_defaults_when_no_file():
    """Returns safe defaults when config.yaml is absent."""
    cfg = load_config("/nonexistent/path/config.yaml")
    assert "default" in cfg.compartments
    default = cfg.compartments["default"]
    assert "fs_read" in default.permissions
    assert "fs_write" in default.permissions


def test_load_yaml_compartments():
    """Parses compartment definitions from YAML."""
    try:
        import yaml
    except ImportError:
        pytest.skip("PyYAML not installed")

    tmp = tempfile.mkdtemp()
    try:
        cfg_path = os.path.join(tmp, "config.yaml")
        with open(cfg_path, "w") as f:
            f.write(textwrap.dedent("""\
                compartments:
                  default:
                    filesystem: workspace
                    network: restricted
                  research:
                    filesystem: read-only
                    network: allowed
                agents:
                  claude:
                    compartment: default
                  opencode:
                    compartment: research
            """))
        cfg = load_config(cfg_path)
        assert "default" in cfg.compartments
        assert "research" in cfg.compartments
        research = cfg.compartments["research"]
        assert "network" in research.permissions
        assert "fs_write" not in research.permissions
        assert cfg.agents["claude"].compartment == "default"
        assert cfg.agents["opencode"].compartment == "research"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_policy_for_agent():
    """policy_for_agent returns correct permissions for configured agents."""
    try:
        import yaml
    except ImportError:
        pytest.skip("PyYAML not installed")

    tmp = tempfile.mkdtemp()
    try:
        cfg_path = os.path.join(tmp, "config.yaml")
        with open(cfg_path, "w") as f:
            f.write(textwrap.dedent("""\
                compartments:
                  default:
                    filesystem: workspace
                    network: restricted
                agents:
                  claude:
                    compartment: default
            """))
        cfg = load_config(cfg_path)
        policy = cfg.policy_for_agent("claude")
        assert "permissions" in policy
        assert "fs_read" in policy["permissions"]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_is_compart_workspace():
    tmp = tempfile.mkdtemp()
    try:
        assert not is_compart_workspace(tmp)
        os.makedirs(os.path.join(tmp, ".compart"))
        assert is_compart_workspace(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_find_workspace_root_traversal():
    tmp = tempfile.mkdtemp()
    try:
        os.makedirs(os.path.join(tmp, ".compart"))
        nested = os.path.join(tmp, "src", "deep")
        os.makedirs(nested)
        root = find_workspace_root(nested)
        assert root == tmp
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_find_workspace_root_not_found():
    assert find_workspace_root("/") is None
