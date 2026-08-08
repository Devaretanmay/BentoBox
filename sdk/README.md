# BentoBox SDKs

**One Rust core, two thin language wrappers.**

BentoBox implements kernel sandboxing, output compression, and the
compartment runtime once in Rust. Every language SDK is a thin wrapper over
that core, following a `core -> C ABI -> per-language SDK` layout — so the
same allow/deny decisions, snapshots, credential routing, and message routing
behave identically whether you call them from Python or TypeScript:

```
bentoworks-core (Rust)
 |-- C ABI        (include/bentobox.h)   -> C, any FFI
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

This produces `target/release/libbentoworks_core.dylib`/`.so`, and the
rlib used by the napi crate.

## TypeScript SDK: `sdk/typescript/`

Published on npm as `@bentwork/sdk`:

```bash
cd sdk/typescript
npm install
npm run build   # compiles the napi addon (bentoworks-native.<platform>-<arch>.node)
npm test
```

```ts
import * as bentobox from '@bentwork/sdk'

bentobox.version()                    // "0.9.2"
bentobox.sandboxSupported()           // true
const out = bentobox.compress(text)

// Compartment runtime handle (parse once, route many).
// configs: { configs: [{ name: 'a', allow_outbound_to: ['b'] }, { name: 'b' }] }
// edgesJSON: '[['a','b']]'
const rt = new bentobox.Runtime(configs, edgesJSON)
rt.canRoute('a', 'b')        // true
rt.runOrder()                // ['a', 'b', ...]
rt.names()                   // ['a', 'b', ...]
```

## Python SDK: `python/bentoworks/`

Published on PyPI as `bentoworks` — the same kernel-enforced isolation,
compartments, snapshots, and credential proxy, callable from Python 3.10+:

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
  method) is exercised by `npm test`.
- The crate version (`Cargo.toml`) and the Python package version
  (`pyproject.toml`) are kept in lockstep at `0.9.2` so
  `bentobox_version()` is consistent across all SDKs.
