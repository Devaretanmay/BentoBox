"""Basic example of running code inside a Compart sandbox."""

from compart import Compart, Compartment
from compart.compartments import CompartmentConfig

# Initialize outer container
compart = Compart(workdir=".")

# Register a basic compartment
compart.add(Compartment(
    name="simple_task",
    fn=lambda ctx: print("Hello from basic sandboxed compartment!"),
    config=CompartmentConfig(permissions=["fs_read"])
))

# Execute
result = compart.run()
print(f"Status: {result.status}")
