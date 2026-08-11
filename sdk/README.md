# Compart SDKs

**One Rust core, two thin language wrappers.**

Compart implements kernel sandboxing, output compression, and the
compartment runtime once in Rust. The Python and TypeScript SDKs expose the
supported native bindings directly:

```
compart-core (Rust)
 |-- pyo3 module  (compart._core)     -> Python SDK (published on PyPI)
 `-- napi crate   (sdk/typescript/native) -> TypeScript SDK (Node addon)
```

## Prerequisites

All SDKs require the Rust core built once (from the repository root):

```bash
cargo build --release
```

This produces `target/release/libcompart_core.dylib`/`.so`, and the
rlib used by the napi crate.

## TypeScript SDK: `sdk/typescript/`

The package is built from this repository. Publish it only after the platform
packages have been built and uploaded at the same version:

```bash
cd sdk/typescript
npm install
npm run build   # compiles the napi addon (compart-native.<platform>-<arch>.node)
npm test
```

```ts
import * as compart from '@compart/sdk'

compart.version()                    // "0.9.4"
compart.sandboxSupported()           // true
const out = compart.compress(text)

// Compartment runtime handle (parse once, route many).
// configs: { configs: [{ name: 'a', allow_outbound_to: ['b'] }, { name: 'b' }] }
// edgesJSON: '[['a','b']]'
const rt = new compart.Runtime(configs, edgesJSON)
rt.canRoute('a', 'b')        // true
rt.runOrder()                // ['a', 'b', ...]
rt.names()                   // ['a', 'b', ...]
```

## Python SDK: `python/compart/`

Published on PyPI as `compart` — the same kernel-enforced isolation,
compartments, snapshots, and credential proxy, callable from Python 3.10+:

```bash
pip install compart
```

```python
from compart import Compart
```

## Notes

- Native sandbox application is **irreversible** for the process lifetime.
- The TypeScript SDK's `Runtime` handle (and the Rust core's `names()`
  method) is exercised by `npm test`.
- The Rust core, Python package, TypeScript package, platform packages, and
  napi crate are kept in lockstep at `0.9.4`.
