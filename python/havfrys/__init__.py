"""HAVFRYS — Maintenance Infrastructure for AI-Built Software by HAVFRYS Labs.

Core primitives:
    havfrys.exe("Fix failing tests")
    havfrys.maintain()
    havfrys.run("Fix failing tests")
"""

from .core import havfrys, exe, run, maintain, resume, inspect, HavfrysResult

__all__ = ["havfrys", "exe", "run", "maintain", "resume", "inspect", "HavfrysResult"]
__version__ = "0.3.3"
