"""Box - standalone kernel-level sandbox. No AI awareness.

The lid is part of the box: task-profile classification and behaviour
modules (insulation) live here, not beside it. Plain boxes load no
modules by default - compartments are never predefined. AgentBentoBox
sets ``auto_modules=True`` to load every registered module.
"""

import logging
import os
import shutil
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

from ..engine.events import emit
from .behaviour import BehaviourContext, Engine, discover
from .task_profile import classify as classify_profile

_logger = logging.getLogger("bentoworks.box")

# The Rust _core sandbox is optional - BentoBox works without it,
# which lets users run tests and experiments without compiling the native module.
_CORE = None


def _get_core():
    global _CORE
    if _CORE is None:
        try:
            from bentoworks._core import sandbox_apply, sandbox_check_supported
            _CORE = (sandbox_apply, sandbox_check_supported)
        except ImportError:
            _CORE = ()
    return _CORE


STATE_CREATED = "created"
STATE_READY = "ready"
STATE_RUNNING = "running"
STATE_DESTROYED = "destroyed"

ENGINE_ORDER = ["preparation", "behaviour", "observation"]


@dataclass
class BoxConfig:
    block_network: bool = True
    credential_rules: list = field(default_factory=list)
    snapshot_base: str = ""
    auto_modules: bool = False


class Box:
    BENTOWORKS_DIR = ".bentoworks"

    def __init__(self, workdir: str = ".", config: Optional[BoxConfig] = None):
        self.workdir = os.path.abspath(workdir)
        self.box_id = f"box_{uuid.uuid4().hex[:8]}"
        self.box_dir = os.path.join(self.workdir, self.BENTOWORKS_DIR, "boxes", self.box_id)
        self.config = config or BoxConfig()
        self._state = STATE_CREATED
        self._started_at: Optional[float] = None
        self._sandbox_applied = False
        self._current_policy: dict = {}
        # The lid, folded in: insulation lives on the box.
        self._engines = {name: Engine(name) for name in ENGINE_ORDER}
        self._registered: dict[str, type] = {}
        self._ctx: Optional[BehaviourContext] = None
        emit("box.created", box_id=self.box_id, path=self.box_dir)

    def register_module(self, module_cls) -> "Box":
        """Opt-in a behaviour module. Plain boxes load nothing by default."""
        self._registered[module_cls.name] = module_cls
        return self

    def insulate(self, task_request: str) -> None:
        """Classify the task profile and load behaviour modules into engines.

        Boxes with ``auto_modules`` load every registered module; otherwise
        only modules explicitly added via :meth:`register_module` load.
        """
        task_profile = classify_profile(task_request)
        emit("task_profile", profile=task_profile)
        self._ctx = BehaviourContext(
            box_id=self.box_id,
            box_dir=self.box_dir,
            workdir=self.workdir,
            task_profile=task_profile,
            config={
                "credential_rules": list(self.config.credential_rules),
                "snapshot_base": self.config.snapshot_base,
            },
        )
        module_types = discover() if self.config.auto_modules else dict(self._registered)
        module_count = 0
        for name, cls in module_types.items():
            engine = self._engines.get(cls.engine)
            if engine is not None:
                m = cls()
                m.load(self._ctx)
                engine.modules.append(m)
                module_count += 1
        _logger.info("Box insulated (profile=%s, task=%s, modules=%d)",
                     task_profile, task_request[:60], module_count)
        emit("box.insulated", profile=task_profile, modules=module_count)

    def release(self) -> None:
        for engine in self._engines.values():
            engine.unload_all()
        self._ctx = None
        _logger.info("Box released")
        emit("box.released")

    def dispatch(self, event: str, **data) -> list[Any]:
        results = []
        for name in ENGINE_ORDER:
            results.extend(self._engines[name].dispatch(event, **data))
        return results

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
                    supported_info = check_supported_fn()
                    if isinstance(supported_info, dict):
                        supported = str(supported_info.get("supported", "false")).lower() == "true"
                    else:
                        supported = bool(supported_info)
                    if not supported:
                        _logger.warning("Sandbox not available on this platform")
                    else:
                        applied = apply_fn(self.workdir, self.config.block_network)
                        self._sandbox_applied = applied is not False
                        if self._sandbox_applied:
                            _logger.info("Sandbox applied (network_blocked=%s)", self.config.block_network)
                        else:
                            _logger.warning("Sandbox could not be applied")
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
