"""Tests for local-first havfrys init wizard and client installer module."""

from pathlib import Path
import pytest

from havfrys.installer import run_init_wizard


class TestInstallerWizard:

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

    def test_ensure_workspace_initialized(self, tmp_path):
        from havfrys.installer import ensure_workspace_initialized

        target = tmp_path / "auto_init_proj"
        target.mkdir()
        hav_file = ensure_workspace_initialized(str(target))
        assert hav_file.exists()
        assert (target / ".havfrys" / "HAVFRYS.md").exists()
        content = hav_file.read_text()
        assert "# HAVFRYS" in content
