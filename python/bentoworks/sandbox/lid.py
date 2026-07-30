"""Lid — insulation layer that loads behaviour modules when the box is entered."""

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from .behaviour import BehaviourContext, Engine, discover
from ..engine.events import emit
from .task_profile import classify as classify_profile

_logger = logging.getLogger("bentoworks.lid")


@dataclass
class LidConfig:
    profile: str = "default"
    credential_rules: list = field(default_factory=list)
    snapshot_base: str = ""


ENGINE_ORDER = ["preparation", "optimisation", "behaviour", "observation"]


class Lid:
    def __init__(self, config: Optional[LidConfig] = None):
        self.config = config or LidConfig()
        self._engines = {name: Engine(name) for name in ENGINE_ORDER}
        self._ctx: Optional[BehaviourContext] = None

    def insulate(self, box, task_request: str) -> None:
        task_profile = classify_profile(task_request)
        emit("task_profile", profile=task_profile)
        self._ctx = BehaviourContext(
            box_id=box.box_id,
            box_dir=box.box_dir,
            workdir=box.workdir,
            task_profile=task_profile,
            config={
                "profile": self.config.profile,
                "credential_rules": list(self.config.credential_rules),
                "snapshot_base": self.config.snapshot_base,
            },
        )
        all_modules = discover()
        module_count = 0
        for name, cls in all_modules.items():
            engine = self._engines.get(cls.engine)
            if engine is not None:
                m = cls()
                m.load(self._ctx)
                engine.modules.append(m)
                module_count += 1
        _logger.info("Lid insulated (profile=%s, task=%s, modules=%d)",
                      task_profile, task_request[:60], module_count)
        emit("lid.insulated", profile=task_profile, modules=module_count)

    def release(self) -> None:
        for engine in self._engines.values():
            engine.unload_all()
        self._ctx = None
        _logger.info("Lid released")
        emit("lid.released")

    def dispatch(self, event: str, **data) -> list[Any]:
        results = []
        for name in ENGINE_ORDER:
            engine = self._engines[name]
            results.extend(engine.dispatch(event, **data))
        return results
