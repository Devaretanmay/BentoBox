"""Agent example using AgentCompart with automatic behaviour modules."""

from compart import AgentCompart, Compartment
from compart.compartments import CompartmentConfig

agent = AgentCompart(workdir=".")

def agent_action(ctx):
    print("Agent is reasoning and executing tools...")
    return {"status": "completed", "tokens_processed": 1024}

agent.add(Compartment(
    name="AgentTask",
    fn=agent_action,
    config=CompartmentConfig(permissions=["fs_read", "fs_write", "fs_exec"])
))

result = agent.run(request="Agent code execution task")
print(f"Result summary: {result.summary}")
