"""Compartment - the fundamental execution unit inside a BentoBox."""

from typing import Any, Callable, Optional

from .config import CompartmentConfig
from .message import Message


class Compartment:
    """A named unit of isolated execution with its own permissions and behaviour."""

    config: CompartmentConfig = CompartmentConfig()

    def __init__(
        self,
        name: Optional[str] = None,
        fn: Optional[Callable] = None,
        config: Optional[CompartmentConfig] = None,
    ):
        if name:
            if config:
                config.name = name
            else:
                config = CompartmentConfig(name=name)
        if config:
            self.config = config
        self._fn = fn
        self._inbox: list[Message] = []
        self._outbox: list[Message] = []


    def deliver(self, msg: Message) -> None:
        self._inbox.append(msg)

    def run(self, ctx: Any) -> Any:
        """Execute this compartment's logic.

        Override in subclasses, or pass ``fn`` to the constructor.
        """
        if self._fn is not None:
            return self._fn(ctx)
        raise NotImplementedError(
            f"Compartment '{self.config.name}' has no run logic. "
            "Either subclass it or pass a callable as fn=."
        )


    def receive(self) -> list[Message]:
        """Read all pending messages from other compartments."""
        msgs = list(self._inbox)
        self._inbox.clear()
        return msgs

    def drain_outbox(self) -> list[Message]:
        msgs = list(self._outbox)
        self._outbox.clear()
        return msgs

    def __repr__(self) -> str:
        return f"<Compartment '{self.config.name}': {self.config.permissions}>"
