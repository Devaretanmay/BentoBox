"""Tests for local-first havfrys init wizard and client installer module."""

import json
import os
from pathlib import Path
import pytest

from havfrys.installer import (
    get_havfrys_mcp_config,
    install_claude_code,
    install_cursor,
    install_vscode,
    install_opencode,
    install_gemini,
    install_windsurf,
    install_cline,
    install_continue,
    install_zed,
    run_init_wizard,
)


class TestInstallerWizard:

    def test_get_havfrys_mcp_config_structure(self):
        cfg = get_havfrys_mcp_config()
        assert "command" in cfg
        assert cfg["args"] == ["serve"]

    def test_install_claude_code(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        ok, path = install_claude_code()
        assert ok
        assert os.path.exists(path)

        data = json.loads(Path(path).read_text())
        assert "mcpServers" in data
        assert "havfrys" in data["mcpServers"]
        assert data["mcpServers"]["havfrys"]["args"] == ["serve"]

    def test_install_cursor(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        ok, path = install_cursor()
        assert ok
        data = json.loads(Path(path).read_text())
        assert "havfrys" in data["mcpServers"]

    def test_install_vscode(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        ok, path = install_vscode()
        assert ok
        data = json.loads(Path(path).read_text())
        assert "havfrys" in data["mcpServers"]

    def test_install_windsurf(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        ok, path = install_windsurf()
        assert ok
        data = json.loads(Path(path).read_text())
        assert "havfrys" in data["mcpServers"]

    def test_install_cline(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        ok, path = install_cline()
        assert ok
        data = json.loads(Path(path).read_text())
        assert "havfrys" in data["mcpServers"]

    def test_run_init_wizard_creates_hav_md(self, tmp_path, capsys):
        target = tmp_path / "my_project"
        target.mkdir()
        run_init_wizard(target_dir=str(target))
        out = capsys.readouterr().out
        assert "Initialized" in out
        assert "HAVFRYS.md" in out
        assert (target / ".havfrys" / "HAVFRYS.md").exists()
        hav_content = (target / ".havfrys" / "HAVFRYS.md").read_text()
        assert "# HAVFRYS" in hav_content
        assert "Principles" in hav_content
