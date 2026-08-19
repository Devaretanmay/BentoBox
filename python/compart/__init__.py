from .compart import Compart, AgentCompart, CompartConfig, CompartResult
from .compartments import Compartment, CompartmentConfig

from . import compartments as compartments
from . import hooks as hooks

try:
    from importlib.metadata import version as _package_version
    __version__ = _package_version("compart")
except Exception:
    __version__ = "unknown"

__all__ = [
    "Compart",
    "AgentCompart",
    "CompartConfig",
    "CompartResult",
    "Compartment",
    "CompartmentConfig",
    "compartments",
    "hooks",
]

