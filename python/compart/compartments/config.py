from dataclasses import dataclass, field


@dataclass
class CompartmentConfig:
    """Policy that defines what a compartment can access and how it runs."""

    name: str = "unnamed"
    description: str = ""

    permissions: list[str] = field(default_factory=lambda: ["fs_read"])

    timeout_s: int = 300

    allow_inbound_from: list[str] = field(default_factory=lambda: ["*"])
    allow_outbound_to: list[str] = field(default_factory=lambda: ["*"])
