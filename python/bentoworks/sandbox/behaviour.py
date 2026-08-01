from abc import ABC
from dataclasses import dataclass, field
from typing import Any


@dataclass
class BehaviourContext:
    box_id: str
    box_dir: str
    workdir: str
    task_profile: str
    config: dict = field(default_factory=dict)


class BehaviourModule(ABC):
    """Base class for runtime plugins. Each module hooks into one engine phase."""
    name: str = ""
    engine: str = ""

    def load(self, ctx: BehaviourContext) -> None:
        pass

    def unload(self) -> None:
        pass

    def on_event(self, event: str, **data) -> Any:
        pass


_BUILTIN_MODULES: dict[str, type[BehaviourModule]] = {}


def register(cls):
    _BUILTIN_MODULES[cls.name] = cls
    return cls


def discover() -> dict[str, type[BehaviourModule]]:
    return dict(_BUILTIN_MODULES)


class Engine:
    def __init__(self, name: str):
        self.name = name
        self.modules: list[BehaviourModule] = []

    def unload_all(self) -> None:
        for m in self.modules:
            try:
                m.unload()
            except Exception:
                pass
        self.modules.clear()

    def dispatch(self, event: str, **data) -> list[Any]:
        results = []
        for m in self.modules:
            try:
                r = m.on_event(event, **data)
                if r is not None:
                    results.append(r)
            except Exception:
                pass
        return results
