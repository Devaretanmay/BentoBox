"""Example demonstrating inter-compartment message passing."""

from compart import AgentCompart, Compartment
from compart.compartments import CompartmentConfig

compart = AgentCompart(workdir=".")

def sender_fn(ctx):
    print("[Sender] Dispatching task payload to Receiver...")
    ctx.send("Receiver", {"task": "analyze_log", "target": "app.log"})

def receiver_fn(ctx):
    msgs = ctx.messages
    print(f"[Receiver] Received {len(msgs)} message(s):")
    for m in msgs:
        print(f"  From: {m.from_} | Data: {m.data}")

compart.add(Compartment(
    name="Sender",
    fn=sender_fn,
    config=CompartmentConfig(permissions=["fs_read"], allow_outbound_to=["Receiver"])
))

compart.add(Compartment(
    name="Receiver",
    fn=receiver_fn,
    config=CompartmentConfig(permissions=["fs_read"], allow_inbound_from=["Sender"])
))

compart.edge("Sender", "Receiver")
compart.run()
