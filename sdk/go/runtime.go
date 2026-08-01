package bentobox

/*
#cgo CFLAGS: -I${SRCDIR}/../../include
#cgo LDFLAGS: ${SRCDIR}/../../target/release/libbentoworks_core.a -lpthread -ldl -lm
#include <stdlib.h>
#include <bentobox.h>
*/
import "C"

import (
	"encoding/json"
	"errors"
	"unsafe"
)

// CompartmentConfig declares a compartment's permissions, resource limits, and communication whitelists.
type CompartmentConfig struct {
	Name             string   `json:"name"`
	Description      string   `json:"description"`
	Permissions      []string `json:"permissions"`
	TimeoutS         uint64   `json:"timeout_s"`
	MemoryMB         uint64   `json:"memory_mb"`
	StorageMB        uint64   `json:"storage_mb"`
	CPUPercent       uint64   `json:"cpu_percent"`
	AllowInboundFrom []string `json:"allow_inbound_from"`
	AllowOutboundTo  []string `json:"allow_outbound_to"`
}

// RouteConfig defines a single credential injection rule.
type RouteConfig struct {
	Prefix           string `json:"prefix"`
	Upstream         string `json:"upstream"`
	Header           string `json:"header"`
	Format           string `json:"format"`
	CredentialSource string `json:"credential_source"`
}

// CheckPermission reports whether policy satisfies the required permissions.
func CheckPermission(policy CompartmentConfig, required ...string) (bool, error) {
	policyJSON, err := json.Marshal(policy)
	if err != nil {
		return false, err
	}
	reqJSON, err := json.Marshal(required)
	if err != nil {
		return false, err
	}
	cPolicy := C.CString(string(policyJSON))
	defer C.free(unsafe.Pointer(cPolicy))
	cReq := C.CString(string(reqJSON))
	defer C.free(unsafe.Pointer(cReq))

	rc := C.bentobox_runtime_check_permission(cPolicy, cReq)
	switch rc {
	case 1:
		return true, nil
	case 0:
		return false, nil // denied - the bool is the signal
	case -2:
		return false, errors.New("bentobox: panic in check_permission")
	default:
		return false, lastError() // invalid input
	}
}

// CheckCommand reports whether cmd is allowed by the dangerous-command blocklist.
func CheckCommand(cmd string) (bool, error) {
	cCmd := C.CString(cmd)
	defer C.free(unsafe.Pointer(cCmd))
	rc := C.bentobox_runtime_check_command(cCmd)
	switch rc {
	case 1:
		return true, nil
	case 0:
		return false, nil // blocked - the bool is the signal
	default:
		return false, errors.New("bentobox: panic in check_command")
	}
}

// Snapshot records workdir into snapshotDir, excluding the named top-level dirs.
func Snapshot(workdir, snapshotDir string, exclude []string) (int, error) {
	cWork := C.CString(workdir)
	defer C.free(unsafe.Pointer(cWork))
	cSnap := C.CString(snapshotDir)
	defer C.free(unsafe.Pointer(cSnap))

	var cExclude *C.char
	if len(exclude) > 0 {
		b, err := json.Marshal(exclude)
		if err != nil {
			return 0, err
		}
		cExclude = C.CString(string(b))
		defer C.free(unsafe.Pointer(cExclude))
	}

	rc := C.bentobox_runtime_snapshot(cWork, cSnap, cExclude)
	if rc < 0 {
		return 0, lastError()
	}
	return int(rc), nil
}

// Restore copies changed files from snapshotDir back into workdir.
func Restore(workdir, snapshotDir string) (int, error) {
	cWork := C.CString(workdir)
	defer C.free(unsafe.Pointer(cWork))
	cSnap := C.CString(snapshotDir)
	defer C.free(unsafe.Pointer(cSnap))
	rc := C.bentobox_runtime_restore(cWork, cSnap)
	if rc < 0 {
		return 0, lastError()
	}
	return int(rc), nil
}

// ValidateRuntime reports whether configs and edges form a valid compartment graph.
func ValidateRuntime(configs []CompartmentConfig, edges [][2]string) (bool, error) {
	cfgJSON, err := json.Marshal(map[string]any{"configs": configs})
	if err != nil {
		return false, err
	}
	edgesJSON, err := json.Marshal(edges)
	if err != nil {
		return false, err
	}
	cCfg := C.CString(string(cfgJSON))
	defer C.free(unsafe.Pointer(cCfg))
	cEdges := C.CString(string(edgesJSON))
	defer C.free(unsafe.Pointer(cEdges))

	rc := C.bentobox_runtime_validate(cCfg, cEdges)
	switch rc {
	case 1:
		return true, nil
	case 0:
		return false, nil // invalid - the bool is the signal
	default:
		return false, errors.New("bentobox: panic in validate_runtime")
	}
}

// CanRoute reports whether a message from -> to is permitted by the configs.
func CanRoute(configs []CompartmentConfig, from, to string) (bool, error) {
	cfgJSON, err := json.Marshal(map[string]any{"configs": configs})
	if err != nil {
		return false, err
	}
	cCfg := C.CString(string(cfgJSON))
	defer C.free(unsafe.Pointer(cCfg))
	cFrom := C.CString(from)
	defer C.free(unsafe.Pointer(cFrom))
	cTo := C.CString(to)
	defer C.free(unsafe.Pointer(cTo))

	rc := C.bentobox_runtime_can_route(cCfg, cFrom, cTo)
	switch rc {
	case 1:
		return true, nil
	case 0:
		return false, nil // denied by whitelist - the bool is the signal
	default:
		return false, lastError() // unknown compartment, bad JSON, or panic
	}
}

// CredentialRewrite rewrites path through the matching route, or "" if none match.
func CredentialRewrite(routes []RouteConfig, path string) (string, error) {
	rJSON, err := json.Marshal(routes)
	if err != nil {
		return "", err
	}
	cRoutes := C.CString(string(rJSON))
	defer C.free(unsafe.Pointer(cRoutes))
	cPath := C.CString(path)
	defer C.free(unsafe.Pointer(cPath))

	ptr := C.bentobox_runtime_credential_rewrite(cRoutes, cPath)
	if ptr == nil {
		// "No match" clears last_error; a real failure sets it.
		if msg := lastErrorMsg(); msg != "" {
			return "", errors.New(msg)
		}
		return "", nil
	}
	defer C.bentobox_free(ptr)
	return C.GoString(ptr), nil
}

// CredentialResolve resolves a credential source such as env:VAR.
func CredentialResolve(source string) string {
	cSrc := C.CString(source)
	defer C.free(unsafe.Pointer(cSrc))
	ptr := C.bentobox_runtime_credential_resolve(cSrc)
	if ptr == nil {
		return ""
	}
	defer C.bentobox_free(ptr)
	return C.GoString(ptr)
}

func lastErrorMsg() string {
	ptr := C.bentobox_last_error()
	if ptr == nil {
		return ""
	}
	defer C.bentobox_free(ptr)
	return C.GoString(ptr)
}

// Runtime is an opaque, pre-built compartment runtime. The native handle is
// mutex-protected (safe across goroutines); call Free exactly once.
type Runtime struct {
	handle unsafe.Pointer
}

// NewRuntime builds an opaque runtime handle from configs and edges.
func NewRuntime(configs []CompartmentConfig, edges [][2]string) (*Runtime, error) {
	cfgJSON, err := json.Marshal(map[string]any{"configs": configs})
	if err != nil {
		return nil, err
	}
	cCfg := C.CString(string(cfgJSON))
	defer C.free(unsafe.Pointer(cCfg))

	var cEdges *C.char
	if edges != nil {
		edgesJSON, err := json.Marshal(edges)
		if err != nil {
			return nil, err
		}
		cEdges = C.CString(string(edgesJSON))
		defer C.free(unsafe.Pointer(cEdges))
	}

	h := C.bentobox_runtime_new(cCfg, cEdges)
	if h == nil {
		return nil, lastError()
	}
	return &Runtime{handle: h}, nil
}

// CanRoute reports whether a message from -> to is permitted by this runtime.
func (r *Runtime) CanRoute(from, to string) (bool, error) {
	cFrom := C.CString(from)
	defer C.free(unsafe.Pointer(cFrom))
	cTo := C.CString(to)
	defer C.free(unsafe.Pointer(cTo))

	rc := C.bentobox_runtime_handle_can_route(r.handle, cFrom, cTo)
	switch rc {
	case 1:
		return true, nil
	case 0:
		return false, nil // denied by whitelist - the bool is the signal
	default:
		return false, lastError() // unknown compartment, bad handle, or panic
	}
}

// RunOrder returns the compartment execution order starting at entry.
func (r *Runtime) RunOrder(entry string) ([]string, error) {
	var cEntry *C.char
	if entry != "" {
		cEntry = C.CString(entry)
		defer C.free(unsafe.Pointer(cEntry))
	}

	ptr := C.bentobox_runtime_handle_run_order(r.handle, cEntry)
	if ptr == nil {
		return nil, lastError()
	}
	defer C.bentobox_free(ptr)
	var names []string
	if err := json.Unmarshal([]byte(C.GoString(ptr)), &names); err != nil {
		return nil, err
	}
	return names, nil
}

// Free releases the native handle. Call exactly once when done.
func (r *Runtime) Free() {
	if r.handle != nil {
		C.bentobox_runtime_free(r.handle)
		r.handle = nil
	}
}
