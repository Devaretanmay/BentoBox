.PHONY: test test-rust test-python

# Run the complete local validation suite after making a change.
test: test-rust test-python

test-rust:
	cargo test --all-targets

test-python:
	PYTHONPATH=python python3 -m pytest tests/ -q
