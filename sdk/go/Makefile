# Build the BentoBox Rust core and run the Go SDK tests.
#
# The Go SDK links statically against libbentoworks_core.a, so the core
# must be built (from the repository root) before `go test` can link.

.PHONY: core test all clean

CORE_DIR := ../..

core:
	cd $(CORE_DIR) && cargo build --release

test: core
	go vet ./...
	go test -v ./...

all: test

clean:
	rm -rf bin *.test
