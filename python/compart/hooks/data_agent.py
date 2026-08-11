"""Category C — data / RAG agent sandbox hook.

:class:`DataScienceSandboxHook` gives Pandas/NumPy/Matplotlib data agents a
purpose-built compartment:

* an **isolated scratch workspace** that the agent may freely read/write,
* a **read-only system view** enforced by the kernel sandbox (Landlock /
  Seatbelt) so ``~/.ssh``, cloud configs and the host home stay unreachable,
* **outbound network blocked** unless explicitly granted, so datasets cannot
  be exfiltrated to external IP addresses,
* **credential proxy injection** for the data sources the agent *is* allowed
  to reach (e.g. an S3/DB gateway) without ever exposing the raw key,
* optional **BLAKE3 file diffs** so a workflow can audit exactly what the
  agent changed in the workspace.

The intended workflow is: mount the datasets you want the agent to see into
the isolated workspace (``mount_dataset``), let it run, then read the diffs.
The agent literally never sees a path outside the grant, and it has no
network route out of it.
"""

from __future__ import annotations

import os
import shlex
import shutil
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional, Sequence

from ..sandbox.proxy import RouteConfig
from .base import ExecutionResult, SandboxRunner, validate_permissions

__all__ = [
    "DataSandboxConfig",
    "DataScienceSandboxHook",
]

#: Default permission set for data agents — deliberately lacks ``network``.
DATA_PERMISSIONS: tuple[str, ...] = ("fs_read", "fs_write", "fs_exec")


@dataclass
class DataSandboxConfig:
    """Configuration for a data-science sandbox.

    Attributes
    ----------
    workdir
        Parent directory the isolated workspace is created under.
    permission
        Permissions granted to the data compartment.
    allow_network
        Allow outbound network (default deny — prevents exfiltration).
    credential_rules
        Proxy routes for the allowed data sources.
    libraries
        Optional list of pip packages to pre-install.
    timeout_s
        Per-execution timeout.
    """

    workdir: str = "."
    permission: Sequence[str] = DATA_PERMISSIONS
    allow_network: bool = False
    credential_rules: Sequence[RouteConfig] = field(default_factory=list)
    libraries: Sequence[str] = field(default_factory=tuple)
    timeout_s: int = 600
    sandbox: bool = True


class DataScienceSandboxHook:
    """Sandboxed execution environment for data / RAG agents.

    Parameters
    ----------
    config
        :class:`DataSandboxConfig` controlling permissions and access.
    """

    def __init__(
        self,
        config: Optional[DataSandboxConfig] = None,
        *,
        workdir: Optional[str] = None,
        allow_network: Optional[bool] = None,
        sandbox: Optional[bool] = None,
    ) -> None:
        cfg = config or DataSandboxConfig()
        if workdir is not None:
            cfg.workdir = workdir
        if allow_network is not None:
            cfg.allow_network = allow_network
        if sandbox is not None:
            cfg.sandbox = sandbox
        self._config = cfg
        self._permissions = validate_permissions(cfg.permission)
        base = os.path.abspath(cfg.workdir)
        self._workspace_root = os.path.join(base, ".compart", "data", uuid.uuid4().hex[:8])
        os.makedirs(self._workspace_root, exist_ok=True)
        self._runner = SandboxRunner(
            workdir=self._workspace_root,
            credential_rules=list(cfg.credential_rules),
            sandbox=cfg.sandbox,
            block_network=not cfg.allow_network,
        )
        if cfg.libraries:
            self.install(cfg.libraries)

    @property
    def workspace(self) -> str:
        """Absolute path of the isolated scratch workspace."""
        return self._workspace_root

    @property
    def block_network(self) -> bool:
        """True when the sandbox denies outbound network."""
        return not self._config.allow_network

    def mount_dataset(self, *paths: str) -> list[str]:
        """Copy dataset files into the isolated workspace.

        Only files copied here are visible to the agent, so it can never
        touch the source datasets directly or ship them anywhere (no network
        route exists out of the compartment).

        Parameters
        ----------
        *paths
            Files or directories to copy into the workspace root.

        Returns
        -------
        list[str]
            The workspace-relative paths of the mounted entries.

        Raises
        ------
        ValueError
            If a source path does not exist.
        """
        mounted: list[str] = []
        for path in paths:
            src = os.path.abspath(os.path.expanduser(path))
            if not os.path.exists(src):
                raise ValueError(f"dataset path does not exist: {path}")
            if os.path.isdir(src):
                dst = os.path.join(self._workspace_root, os.path.basename(src))
                shutil.copytree(src, dst, dirs_exist_ok=True)
                mounted.append(os.path.basename(src))
            else:
                dst = os.path.join(self._workspace_root, os.path.basename(src))
                shutil.copy2(src, dst)
                mounted.append(os.path.basename(src))
        return mounted

    def install(self, libraries: Sequence[str]) -> ExecutionResult:
        """Pre-install pip libraries inside the sandbox.

        Parameters
        ----------
        libraries
            Pip package names (or ``pkg==version`` pins).

        Returns
        -------
        ExecutionResult
        """
        if not libraries:
            return ExecutionResult()
        quoted = " ".join(f"'{p}'" for p in libraries)
        return self._runner.run(
            f"python3 -m pip install --quiet {quoted}",
            permissions=self._permissions,
            timeout_s=self._config.timeout_s,
        )

    def run(
        self,
        code: str,
        *,
        timeout_s: Optional[int] = None,
        env: Optional[dict[str, str]] = None,
    ) -> ExecutionResult:
        """Execute a data-processing ``code`` snippet in the sandbox.

        Parameters
        ----------
        code
            Python source (Pandas/NumPy/Matplotlib typically).
        timeout_s
            Override the configured timeout.
        env
            Optional extra environment variables (e.g. proxy auth context).

        Returns
        -------
        ExecutionResult
        """
        return self._runner.run_code(
            code,
            permissions=self._permissions,
            timeout_s=timeout_s or self._config.timeout_s,
            env=env,
            name="data-agent",
        )

    def run_file(self, filename: str, *, timeout_s: Optional[int] = None) -> ExecutionResult:
        """Execute a script already present in the workspace.

        Parameters
        ----------
        filename
            Workspace-relative script path.
        timeout_s
            Override the configured timeout.

        Returns
        -------
        ExecutionResult
        """
        script = os.path.join(self._workspace_root, filename)
        return self._runner.run(
            f"python3 {shlex.quote(filename)}",
            permissions=self._permissions,
            timeout_s=timeout_s or self._config.timeout_s,
            name="data-agent-file",
            cwd=self._workspace_root,
        )

    def cleanup(self) -> None:
        """Remove the isolated workspace."""
        shutil.rmtree(self._workspace_root, ignore_errors=True)