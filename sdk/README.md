# BentoBox SDKs

BentoBox's Rust core (`bentoworks-core`) is the single source of truth for
kernel sandboxing and output compression. Every language SDK is a thin
wrapper over that core, mirroring Nono's `core → C ABI → per-language SDK`
architecture.

```
bentoworks-core (Rust)
 ├── C ABI        (include/bentobox.h)   → Go SDK (cgo), C, any FFI
 ├── pyo3 module  (bentoworks._core)     → Python SDK (published on PyPI)
 └── napi crate   (sdk/typescript/native) → TypeScript SDK (Node addon)
```

## The stable C ABI

Declared in [`include/bentobox.h`](../include/bentobox.h):

| Function | Purpose |
| --- | --- |
| `bentobox_version()` | Core version string |
| `bentobox_sandbox_supported()` | 1 if kernel sandboxing is available |
| `bentobox_sandbox_apply(path, block_network)` | Apply sandbox (irreversible) |
| `bentobox_sandbox_why(path, worktree, block_network)` | Explain a block |
| `bentobox_compress(content)` | Smart-crush output text |
| `bentobox_last_error()` | Last error message |
| `bentobox_free(ptr)` | Free any string returned by this API |

**Ownership rule:** every string returned by the API is allocated by Rust and
must be freed with `bentobox_free()`. All functions are panic-safe
(`catch_unwind`) and never unwind across the FFI boundary.

## Prerequisites

All SDKs require the Rust core built once (from the repository root):

```bash
cargo build --release
```

This produces `target/release/libbentoworks_core.a` (Go static linking),
`.dylib`/`.so`, and the rlib used by the napi crate.

## Go SDK — `sdk/go/`

```bash
cd sdk/go
make test      # builds core, runs go vet + go test
```

```go
import "github.com/Devaretanmay/BentoBox/sdk/go" // package bentobox

v := bentobox.Version()                 // "0.9.0"
ok := bentobox.SandboxSupported()       // true on macOS/Linux
compressed, _ := bentobox.Compress(text)
reason, _ := bentobox.SandboxWhy("/etc/passwd", "/tmp/work", true)
err := bentobox.SandboxApply("/path/to/work", true) // irreversible!
```

## TypeScript SDK — `sdk/typescript/`

```bash
cd sdk/typescript
npm install
npm run build   # compiles the napi addon (bentoworks-native.<platform>-<arch>.node)
npm test
```

```ts
import { version, sandboxSupported, compress, sandboxWhy } from '@bentobox/sdk'

version()                    // "0.9.0"
sandboxSupported()           // true
const out = compress(text)
const why = sandboxWhy('/etc/passwd', '/tmp/work', true)
```

## Python SDK — `python/bentoworks/`

Published on PyPI as `bentoworks`:

```bash
pip install bentoworks
```

```python
from bentoworks import BentoBox
```

## Notes

- `bentobox_sandbox_apply` is **irreversible** for the process lifetime —
  no SDK test calls it; it is exercised only through the Python
  `Box.enter(sandbox=...)` path.
- The crate version (`Cargo.toml`) and the Python package version
  (`pyproject.toml`) are kept in lockstep at `0.9.0` so
  `bentobox_version()` is consistent across all SDKs.
