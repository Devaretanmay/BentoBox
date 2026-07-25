"""Stress tests and edge case validation for the 8 HAVFRYS improvements."""

import os
import shutil
import pytest
from havfrys.validator import extract_semantic_failures
from havfrys.context import scaffold_greenfield_workspace, resolve_context, ContextType
from havfrys.branch_loop import BranchLoopDetector, AttemptSignature
from havfrys.orchestrator import Orchestrator, MicroBranch
from havfrys.installer import run_doctor, detect_installed_clients


def test_1_semantic_failures_edge_cases():
    # Edge Case 1: None / Empty
    assert extract_semantic_failures("") == ""
    
    # Edge Case 2: Unicode & Special characters
    log_with_unicode = "FAILED tests/test_foo.py::test_utf8 - AssertionError: 💥 test error 🔥"
    res = extract_semantic_failures(log_with_unicode)
    assert "HAVFRYS Failure Analysis" in res
    assert "test_utf8" in res

    # Edge Case 3: More than 5 errors (should cap at 5)
    huge_log = "\n".join([f"FAILED test_{i}.py::test_bar - Error" for i in range(20)])
    res2 = extract_semantic_failures(huge_log)
    assert res2.count("• FAILED") == 5


def test_2_quality_aware_branch_selection():
    orch = Orchestrator(task="test task", workdir="/tmp")
    
    # Mock micro-branches
    class DummyResult:
        def __init__(self, status, diff_lines, attempts_used, tokens_used):
            self.status = status
            self.diff_lines = diff_lines
            self.attempts_used = attempts_used
            self.tokens_used = tokens_used

    class DummyBranch:
        def __init__(self, result):
            self.result = result

    # Scenario A: Branch 1 (diff=10, attempts=1), Branch 2 (diff=2, attempts=2)
    b1 = DummyBranch(DummyResult("success", 10, 1, 100))
    b2 = DummyBranch(DummyResult("success", 2, 2, 80))
    winner = orch._select_winner([b1, b2])
    assert winner == b2  # Smaller diff wins

    # Scenario B: All diffs == 0
    b3 = DummyBranch(DummyResult("success", 0, 1, 50))
    b4 = DummyBranch(DummyResult("success", 0, 2, 30))
    winner_zero = orch._select_winner([b3, b4])
    assert winner_zero in [b3, b4]


def test_3_and_5_greenfield_scaffolding_multilang(tmp_path):
    # Rust
    rust_dir = tmp_path / "rust_proj"
    scaffold_greenfield_workspace(str(rust_dir), "Build a Rust CLI tool")
    assert (rust_dir / "main.rs").exists()

    # Go
    go_dir = tmp_path / "go_proj"
    scaffold_greenfield_workspace(str(go_dir), "Build a Golang server")
    assert (go_dir / "main.go").exists()

    # TS / Node
    node_dir = tmp_path / "node_proj"
    scaffold_greenfield_workspace(str(node_dir), "Build an Express TS web app")
    assert (node_dir / "index.js").exists()

    # Python (Default)
    py_dir = tmp_path / "py_proj"
    scaffold_greenfield_workspace(str(py_dir), "Build a FastAPI invoice service")
    assert (py_dir / "app.py").exists()

    # Non-empty dir should NOT overwrite existing files
    scaffold_greenfield_workspace(str(py_dir), "Build a Rust project")
    assert not (py_dir / "main.rs").exists()


def test_6_zero_diff_stagnation_early_termination():
    detector = BranchLoopDetector(stagnation_threshold=3)
    
    # 1st attempt: zero diff
    sig1 = AttemptSignature(index=1, exit_code=1, output_hash="h1", error_hash="e1", diff_lines=0, tokens_spent=50)
    v1 = detector.record(sig1)
    assert not v1.should_kill

    # 2nd attempt: zero diff -> kill immediately
    sig2 = AttemptSignature(index=2, exit_code=1, output_hash="h2", error_hash="e2", diff_lines=0, tokens_spent=50)
    v2 = detector.record(sig2)
    assert v2.should_kill
    assert v2.loop_type == "no_diff"


def test_8_doctor_diagnostics_does_not_crash(capsys):
    run_doctor()
    captured = capsys.readouterr()
    assert "Runtime Diagnostics" in captured.out
    assert "Toolchain" in captured.out


def test_dynamic_docker_image_inference(tmp_path):
    from havfrys.core import _infer_docker_image

    rust_dir = tmp_path / "rust_proj"
    rust_dir.mkdir()
    (rust_dir / "Cargo.toml").write_text("[package]\nname='foo'")
    assert _infer_docker_image(str(rust_dir)) == "rust:latest"

    node_dir = tmp_path / "node_proj"
    node_dir.mkdir()
    (node_dir / "package.json").write_text("{}")
    assert _infer_docker_image(str(node_dir)) == "node:latest"

    go_dir = tmp_path / "go_proj"
    go_dir.mkdir()
    (go_dir / "go.mod").write_text("module foo")
    assert _infer_docker_image(str(go_dir)) == "golang:latest"
