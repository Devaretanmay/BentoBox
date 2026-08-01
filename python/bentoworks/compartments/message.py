import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Message:
    from_: str
    to: str
    data: Any
    type: str = "data"  # data | signal | error | result
    timestamp: float = field(default_factory=time.time)
