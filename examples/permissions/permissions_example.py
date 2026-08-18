"""Example demonstrating granular per-compartment permission enforcement."""

import os
from compart import AgentCompart, Compartment
from compart.compartments import CompartmentConfig

compart = AgentCompart(workdir=".")

def restricted_fs_action(ctx):
    print("Trying to read SSH credentials...")
    try:
        with open(os.path.expanduser("~/.ssh/id_rsa"), "r") as f:
            print("Access granted:", f.read(10))
    except Exception as exc:
        print("BLOCKED BY KERNEL SANDBOX:", exc)

compart.add(Compartment(
    name="RestrictedUnit",
    fn=restricted_fs_action,
    config=CompartmentConfig(permissions=["fs_read"])
))

compart.run()
