# Compart v1.0.0 API Reference

Complete documentation for the Compart Python SDK, CLI, and TypeScript bindings.

---

## 1. Python SDK Reference

### `Compart(workdir=".", config=None, verbose=False)`
Base outer compartment container.
- `add(compartment: Compartment) -> Compart`: Register an inner compartment.
- `edge(from_name: str, to_name: str) -> Compart`: Wire a directional message path between two compartments.
- `register_module(module_cls) -> Compart`: Opt-in a behavior module (e.g., `CompressionModule`, `SnapshotModule`).
- `run(entry=None, request="") -> CompartResult`: Materialize the kernel sandbox and execute inner compartments.

### `AgentCompart(workdir=".", config=None, verbose=False)`
Agent-oriented outer compartment container. Auto-loads all behavior modules (Credential Proxy, Snapshots, Compression) by default.

### `Compartment(name, fn=None, config=None)`
Individual isolated execution unit inside an outer compartment.
- `deliver(message: Message)`: Deliver inbound message to inbox.
- `receive() -> list[Message]`: Read pending messages.
- `run(ctx: CompartmentContext)`: Execute compartment logic.

### `CompartmentConfig`
Configuration dataclass for an inner compartment.
- `permissions`: List of permissions (`"fs_read"`, `"fs_write"`, `"fs_exec"`, `"network"`).
- `timeout_s`: Hard execution timeout in seconds.
- `allow_inbound_from`: List of allowed source compartment names (`["*"]` for all).
- `allow_outbound_to`: List of allowed target compartment names (`["*"]` for all).

### `RouteConfig`
Credential proxy route rule.
- `prefix`: Path prefix to intercept (e.g. `"/openai"`).
- `upstream`: Target base URL (e.g. `"https://api.openai.com"`).
- `header`: Header name to inject (default `"Authorization"`).
- `format`: Format template (default `"Bearer {credential}"`).
- `credential_source`: Environment variable source (e.g. `"env:OPENAI_API_KEY"`).

---

## 2. CLI Reference (`compart`)

| Command | Usage | Description |
| :--- | :--- | :--- |
| `compart init` | `compart init` | Initialize `.compart/` project and `topology.json`. |
| `compart inspect` | `compart inspect [--json]` | View declared topology or dump JSON schema. |
| `compart compartment create` | `compart compartment create <name>` | Declare an inner compartment. |
| `compart connect` | `compart connect <src> <dst>` | Connect two declared compartments. |
| `compart run` | `compart run` | Materialize declared topology into kernel runtime. |
| `compart exec` | `compart exec -- <command>` | Ephemerally run a single command in a sandbox. |

---

## 3. Framework Hooks Reference

- **LangChain**: `from compart.hooks.langchain import CompartPythonREPLTool`
- **CrewAI**: `from compart.hooks.crewai import CompartCodeInterpreterTool`
- **AutoGen**: `from compart.hooks.autogen import CompartCodeExecutor`
- **DataAgent**: `from compart.hooks.data_agent import CompartDataScienceSandbox`

---

## 4. TypeScript SDK (Node.js)

```typescript
import { sandboxSupported, Runtime } from "@compart/sdk";

if (sandboxSupported()) {
  const runtime = new Runtime("./workspace");
  // Execute sandboxed JS/TS code...
}
```

> *Note: npm package `@compart/sdk` distribution pipeline is listed on the upcoming roadmap.*
