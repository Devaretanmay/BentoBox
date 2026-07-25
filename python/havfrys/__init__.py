"""HAVFRYS — Maintenance Infrastructure for AI-Built Software by HAVFRYS Labs.

Core primitives:
    havfrys.exe("Fix failing tests")
    havfrys.maintain()
"""

from .core import havfrys, exe, maintain, resume, inspect, HavfrysResult

__all__ = ["havfrys", "exe", "maintain", "resume", "inspect", "HavfrysResult"]
__version__ = "0.3.5"
