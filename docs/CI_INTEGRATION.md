# Compart CI/CD Drop-In Security & Acceleration Guide

> Run CI steps with local OS-kernel controls and no separate service or daemon.

---

## 1. Zero Infrastructure & $0.00 Cost Model

Compart CI integration requires **no managed infrastructure, no paid runner services, no Docker daemons, and no cloud subscriptions**.

- **Uses OS Kernel Primitives**: Sandboxing is enforced natively by Linux **Landlock** (kernel ≥ 5.13) and macOS **Seatbelt** (`sandbox_init()`), which ship built-in with standard CI runners (e.g. GitHub Actions `ubuntu-latest`).
- **Daemonless Execution**: Sandboxing rules apply directly at the process level; measure startup on your runner.
- **Total Cost**: No Compart service fee; normal CI runner costs still apply.

---

## 2. Drop-In Integration Options

### Option A: GitHub Actions 1-Line Setup (`action.yml`)

Add the repository action at the top of your steps:

```yaml
name: CI Pipeline

on: [push, pull_request]

jobs:
  test-and-build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      # 1-Line Drop-In: Installs and configures kernel-sandbox defaults
      - uses: Devaretanmay/Compart@main
        with:
          network: 'false'  # Block untrusted PR network exfiltration

      # Run your standard commands inside the kernel sandbox:
      - run: python3 -m compart.ci.runner "pytest"
      - run: python3 -m compart.ci.runner "npm run build"
```

---

### Option B: Run the module directly

For **Jenkins**, **GitLab CI**, **CircleCI**, or **Bitbucket Pipelines**, invoke the runner module explicitly:

```bash
# BEFORE (Unsandboxed CI step):
npm test
pytest

# AFTER (1-Word Prefix — Kernel Sandboxed & Accelerated):
python3 -m compart.ci.runner "npm test"
python3 -m compart.ci.runner "pytest"
```

---

## 3. Speed & Security Benchmarks

| Metric | Traditional Docker / MicroVM CI | Compart Accelerated CI |
| :--- | :--- | :--- |
| **Stage Startup Boot Time** | ~5,000ms – 30,000ms | Depends on runner, Python, and repository size |
| **Workspace Reset** | Container rebuild or external reset | BLAKE3 snapshot/restore; measure on your repository |
| **Network Security** | Open Egress (High exfiltration risk) | TCP egress blocked where supported by the OS |
| **Secret Theft Protection** | Vulnerable to malicious PR scripts | **Protected by deny-by-default rules** |
| **Infrastructure Cost** | Paid Runner / VM scaling | No additional Compart service |
