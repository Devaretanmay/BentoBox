"""Controlled recreation of an autonomous agent attempting environment escape.

Demonstrates how Compart neutralizes the blast radius of an uncontained agent.
"""

import os
import subprocess
from compart import AgentCompart, Compartment
from compart.compartments import CompartmentConfig

print("=== Compart Security Boundary Demo ===")

def untrusted_agent_behavior(ctx):
    print("1. Inspecting workspace...")
    print("   [OK] Workspace file access allowed.")

    print("\n2. Attempting path traversal to access host credentials...")
    try:
        with open(os.path.expanduser("~/.ssh/id_rsa"), "r") as f:
            print("   [EXPLOIT SUCCESSFUL]")
    except Exception as exc:
        print(f"   [BLOCKED BY KERNEL SANDBOX]: {exc}")

    print("\n3. Attempting command execution...")
    try:
        subprocess.run(["python3", "-c", "print('Executing arbitrary shell')"], check=True)
    except Exception as exc:
        print(f"   [BLOCKED BY PERMISSION POLICY]: {exc}")

compart = AgentCompart(workdir=".")
compart.add(Compartment(
    name="AgentResearch",
    fn=untrusted_agent_behavior,
    config=CompartmentConfig(permissions=["fs_read"])
))

compart.run()
