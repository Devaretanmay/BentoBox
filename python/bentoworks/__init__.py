from .bentobox import BentoBox, AgentBentoBox, BentoBoxConfig, BentoBoxResult

from . import compartments as compartments
from . import errors as errors

try:
    from importlib.metadata import version as _package_version
    __version__ = _package_version("bentoworks")
except Exception:
    __version__ = "unknown"

__all__ = [
    "BentoBox",
    "AgentBentoBox",
    "BentoBoxConfig",
    "BentoBoxResult",
    "compartments",
    "errors",
]
