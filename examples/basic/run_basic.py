"""Basic example of running code inside a Compart sandbox."""

from compart import Compart, Compartment
from compart.compartments import CompartmentConfig

compart = Compart(workdir=".")

compart.add(Compartment(
    name="simple_task",
    fn=lambda ctx: print("Hello from basic sandboxed compartment!"),
    config=CompartmentConfig(permissions=["fs_read"])
))

result = compart.run()
print(f"Status: {result.status}")
