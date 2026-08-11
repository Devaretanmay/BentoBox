"""Nested multi-compartment execution example."""

from compart import AgentCompart, Compartment
from compart.compartments import CompartmentConfig

compart = AgentCompart(workdir=".")

# Compartment 1: Research
compart.add(Compartment(
    name="Research",
    fn=lambda ctx: print("Performing research phase..."),
    config=CompartmentConfig(permissions=["fs_read"])
))

# Compartment 2: Builder
compart.add(Compartment(
    name="Builder",
    fn=lambda ctx: print("Building code phase..."),
    config=CompartmentConfig(permissions=["fs_read", "fs_write", "fs_exec"])
))

# Wire directional edge
compart.edge("Research", "Builder")

result = compart.run()
print(f"Executed compartments: {result.compartments_completed}")
