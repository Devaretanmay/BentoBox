"""CompartmentConfig — per-compartment policy for permissions, resources, and communication."""

from dataclasses import dataclass, field


PERMISSION_FS_READ = "fs_read"
PERMISSION_FS_WRITE = "fs_write"
PERMISSION_FS_EXEC = "fs_exec"
PERMISSION_NETWORK = "network"
PERMISSION_GPU = "gpu"
PERMISSION_SYS_INFO = "sys_info"

ALL_PERMISSIONS = [
    PERMISSION_FS_READ,
    PERMISSION_FS_WRITE,
    PERMISSION_FS_EXEC,
    PERMISSION_NETWORK,
    PERMISSION_GPU,
    PERMISSION_SYS_INFO,
]


@dataclass
class CompartmentConfig:
    """Policy that defines what a compartment can access and how it runs.

    Every compartment has its own config — no two compartments need the
    same set of permissions or resource limits, even inside the same Box.
    """

    # ── Identity ────────────────────────────────────────────────────────
    name: str = "unnamed"
    description: str = ""

    # ── Sandbox permissions ─────────────────────────────────────────────
    # Each permission controls a domain the compartment can interact with.
    permissions: list[str] = field(default_factory=lambda: [PERMISSION_FS_READ])

    # ── Resource limits (0 = unlimited) ─────────────────────────────────
    timeout_s: int = 300
    memory_mb: int = 0
    storage_mb: int = 0
    cpu_percent: int = 0

    # ── Communication whitelist ─────────────────────────────────────────
    # Which other compartments can send messages to / receive from this one.
    # "*" means any. An empty list means none.
    allow_inbound_from: list[str] = field(default_factory=lambda: ["*"])
    allow_outbound_to: list[str] = field(default_factory=lambda: ["*"])

    def has(self, permission: str) -> bool:
        return permission in self.permissions
