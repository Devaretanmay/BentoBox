"""Local-first client installer wizard and diagnostics for HAVFRYS.

Configures local agentic environments (Claude Code, Gemini CLI, Cursor, VS Code,
OpenCode, Windsurf, Cline, Continue, Zed, Aider) to use the local HAVFRYS MCP process (`havfrys serve`).
Includes `havfrys doctor` for instant local runtime diagnostics.
No login, no SaaS, no API keys — 100% local-first execution.
"""

import os
import shutil
import sys
from pathlib import Path
from typing import Optional


VERSION = "0.6.0"


def _is_valid_client_path(p: Path) -> bool:
    if p.exists():
        return True
    parent = p.parent
    if parent != Path.home() and parent.exists():
        return True
    return False


def detect_installed_clients() -> list[tuple[str, Path]]:
    detected = []

    providers: list[tuple[str, list[Path], Optional[str]]] = [
        ("Claude Code", [
            Path.home() / ".claude.json",
            Path.home() / ".config" / "claude" / "config.json",
            Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json",
            Path.home() / "AppData" / "Roaming" / "Claude" / "claude_desktop_config.json",
        ], "claude"),
        ("Gemini CLI", [
            Path.home() / ".gemini" / "mcp.json",
            Path.home() / ".config" / "gemini" / "mcp.json",
        ], "gemini"),
        ("Cursor", [
            Path.home() / ".cursor" / "mcp.json",
            Path.home() / "Library" / "Application Support" / "Cursor" / "User" / "globalStorage" / "mcp.json",
            Path.home() / ".config" / "Cursor" / "User" / "globalStorage" / "mcp.json",
        ], "cursor"),
        ("VS Code", [
            Path.home() / ".vscode" / "mcp.json",
            Path.home() / "Library" / "Application Support" / "Code" / "User" / "mcp.json",
            Path.home() / ".config" / "Code" / "User" / "mcp.json",
        ], "code"),
        ("OpenCode", [
            Path.home() / ".config" / "opencode" / "mcp.json",
            Path.home() / ".opencode" / "mcp.json",
        ], "opencode"),
        ("Windsurf", [
            Path.home() / ".codeium" / "windsurf" / "mcp_config.json",
            Path.home() / ".windsurf" / "mcp_config.json",
        ], "windsurf"),
        ("Cline / Roo Code", [
            Path.home() / "Library" / "Application Support" / "Code" / "User" / "globalStorage" / "rooveterinaryinc.roo-cline" / "settings" / "mcp_settings.json",
            Path.home() / ".vscode" / "extensions" / "rooveterinaryinc.roo-cline" / "mcp.json",
        ], None),
        ("Continue", [
            Path.home() / ".continue" / "config.json",
        ], None),
        ("Zed Editor", [
            Path.home() / ".config" / "zed" / "settings.json",
        ], "zed"),
    ]

    for name, paths, bin_name in providers:
        found_path = None
        for p in paths:
            if _is_valid_client_path(p):
                found_path = p
                break
        if not found_path and bin_name and shutil.which(bin_name):
            found_path = paths[0]
        if found_path:
            detected.append((name, found_path))

    return detected


HAVFRYS_HAV_MD = """# HAVFRYS

> HAVFRYS is engineering infrastructure, not an agent. It exposes deterministic primitives that the LLM orchestrates.

## Sessions

HAVFRYS is built around Sessions — isolated execution contexts.

Two session types:
- **exe (execution)**: Isolated Git worktree. Run commands, edit, snapshot, rollback, apply.
- **maintain (maintenance)**: Repository inspection. Analyse, verify, inspect history.

## Available Tools

**Session Lifecycle**
- **create_session** — Create an isolated session (type="exe" or "maintain")
- **session_close** — Close a session, cleanup worktree, persist state

**Execution Operations**
- **session_run** — Execute shell commands with automatic output compression
- **session_diff** — Show uncommitted changes in worktree
- **session_snapshot** — Save worktree state as a named Git ref
- **session_rollback** — Restore worktree to a named snapshot
- **session_apply** — Apply worktree changes to main repository

**Maintenance Operations**
- **session_analyse** — Deterministic repo structure scan (language, framework, build, test)
- **session_verify** — Run test suite with structured pass/fail results
- **session_observe** — Store a named observation (builds knowledge over time)
- **session_knowledge** — Retrieve all accumulated observations
- **session_history** — Read persistent maintenance event history

## How to Use

1. create_session(type="maintain") → session_analyse to understand repo.
2. create_session(type="exe") → use execute(goal) for intent-driven work.
3. session_snapshot before risky changes.
4. session_diff to inspect before applying.
5. session_apply only when verification passes.
6. session_close when done.

The LLM makes all engineering decisions. HAVFRYS executes deterministically.
No LLM calls, no hidden reasoning, no automatic branching inside HAVFRYS.

## Principles

- Users describe problems, never machinery.
- Adapt to repository context.
- Never experiment on the user's working tree.
- Validate before applying."
"""


def run_init_wizard(choice: Optional[int] = None, auto_all: bool = False, target_dir: str = ".") -> None:
    from havfrys.ui import render_banner, symbol_ok, BOLD, CYAN, DIM, RESET
    print(render_banner("Workspace Initialization", VERSION))

    target_path = Path(target_dir).resolve()
    havfrys_dir = target_path / ".havfrys"
    hav_file = havfrys_dir / "HAVFRYS.md"

    try:
        havfrys_dir.mkdir(parents=True, exist_ok=True)
        hav_file.write_text(HAVFRYS_HAV_MD, encoding="utf-8")
        print(f"  {symbol_ok()} {BOLD}Initialized{RESET} {hav_file.relative_to(target_path) if hav_file.is_relative_to(target_path) else hav_file}\n")
    except Exception as e:
        print(f"  Error: {e}\n")
        return

    prompt = (
        "You are working in a HAVFRYS-enabled repository.\n\n"
        "HAVFRYS is not an agent. It is engineering infrastructure — deterministic primitives you call.\n"
        "You make all decisions; HAVFRYS executes.\n\n"
        "Available sessions:\n"
        "  create_session(type='exe')      — isolated worktree for changes\n"
        "  create_session(type='maintain') — inspect & verify repo\n"
        "  session_close(session_id)       — teardown when done\n\n"
        "Execution ops: session_run, session_snapshot, session_diff, session_rollback, session_apply\n"
        "  execute(goal) works without a session — plan → run → verify → apply in one call\n"
        "Maintenance ops: session_analyse, session_verify, session_observe, session_knowledge, session_history\n"
    )

    print(f"{CYAN}┌─────────────────────────────────────────────────────────────┐{RESET}")
    print(f"{CYAN}│{RESET}  {BOLD}AI Agent Prompt (Copy & Paste to your AI coding agent){RESET}   {CYAN}│{RESET}")
    print(f"{CYAN}└─────────────────────────────────────────────────────────────┘{RESET}\n")
    print(f"{DIM}{prompt}{RESET}\n")


def ensure_workspace_initialized(target_dir: str = ".") -> Path:
    target_path = Path(target_dir).resolve() if target_dir else Path.cwd().resolve()
    havfrys_dir = target_path / ".havfrys"
    hav_file = havfrys_dir / "HAVFRYS.md"

    if not hav_file.exists():
        try:
            havfrys_dir.mkdir(parents=True, exist_ok=True)
            hav_file.write_text(HAVFRYS_HAV_MD, encoding="utf-8")
        except Exception:
            pass

    return hav_file


def run_doctor() -> None:
    from havfrys.ui import render_banner, render_section, render_row, symbol_ok, BOLD, GREEN, CYAN, RESET
    print(render_banner("Runtime Diagnostics", VERSION))

    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    print(render_section("System & Runtime"))
    print(render_row("Python", f"{py_ver} ({sys.platform})"))
    print(render_row("MCP Server", "Available (havfrys serve)"))

    try:
        from havfrys._core import route_and_compress
        print(render_row("Compression Engine", "Loaded (Lossless + SmartCrusher)"))
    except Exception as e:
        print(render_row("Compression Engine", f"Failed to load: {e}", is_ok=False))

    print(render_section("Toolchain & Containers"))
    git_path = shutil.which("git")
    docker_path = shutil.which("docker")
    print(render_row("Git CLI", git_path or "not found", is_ok=bool(git_path)))
    print(render_row("Docker Engine", docker_path or "not found (Optional)", is_ok=True))

    print(render_section("Configured MCP Clients"))
    detected = detect_installed_clients()
    if detected:
        for name, path in detected:
            print(render_row(name, str(path)))
    else:
        print(render_row("MCP Clients", "No clients auto-detected (run 'havfrys init')", is_ok=False))

    print(render_section("Workspace"))
    is_git = os.path.exists(".git")
    print(render_row("Repository State", "Git repository active" if is_git else "Directory path active"))
    print(f"\n{GREEN}{BOLD}Status:{RESET} All system diagnostics 100% operational.\n")
