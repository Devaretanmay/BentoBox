# Compart Quickstart Guide

Get up and running with Compart in under 2 minutes.

---

## 1. Installation

Install Compart via PyPI:

```bash
pip install compart
```

---

## 2. Using the Declarative CLI

The Compart CLI provides an Infrastructure-as-Code workflow for configuring and materializing isolated agent sandboxes.

### Step 1: Initialize a Compart Project
```bash
mkdir my-agent && cd my-agent
compart init
```
This creates a `.compart/` control-plane directory containing `topology.json`.

### Step 2: Declare Compartments & Permission Rules
```bash
# Add a compartment for agent reasoning & research
compart compartment create Research

# Add a compartment for running builds
compart compartment create Builder

# Wire a communication path from Research to Builder
compart connect Research Builder
```

### Step 3: Inspect the Declared Topology
```bash
compart inspect
```

You can view the raw JSON topology (versionable in Git) anytime:
```bash
compart inspect --json
```

### Step 4: Materialize and Run
```bash
compart run
```
Compart materializes `topology.json` into an ephemeral OS-level kernel sandbox (macOS Seatbelt / Linux Landlock), executes the workload, and tears down the environment.

---

## 3. Quick Ephemeral Execution (`compart exec`)

Need to run a quick script safely inside a kernel sandbox without creating a project?

```bash
compart exec -- python3 -c "print('Running safely inside kernel sandbox')"
```

If the script tries to access `~/.ssh` or unauthorized paths, the kernel blocks it instantly!

---

## 4. Using the Python SDK

Integrate Compart directly into your AI application code:

```python
from compart import Compartment, AgentCompart, CompartConfig
from compart.compartments import CompartmentConfig

# Initialize the agent container
agent = AgentCompart(workdir=".")

# Define an inner compartment with restricted permissions
agent.add(Compartment(
    name="Researcher",
    fn=lambda ctx: print("Researching safely..."),
    config=CompartmentConfig(permissions=["fs_read"])
))

# Execute the container
result = agent.run()
print(f"Status: {result.status}")
```

---

## 5. Security Principles

- **Deny-by-Default**: Filesystem paths outside your `workdir` and network access are blocked by default.
- **Zero-Docker**: Operates natively on OS kernel primitives with sub-millisecond overhead.
- **Git Security Reviews**: Your `.compart/topology.json` file is checked into Git so `git diff` highlights security permission expansions during PR code reviews.
