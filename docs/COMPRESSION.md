# Output Crusher & Token Compression Guide

Long execution logs, stack traces, and verbose build outputs can quickly overwhelm LLM context windows and increase API costs. Compart includes a native Rust compression engine that compresses agent outputs before returning them to LLM context.

---

## 1. Core Compression Engines

The Compart Rust core (`src/engines/compression/`) includes four specialized compression engines:

1. **BM25 & Log Crusher**: Filters repetitive log lines (e.g. build output loops, progress bars) while preserving error tracebacks, exceptions, and key status lines.
2. **Smart Crusher (JSON Compaction)**: Compacts large JSON arrays and API responses into key sample records and structural schemas.
3. **Diff Compressor**: Trims git diffs to show modified code sections while dropping unchanged context padding.
4. **Text Crusher**: Performs semantic sentence deduplication and token reduction.

---

## 2. Content-Addressable Compression Registry (CCR Cache)

To avoid re-compressing identical log outputs across agent loops, Compart caches compressed outputs in a Content-Addressable Compression Registry (CCR) using BLAKE3 content hashing.

---

## 3. Usage in Agent Workflows

```python
from compart.sandbox.compression import CompressionModule

crusher = CompressionModule()

verbose_log = """
[INFO] Step 1/100 complete
[INFO] Step 2/100 complete
... (95 identical lines) ...
[ERROR] FileNotFoundError: 'config.yaml' missing on line 42
"""

# Compress output for LLM context
compressed_text = crusher.compress(verbose_log, max_tokens=200)
print(compressed_text)
```

In `AgentCompart`, log crushing is enabled automatically on compartment outputs.
