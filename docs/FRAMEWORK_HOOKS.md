# Compart Framework Integration Hooks

Run AI agent code inside kernel-enforced compartments from any major agent framework. Compart provides lightweight, drop-in tool wrappers for popular Python agent frameworks.

---

## 1. LangGraph Integration

Wrap any LangGraph node execution inside an isolated compartment:

```python
from compart.hooks import CompartGraphNode
from langgraph.graph import StateGraph, START, END

def data_processing_node(state, ctx):
    # This code executes inside an isolated kernel compartment
    with open(f"{ctx.workdir}/output.txt", "w") as f:
        f.write(state["value"].upper())
    return {"status": "complete"}

node = CompartGraphNode(data_processing_node, workdir=".")

builder = StateGraph(dict)
builder.add_node("process", node.attach(builder))
builder.add_edge(START, "process")
builder.add_edge("process", END)
```

---

## 2. LangChain Integration

Replace standard Python REPL tools with a kernel-enforced sandboxed version:

```python
from compart.hooks import CompartPythonREPLTool

# Create a sandboxed Python REPL tool
tool = CompartPythonREPLTool(permissions=["fs_read", "fs_write"])

# Execute agent-generated code safely
result = tool.invoke("print(21 * 2)")
print(result)
```

---

## 3. CrewAI Integration

Replace Docker-based code execution in CrewAI with native sub-millisecond Compart sandboxing:

```python
from crewai import Agent
from compart.hooks import CompartCodeInterpreterTool

# Initialize agent with Compart code interpreter
agent = Agent(
    role="Data Analyst",
    goal="Analyze logs safely",
    tools=[CompartCodeInterpreterTool(permissions=["fs_read"])]
)
```

---

## 4. AutoGen Integration

Sandbox multi-turn code block execution in AutoGen conversations:

```python
from compart.hooks import CompartCodeExecutor, CodeBlock

executor = CompartCodeExecutor(permissions=["fs_read", "fs_write", "fs_exec"])
result = executor.execute_code_blocks([
    CodeBlock("python", "print('Hello from AutoGen inside Compart')")
])

print(f"Exit code: {result.exit_code}")
print(f"Output: {result.output}")
```

---

## 5. Data Science & RAG Agent Integration

Mount read-only datasets, enforce default-deny network rules to prevent data exfiltration, and track pandas file diffs:

```python
from compart.hooks import DataScienceSandboxHook

hook = DataScienceSandboxHook(workdir=".")
hook.mount_dataset("sales_data.csv")

# Run agent analysis
result = hook.run("""
import pandas as pd
df = pd.read_csv('sales_data.csv')
print(f"Dataset shape: {df.shape}")
""")

print("File Diffs:", result.diffs)
```
