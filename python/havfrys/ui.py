"""HAVFRYS Terminal UI & Aesthetics Engine.

Provides high-grade terminal UI components inspired by modern CLI tools
(Vercel, Modal, Claude Code, Supabase, Railway):
- ANSI Color Tokens
- Box Framing & Header Banners
- Status Badges (✔, ✖, ℹ, ◆, ➜)
- Key-Value Status Tables
"""

import sys
import os

# Check color support
SUPPORTS_COLOR = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None

if SUPPORTS_COLOR:
    BOLD = "\033[1m"
    DIM = "\033[2m"
    CYAN = "\033[36m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    RED = "\033[31m"
    RESET = "\033[0m"
else:
    BOLD = DIM = CYAN = GREEN = YELLOW = RED = RESET = ""


def symbol_ok() -> str:
    return f"{GREEN}✔{RESET}" if SUPPORTS_COLOR else "[OK]"


def symbol_err() -> str:
    return f"{RED}✖{RESET}" if SUPPORTS_COLOR else "[ERR]"



def render_banner(title: str, version: str = "") -> str:
    """Render a clean box-framed CLI header banner."""
    ver_str = f" v{version}" if version else ""
    full_title = f"HAVFRYS Labs — {title}{ver_str}"
    line = "─" * (len(full_title) + 4)
    
    top = f"{CYAN}┌{line}┐{RESET}"
    mid = f"{CYAN}│{RESET}  {BOLD}{full_title}{RESET}  {CYAN}│{RESET}"
    bot = f"{CYAN}└{line}┘{RESET}"
    
    return f"\n{top}\n{mid}\n{bot}\n"


def render_section(title: str) -> str:
    """Render bold section header."""
    return f"\n{BOLD}{CYAN}{title}{RESET}"


def render_row(label: str, status_text: str, is_ok: bool = True, indent: int = 2) -> str:
    """Render a key-value status row."""
    icon = symbol_ok() if is_ok else f"{YELLOW}○{RESET}"
    pad = " " * indent
    return f"{pad}{icon} {BOLD}{label:<20}{RESET} {DIM}{status_text}{RESET}"
