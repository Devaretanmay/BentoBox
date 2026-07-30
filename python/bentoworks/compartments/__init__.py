"""Compartments — isolated execution units inside a BentoBox.

Instead of a fixed pipeline (Intent → Plan → Execute → Verify), each
compartment is a self-contained execution unit with its own permissions,
resource limits, and communication channels. The runtime has no opinion
about what compartments do — it only coordinates their lifecycle and
routes typed ``Message`` objects between them.

Usage::

    from bentoworks import BentoBox
    from bentoworks.compartments import Compartment, CompartmentConfig

    box = BentoBox()
    box.add(Compartment(name="build", fn=run_build,
                        config=CompartmentConfig(permissions=["fs_read", "fs_exec"])))
    result = box.run()
"""

from .base import Compartment
from .config import CompartmentConfig
from .message import Message
from .runtime import CompartmentRuntime, CompartmentContext

__all__ = [
    "Compartment",
    "CompartmentConfig",
    "CompartmentRuntime",
    "CompartmentContext",
    "Message",
]
