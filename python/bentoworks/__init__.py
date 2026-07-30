"""BentoBox — kernel-level sandbox with compartmentalized isolated execution.

The core abstraction is a ``BentoBox`` — an isolated sandbox whose
environment is automatically optimized. Inside the box, **compartments**
define what runs, with each having its own permissions and resource limits.

Usage::

    from bentoworks import BentoBox
    from bentoworks.compartments import Compartment, CompartmentConfig

    box = BentoBox()
    box.add(Compartment(
        name="build",
        fn=lambda ctx: __import__("os").system("pytest"),
        config=CompartmentConfig(permissions=["fs_read", "fs_exec"]),
    ))
    result = box.run()
    print(result.status, result.summary)

See https://github.com/Devaretanmay/BentoBox for full documentation.
"""

from .bentobox import BentoBox, BentoBoxConfig, BentoBoxResult

from . import compartments as compartments
from . import errors as errors

__version__ = "0.9.0"

__all__ = [
    "BentoBox",
    "BentoBoxConfig",
    "BentoBoxResult",
    "compartments",
    "errors",
]
