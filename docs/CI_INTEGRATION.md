# BentoBox CI/CD Drop-In Security & Acceleration Guide

> **Transform any existing CI/CD pipeline into a sub-millisecond, OS kernel-enforced execution engine with zero infrastructure costs.**

---

## 1. Zero Infrastructure & $0.00 Cost Model

BentoBox CI integration requires **no managed infrastructure, no paid runner services, no Docker daemons, and no cloud subscriptions**.

- **Uses OS Kernel Primitives**: Sandboxing is enforced natively by Linux **Landlock** (kernel ≥ 5.13) and macOS **Seatbelt** (`sandbox_init()`), which ship built-in with standard CI runners (e.g. GitHub Actions `ubuntu-latest`).
- **Daemonless Execution**: Sandboxing rules apply directly at the process level in **< 1ms**.
- **Total Cost**: **$0.00**.

---

## 2. Drop-In Integration Options

### Option A: GitHub Actions 1-Line Setup (`action.yml`)

Add `uses: bentoworks/setup@v1` at the top of your steps:

```yaml
name: CI Pipeline

on: [push, pull_request]

jobs:
  test-and-build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      # 1-Line Drop-In: Installs and configures kernel-sandbox defaults
      - uses: bentoworks/setup@v1
        with:
          network: 'false'  # Block untrusted PR network exfiltration

      # Run your standard commands inside the kernel sandbox:
      - run: python3 -m bentoworks.ci.runner "pytest"
      - run: python3 -m bentoworks.ci.runner "npm run build"
```

---

### Option B: The 1-Word Command Prefix (`bento`)

For **Jenkins**, **GitLab CI**, **CircleCI**, or **Bitbucket Pipelines**, prefix existing step commands with `bento`:

```bash
# BEFORE (Unsandboxed CI step):
npm test
pytest

# AFTER (1-Word Prefix — Kernel Sandboxed & Accelerated):
bento npm test
bento pytest
```

---

## 3. Speed & Security Benchmarks

| Metric | Traditional Docker / MicroVM CI | BentoBox Accelerated CI |
| :--- | :--- | :--- |
| **Stage Startup Boot Time** | ~5,000ms – 30,000ms | **< 1ms** (Kernel syscall enforcement) |
| **Workspace Reset Time** | ~3,000ms – 10,000ms (Container rebuild) | **< 100ms** (BLAKE3 Hash Rollback) |
| **Network Security** | Open Egress (High exfiltration risk) | **Blocked per-stage by OS kernel** |
| **Secret Theft Protection** | Vulnerable to malicious PR scripts | **Protected by deny-by-default rules** |
| **Infrastructure Cost** | Paid Runner / VM scaling | **$0.00 (Native Runner Execution)** |
