"""Compart Desktop — Native launcher with real Python backend API.

Exposes SandboxRunner, SnapshotManager, and workspace introspection
to the frontend via pywebview's js_api bridge.
"""

import json
import os
import sys
import threading

import webview

# Ensure the compart package is importable
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
_PYTHON_DIR = os.path.join(_REPO_ROOT, "python")
if _PYTHON_DIR not in sys.path:
    sys.path.insert(0, _PYTHON_DIR)

from compart.hooks.base import SandboxRunner, ExecutionResult, VALID_PERMISSIONS
from compart.sandbox.snapshot import SnapshotManager, _file_hash, _DEFAULT_EXCLUDE
from compart.sandbox.proxy import RouteConfig


class CompartAPI:
    """Backend exposed to the frontend via window.pywebview.api.*"""

    def __init__(self):
        self._last_result: dict | None = None
        self._last_workdir: str | None = None

    # ── Workspace info ──

    def get_workspace(self):
        """Return the repo root as the default workspace."""
        return _REPO_ROOT

    def list_workspace_files(self, workdir: str):
        """List top-level files in the workspace (non-hidden, non-excluded)."""
        workdir = os.path.abspath(workdir or _REPO_ROOT)
        if not os.path.isdir(workdir):
            return []
        entries = []
        for name in sorted(os.listdir(workdir)):
            if name.startswith(".") or name in _DEFAULT_EXCLUDE:
                continue
            full = os.path.join(workdir, name)
            entries.append({
                "name": name,
                "is_dir": os.path.isdir(full),
                "size": os.path.getsize(full) if os.path.isfile(full) else 0,
            })
        return entries

    # ── Sandbox execution ──

    def run_sandboxed(self, command: str, workdir: str, permissions: list,
                      sandbox: bool, block_network: bool):
        """Run a real shell command inside a Compart sandbox.

        Returns the ExecutionResult as a plain dict with:
        returncode, stdout, stderr, diffs, elapsed_s, error, timed_out
        """
        workdir = os.path.abspath(workdir or _REPO_ROOT)
        perms = [p for p in permissions if p in VALID_PERMISSIONS]
        if not perms:
            perms = ["fs_read"]

        runner = SandboxRunner(
            workdir=workdir,
            sandbox=sandbox,
            block_network=block_network,
        )
        result = runner.run(
            command=command,
            permissions=perms,
            timeout_s=60,
            snapshot=True,
        )
        result_dict = result.as_dict()
        self._last_result = result_dict
        self._last_workdir = workdir
        return result_dict

    # ── Snapshot & rollback ──

    def rollback(self):
        """Rollback workspace to the last pre-run snapshot."""
        if not self._last_workdir:
            return {"restored": 0, "error": "No previous run to rollback."}
        snapshot_dir = os.path.join(self._last_workdir, ".compart", "snapshots")
        if not os.path.isdir(snapshot_dir):
            return {"restored": 0, "error": "No snapshot directory found."}
        # Find the most recent snapshot subdirectory
        subs = sorted([
            d for d in os.listdir(snapshot_dir)
            if os.path.isdir(os.path.join(snapshot_dir, d))
        ])
        if not subs:
            return {"restored": 0, "error": "No snapshots available."}
        latest = os.path.join(snapshot_dir, subs[-1])
        snap = SnapshotManager(workdir=self._last_workdir, snapshot_dir=latest)
        count = snap.restore()
        return {"restored": count}

    # ── System info ──

    def get_system_info(self):
        """Return platform sandbox support info."""
        import platform
        system = platform.system()
        sandbox_type = "Seatbelt" if system == "Darwin" else "Landlock" if system == "Linux" else "None"
        try:
            from compart._core import sandbox_apply  # noqa: F401
            native_available = True
        except ImportError:
            native_available = False
        return {
            "os": system,
            "sandbox_type": sandbox_type,
            "native_available": native_available,
            "python": platform.python_version(),
        }


def main():
    api = CompartAPI()
    dir_path = os.path.dirname(os.path.realpath(__file__))
    html_path = os.path.join(dir_path, "index.html")

    window = webview.create_window(
        title="Compart",
        url=html_path,
        js_api=api,
        width=1180,
        height=760,
        resizable=True,
        min_size=(900, 600),
    )
    webview.start(debug=False)


if __name__ == "__main__":
    main()
