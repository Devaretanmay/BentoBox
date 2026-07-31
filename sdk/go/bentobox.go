// Package bentobox is the Go SDK for the BentoBox kernel sandbox.
//
// It wraps the stable C ABI of the BentoBox Rust core (bentoworks-core)
// through cgo. The native library is linked statically from
// ../../target/release/libbentoworks_core.a — build it first with:
//
//	cargo build --release   (from the repository root)
package bentobox

/*
#cgo CFLAGS: -I${SRCDIR}/../../include
#cgo LDFLAGS: ${SRCDIR}/../../target/release/libbentoworks_core.a -lpthread -ldl -lm
#include <stdlib.h>
#include <bentobox.h>
*/
import "C"

import (
	"errors"
	"unsafe"
)

// Version returns the version of the native core library.
func Version() string {
	ptr := C.bentobox_version()
	if ptr == nil {
		return ""
	}
	defer C.bentobox_free(ptr)
	return C.GoString(ptr)
}

// SandboxSupported reports whether kernel sandboxing is available on this platform.
func SandboxSupported() bool {
	return C.bentobox_sandbox_supported() == 1
}

// SandboxApply applies the kernel sandbox to the current process tree,
// restricting access to worktreePath (plus system essentials).
// This is irreversible for the lifetime of the process.
func SandboxApply(worktreePath string, blockNetwork bool) error {
	cPath := C.CString(worktreePath)
	defer C.free(unsafe.Pointer(cPath))
	block := int32(0)
	if blockNetwork {
		block = 1
	}
	rc := C.bentobox_sandbox_apply(cPath, C.int(block))
	if rc == 0 {
		return nil
	}
	if rc == -2 {
		return errors.New("bentobox: panic while applying sandbox")
	}
	return lastError()
}

// SandboxWhy explains why path (file or tcp:/udp: address) would be
// blocked by the sandbox rules for worktreePath.
func SandboxWhy(path, worktreePath string, blockNetwork bool) (string, error) {
	cPath := C.CString(path)
	defer C.free(unsafe.Pointer(cPath))
	cWorktree := C.CString(worktreePath)
	defer C.free(unsafe.Pointer(cWorktree))
	block := int32(0)
	if blockNetwork {
		block = 1
	}
	ptr := C.bentobox_sandbox_why(cPath, cWorktree, C.int(block))
	if ptr == nil {
		return "", lastError()
	}
	defer C.bentobox_free(ptr)
	return C.GoString(ptr), nil
}

// Compress runs content through the BentoBox smart crusher.
func Compress(content string) (string, error) {
	cContent := C.CString(content)
	defer C.free(unsafe.Pointer(cContent))
	ptr := C.bentobox_compress(cContent)
	if ptr == nil {
		return "", lastError()
	}
	defer C.bentobox_free(ptr)
	return C.GoString(ptr), nil
}

func lastError() error {
	ptr := C.bentobox_last_error()
	if ptr == nil {
		return errors.New("bentobox: unknown error")
	}
	defer C.bentobox_free(ptr)
	return errors.New("bentobox: " + C.GoString(ptr))
}
