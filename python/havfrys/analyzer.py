"""Deterministic repository inspection: directory structure, manifests, build systems, dependency files, test configuration, language detection."""

import hashlib
import json
import os
from dataclasses import dataclass
from typing import Optional


SCHEMA_VERSION = 1


@dataclass
class AnalyseResult:
    status: str = "success"
    schema_version: int = SCHEMA_VERSION
    language: str = ""
    framework: str = ""
    build_system: str = ""
    test_framework: str = ""
    test_command: str = ""
    lint_command: str = ""
    deps: list = None
    docker: bool = False
    workspace_type: str = ""
    subprojects: list = None
    structure: dict = None
    execution_time_ms: int = 0
    cached: bool = False
    operation_id: str = ""


_IGNORE_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", "target",
    "build", "dist", ".mypy_cache", ".pytest_cache", ".tox",
    "egg-info", ".next", ".nuxt", ".cache", ".havfrys",
}

_MANIFEST_FRAMEWORKS = {
    "pyproject.toml": ("Python", "pip"),
    "setup.py": ("Python", "setuptools"),
    "requirements.txt": ("Python", "pip"),
    "Cargo.toml": ("Rust", "cargo"),
    "package.json": ("Node.js", "npm"),
    "go.mod": ("Go", "go"),
    "Makefile": ("C/C++", "make"),
    "pom.xml": ("Java", "maven"),
    "build.gradle": ("Java", "gradle"),
    "CMakeLists.txt": ("C/C++", "cmake"),
}

_TEST_FRAMEWORKS = {
    "pytest.ini": "pytest",
    "setup.cfg": "pytest",
    "pyproject.toml": "pytest",
    "jest.config.js": "jest",
    "jest.config.ts": "jest",
    "vitest.config.ts": "vitest",
    "go.mod": "go test",
    "Cargo.toml": "cargo test",
}


def _compute_fingerprint(path: str) -> str:
    """Lightweight fingerprint: tracked files + mtimes + lockfiles + manifests."""
    dirs_to_hash = ["src", "lib", "tests", "backend", "frontend", "app"]
    h = hashlib.sha256()
    base = os.path.abspath(path)

    for item in sorted(os.listdir(base)):
        if item.startswith(".") and item not in (".python-version", ".env"):
            continue
        if item in _IGNORE_DIRS:
            continue
        fp = os.path.join(base, item)
        if os.path.isfile(fp):
            h.update(f"{item}:{os.path.getmtime(fp):.0f}".encode())
        elif os.path.isdir(fp) and item in dirs_to_hash:
            for root, dirs, files in os.walk(fp):
                dirs[:] = [d for d in dirs if not d.startswith(".") and d not in _IGNORE_DIRS]
                for f in sorted(files):
                    fpath = os.path.join(root, f)
                    try:
                        h.update(f"{os.path.relpath(fpath, base)}:{os.path.getmtime(fpath):.0f}".encode())
                    except Exception:
                        pass

    lockfiles = ["poetry.lock", "Cargo.lock", "yarn.lock", "package-lock.json", "Gemfile.lock"]
    for lf in lockfiles:
        lfp = os.path.join(base, lf)
        if os.path.exists(lfp):
            try:
                h.update(lfp.encode() + b":" + str(os.path.getmtime(lfp)).encode())
            except Exception:
                pass

    return h.hexdigest()[:16]


def _get_cache_path(base: str) -> str:
    return os.path.join(base, ".havfrys", "memory", "detected.json")


def analyse(path: str = ".", depth: int = 3) -> AnalyseResult:
    import uuid
    import time
    op_id = f"an_{uuid.uuid4().hex[:8]}"
    start = time.time()
    base = os.path.abspath(path)

    if not os.path.isdir(base):
        return AnalyseResult(
            status="error", language="", execution_time_ms=0, operation_id=op_id,
        )

    fingerprint = _compute_fingerprint(base)
    cache_path = _get_cache_path(base)

    if os.path.exists(cache_path):
        try:
            with open(cache_path) as f:
                cached = json.load(f)
            if cached.get("_fingerprint") == fingerprint:
                cached["cached"] = True
                cached["execution_time_ms"] = 0
                cached["operation_id"] = op_id
                return AnalyseResult(**cached)
        except Exception:
            pass

    manifests = []
    found_lang = ""
    found_framework = ""
    found_build = ""

    for fname, (lang, build) in _MANIFEST_FRAMEWORKS.items():
        if os.path.exists(os.path.join(base, fname)):
            manifests.append(fname)
            if found_lang:
                found_lang = f"{found_lang}+{lang}"
                found_build = f"{found_build}+{build}"
            else:
                found_lang = lang
                found_build = build

    if not found_lang:
        found_lang = "Unknown"
        found_build = "none"

    test_framework = ""
    test_command = ""
    for mf, tf in _TEST_FRAMEWORKS.items():
        if os.path.exists(os.path.join(base, mf)):
            test_framework = tf
            break

    if test_framework == "pytest":
        py = "python3"
        for venv_dir in (".venv", "venv", ".env", "env"):
            candidate = os.path.join(base, venv_dir, "bin", "python")
            if os.path.exists(candidate):
                py = candidate
                break
        test_command = f"{py} -m pytest --tb=short -q"
    elif test_framework == "cargo test":
        test_command = "cargo test"
    elif test_framework == "go test":
        test_command = "go test ./..."

    lint_command = ""
    if os.path.exists(os.path.join(base, "ruff.toml")) or os.path.exists(os.path.join(base, ".ruff.toml")):
        lint_command = "ruff check ."
    elif os.path.exists(os.path.join(base, ".eslintrc.js")) or os.path.exists(os.path.join(base, ".eslintrc.json")):
        lint_command = "npx eslint ."
    elif os.path.exists(os.path.join(base, ".golangci.yml")) or os.path.exists(os.path.join(base, ".golangci.yaml")):
        lint_command = "golangci-lint run"

    has_docker = os.path.exists(os.path.join(base, "Dockerfile")) or os.path.exists(
        os.path.join(base, "docker-compose.yml")
    )

    deps = []
    if os.path.exists(os.path.join(base, "requirements.txt")):
        deps.append("requirements.txt")
    if os.path.exists(os.path.join(base, "pyproject.toml")):
        deps.append("pyproject.toml")
    if os.path.exists(os.path.join(base, "Cargo.toml")):
        deps.append("Cargo.toml")
    if os.path.exists(os.path.join(base, "package.json")):
        deps.append("package.json")

    subprojects = []
    for sub in ("backend", "frontend", "server", "client", "api", "web", "app"):
        subpath = os.path.join(base, sub)
        if os.path.isdir(subpath):
            for mf in _MANIFEST_FRAMEWORKS:
                if os.path.exists(os.path.join(subpath, mf)):
                    subprojects.append(f"{sub}/{mf}")
                    break

    structure = _scan_structure(base, depth)

    fullstack_py_node = any(m.endswith(("pyproject.toml", "requirements.txt")) for m in manifests) and "package.json" in manifests
    if fullstack_py_node:
        workspace_type = "monorepo"
    elif subprojects:
        workspace_type = "multi-package"
    elif len(manifests) > 0:
        workspace_type = "single-package"
    else:
        workspace_type = "flat"

    result = AnalyseResult(
        status="success",
        language=found_lang,
        framework=found_framework,
        build_system=found_build,
        test_framework=test_framework,
        test_command=test_command,
        lint_command=lint_command,
        deps=deps,
        docker=has_docker,
        workspace_type=workspace_type,
        subprojects=subprojects if subprojects else None,
        structure=structure,
        execution_time_ms=0,
        cached=False,
        operation_id=op_id,
    )

    try:
        cache_data = {
            "_fingerprint": fingerprint,
            "status": result.status,
            "schema_version": result.schema_version,
            "language": result.language,
            "framework": result.framework,
            "build_system": result.build_system,
            "test_framework": result.test_framework,
            "test_command": result.test_command,
            "lint_command": result.lint_command,
            "deps": result.deps,
            "docker": result.docker,
            "workspace_type": result.workspace_type,
            "subprojects": result.subprojects,
            "structure": result.structure,
            "execution_time_ms": 0,
            "cached": True,
            "operation_id": op_id,
        }
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        with open(cache_path, "w") as f:
            json.dump(cache_data, f, indent=2)
    except Exception:
        pass

    result.execution_time_ms = int((time.time() - start) * 1000)
    return result


def _scan_structure(base: str, max_depth: int) -> dict:
    dirs_found = []
    backend_dirs = []
    frontend_dirs = []
    core_dirs = []
    test_dirs = []
    doc_dirs = []

    for root, dirs, files in os.walk(base):
        dirs[:] = [d for d in dirs if not d.startswith(".") and d not in _IGNORE_DIRS]
        rel = os.path.relpath(root, base)
        depth = 0 if rel == "." else len(rel.split(os.sep))
        if depth > max_depth:
            dirs.clear()
            continue
        if rel != ".":
            dname = os.path.basename(root)
            dirs_found.append((rel, dname))

    for rel, d in dirs_found:
        if d in ("backend", "server", "api", "service", "services"):
            backend_dirs.append(rel)
        elif d in ("frontend", "client", "web", "ui"):
            frontend_dirs.append(rel)
        elif d in ("src", "lib", "app", "core", "models", "routes", "controllers", "components", "utils", "helpers"):
            core_dirs.append(rel)
        elif d in ("tests", "test", "spec", "specs", "__tests__"):
            test_dirs.append(rel)
        elif d in ("docs", "documentation", "doc", "wiki"):
            doc_dirs.append(rel)

    architecture = []
    if backend_dirs:
        architecture.append(f"Backend ({', '.join(sorted(backend_dirs)[:3])})")
    if frontend_dirs:
        architecture.append(f"Frontend ({', '.join(sorted(frontend_dirs)[:3])})")
    if core_dirs:
        architecture.append(f"Core ({', '.join(sorted(core_dirs)[:4])})")
    if test_dirs:
        architecture.append(f"Tests ({', '.join(sorted(test_dirs)[:3])})")
    if doc_dirs:
        architecture.append(f"Docs ({', '.join(sorted(doc_dirs)[:2])})")

    return {
        "dirs": [r for r, _ in dirs_found[:20]],
        "architecture": architecture if architecture else ["Flat"],
    }
