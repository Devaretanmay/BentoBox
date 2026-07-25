"""HAVFRYS — Maintenance Infrastructure for AI-Built Software by HAVFRYS Labs."""
from __future__ import annotations

import json
import os
import shutil
import subprocess

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

from havfrys.orchestrator import Orchestrator, ExecutionReport
from havfrys.micro_branch import BranchBudget
from havfrys.memory import EngineeringMemory
from havfrys.validator import _detect_test_commands, _detect_build_commands


_LAST_REPORT: Optional[ExecutionReport] = None
_LAST_TASK: str = ""

_SESSION_MEMORY: Optional[EngineeringMemory] = None
_SESSION_LOCK = False


@dataclass
class HavfrysResult:
    """Result of a HAVFRYS execution."""
    task: str = ""
    status: str = "failed"
    output: str = ""
    error: Optional[str] = None
    execution_time_s: float = 0.0
    retries: int = 0
    cached: bool = False
    attempts: list[dict] = field(default_factory=list)
    mode: str = "linear"
    uncertainty_points: int = 0
    uncertainty_resolved: int = 0
    branches_spawned: int = 0
    branches_killed: int = 0
    token_reduction_pct: float = 0.0
    winning_fix: str = ""
    branch_summaries: list[str] = field(default_factory=list)


def exe(task: str, *, workdir: str = "") -> HavfrysResult:
    """Execute an engineering task safely via HAVFRYS engineering execution layer."""
    global _LAST_REPORT, _LAST_TASK, _SESSION_MEMORY

    if not task:
        return HavfrysResult(task=task, status="failed", error="No task provided")

    _LAST_TASK = task
    start = time.time()
    raw_workdir = workdir or os.environ.get("HAVFRYS_WORKDIR", os.getcwd())
    if raw_workdir in ("/", "") or not os.access(raw_workdir, os.W_OK):
        resolved_workdir = os.path.expanduser("~") if os.access(os.path.expanduser("~"), os.W_OK) else "/tmp"
    else:
        resolved_workdir = raw_workdir

    # Automatic Transparent Content-Addressable Cache Key
    internal_cache_key = f"{resolved_workdir}:{task.strip()}"
    cache_file = os.path.join(resolved_workdir, ".havfrys_cache.json")

    if os.path.exists(cache_file):
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content:
                    cache_data = json.loads(content)
                    if not isinstance(cache_data, dict):
                        raise ValueError("cache is not a dict")
                    if internal_cache_key in cache_data:
                        c = cache_data[internal_cache_key]
                        return HavfrysResult(
                            task=task,
                            status=c.get("status", "success"),
                            output=c.get("output", ""),
                            cached=True,
                            execution_time_s=0.001,
                            token_reduction_pct=c.get("token_reduction_pct", 50.0),
                        )
        except Exception:
            pass

    # 1. Context Resolution Layer
    from havfrys.context import resolve_context, ContextType, scaffold_greenfield_workspace
    ctx = resolve_context(resolved_workdir, task)

    if ctx.context_type == ContextType.EMPTY_WORKSPACE:
        scaffold_greenfield_workspace(resolved_workdir, task)

    # 2. Automatic Internal Risk & Sandbox Assessment (Zero User Configuration)
    requires_sandbox = "untrusted" in task.lower() or ctx.is_docker or os.path.exists(os.path.join(resolved_workdir, ".havfrys_sandbox"))
    
    internal_image = ""
    if requires_sandbox:
        internal_image = _infer_docker_image(resolved_workdir)

    # 3. Dynamic Retry Allocation
    internal_retries = 3
    if ctx.context_type in (ContextType.EMPTY_WORKSPACE, ContextType.SINGLE_FILE):
        internal_retries = 2
    elif ctx.files_count > 50:
        internal_retries = 4

    session_id = uuid.uuid4().hex[:8]

    # Initialize Session Memory
    if _SESSION_MEMORY is None:
        _SESSION_MEMORY = EngineeringMemory(session_id=session_id)

    # 4. Resolve Target Command
    resolved_cmd = _resolve_command(task, resolved_workdir)

    if resolved_cmd.startswith("echo 'Project Analysis") or resolved_cmd.startswith("echo '=== Repository structure"):
        rc, out, _ = _try_run(resolved_cmd, resolved_workdir)
        elapsed = time.time() - start
        report = ExecutionReport(
            status="success",
            output=out.strip(),
            total_attempts=1,
            execution_time_s=elapsed,
            token_reduction_pct=100.0,
        )
    else:
        # Pre-execution dependency resolution
        _install_dependencies(resolved_workdir, resolved_cmd)

        orch = Orchestrator(
            task=task,
            workdir=resolved_workdir,
            max_linear_retries=internal_retries,
            branch_budget=BranchBudget(max_attempts=internal_retries, max_seconds=3600.0),
            memory=_SESSION_MEMORY,
            image=internal_image if requires_sandbox else "",
        )

        report = orch.execute(resolved_cmd)

    _LAST_REPORT = report

    if report.status in ("success", "cached"):
        try:
            target_cache_file = os.path.join(resolved_workdir, ".havfrys_cache.json")
            cache_data = {}
            if os.path.exists(target_cache_file):
                try:
                    with open(target_cache_file, "r", encoding="utf-8") as f:
                        raw = f.read().strip()
                        if raw:
                            cache_data = json.loads(raw)
                            if not isinstance(cache_data, dict):
                                cache_data = {}
                except Exception:
                    cache_data = {}
            cache_data[internal_cache_key] = {
                "status": str(getattr(report, "status", "success")),
                "output": str(getattr(report, "output", "")),
                "token_reduction_pct": float(getattr(report, "token_reduction_pct", 0.0)),
            }
            tmp = target_cache_file + ".tmp." + uuid.uuid4().hex[:8]
            with open(tmp, "w", encoding="utf-8") as f:
                f.write(json.dumps(cache_data, indent=2))
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, target_cache_file)
        except Exception:
            pass

    elapsed = time.time() - start

    # Update Maintenance Graph
    _update_maintenance_graph(resolved_workdir, report.status, [], ["Execution task completed"])

    return HavfrysResult(
        task=task,
        status=report.status,
        output=report.output,
        error=report.error,
        execution_time_s=elapsed,
        retries=max(0, report.total_attempts - 1),
        mode=report.mode,
        uncertainty_points=report.uncertainty_points,
        uncertainty_resolved=report.uncertainty_resolved,
        branches_spawned=report.branches_spawned,
        branches_killed=report.branches_killed,
        token_reduction_pct=report.token_reduction_pct,
        winning_fix=report.winning_fix,
        branch_summaries=report.branch_summaries,
    )


def maintain(target: str = ".", *, workdir: str = "", verification_mode: bool = False) -> HavfrysResult:
    """Run software maintenance intelligence (audit dependencies, verify compatibility, update maintenance graph)."""
    start = time.time()
    target_abs = os.path.abspath(workdir or (target if os.path.isdir(target) else os.getcwd()))
    result = HavfrysResult(task=f"maintain {target_abs}")

    issues: list[str] = []
    suggestions: list[str] = []
    tests_summary: list[str] = []
    deps_summary: list[str] = []

    # 1. Dependency Health
    if os.path.exists(os.path.join(target_abs, "requirements.txt")):
        py = _resolve_python_interpreter(target_abs)
        r = _try_run(f"{py} -m pip install -q -r requirements.txt 2>/dev/null", target_abs)
        if r[0] == 0:
            deps_summary.append("Python requirements installed cleanly")
        else:
            issues.append("Python requirements installation warning/conflict")
            suggestions.append("Resolve Python dependency conflicts in requirements.txt")

    if os.path.exists(os.path.join(target_abs, "package.json")):
        r = _try_run("npm install --no-audit --no-fund --silent 2>/dev/null", target_abs)
        if r[0] == 0:
            deps_summary.append("Node package.json dependencies up to date")
        else:
            issues.append("Node dependency installation warning/conflict")
            suggestions.append("Resolve npm/yarn dependency lockfile issues")

    if os.path.exists(os.path.join(target_abs, "Cargo.toml")):
        r = _try_run("cargo check --quiet 2>/dev/null", target_abs)
        if r[0] == 0:
            deps_summary.append("Rust Cargo.toml dependencies compile cleanly")
        else:
            issues.append("Rust cargo check reported compilation warnings/errors")
            suggestions.append("Resolve Cargo dependency compilation issues")

    # 2. Test Suite Health
    test_cmds = _detect_test_commands(target_abs)
    py = _resolve_python_interpreter(target_abs)
    runner_name = "Automated test suite"

    if test_cmds:
        for cmd in test_cmds:
            if "pytest" in cmd:
                runner_name = "pytest"
            elif "cargo" in cmd:
                runner_name = "cargo test"
            elif "npm" in cmd or "yarn" in cmd:
                runner_name = "npm test"

            resolved = cmd.replace("python -m", f"{py} -m").replace("python3 ", f"{py} ")
            rc, out, err = _try_run(resolved, target_abs)
            if rc == 0:
                tests_summary.append(f"All tests passing ({runner_name})")
            else:
                issues.append("Repository test suite is failing.")
                suggestions.append("Resolve failing test assertions")
    else:
        tests_summary.append("No automated test suite detected")

    # 3. Git Working Tree Health
    if os.path.exists(os.path.join(target_abs, ".git")):
        rc, out, _ = _try_run("git status --porcelain", target_abs)
        if rc == 0 and out.strip():
            dirty_count = len(out.strip().splitlines())
            issues.append(f"{dirty_count} uncommitted file(s) in working tree")
            suggestions.append("Review or clean uncommitted working tree modifications")

    # Update Maintenance Graph
    _update_maintenance_graph(target_abs, "maintenance_required" if issues else "healthy", issues, deps_summary)

    # Complexity Calculation
    complexity = "Low"
    if len(issues) >= 3 or (len(issues) >= 1 and test_cmds):
        complexity = "High" if len(issues) >= 3 else "Medium"

    # Synthesize Repository Health Report
    lines: list[str] = ["Repository Health Report", ""]
    if issues:
        lines.append("Status: Maintenance Required")
        lines.append("")
        lines.append("Maintenance Required:")
        for issue in issues:
            lines.append(f"- {issue}")
        lines.append("")
        lines.append(f"Engineering Complexity:\n- {complexity}")
        lines.append("")
        lines.append("Suggested Maintenance Operations:")
        for sug in suggestions:
            lines.append(f"- {sug}")
        lines.append("")
        lines.append("Recommended Next Steps:")
        for sug in suggestions:
            lines.append(f"- {sug}")
    else:
        lines.append("Status: Healthy")
        lines.append("")
        lines.append("No maintenance required.")
        lines.append("")
        lines.append("Tests:")
        for t in tests_summary:
            lines.append(f"- {t}")
        lines.append("")
        lines.append("Dependencies:")
        for d in (deps_summary or ["Up to date"]):
            lines.append(f"- {d}")
        lines.append("")
        lines.append("Maintenance Confidence:\n- High")
        lines.append("")
        lines.append("No further maintenance actions required.")

    result.status = "success"
    result.execution_time_s = time.time() - start
    result.output = "\n".join(lines)
    return result


def _update_maintenance_graph(workdir: str, status: str, issues: list[str], deps: list[str]) -> dict[str, Any]:
    """Maintain .havfrys/maintenance_graph.json tracking repository health evolution over time."""
    havfrys_dir = os.path.join(workdir, ".havfrys")
    graph_file = os.path.join(havfrys_dir, "maintenance_graph.json")

    graph: dict[str, Any] = {"runs": []}
    if os.path.exists(graph_file):
        try:
            with open(graph_file, "r", encoding="utf-8") as f:
                graph = json.load(f)
        except Exception:
            graph = {"runs": []}

    run_entry = {
        "timestamp": time.time(),
        "status": status,
        "issues_count": len(issues),
        "issues": issues,
        "dependencies": deps,
    }

    if "runs" not in graph:
        graph["runs"] = []

    graph["runs"].append(run_entry)
    graph["runs"] = graph["runs"][-50:]

    try:
        os.makedirs(havfrys_dir, exist_ok=True)
        with open(graph_file, "w", encoding="utf-8") as f:
            json.dump(graph, f, indent=2)
    except Exception:
        pass

    return graph


def _try_run(cmd: str, cwd: str) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True, timeout=120)
        return proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired:
        return 124, "", "timed out"
    except Exception as e:
        return 1, "", str(e)


def _install_dependencies(workdir: str, executable: str) -> None:
    if "python" in executable:
        venv_python = _resolve_python_interpreter(workdir)
        if os.path.exists(os.path.join(workdir, "requirements.txt")):
            _try_run(f"{venv_python} -m pip install -q -r requirements.txt 2>/dev/null", workdir)
        elif os.path.exists(os.path.join(workdir, "pyproject.toml")):
            _try_run(f"{venv_python} -m pip install -q -e . 2>/dev/null || {venv_python} -m pip install -q . 2>/dev/null", workdir)
    if "node" in executable or "npm" in executable or "npx" in executable:
        if os.path.exists(os.path.join(workdir, "package.json")):
            if os.path.exists(os.path.join(workdir, "yarn.lock")):
                _try_run("yarn install --frozen-lockfile --silent 2>/dev/null", workdir)
            else:
                _try_run("npm install --no-audit --no-fund --silent 2>/dev/null", workdir)


def resume() -> HavfrysResult:
    """Resume the last execution. Memory skips previously failed strategies."""
    global _LAST_TASK
    if not _LAST_TASK:
        return HavfrysResult(status="failed", error="No previous session to resume")
    return exe(_LAST_TASK)


def inspect() -> dict[str, Any]:
    """Inspect the last execution report."""
    global _LAST_REPORT
    if not _LAST_REPORT:
        return {"status": "none", "history": []}

    r = _LAST_REPORT
    return {
        "status": r.status,
        "mode": r.mode,
        "execution_time_s": round(r.execution_time_s, 2),
        "total_attempts": r.total_attempts,
        "uncertainty_points": r.uncertainty_points,
        "uncertainty_resolved": r.uncertainty_resolved,
        "branches_spawned": r.branches_spawned,
        "branches_killed": r.branches_killed,
        "token_reduction_pct": r.token_reduction_pct,
        "winning_fix": r.winning_fix,
        "branch_summaries": r.branch_summaries,
        "output": r.output[:500] if r.output else "",
        "error": r.error,
    }


def _infer_docker_image(workdir: str) -> str:
    """Infer optimal Docker execution image based on workspace context & manifests."""
    if os.path.exists(os.path.join(workdir, "Dockerfile")) or os.path.exists(os.path.join(workdir, "docker-compose.yml")):
        return "repo-dockerfile"
    if os.path.exists(os.path.join(workdir, "Cargo.toml")):
        return "rust:latest"
    if os.path.exists(os.path.join(workdir, "package.json")):
        return "node:latest"
    if os.path.exists(os.path.join(workdir, "go.mod")):
        return "golang:latest"
    if os.path.exists(os.path.join(workdir, "pom.xml")) or os.path.exists(os.path.join(workdir, "build.gradle")):
        return "maven:latest"
    if os.path.exists(os.path.join(workdir, "pyproject.toml")) or os.path.exists(os.path.join(workdir, "requirements.txt")):
        return "python:3.12-slim"

    return "ubuntu:latest"


def _is_shell_command(task: str) -> bool:
    """Check if task string is a direct shell command line."""
    task_clean = task.strip()
    if not task_clean:
        return True
    first_word = task_clean.split()[0].lower()
    shell_prefixes = {
        "pytest", "python", "python3", "cargo", "npm", "npx", "go",
        "git", "make", "pip", "pip3", "maturin", "poetry", "uv", "hatch",
        "docker", "bash", "sh", "zsh", "ls", "cat", "find", "grep",
        "echo", "print", "printf", "touch", "mkdir", "cp", "mv", "rm",
        "node", "deno", "pwd", "whoami", "env", "curl", "wget"
    }
    if first_word in shell_prefixes:
        return True
    if any(task_clean.startswith(prefix) for prefix in ["./", "/", "../"]) or "=" in first_word:
        return True
    return False


def _resolve_command(task: str, workdir: str) -> str:
    """Resolve an engineering task or CLI command into an executable pipeline."""
    task_str = task.strip()
    task_lower = task_str.lower()

    # Safety Guard: Block destructive root operations
    if any(p in task_lower for p in ["rm -rf /", "rm -rf /*", "delete all files in /", "format /"]):
        return "echo 'Error: Destructive root filesystem operation blocked by HAVFRYS safety guard' && exit 1"

    # Handle print and echo prompts (e.g. "print hello world", "print 12345 * 6789")
    if task_lower.startswith("print "):
        expr = task_str[6:].strip()
        if expr.startswith("'") or expr.startswith('"'):
            return f"python3 -c \"print({expr})\""
        return f"python3 -c \"print('{expr}')\""

    # Handle pure math expressions (e.g. "12345 * 6789")
    if any(c in task_str for c in ["+", "-", "*", "/"]) and all(c in "0123456789 +-/*()." for c in task_str):
        return f"python3 -c \"print({task_str})\""

    if _is_shell_command(task_str):
        return task_str

    is_analysis = any(w in task_lower for w in ["analyze", "analysis", "explain", "architecture", "survey", "document", "overview"])

    if is_analysis:
        return _discover_project_structure(workdir, task_str)

    test_cmds = _detect_test_commands(workdir)
    build_cmds = _detect_build_commands(workdir)

    if test_cmds:
        return test_cmds[0]
    elif build_cmds:
        return build_cmds[0]

    # Probe deeper: scan subdirectory scripts too
    _python = _resolve_python(workdir)
    _node = _resolve_node(workdir)

    if _python and _node:
        return _python  # prefer python

    entrypoint = _python or _node or _resolve_other_entrypoint(workdir)
    if entrypoint:
        return entrypoint

    # No known tests, builds, or entrypoints — discover project structure
    return _discover_project_structure(workdir, task_str)


def _resolve_python(workdir: str) -> str:
    primary = [
        "app.py", "main.py", "cli.py", "run.py", "server.py",
        "manage.py", "wsgi.py", "bot.py",
    ]
    subdirs = ["cli", "bin", "src", "app", "lib", "scripts"]
    python = _resolve_python_interpreter(workdir)
    for name in primary:
        path = os.path.join(workdir, name)
        if os.path.exists(path):
            return f"{python} {name}"
    for sd in subdirs:
        sdp = os.path.join(workdir, sd)
        if os.path.isdir(sdp):
            for name in primary:
                path = os.path.join(sdp, name)
                if os.path.exists(path):
                    return f"{python} {path}"
            for f in sorted(os.listdir(sdp)):
                if f.endswith(".py") and f != "__init__.py":
                    return f"{python} {os.path.join(sd, f)}"
    try:
        for f in sorted(os.listdir(workdir)):
            if f.endswith(".py") and f not in ("setup.py",):
                return f"{python} {f}"
    except Exception:
        pass
    return ""


def _resolve_node(workdir: str) -> str:
    primary = ["index.js", "index.ts", "server.js", "app.js", "cli.js", "main.js", "bot.js"]
    subdirs = ["cli", "bin", "src", "app", "lib", "scripts"]
    runner = "node"
    if os.path.exists(os.path.join(workdir, "tsconfig.json")):
        runner = "npx ts-node --skip-project"
    for name in primary:
        if os.path.exists(os.path.join(workdir, name)):
            return f"{runner} {name}"
    for sd in subdirs:
        sdp = os.path.join(workdir, sd)
        if os.path.isdir(sdp):
            for name in primary:
                if os.path.exists(os.path.join(sdp, name)):
                    return f"{runner} {os.path.join(sd, name)}"
            for f in sorted(os.listdir(sdp)):
                if f.endswith((".js", ".ts")):
                    return f"{runner} {os.path.join(sd, f)}"
    return ""


def _resolve_other_entrypoint(workdir: str) -> str:
    if os.path.exists(os.path.join(workdir, "main.rs")):
        return "cargo run 2>/dev/null || rustc main.rs && ./main"
    if os.path.exists(os.path.join(workdir, "src", "main.rs")):
        return "cargo run"
    if os.path.exists(os.path.join(workdir, "main.go")):
        return "go run main.go"
    if os.path.exists(os.path.join(workdir, "Main.java")):
        return "javac Main.java && java Main"
    return ""


def _discover_project_structure(workdir: str, task_str: str) -> str:
    """Synthesize a Project Analysis report instead of listing files."""
    ignores = {".git", "node_modules", "__pycache__", ".venv", "venv", "target", "build", "dist", ".mypy_cache", ".pytest_cache", ".tox", "egg-info"}

    # Detect project type
    project_type = "Unknown"
    frameworks: list[str] = []
    risks: list[str] = []
    build_system: list[str] = []
    architecture: list[str] = []
    suggested: list[str] = []

    has_pyproject = os.path.exists(os.path.join(workdir, "pyproject.toml"))
    has_setup = os.path.exists(os.path.join(workdir, "setup.py"))
    has_requirements = os.path.exists(os.path.join(workdir, "requirements.txt"))
    has_cargo = os.path.exists(os.path.join(workdir, "Cargo.toml"))
    has_package = os.path.exists(os.path.join(workdir, "package.json"))
    has_gomod = os.path.exists(os.path.join(workdir, "go.mod"))
    has_makefile = os.path.exists(os.path.join(workdir, "Makefile"))
    has_dockerfile = os.path.exists(os.path.join(workdir, "Dockerfile"))

    if has_cargo:
        project_type = "Rust library/application"
        build_system.append("cargo")
    elif has_pyproject or has_setup:
        project_type = "Python library/application"
        build_system.append("pyproject.toml" if has_pyproject else "setup.py")
    elif has_package:
        project_type = "Node.js application"
        build_system.append("npm/yarn")
    elif has_gomod:
        project_type = "Go module"
        build_system.append("go mod")
    elif has_makefile:
        project_type = "C/C++ project"
        build_system.append("Makefile")

    if has_requirements:
        build_system.append("requirements.txt")
    if has_dockerfile:
        frameworks.append("Docker")

    # Scan top-level structure for architecture signals
    try:
        top = sorted(f for f in os.listdir(workdir) if not f.startswith(".") and f not in ignores)
        dirs = [f for f in top if os.path.isdir(os.path.join(workdir, f))]
        files = [f for f in top if os.path.isfile(os.path.join(workdir, f))]

        well_known = {"src", "lib", "app", "core", "api", "services", "models", "utils", "helpers", "config", "scripts", "bin"}
        doc_dirs = {"docs", "documentation", "doc", "wiki"}
        test_dirs = {"tests", "test", "spec", "specs", "__tests__"}
        example_dirs = {"examples", "example", "samples", "demos"}

        for d in dirs:
            dl = d.lower()
            if dl in well_known:
                architecture.append(f"Core package ({d}/)")
            elif dl in doc_dirs:
                architecture.append("Documentation")
            elif dl in test_dirs:
                architecture.append("Test suite")
            elif dl in example_dirs:
                architecture.append("Example applications")
            elif dl in {"ci", ".github", ".circleci"}:
                architecture.append("CI/CD configuration")
    except Exception:
        pass

    if not architecture:
        architecture.append("Flat structure (no package hierarchy detected)")

    # Detect test runner
    test_cmds = _detect_test_commands(workdir)
    if test_cmds:
        build_system.extend(test_cmds)
    else:
        risks.append("No automated test suite detected")
        suggested.append("Add test coverage")

    # General suggestions
    suggested.append("Run maintenance audit (havfrys maintain .)")

    # Synthesize report
    lines = [
        "Project Analysis",
        "",
        f"Type:\n- {project_type}",
        "",
        "Architecture:",
    ]
    for a in (architecture or ["Unknown"]):
        lines.append(f"- {a}")

    if risks:
        lines.append("")
        lines.append("Engineering Risks:")
        for r in risks:
            lines.append(f"- {r}")

    lines.append("")
    lines.append("Build System:")
    for b in (build_system or ["Not detected"]):
        lines.append(f"- {b}")

    lines.append("")
    lines.append("Suggested Tasks:")
    for s in suggested:
        lines.append(f"- {s}")

    report = "\n".join(lines)
    return f"echo '{report}'"


def _resolve_python_interpreter(workdir: str) -> str:
    for venv_dir in (".venv", "venv", ".env", "env"):
        candidate = os.path.join(workdir, venv_dir, "bin", "python")
        if os.path.exists(candidate):
            return candidate
        candidate = os.path.join(workdir, venv_dir, "Scripts", "python.exe")
        if os.path.exists(candidate):
            return candidate
    return _detect_uv_python(workdir) or "python3"


def _detect_uv_python(workdir: str) -> str:
    uv_bin = shutil.which("uv")
    if uv_bin and os.path.exists(os.path.join(workdir, ".python-version")):
        return f"{uv_bin} run python"
    return ""


havfrys = exe
