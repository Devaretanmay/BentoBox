"""Compart workspace configuration loader.

Reads `.compart/config.yaml` and returns typed config objects for compartments,
agent defaults, and workflow topologies.  Maps human-readable YAML shorthand
(``filesystem: workspace``) to internal policy permission sets.
"""

from __future__ import annotations

import os
import warnings
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

try:
    import yaml
    _YAML_AVAILABLE = True
except ImportError:
    _YAML_AVAILABLE = False


_FILESYSTEM_TO_PERMISSIONS: Dict[str, List[str]] = {
    "workspace":  ["fs_read", "fs_write"],
    "read-only":  ["fs_read"],
    "read-write": ["fs_read", "fs_write"],
    "none":       [],
}

_NETWORK_TO_PERMISSIONS: Dict[str, List[str]] = {
    "restricted": [],
    "allowed":    ["network"],
    "denied":     [],
}


def _resolve_permissions(fs: str, network: str, execute: bool = True) -> List[str]:
    perms: List[str] = list(_FILESYSTEM_TO_PERMISSIONS.get(fs, ["fs_read", "fs_write"]))
    perms += _NETWORK_TO_PERMISSIONS.get(network, [])
    if execute and "fs_exec" not in perms:
        perms.append("fs_exec")
    return list(dict.fromkeys(perms))  # deduplicate, preserve order


# ── Typed config objects ────────────────────────────────────────────────────

@dataclass
class CompartmentConfig:
    name: str
    permissions: List[str] = field(default_factory=lambda: ["fs_read", "fs_write", "fs_exec"])
    filesystem: str = "workspace"
    network: str = "restricted"
    execute: bool = True


@dataclass
class AgentConfig:
    name: str
    compartment: str = "default"
    extra_env: Dict[str, str] = field(default_factory=dict)


@dataclass
class WorkflowNodeConfig:
    name: str
    type: str = "process"         # "agent" | "process" | "service"
    command: str = ""
    compartment: str = "default"
    depends_on: List[str] = field(default_factory=list)


@dataclass
class WorkflowConfig:
    name: str
    nodes: List[WorkflowNodeConfig] = field(default_factory=list)


@dataclass
class WorkspaceConfig:
    compartments: Dict[str, CompartmentConfig] = field(default_factory=dict)
    agents: Dict[str, AgentConfig] = field(default_factory=dict)
    workflows: Dict[str, WorkflowConfig] = field(default_factory=dict)

    def compartment_for_agent(self, agent_name: str) -> CompartmentConfig:
        """Return the CompartmentConfig the agent should run in."""
        agent_cfg = self.agents.get(agent_name)
        compartment_name = agent_cfg.compartment if agent_cfg else "default"
        return self.compartments.get(compartment_name, _default_compartment())

    def policy_for_agent(self, agent_name: str) -> Dict[str, Any]:
        comp = self.compartment_for_agent(agent_name)
        return {"permissions": comp.permissions}


def _default_compartment() -> CompartmentConfig:
    return CompartmentConfig(
        name="default",
        permissions=["fs_read", "fs_write", "fs_exec"],
        filesystem="workspace",
        network="restricted",
    )


def _default_config() -> WorkspaceConfig:
    return WorkspaceConfig(
        compartments={"default": _default_compartment()},
        agents={},
        workflows={},
    )


# ── Loader ──────────────────────────────────────────────────────────────────

def load_config(config_path: Optional[str] = None) -> WorkspaceConfig:
    """Load `.compart/config.yaml`.  Returns safe defaults when not found."""
    if config_path is None:
        config_path = os.path.join(".compart", "config.yaml")

    if not os.path.exists(config_path):
        return _default_config()

    if not _YAML_AVAILABLE:
        warnings.warn(
            "PyYAML is not installed. Install it with `pip install pyyaml` "
            "to use .compart/config.yaml. Falling back to default policy.",
            RuntimeWarning,
            stacklevel=2,
        )
        return _default_config()

    with open(config_path, encoding="utf-8") as f:
        raw: Dict[str, Any] = yaml.safe_load(f) or {}

    compartments: Dict[str, CompartmentConfig] = {}
    for cname, cdata in (raw.get("compartments") or {}).items():
        if not isinstance(cdata, dict):
            continue
        fs = cdata.get("filesystem", "workspace")
        net = cdata.get("network", "restricted")
        exe = cdata.get("execute", True)
        compartments[cname] = CompartmentConfig(
            name=cname,
            filesystem=fs,
            network=net,
            execute=exe,
            permissions=_resolve_permissions(fs, net, exe),
        )
    if "default" not in compartments:
        compartments["default"] = _default_compartment()

    agents: Dict[str, AgentConfig] = {}
    for aname, adata in (raw.get("agents") or {}).items():
        if not isinstance(adata, dict):
            continue
        agents[aname] = AgentConfig(
            name=aname,
            compartment=adata.get("compartment", "default"),
            extra_env=adata.get("env") or {},
        )

    def _parse_workflow_data(name: str, data: Any) -> Optional[WorkflowConfig]:
        if not isinstance(data, dict):
            return None
        nodes: List[WorkflowNodeConfig] = []
        if "nodes" in data and isinstance(data["nodes"], dict):
            for nname, ndata in data["nodes"].items():
                if not isinstance(ndata, dict):
                    continue
                nodes.append(WorkflowNodeConfig(
                    name=nname,
                    type=ndata.get("type", "process"),
                    command=ndata.get("command", ""),
                    compartment=ndata.get("compartment", "default"),
                    depends_on=ndata.get("depends_on") or [],
                ))
        elif "steps" in data and isinstance(data["steps"], list):
            for sdata in data["steps"]:
                if not isinstance(sdata, dict):
                    continue
                sname = sdata.get("name") or sdata.get("id") or f"step_{len(nodes)+1}"
                nodes.append(WorkflowNodeConfig(
                    name=sname,
                    type=sdata.get("type", "process"),
                    command=sdata.get("command", ""),
                    compartment=sdata.get("compartment", "default"),
                    depends_on=sdata.get("depends_on") or [],
                ))
        return WorkflowConfig(name=name, nodes=nodes)

    workflows: Dict[str, WorkflowConfig] = {}
    for wname, wdata in (raw.get("workflows") or {}).items():
        wf = _parse_workflow_data(wname, wdata)
        if wf:
            workflows[wname] = wf

    ws_root = os.path.dirname(os.path.dirname(os.path.abspath(config_path)))
    wf_dir = os.path.join(ws_root, "workflows")
    if os.path.isdir(wf_dir) and _YAML_AVAILABLE:
        for fname in sorted(os.listdir(wf_dir)):
            if fname.endswith((".yaml", ".yml")):
                wname = os.path.splitext(fname)[0]
                try:
                    with open(os.path.join(wf_dir, fname), encoding="utf-8") as wf_file:
                        wf_raw = yaml.safe_load(wf_file) or {}
                    declared_name = wf_raw.get("name") or wname
                    wf = _parse_workflow_data(declared_name, wf_raw)
                    if wf:
                        workflows[declared_name] = wf
                        if declared_name != wname:
                            workflows[wname] = wf
                except Exception as exc:
                    warnings.warn(
                        f"Failed to parse workflow file workflows/{fname}: {exc}",
                        RuntimeWarning,
                        stacklevel=2,
                    )

    return WorkspaceConfig(
        compartments=compartments,
        agents=agents,
        workflows=workflows,
    )


def is_compart_workspace(path: Optional[str] = None) -> bool:
    """Return True if *path* (or cwd) is inside a Compart workspace."""
    check = os.path.abspath(path or ".")
    while True:
        if os.path.isdir(os.path.join(check, ".compart")):
            return True
        parent = os.path.dirname(check)
        if parent == check:
            return False
        check = parent


def find_workspace_root(path: Optional[str] = None) -> Optional[str]:
    """Walk up the directory tree looking for a .compart/ directory."""
    check = os.path.abspath(path or ".")
    while True:
        if os.path.isdir(os.path.join(check, ".compart")):
            return check
        parent = os.path.dirname(check)
        if parent == check:
            return None
        check = parent
