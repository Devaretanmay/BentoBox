# Compart v1.0.0 Documentation Map & API Reference

Welcome to the official Compart documentation.

---

## 1. Documentation Index

- **[Quickstart Guide](QUICKSTART.md)**: 2-minute quickstart guide for CLI and Python SDK.
- **[Declarative CLI Guide](CLI.md)**: Infrastructure-as-Code workflow, `.compart/topology.json` schema, and Git PR security reviews.
- **[Framework Integration Hooks](FRAMEWORK_HOOKS.md)**: Drop-in sandboxing for LangChain, LangGraph, CrewAI, AutoGen, and Data/RAG agents.
- **[Zero-Trust Credential Proxy](CREDENTIAL_PROXY.md)**: Path rewriting and secret masking for outbound LLM API requests.
- **[BLAKE3 Snapshots & Worktree Rollback](SNAPSHOTS.md)**: Fast workspace hashing, diff tracking, and differential file restoration.
- **[Output Crusher & Token Compression](COMPRESSION.md)**: Log crushing, JSON array compaction, and LLM token reduction.
- **[TypeScript & Node.js SDK](TYPESCRIPT_SDK.md)**: Native NAPI-RS bindings and TypeScript API reference.
- **[CI/CD Security & Acceleration](CI_INTEGRATION.md)**: GitHub Actions and CI runner security integration.
- **[Real-World Use Cases](USE_CASES.md)**: Practical security scenarios and agent sandboxing patterns.

---

## 2. Python SDK Core API Reference

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
