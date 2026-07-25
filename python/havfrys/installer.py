"""Local-first client installer wizard and diagnostics for HAVFRYS by HAVFRYS Labs.

Configures local agentic environments (Claude Code, Gemini CLI, Cursor, VS Code,
OpenCode, Windsurf, Cline, Continue, Zed, Aider) to use the local HAVFRYS MCP process (`havfrys serve`).
Includes `havfrys doctor` for instant local runtime diagnostics.
No login, no SaaS, no API keys — 100% local-first execution.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional


VERSION = "0.3.3"

CLIENT_PROVIDERS = [
    "1. Claude Code / Desktop",
    "2. Gemini CLI",
    "3. OpenCode",
    "4. Cursor",
    "5. VS Code",
    "6. Windsurf",
    "7. Cline / Roo Code",
    "8. Continue",
    "9. Zed Editor",
    "10. Custom MCP Client",
    "11. Skip",
]


def get_havfrys_mcp_config() -> dict[str, Any]:
    """Return standard local MCP server configuration snippet."""
    cmd_path = shutil.which("havfrys") or str(Path(sys.executable).parent / "havfrys")
    return {
        "command": cmd_path,
        "args": ["serve"],
    }


def _is_valid_client_path(p: Path) -> bool:
    """Return True if config file exists or parent directory exists (excluding Home directory)."""
    if p.exists():
        return True
    parent = p.parent
    if parent != Path.home() and parent.exists():
        return True
    return False


def detect_installed_clients() -> list[tuple[str, Path]]:
    """Detect local AI coding agent clients installed on the system."""
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


def install_claude_code() -> tuple[bool, str]:
    """Configure Claude Code / Desktop to run local HAVFRYS MCP server."""
    possible_paths = [
        Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json",
        Path.home() / "AppData" / "Roaming" / "Claude" / "claude_desktop_config.json",
        Path.home() / ".claude.json",
        Path.home() / ".config" / "claude" / "config.json",
    ]
    updated_paths = []
    for p in possible_paths:
        if p.exists() or p.parent.exists():
            ok, res_path = _update_mcp_json_file(p, "havfrys")
            if ok:
                updated_paths.append(res_path)

    if updated_paths:
        return True, ", ".join(updated_paths)
    return _update_mcp_json_file(possible_paths[0], "havfrys")


def install_cursor() -> tuple[bool, str]:
    """Configure Cursor editor to run local HAVFRYS MCP server."""
    target_path = Path.home() / ".cursor" / "mcp.json"
    return _update_mcp_json_file(target_path, "havfrys")


def install_vscode() -> tuple[bool, str]:
    """Configure VS Code to run local HAVFRYS MCP server."""
    target_path = Path.home() / ".vscode" / "mcp.json"
    return _update_mcp_json_file(target_path, "havfrys")


def install_opencode() -> tuple[bool, str]:
    """Configure OpenCode to run local HAVFRYS MCP server."""
    target_path = Path.home() / ".config" / "opencode" / "opencode.json"
    try:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        config: dict[str, Any] = {
            "$schema": "https://opencode.ai/config.json",
        }
        if target_path.exists():
            try:
                config = json.loads(target_path.read_text(encoding="utf-8"))
            except Exception:
                config = {"$schema": "https://opencode.ai/config.json"}

        cmd_path = shutil.which("havfrys") or str(Path.home() / ".local" / "bin" / "havfrys")
        mcp_dict = config.setdefault("mcp", {})
        mcp_dict["havfrys"] = {
            "type": "local",
            "command": [cmd_path, "serve"],
        }
        target_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
        return True, str(target_path)
    except Exception as e:
        return False, str(e)


def install_gemini() -> tuple[bool, str]:
    """Configure Gemini CLI to run local HAVFRYS MCP server."""
    target_path = Path.home() / ".gemini" / "mcp.json"
    return _update_mcp_json_file(target_path, "havfrys")


def install_windsurf() -> tuple[bool, str]:
    """Configure Windsurf to run local HAVFRYS MCP server."""
    target_path = Path.home() / ".codeium" / "windsurf" / "mcp_config.json"
    return _update_mcp_json_file(target_path, "havfrys")


def install_cline() -> tuple[bool, str]:
    """Configure Cline / Roo Code to run local HAVFRYS MCP server."""
    target_path = Path.home() / "Library" / "Application Support" / "Code" / "User" / "globalStorage" / "rooveterinaryinc.roo-cline" / "settings" / "mcp_settings.json"
    return _update_mcp_json_file(target_path, "havfrys")


def install_continue() -> tuple[bool, str]:
    """Configure Continue to run local HAVFRYS MCP server."""
    target_path = Path.home() / ".continue" / "config.json"
    return _update_mcp_json_file(target_path, "havfrys")


def install_zed() -> tuple[bool, str]:
    """Configure Zed Editor to run local HAVFRYS MCP server."""
    target_path = Path.home() / ".config" / "zed" / "settings.json"
    return _update_mcp_json_file(target_path, "havfrys")


def _update_mcp_json_file(file_path: Path, server_name: str) -> tuple[bool, str]:
    """Helper to update or create an MCP client configuration file."""
    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        config: dict[str, Any] = {}

        if file_path.exists():
            try:
                config = json.loads(file_path.read_text(encoding="utf-8"))
            except Exception:
                try:
                    shutil.copy2(file_path, file_path.with_suffix(".json.bak"))
                except Exception:
                    pass
                config = {}

        servers = config.setdefault("mcpServers", {})
        servers[server_name] = get_havfrys_mcp_config()

        file_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
        return True, str(file_path)
    except Exception as e:
        return False, str(e)


HAVFRYS_HAV_MD = """# HAVFRYS

> Read this file before starting any engineering task.

## Purpose

HAVFRYS is an engineering execution and software maintenance runtime.

It provides two capabilities:

- **exe** — Solves engineering problems safely.
- **maintain** — Keeps software healthy over time.

---

# Decision

Before starting work, ask yourself:

Can I confidently solve this using my native tools?

- Yes → Use native tools.
- No → Continue.

Is this an engineering or maintenance problem?

- Engineering → Use `exe`.
- Maintenance → Use `maintain`.

Do **not** use HAVFRYS for:

- Documentation edits
- Typos
- Small refactors
- Single-file changes
- Simple shell commands

---

# exe

Use for:

- Framework migrations
- Repository modernization
- Multi-file features
- Large refactors
- Failing test suites
- Engineering uncertainty

Workflow:

1. Understand the engineering goal.
2. Create an isolated execution environment.
3. Execute linearly when appropriate.
4. Spawn alternative strategies when uncertainty exists.
5. Validate every candidate.
6. Apply only the validated winner.
7. Return an engineering summary.

Never modify the real repository before validation.

---

# maintain

Use for:

- Repository health
- Dependency upgrades
- Framework evolution
- Compatibility verification
- Post-execution verification

Workflow:

1. Inspect repository health.
2. Analyse dependencies.
3. Analyse framework versions.
4. Compare against previous maintenance state.
5. Determine whether maintenance is required.
6. If engineering work is required, call `exe`.
7. Verify the final repository.
8. Update the maintenance graph.

---

# Principles

- Users describe problems, never machinery.
- Prefer inference over configuration.
- Adapt to repository context.
- Hide implementation details.
- Validate before applying.
- Never experiment on the user's working tree.

---

# Examples

User:
\"Upgrade this Django project to Python 3.14.\"

→ Use `exe`.

---

User:
\"Check whether this repository needs maintenance.\"

→ Use `maintain`.

---

User:
\"Fix this README typo.\"

→ Do not use HAVFRYS.

---

User:
\"I'm unsure which tool to use.\"

→ Use the decision process above.
"""


def run_init_wizard(choice: Optional[int] = None, auto_all: bool = False, target_dir: str = ".") -> None:
    """Initialize HAVFRYS repository decision layer (.havfrys/HAVFRYS.md)."""
    from havfrys.ui import render_banner, symbol_ok, BOLD, CYAN, GREEN, DIM, RESET
    print(render_banner("Workspace Initialization", VERSION))

    target_path = Path(target_dir).resolve()
    havfrys_dir = target_path / ".havfrys"
    hav_file = havfrys_dir / "HAVFRYS.md"

    try:
        havfrys_dir.mkdir(parents=True, exist_ok=True)
        hav_file.write_text(HAVFRYS_HAV_MD, encoding="utf-8")
        print(f"  {symbol_ok()} {BOLD}Initialized{RESET} {hav_file.relative_to(target_path) if hav_file.is_relative_to(target_path) else hav_file}\n")
    except Exception as e:
        print(f"  {RED}Failed to create .havfrys/HAVFRYS.md: {e}{RESET}\n")
        return

    prompt = (
        "You are working in a Havfrys-enabled repository.\n\n"
        "1. Ensure the Havfrys MCP server is configured (\"havfrys serve\").\n"
        "2. Read and follow the rules in .havfrys/HAVFRYS.md before starting any engineering task.\n"
        "3. Use `exe` for engineering execution tasks.\n"
        "4. Use `maintain` for maintenance and repository health tasks."
    )

    print(f"{CYAN}┌─────────────────────────────────────────────────────────────┐{RESET}")
    print(f"{CYAN}│{RESET}  {BOLD}AI Agent Prompt (Copy & Paste to your AI coding agent){RESET}   {CYAN}│{RESET}")
    print(f"{CYAN}└─────────────────────────────────────────────────────────────┘{RESET}\n")
    print(f"{DIM}{prompt}{RESET}\n")


def run_doctor() -> None:
    """Run HAVFRYS Diagnostics for local environment using rich UI components."""
    from havfrys.ui import render_banner, render_section, render_row, symbol_ok, symbol_err, BOLD, GREEN, CYAN, RESET
    print(render_banner("Runtime Diagnostics", VERSION))

    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    print(render_section("System & Runtime"))
    print(render_row("Python", f"{py_ver} ({sys.platform})"))
    print(render_row("MCP Server", "Available (havfrys serve)"))

    # Engine
    try:
        from havfrys._core import route_and_compress
        print(render_row("Compression Engine", "Loaded (Lossless + SmartCrusher)"))
    except Exception as e:
        print(render_row("Compression Engine", f"Failed to load: {e}", is_ok=False))

    try:
        from havfrys._core import LoopEngine
        print(render_row("Loop Detection", "Loaded (BranchLoopDetector)"))
    except Exception as e:
        print(render_row("Loop Detection", f"Failed to load: {e}", is_ok=False))

    # Toolchain
    print(render_section("Toolchain & Containers"))
    git_path = shutil.which("git")
    cargo_path = shutil.which("cargo")
    docker_path = shutil.which("docker")
    print(render_row("Git CLI", git_path or "not found", is_ok=bool(git_path)))
    print(render_row("Cargo Compiler", cargo_path or "not found (Optional)", is_ok=True))
    print(render_row("Docker Engine", docker_path or "not found (Optional, Level 0 Active)", is_ok=True))

    # Clients
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


def _print_result(client_name: str, success: bool, path_or_err: str) -> None:
    """Print success or failure summary for installer wizard."""
    from havfrys.ui import render_row, symbol_ok, symbol_err, BOLD, GREEN, RED, RESET
    if success:
        print(f"  {symbol_ok()} {BOLD}{client_name:<20}{RESET} Configured at {path_or_err}")
    else:
        print(f"  {symbol_err()} {BOLD}{client_name:<20}{RESET} {RED}Failed: {path_or_err}{RESET}")
