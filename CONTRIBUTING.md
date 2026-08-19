# Contributing to Compart

We welcome contributions to the Compart source-available runtime!

## Licensing & License Agreement

By contributing to Compart, you agree that your contributions will be licensed under the [Elastic License 2.0 (ELv2)](LICENSE).

## Development Setup

1. **Prerequisites**: Python >= 3.10, Rust >= 1.75, `maturin` (`pip install maturin`).
2. **Build Native Extension**:
   ```bash
   maturin develop
   ```
3. **Run Tests**:
   ```bash
   python3 -m pytest
   ```

## Pull Request Guidelines

- Ensure all existing unit and E2E tests pass.
- Write unit tests for new features or bug fixes.
- Keep changes focused, surgical, and well-documented.
