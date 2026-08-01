# BentoBox SDKs

**One Rust core, three thin language wrappers.**

BentoBox implements kernel sandboxing, output compression, and the
compartment runtime once in Rust. Every language SDK is a thin wrapper over
that core, following a `core -> C ABI -> per-language SDK` layout:

```
bentoworks-core (Rust)
 |-- C ABI        (include/bentobox.h)   -> Go SDK (cgo), C, any FFI
 |-- pyo3 module  (bentoworks._core)     -> Python SDK (published on PyPI)
 `-- napi crate   (sdk/typescript/native) -> TypeScript SDK (Node addon)
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

## Go SDK: `sdk/go/`

```bash
cd sdk/go
make test      # builds core, runs go vet + go test
```

```go
import "github.com/Devaretanmay/BentoBox/sdk/go" // package bentobox

v := bentobox.Version()                 // "0.9.1"
ok := bentobox.SandboxSupported()       // true on macOS/Linux
compressed, _ := bentobox.Compress(text)
reason, _ := bentobox.SandboxWhy("/etc/passwd", "/tmp/work", true)
err := bentobox.SandboxApply("/path/to/work", true) // irreversible!
```

## TypeScript SDK: `sdk/typescript/`

```bash
cd sdk/typescript
npm install
npm run build   # compiles the napi addon (bentoworks-native.<platform>-<arch>.node)
npm test
```

```ts
import * as bentobox from '@bentobox/sdk'

bentobox.version()                    // "0.9.1"
bentobox.sandboxSupported()           // true
const out = bentobox.compress(text)
const why = bentobox.sandboxWhy('/etc/passwd', '/tmp/work', true)

// Compartment runtime handle (parse once, route many).
// configs: { configs: [{ name: 'a', allow_outbound_to: ['b'] }, { name: 'b' }] }
// edgesJSON: '[['a','b']]'
const rt = new bentobox.Runtime(configs, edgesJSON)
rt.canRoute('a', 'b')        // true
rt.runOrder()                // ['a', 'b', ...]
rt.names()                   // ['a', 'b', ...]
```

## Python SDK: `python/bentoworks/`

Published on PyPI as `bentoworks`:

```bash
pip install bentoworks
```

```python
from bentoworks import BentoBox
```

## Notes

- `bentobox_sandbox_apply` is **irreversible** for the process lifetime.
  No SDK test calls it; it is exercised only through the Python
  `Box.enter(sandbox=...)` path.
- The TypeScript SDK's `Runtime` handle (and the Rust core's `names()`
  method) is exercised by `npm test`; the Go `Runtime` handle is exercised
  by `go test`.
- The crate version (`Cargo.toml`) and the Python package version
  (`pyproject.toml`) are kept in lockstep at `0.9.1` so
  `bentobox_version()` is consistent across all SDKs.
