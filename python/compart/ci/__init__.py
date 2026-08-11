"""Compart CI/CD Drop-In Integration Module.

Provides local kernel-enforced sandboxing and snapshot-based state handling
for GitHub Actions, GitLab CI, Jenkins, and CircleCI.
"""

__all__ = ["run_ci_step", "CompartCIRunner"]


def __getattr__(name):
    if name in __all__:
        from .runner import CompartCIRunner, run_ci_step
        return {"CompartCIRunner": CompartCIRunner, "run_ci_step": run_ci_step}[name]
    raise AttributeError(name)
