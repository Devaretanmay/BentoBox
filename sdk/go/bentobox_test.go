package bentobox

import (
	"strings"
	"testing"
)

func TestVersion(t *testing.T) {
	v := Version()
	if v == "" {
		t.Fatal("expected a non-empty version")
	}
	t.Logf("core version: %s", v)
}

func TestSandboxSupported(t *testing.T) {
	// Should return a bool without error; macOS/Linux report true.
	_ = SandboxSupported()
}

func TestCompress(t *testing.T) {
	content := strings.Repeat("the quick brown fox jumps over the lazy dog. ", 10)
	out, err := Compress(content)
	if err != nil {
		t.Fatalf("Compress failed: %v", err)
	}
	if out == "" {
		t.Fatal("expected non-empty compressed output")
	}
	t.Logf("compressed %d bytes -> %d bytes", len(content), len(out))
}

func TestSandboxWhy(t *testing.T) {
	reason, err := SandboxWhy("/etc/passwd", "/tmp/work", true)
	if err != nil {
		t.Fatalf("SandboxWhy failed: %v", err)
	}
	if !strings.Contains(strings.ToLower(reason), "blocked") {
		t.Logf("note: reason did not mention 'blocked': %s", reason)
	}
}

func TestSandboxWhyEmptyPath(t *testing.T) {
	// Empty path is a valid non-null C string; the assertion is simply that
	// the call returns without crashing or panicking across the FFI boundary.
	_, err := SandboxWhy("", "/tmp/work", true)
	_ = err // either an explanation or an error is acceptable
}
