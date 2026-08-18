"""Compart CI/CD Drop-In Integration Module.

Provides local kernel-enforced sandboxing and snapshot-based state handling
for GitHub Actions, GitLab CI, Jenkins, and CircleCI.
"""

from .runner import CompartCIRunner, run_ci_step

__all__ = ["run_ci_step", "CompartCIRunner"]
