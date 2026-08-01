"""Box - standalone kernel-level sandbox. No AI awareness."""

import logging
import os
import shutil
import time
import uuid
from dataclasses import dataclass
from typing import Optional

from ..engine.events import emit

_logger = logging.getLogger("bentoworks.box")

# The Rust _core sandbox is optional - BentoBox works without it,
# which lets users run tests and experiments without compiling the native module.
_CORE = None


def _get_core():
    global _CORE
    if _CORE is None:
        try:
            from bentoworks._core import sandbox_apply, sandbox_check_supported, sandbox_why
            _CORE = (sandbox_apply, sandbox_check_supported, sandbox_why)
        except ImportError:
            _CORE = ()
    return _CORE

STATE_CREATED = "created"
STATE_READY = "ready"
STATE_RUNNING = "running"
STATE_DESTROYED = "destroyed"


@dataclass
class BoxConfig:
    timeout_s: int = 600
    block_network: bool = True


class Box:
    BENTOWORKS_DIR = ".bentoworks"

    def __init__(self, workdir: str = "."):
        self.workdir = os.path.abspath(workdir)
        self.box_id = f"box_{uuid.uuid4().hex[:8]}"
        self.box_dir = os.path.join(self.workdir, self.BENTOWORKS_DIR, "boxes", self.box_id)
        self.config = BoxConfig()
        self._state = STATE_CREATED
        self._started_at: Optional[float] = None
        self._sandbox_applied = False
        self._current_policy: dict = {}
        emit("box.created", box_id=self.box_id, path=self.box_dir)

    def enter(self, block_network: Optional[bool] = None, sandbox: Optional[bool] = None) -> bool:
        if self._state != STATE_CREATED:
            raise RuntimeError(f"Cannot enter from state: {self._state}")
        self._state = STATE_READY
        os.makedirs(self.box_dir, exist_ok=True)
        if block_network is not None:
            self.config.block_network = block_network
        self._sandbox_applied = False
        core = _get_core()
        if sandbox is None or sandbox:
            if len(core) >= 2:
                apply_fn, check_supported_fn = core[0], core[1]
                try:
                    supported = check_supported_fn()
                    if not supported:
                        _logger.warning("Sandbox not available on this platform")
                    else:
                        apply_fn(self.workdir, self.config.block_network)
                        self._sandbox_applied = True
                        _logger.info("Sandbox applied (network_blocked=%s)", self.config.block_network)
                except Exception as e:
                    _logger.warning("Sandbox unavailable, continuing without: %s", e)
        self._state = STATE_RUNNING
        self._started_at = time.time()
        emit("box.entered", box_id=self.box_id, sandbox_applied=self._sandbox_applied)
        return self._sandbox_applied

    def apply_policy(self, config) -> None:
        """Records the current compartment's policy so the SandboxEnforcer can read it."""
        self._current_policy = {
            "name": config.name,
            "permissions": list(config.permissions),
            "timeout_s": config.timeout_s,
            "memory_mb": config.memory_mb,
            "storage_mb": config.storage_mb,
        }
        _logger.debug(
            "Policy for compartment '%s': %s",
            config.name, config.permissions,
        )

    def exit(self) -> None:
        if self._state not in (STATE_RUNNING, STATE_READY):
            raise RuntimeError(f"Cannot exit from state: {self._state}")
        if os.path.isdir(self.box_dir):
            shutil.rmtree(self.box_dir, ignore_errors=True)
        self._state = STATE_DESTROYED
        self._started_at = None
        self._current_policy = {}
        _logger.info("Box %s destroyed", self.box_id)
        emit("box.destroyed", box_id=self.box_id)

    def why(self, path: str) -> str:
        """Queries the Rust sandbox diagnostic: why would this path be blocked?"""
        core = _get_core()
        if len(core) < 3:
            return (
                f"INFO - Rust sandbox module not loaded.\n"
                f"Run 'maturin develop --offline' to build the native module.\n"
                f"Without it, BentoBox runs in no-sandbox mode."
            )
        try:
            why_fn = core[2]
            if path.startswith(("tcp:", "udp:", "http://", "https://")):
                resolved = path
            else:
                resolved = os.path.abspath(os.path.expanduser(path))
            return why_fn(resolved, self.workdir, self.config.block_network)
        except Exception as e:
            return f"ERROR - Diagnostic failed: {e}"

    @property
    def state(self) -> str:
        return self._state

    @property
    def elapsed_s(self) -> float:
        if self._started_at is None:
            return 0.0
        return round(time.time() - self._started_at, 2)

    @property
    def is_active(self) -> bool:
        return self._state == STATE_RUNNING
