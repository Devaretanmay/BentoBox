"""BentoBox CI/CD Drop-In Integration Module.

Provides zero-cost, zero-infrastructure kernel-enforced sandboxing
and sub-millisecond state resets for GitHub Actions, GitLab CI, Jenkins, and CircleCI.
"""

from .runner import run_ci_step, BentoCIRunner

__all__ = ["run_ci_step", "BentoCIRunner"]
