"""BentoBox error hierarchy."""


class BentoBoxError(Exception):
    """Base for all BentoBox exceptions."""


class ConfigError(BentoBoxError):
    """Configuration is invalid."""


class SandboxError(BentoBoxError):
    """Sandbox enforcement unavailable or failed."""


class LayerError(BentoBoxError):
    """A compartment layer failed during execution."""
