# Compart API Reference & Documentation Map

**Version:** 1.0.4  
**Package:** `compart` (PyPI)

---

## 1. Documentation Index

- **[Quickstart Guide](QUICKSTART.md)**: 2-minute quickstart guide for CLI and Python workflows.
- **[CLI Reference Guide](CLI.md)**: Complete guide to the frozen public CLI contract (`init`, `status`, `inspect`, `claude`, `opencode`, `codex`, `cursor`, `aider`, `exec`, `-w`, `step`, `--run`, `diff`, `apply`, `commit`, `undo`, `restore`).
- **[Agent Execution & TUI Supervision](AGENT_EXECUTION.md)**: Details on PTY terminal supervision, interactive coding agents, and kernel isolation.
- **[Framework Integration Hooks](FRAMEWORK_HOOKS.md)**: Drop-in sandboxing for LangGraph, LangChain, CrewAI, and AutoGen.
- **[Zero-Trust Credential Proxy](CREDENTIAL_PROXY.md)**: Safe API key injection and request routing without exposing raw secrets.
- **[BLAKE3 Snapshots & Rollback](SNAPSHOTS.md)**: Fast workspace hashing, diff tracking, and physical restoration with `compart undo`.
- **[Output Compression & Token Crushing](COMPRESSION.md)**: High-speed Rust token reduction engines (`SmartCrusher`, `LogCompressor`, `DiffCompressor`).
- **[TypeScript & Node.js SDK](TYPESCRIPT_SDK.md)**: Native NAPI-RS bindings and TypeScript API reference.
- **[CI/CD Security Integration](CI_INTEGRATION.md)**: GitHub Actions and CI runner drop-in step isolation.
- **[Use Cases & Working Examples](USE_CASES.md)**: Practical security scenarios, prompt injection defense, and REPL sandboxing patterns.

---

## 2. Core Python SDK Classes

### `Compart(workdir=".", config=None, verbose=False)`
Base compartment container for custom agent pipelines.
- `add(compartment: Compartment) -> Compart`: Register an inner isolated compartment.
- `edge(from_name: str, to_name: str) -> Compart`: Wire a directional dependency/communication path.
- `register_module(module_cls) -> Compart`: Register an optional behavior module.
- `run(entry=None, request="") -> CompartResult`: Execute the topology under OS kernel isolation.

### `AgentCompart(workdir=".", config=None, verbose=False)`
Agent-oriented outer compartment container. Automatically loads standard behavior modules (Credential Proxy, Snapshots, Compression).

### `Compartment(name, fn=None, config=None)`
An individual unit of work executed in a specific kernel sandbox.
- `deliver(message: Message)`: Queue an inbound message.
- `receive() -> list[Message]`: Retrieve pending messages.
- `run(ctx: CompartmentContext)`: Execute compartment logic.

### `CompartmentConfig`
Configuration dataclass defining isolation rules:
- `permissions`: List of permissions (`"fs_read"`, `"fs_write"`, `"fs_exec"`, `"network"`).
- `filesystem`: Filesystem access mode (`"workspace"`, `"read-only"`, `"read-write"`, `"blocked"`).
- `network`: Network mode (`"allowed"`, `"restricted"`, `"blocked"`).
- `timeout_s`: Hard execution timeout in seconds.
- `allow_inbound_from`: Allowed source compartment names (`["*"]` for all).
- `allow_outbound_to`: Allowed target compartment names (`["*"]` for all).

### `RouteConfig`
Credential proxy routing rule:
- `prefix`: Path prefix to intercept (e.g. `"/openai"`).
- `upstream`: Target base URL (e.g. `"https://api.openai.com"`).
- `header`: Header name to inject (default `"Authorization"`).
- `format`: Format template (default `"Bearer {credential}"`).
- `credential_source`: Environment variable name (e.g. `"env:OPENAI_API_KEY"`).

### `SandboxRunner(workdir=".", verbose=False, block_network=False)`
Low-level process execution runner that applies kernel sandbox (Seatbelt / Landlock) to shell commands and captures file diffs.
- `run(command: str, permissions=None, env=None) -> ExecutionResult`
- `run_code(code: str, language="python", permissions=None, env=None) -> ExecutionResult`
