"""RL task simulation tests — multi-trial loops, branch isolation, environment analysis."""

import os
import subprocess
import time
import json
import pytest
from havfrys.session import ExecutionSession, MaintenanceSession, get_session


class TestExecutionSessionRLTasks:

    def test_rl_multi_trial_rollback_loop(self, tmp_path):
        """RL agent spawns trial, runs experiment, snapshots, evaluates,
        rolls back on failure, iterates to convergence."""
        target = tmp_path / "rl_trials"
        target.mkdir()
        (target / "train.py").write_text(
            "import sys\n"
            "lr = float(sys.argv[1]) if len(sys.argv) > 1 else 0.1\n"
            "reward = 1.0 / (1.0 + abs(lr - 0.01))\n"
            "print(f'reward={reward:.4f}')\n"
        )

        lrs = [0.5, 0.1, 0.01, 0.001]
        best_reward = -1.0
        best_lr = None

        for lr in lrs:
            session = ExecutionSession(workdir=str(target))
            code, out, err, elapsed = session.run(f"python3 train.py {lr}")
            assert code == 0

            snap_msg = session.snapshot(f"trial_lr_{lr}")
            assert "Snapshot" in snap_msg

            reward = None
            for line in out.splitlines():
                if line.startswith("reward="):
                    reward = float(line.split("=")[1])

            if reward is not None and reward > best_reward:
                best_reward = reward
                best_lr = lr

            session.exit()

        assert best_lr == 0.01
        assert best_reward > 0.5

    def test_rl_branch_isolation(self, tmp_path):
        """Multiple parallel worktrees — each trial isolated, no cross-contamination."""
        target = tmp_path / "rl_parallel"
        target.mkdir()
        (target / "counter.py").write_text(
            "import os\n"
            "counter_file = 'trial_counter.txt'\n"
            "count = 0\n"
            "if os.path.exists(counter_file):\n"
            "    with open(counter_file) as f:\n"
            "        count = int(f.read().strip())\n"
            "count += 1\n"
            "with open(counter_file, 'w') as f:\n"
            "    f.write(str(count))\n"
            "print(f'count={count}')\n"
        )

        sessions = []
        n_trials = 5
        for i in range(n_trials):
            s = ExecutionSession(workdir=str(target))
            sessions.append(s)

        results = []
        for s in sessions:
            code, out, err, elapsed = s.run("python3 counter.py")
            assert code == 0
            count = None
            for line in out.splitlines():
                if line.startswith("count="):
                    count = int(line.split("=")[1])
            results.append(count)

        for s in sessions:
            s.exit()

        # Each isolated worktree sees count=1 (no cross-contamination)
        assert all(c == 1 for c in results), f"Expected all 1s, got {results}"

    def test_rl_failure_recovery(self, tmp_path):
        """RL agent crashes mid-experiment; snapshot restores clean state."""
        target = tmp_path / "rl_recovery"
        target.mkdir()
        (target / "experiment.py").write_text(
            "import sys\n"
            "with open('state.txt', 'w') as f:\n"
            "    f.write('partial')\n"
            "if len(sys.argv) > 1 and sys.argv[1] == 'crash':\n"
            "    raise RuntimeError('simulated crash')\n"
            "with open('state.txt', 'w') as f:\n"
            "    f.write('complete')\n"
        )

        session = ExecutionSession(workdir=str(target))

        # Run successful init
        code, _, _, _ = session.run("python3 experiment.py no_crash")
        assert code == 0
        state_file = os.path.join(session.worktree_path, "state.txt")
        assert open(state_file).read() == "complete"

        snap_msg = session.snapshot("clean_state")
        assert "Snapshot" in snap_msg

        # Run crashing experiment — corrupts state
        code, _, _, _ = session.run("python3 experiment.py crash")
        assert code != 0
        assert open(state_file).read() == "partial"

        # Rollback to clean state
        roll_msg = session.rollback("clean_state")
        assert "rolled back" in roll_msg.lower()
        assert open(state_file).read() == "complete"

        session.exit()

    def test_rl_compressed_output_in_loop(self, tmp_path):
        """RL training loop output auto-compressed when above threshold."""
        target = tmp_path / "rl_compress"
        target.mkdir()
        # Generate enough output to exceed 5KB auto-compression threshold
        lines = [f"step={i} loss={0.1/(i+1)+1:.6f} time={i*0.01:.4f}" for i in range(1, 600)]
        long_log = "\n".join(lines)
        (target / "train.sh").write_text(f"cat <<'EOF'\n{long_log}\nEOF\n")

        from havfrys._core import route_and_compress
        assert len(long_log) > 5120, f"Need >5KB for auto-compress, got {len(long_log)}"

        session = ExecutionSession(workdir=str(target))
        code, out, err, elapsed = session.run("bash train.sh")
        assert code == 0

        # Auto-compression should trigger (output > 5KB)
        raw_len = len(long_log)
        compressed_len = len(out)
        assert compressed_len < raw_len, (
            f"Expected compression ({compressed_len} >= {raw_len})"
        )

        # route_and_compress still works standalone
        compressed = route_and_compress(long_log)
        assert len(compressed) < raw_len

        session.exit()

    def test_rl_apply_verified_trial(self, tmp_path):
        """RL agent runs trial in worktree, verifies success, applies to main repo."""
        target = tmp_path / "rl_apply_trial"
        target.mkdir()
        (target / ".gitignore").write_text("__pycache__/\n*.pyc\n")
        (target / "policy.py").write_text(
            "# Original policy\n"
            "def act(obs):\n"
            "    return 0\n"
        )

        session = ExecutionSession(workdir=str(target))

        # Write improved policy in worktree
        policy_path = os.path.join(session.worktree_path, "policy.py")
        with open(policy_path, "w") as f:
            f.write(
                "# Improved policy\n"
                "def act(obs):\n"
                "    return 1 if obs > 0.5 else 0\n"
            )

        # Verify it works in isolation
        code, _, _, _ = session.run("python3 -c \"from policy import act; assert act(0.6) == 1; assert act(0.3) == 0\"")
        assert code == 0, "improved policy failed verification"

        app_msg = session.apply()
        assert "Successfully applied" in app_msg

        # Main repo has the change
        main_policy = target / "policy.py"
        assert "Improved policy" in main_policy.read_text()

        session.exit()

    def test_rl_multi_branch_sweep(self, tmp_path):
        """Hyperparameter sweep across N branches — verify each sees own config."""
        target = tmp_path / "rl_sweep"
        target.mkdir()
        (target / "sweep.py").write_text(
            "import json\n"
            "import os\n"
            "with open('config.json') as f:\n"
            "    cfg = json.load(f)\n"
            "print(f'batch_size={cfg[\"batch_size\"]} lr={cfg[\"lr\"]}')\n"
        )

        configs = [
            {"batch_size": 32, "lr": 0.01},
            {"batch_size": 64, "lr": 0.001},
            {"batch_size": 128, "lr": 0.0001},
        ]

        sessions = []
        for cfg in configs:
            s = ExecutionSession(workdir=str(target))
            cfg_path = os.path.join(s.worktree_path, "config.json")
            with open(cfg_path, "w") as f:
                json.dump(cfg, f)
            sessions.append(s)

        for i, s in enumerate(sessions):
            code, out, err, elapsed = s.run("python3 sweep.py")
            assert code == 0
            assert f"batch_size={configs[i]['batch_size']}" in out
            assert f"lr={configs[i]['lr']}" in out

        for s in sessions:
            s.exit()

    def test_rl_session_reentry(self, tmp_path):
        """get_session re-enters existing session by id."""
        target = tmp_path / "rl_reentry"
        target.mkdir()
        (target / "script.py").write_text("print('run_once')\n")

        s1 = ExecutionSession(workdir=str(target))

        s2 = get_session(session_id=s1.session_id, workdir=str(target), session_type="execution")
        assert s2 is s1

        code, out, _, _ = s1.run("python3 script.py")
        assert code == 0
        assert "run_once" in out

        s1.exit()


class TestMaintenanceSessionRLTasks:

    def test_rl_env_analysis(self, tmp_path):
        """RL environment analysis — detect language, framework, test infra."""
        target = tmp_path / "rl_env"
        target.mkdir()
        (target / "pyproject.toml").write_text("[project]\nname='rl_env'\ndependencies=['torch', 'gymnasium']\n")
        (target / "pytest.ini").write_text("[pytest]\n")
        (target / "train.py").write_text("def train():\n    pass\n")
        (target / "tests").mkdir()
        (target / "tests" / "test_policy.py").write_text("def test_policy():\n    pass\n")

        # MaintenanceSession does not auto-init git; do it explicitly
        subprocess.run(["git", "init"], cwd=str(target), capture_output=True)
        subprocess.run(["git", "add", "-A"], cwd=str(target), capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "init"],
            cwd=str(target), capture_output=True,
            env={**os.environ,
                 "GIT_AUTHOR_NAME": "test", "GIT_AUTHOR_EMAIL": "test@test",
                 "GIT_COMMITTER_NAME": "test", "GIT_COMMITTER_EMAIL": "test@test"},
        )

        session = MaintenanceSession(workdir=str(target))
        analysis = json.loads(session.analyse())

        assert analysis["language"] == "Python"
        assert "pytest" in analysis["test_framework"].lower()
        assert analysis["is_git_repo"] is True
        assert analysis["files_count"] > 0
        assert "pip" in analysis.get("build_system", "")

        exit_msg = session.exit()
        assert "closed" in exit_msg

    def test_rl_infra_verify(self, tmp_path):
        """RL infrastructure verification — test suite passes."""
        target = tmp_path / "rl_infra"
        target.mkdir()
        (target / "pyproject.toml").write_text("[project]\nname='rl_infra'\n")
        (target / "pytest.ini").write_text("[pytest]\n")
        tests_dir = target / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_env.py").write_text(
            "def test_observation_space():\n"
            "    assert 1 + 1 == 2\n"
            "\n"
            "def test_action_space():\n"
            "    assert [0, 1, 2][0] == 0\n"
        )

        session = MaintenanceSession(workdir=str(target))
        result = session.verify()

        assert result["passed"] is True
        assert result["status"] == "success"
        assert "pytest" in result["command_used"]
        assert result["failures"] is None or len(result["failures"]) == 0

        session.exit()

    def test_rl_history_tracking(self, tmp_path):
        """RL experiment evolution tracked in maintenance graph."""
        target = tmp_path / "rl_history"
        target.mkdir()
        (target / "pyproject.toml").write_text("[project]\nname='rl_history'\n")

        session = MaintenanceSession(workdir=str(target))

        graph = session.history()
        assert graph is not None

        analysis = json.loads(session.analyse())
        assert analysis["files_count"] > 0

        session.exit()

    def test_rl_failing_env_verify(self, tmp_path):
        """RL infra with failing test — verify reports failure correctly."""
        target = tmp_path / "rl_failing"
        target.mkdir()
        (target / "pyproject.toml").write_text("[project]\nname='rl_failing'\n")
        (target / "pytest.ini").write_text("[pytest]\n")
        tests_dir = target / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_env.py").write_text(
            "def test_observation_space():\n"
            "    assert 1 + 1 == 3\n"
        )

        session = MaintenanceSession(workdir=str(target))
        result = session.verify()

        assert result["passed"] is False
        assert result["status"] == "failure"
        assert len(result["failures"]) > 0

        session.exit()

    def test_rl_empty_workspace_context(self, tmp_path):
        """RL empty workspace — analysis shows no project detected."""
        target = tmp_path / "rl_empty"
        target.mkdir()

        session = MaintenanceSession(workdir=str(target))
        analysis = json.loads(session.analyse())
        # Empty dir — no git, no files, no build system
        assert analysis["is_git_repo"] is False
        assert analysis["files_count"] >= 0
        assert analysis.get("build_system", "") in ("", "none")

        session.exit()

    def test_rl_docker_environment(self, tmp_path):
        """RL environment with Docker — analysis detects docker."""
        target = tmp_path / "rl_docker"
        target.mkdir()
        (target / "Dockerfile").write_text("FROM python:3.11\n")
        (target / "train.py").write_text("def train():\n    pass\n")

        session = MaintenanceSession(workdir=str(target))
        analysis = json.loads(session.analyse())
        assert analysis["docker"] is True

        exit_msg = session.exit()
        assert "closed" in exit_msg

    def test_rl_cache_fingerprint(self, tmp_path):
        """Analysis cache hit on repeat call with same fingerprint."""
        target = tmp_path / "rl_cache"
        target.mkdir()
        (target / "pyproject.toml").write_text("[project]\nname='rl_cache'\n")
        (target / "train.py").write_text("def train():\n    pass\n")

        session = MaintenanceSession(workdir=str(target))

        res1 = json.loads(session.analyse())
        # Ensure metadata file exists from first analysis
        time.sleep(0.1)
        # Second call should hit cache
        res2 = json.loads(session.analyse())

        assert res1["language"] == res2["language"]
        assert res1["build_system"] == res2["build_system"]

        session.exit()
