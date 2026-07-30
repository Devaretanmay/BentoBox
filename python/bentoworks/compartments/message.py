"""Message — typed data exchange unit between compartments."""

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Message:
    """A typed message sent from one compartment to another.

    Compartments never call each other directly. They exchange messages
    through the runtime, which routes them based on declared edges.
    """

    from_: str
    to: str
    data: Any
    type: str = "data"  # data | signal | error | result
    timestamp: float = field(default_factory=time.time)
