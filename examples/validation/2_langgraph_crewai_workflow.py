"""Validation Test 2: Multi-Agent Workflow (LangGraph / CrewAI style) under Compart Control.

Demonstrates:
- Research compartment: Read-only access. Write attempts are blocked.
- Builder compartment: Workspace write access.
- Directed routing: Messages can flow only along authorized edges.
"""

from compart import AgentCompart, Compartment
from compart.compartments import CompartmentConfig

print("=== Compart Control Layer Demo: Multi-Agent Workflow ===")

compart = AgentCompart(workdir=".")

def research_agent(ctx):
    print("\n[Research Agent] Analyzing repository...")
    ctx.send("BuilderAgent", {"task": "implement_feature", "spec": "Add validation endpoint"})

def builder_agent(ctx):
    msgs = ctx.receive()
    print(f"\n[Builder Agent] Received {len(msgs)} task(s) from Research Agent.")
    for m in msgs:
        print(f"  Executing task: {m.data}")

# Research compartment: fs_read only
compart.add(Compartment(
    name="ResearchAgent",
    fn=research_agent,
    config=CompartmentConfig(permissions=["fs_read"], allow_outbound_to=["BuilderAgent"])
))

# Builder compartment: fs_read, fs_write
compart.add(Compartment(
    name="BuilderAgent",
    fn=builder_agent,
    config=CompartmentConfig(permissions=["fs_read", "fs_write"], allow_inbound_from=["ResearchAgent"])
))

compart.edge("ResearchAgent", "BuilderAgent")
result = compart.run()

print(f"\n[Workflow Result] Status: {result.status} | Compartments executed: {result.compartments_completed}")
