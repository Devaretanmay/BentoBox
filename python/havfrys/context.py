"""Context Resolution Layer — classifies workspace into engineering context types."""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum

from havfrys.validator import _detect_test_commands


class ContextType(str, Enum):
    EMPTY_WORKSPACE = "empty_workspace"
    SINGLE_FILE = "single_file"
    REPOSITORY = "repository"
    DOCKER_PROJECT = "docker_project"
    DOCUMENTATION = "documentation"


@dataclass
class EngineeringContext:
    context_type: ContextType
    is_git_repo: bool
    has_test_suite: bool
    has_build_system: bool
    is_docker: bool
    files_count: int
    primary_language: str = "unknown"
    summary: str = ""


def resolve_context(workdir: str, goal: str = "") -> EngineeringContext:
    """Inspect the target directory and goal to resolve the Engineering Context."""
    workdir_abs = os.path.abspath(workdir or os.getcwd())

    if not os.path.exists(workdir_abs):
        os.makedirs(workdir_abs, exist_ok=True)

    files = []
    try:
        ignored_dirs = {".git", ".havfrys", "node_modules", "venv", ".venv", "__pycache__", "target", "build", "dist", "site-packages"}
        for root, dirs, filenames in os.walk(workdir_abs):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ignored_dirs]
            for f in filenames:
                if not f.startswith("."):
                    files.append(os.path.join(root, f))
    except Exception:
        pass

    files_count = len(files)
    is_git_repo = os.path.exists(os.path.join(workdir_abs, ".git"))
    is_docker = os.path.exists(os.path.join(workdir_abs, "Dockerfile")) or os.path.exists(
        os.path.join(workdir_abs, "docker-compose.yml")
    )

    build_manifests = {"Cargo.toml", "pyproject.toml", "package.json", "go.mod", "Makefile", "pom.xml"}
    has_build_system = any(os.path.exists(os.path.join(workdir_abs, m)) for m in build_manifests)

    from havfrys.validator import _detect_test_commands
    test_cmds = _detect_test_commands(workdir_abs)
    has_test_suite = len(test_cmds) > 0

    if files_count == 0:
        ctx_type = ContextType.EMPTY_WORKSPACE
        summary = "Empty workspace (Greenfield task)"
    elif files_count == 1:
        ctx_type = ContextType.SINGLE_FILE
        summary = f"Single file target ({files[0]})"
    elif is_docker:
        ctx_type = ContextType.DOCKER_PROJECT
        summary = "Docker project environment"
    elif has_build_system or is_git_repo:
        ctx_type = ContextType.REPOSITORY
        summary = f"Software repository ({files_count} files, git={is_git_repo})"
    else:
        ctx_type = ContextType.DOCUMENTATION
        summary = f"General workspace ({files_count} files)"

    return EngineeringContext(
        context_type=ctx_type,
        is_git_repo=is_git_repo,
        has_test_suite=has_test_suite,
        has_build_system=has_build_system,
        is_docker=is_docker,
        files_count=files_count,
        summary=summary,
    )


def scaffold_greenfield_workspace(workdir: str, goal: str) -> None:
    """Scaffold baseline workspace file targets for greenfield tasks."""
    workdir_abs = os.path.abspath(workdir or os.getcwd())
    if not os.path.exists(workdir_abs):
        os.makedirs(workdir_abs, exist_ok=True)

    existing = [f for f in os.listdir(workdir_abs) if not f.startswith(".")]
    if existing:
        return

    goal_lower = goal.lower()
    if any(w in goal_lower for w in ["rust", "cargo"]):
        with open(os.path.join(workdir_abs, "main.rs"), "w", encoding="utf-8") as f:
            f.write("fn main() {\n    println!(\"Hello from HAVFRYS\");\n}\n")
    elif any(w in goal_lower for w in ["go", "golang"]):
        with open(os.path.join(workdir_abs, "main.go"), "w", encoding="utf-8") as f:
            f.write("package main\nimport \"fmt\"\nfunc main() {\n    fmt.Println(\"Hello from HAVFRYS\")\n}\n")
    elif any(w in goal_lower for w in ["node", "express", "typescript", "ts", "javascript", "js"]):
        with open(os.path.join(workdir_abs, "index.js"), "w", encoding="utf-8") as f:
            f.write("// Scaffolded by HAVFRYS\nconsole.log('Hello from HAVFRYS');\n")
    else:
        with open(os.path.join(workdir_abs, "app.py"), "w", encoding="utf-8") as f:
            f.write("# Scaffolded by HAVFRYS\n")
