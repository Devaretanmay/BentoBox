.PHONY: test test-rust test-python build-dev

# Run the complete local validation suite after making a change.
test: test-rust test-python

build-dev:
	maturin develop

test-rust:
	cargo test --all-targets

test-python:
	python3 -m pytest tests/ -q

