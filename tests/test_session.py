"""Unit tests for stateful Execution and Maintenance Environments."""

import os
import subprocess
import pytest
from havfrys.session import ExecutionSession, MaintenanceSession, get_session


class TestExecutionSession:

    def test_execution_session_lifecycle(self, tmp_path):
        target = tmp_path / "repo"
        target.mkdir()
        (target / "app.py").write_text("print('hello')\n")

        # Create session
        session = ExecutionSession(workdir=str(target))
        assert session.session_id.startswith("exe_")
        assert os.path.exists(session.worktree_path)

        # Run command inside worktree
        code, out, err, elapsed = session.run("python3 app.py")
        assert code == 0
        assert "hello" in out

        # Create snapshot
        snap_msg = session.snapshot("pre_change")
        assert "pre_change" in snap_msg

        # Modify file in worktree
        with open(os.path.join(session.worktree_path, "app.py"), "w") as f:
            f.write("print('modified')\n")

        diff = session.diff()
        assert "modified" in diff

        # Rollback
        roll_msg = session.rollback("pre_change")
        assert "pre_change" in roll_msg

        # Apply & Exit
        with open(os.path.join(session.worktree_path, "new_file.txt"), "w") as f:
            f.write("new file content\n")

        apply_msg = session.apply()
        assert "Successfully applied" in apply_msg
        assert (target / "new_file.txt").exists()

        exit_msg = session.exit()
        assert "closed" in exit_msg
        assert not os.path.exists(session.worktree_path)


class TestMaintenanceSession:

    def test_maintenance_session_lifecycle(self, tmp_path):
        target = tmp_path / "maint_repo"
        target.mkdir()
        (target / "pyproject.toml").write_text("[project]\nname='foo'\n")

        session = MaintenanceSession(workdir=str(target))
        assert session.session_id.startswith("maint_")

        analysis = session.analyse()
        assert "Python" in analysis
        assert '"is_git_repo": true' in analysis or '"is_git_repo": false' in analysis

        # observe + knowledge persistence
        msg = session.observe("test_key", "test_value")
        assert "recorded" in msg
        knowledge = session.knowledge()
        assert "observations" in knowledge
        assert knowledge["observations"]["test_key"]["value"] == "test_value"

        exit_msg = session.exit()
        assert "closed" in exit_msg
