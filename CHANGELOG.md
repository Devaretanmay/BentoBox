# Changelog

All notable changes to BentoBox are documented here.

## [0.9.1] - 2026-07-31

### Fixed

- **CLI: `bentoworks run` now prints command output.** The compartment
  function returned a `subprocess.CompletedProcess` while the CLI only
  printed dict results, so `stdout`/`stderr` were silently swallowed. The
  CLI now captures and prints `Stdout:`/`Stderr:` blocks after the run
  summary.
- **CLI: non-zero command exit codes now surface.** `bentoworks run "exit 3"`
  previously reported `Status: success`; the CLI now exits with status `1`
  when the shell command fails.
- **Credential proxy: absolute-form (`HTTP_PROXY`) requests now get
  credential-injected.** Route matching now uses the path component of the
  request target, so both origin-form (`/openai/v1/chat`) and absolute-form
  (`http://host/openai/v1/chat`, as sent by `HTTP_PROXY` clients) are
  matched and rewritten. Query strings survive the rewrite.
- **TypeScript SDK: fixed compile error.** `Runtime::names()` in the napi
  wrapper called a method that had been removed from the Rust `Runtime`
  struct; the `names()` method was restored, so `npm run build` and
  `npm test` pass again.

### Changed

- **Docs restyled.** The README and SDK docs now follow the structure used
  by top YC developer-tool projects: a one-line value proposition, an
  above-the-fold quickstart, a "Why" section, a feature table, and a
  professional footer. The stale `bentoworks.runtime` import in the
  "Advanced Users" example was replaced with the correct
  `bentoworks.compartments` subclass pattern.
- **Tests import the installed package.** The pytest `pythonpath = ["python"]`
  config was removed because the source tree no longer contains a compiled
  native core (`_core` ships inside the wheel). Install the package
  (`pip install .`) before running the test suite.
- **Test isolation.** `Box.enter()` calls in the box-lifecycle tests now pass
  `sandbox=False`, so the irreversible kernel Seatbelt sandbox is no longer
  applied to the shared pytest process (which poisoned `os.getcwd()` for
  later tests).

### Added

- `tests/test_cli.py` - CLI regression tests (stdout/stderr printing, exit
  codes, `goal` positional, `why`).
- `tests/test_proxy.py` - credential proxy regression tests (origin-form,
  absolute-form, no-match pass-through, query preservation).

### Verified

- Python: 73 tests pass (installed wheel).
- Rust core: 425 tests pass.
- Go SDK: `go vet` clean, 15 tests pass.
- TypeScript SDK: builds and all smoke tests pass.
