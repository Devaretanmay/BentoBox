use std::ffi::{c_char, c_void, CStr, CString};
use std::panic::{catch_unwind, AssertUnwindSafe};
use std::ptr;
use std::sync::Mutex;

/// Last error message for `bentobox_last_error()`.
///
/// Process-global (not thread-local) because Go goroutines and the napi
/// thread pool can migrate between OS threads between two cgo/FFI calls.
static LAST_ERROR: Mutex<String> = Mutex::new(String::new());

fn set_error(msg: impl Into<String>) {
    if let Ok(mut e) = LAST_ERROR.lock() {
        *e = msg.into();
    }
}

/// Convert a borrowed C string to a Rust String, recording an error on failure.
fn cstr_to_string(ptr: *const c_char) -> Result<String, String> {
    if ptr.is_null() {
        return Err("null pointer passed to C ABI".to_string());
    }
    unsafe { CStr::from_ptr(ptr) }
        .to_str()
        .map(|s| s.to_owned())
        .map_err(|_| "C string was not valid UTF-8".to_string())
}

/// Allocate a C string owned by the caller; free with `bentobox_free`.
/// Returns NULL (and records an error) if `s` contains an interior NUL byte,
/// so callers never receive a silently truncated result.
unsafe fn alloc_string(s: String) -> *mut c_char {
    match CString::new(s) {
        Ok(c) => c.into_raw(),
        Err(_) => {
            set_error("result contained an interior NUL byte");
            ptr::null_mut()
        }
    }
}

/// Version of the core library.
///
/// Caller must free the result with `bentobox_free`.
#[no_mangle]
pub extern "C" fn bentobox_version() -> *mut c_char {
    unsafe { alloc_string(env!("CARGO_PKG_VERSION").to_string()) }
}

/// 1 if kernel sandboxing is supported on this platform, 0 otherwise.
#[no_mangle]
pub extern "C" fn bentobox_sandbox_supported() -> i32 {
    i32::from(crate::sandbox::check_supported())
}

/// Apply the sandbox, restricting the current process tree to `worktree_path`.
///
/// Returns 0 on success, -1 on sandbox failure, -2 on panic.
/// Check `bentobox_last_error()` for details.
#[no_mangle]
pub extern "C" fn bentobox_sandbox_apply(worktree_path: *const c_char, block_network: i32) -> i32 {
    let result = catch_unwind(AssertUnwindSafe(|| -> Result<(), String> {
        let path = cstr_to_string(worktree_path)?;
        crate::sandbox::apply(&path, block_network != 0)
    }));
    match result {
        Ok(Ok(())) => 0,
        Ok(Err(e)) => {
            set_error(e);
            -1
        }
        Err(_) => {
            set_error("panic while applying sandbox");
            -2
        }
    }
}

/// Explain why `path` (file or `tcp:`/`udp:` address) would be blocked by the
/// sandbox rules for `worktree_path`.
///
/// Returns an allocated string (free with `bentobox_free`) or NULL on error.
#[no_mangle]
pub extern "C" fn bentobox_sandbox_why(
    path: *const c_char,
    worktree_path: *const c_char,
    block_network: i32,
) -> *mut c_char {
    let result = catch_unwind(AssertUnwindSafe(|| -> Result<String, String> {
        let path = cstr_to_string(path)?;
        let worktree = cstr_to_string(worktree_path)?;
        Ok(crate::sandbox::why(&path, &worktree, block_network != 0))
    }));
    match result {
        Ok(Ok(s)) => unsafe { alloc_string(s) },
        Ok(Err(e)) => {
            set_error(e);
            ptr::null_mut()
        }
        Err(_) => {
            set_error("panic while explaining sandbox block");
            ptr::null_mut()
        }
    }
}

/// Compress `content` through the smart crusher.
///
/// Returns an allocated string (free with `bentobox_free`) or NULL on error.
#[no_mangle]
pub extern "C" fn bentobox_compress(content: *const c_char) -> *mut c_char {
    let result = catch_unwind(AssertUnwindSafe(|| -> Result<String, String> {
        let content = cstr_to_string(content)?;
        Ok(crate::compress::compress_content(&content))
    }));
    match result {
        Ok(Ok(s)) => unsafe { alloc_string(s) },
        Ok(Err(e)) => {
            set_error(e);
            ptr::null_mut()
        }
        Err(_) => {
            set_error("panic while compressing");
            ptr::null_mut()
        }
    }
}

/// Get the last error message as an allocated string (free with `bentobox_free`).
#[no_mangle]
pub extern "C" fn bentobox_last_error() -> *mut c_char {
    let msg = LAST_ERROR.lock().map(|e| e.clone()).unwrap_or_default();
    unsafe { alloc_string(msg) }
}

/// Free a string returned by this API.
#[no_mangle]
pub unsafe extern "C" fn bentobox_free(ptr: *mut c_char) {
    if !ptr.is_null() {
        drop(CString::from_raw(ptr));
    }
}

// =========================================================================
// Compartment runtime — enforcer, snapshots, credentials, coordination
// =========================================================================

/// Enforce a policy JSON `{"permissions": [...]}` against required permissions.
/// Returns 1 (allowed) / 0 (denied) / -1 (invalid input). Check `bentobox_last_error()`.
#[no_mangle]
pub extern "C" fn bentobox_runtime_check_permission(
    policy_json: *const c_char,
    required_json: *const c_char,
) -> i32 {
    let result = catch_unwind(AssertUnwindSafe(|| -> Result<bool, String> {
        let policy = parse_json::<serde_json::Value>(cstr_to_string(policy_json)?)?;
        let required: Vec<String> = parse_json(cstr_to_string(required_json)?)?;
        // check_permission_json only errors on a genuine denial, so a false
        // result means "denied"; JSON parse failures already surfaced above.
        crate::runtime::enforcer::check_permission_json(&policy, &required)
            .map(|_| true)
            .or_else(|e| {
                set_error(e);
                Ok(false)
            })
    }));
    match result {
        Ok(Ok(true)) => 1,
        Ok(Ok(false)) => 0,
        Ok(Err(e)) => {
            set_error(e);
            -1
        }
        Err(_) => {
            set_error("panic in runtime check_permission");
            -2
        }
    }
}

/// Check a command string against the dangerous-command blocklist.
/// Returns 1 (allowed) / 0 (blocked) — check `bentobox_last_error()` for the reason.
#[no_mangle]
pub extern "C" fn bentobox_runtime_check_command(cmd: *const c_char) -> i32 {
    let result = catch_unwind(AssertUnwindSafe(|| -> Result<(), String> {
        let cmd = cstr_to_string(cmd)?;
        crate::runtime::enforcer::check_command(&cmd)
    }));
    match result {
        Ok(Ok(())) => 1,
        Ok(Err(e)) => {
            set_error(e);
            0
        }
        Err(_) => {
            set_error("panic in runtime check_command");
            -2
        }
    }
}

/// Create a filesystem snapshot of `workdir` into `snapshot_dir`.
/// Returns the number of files snapshotted, or -1/-2 on failure.
#[no_mangle]
pub extern "C" fn bentobox_runtime_snapshot(
    workdir: *const c_char,
    snapshot_dir: *const c_char,
    exclude_json: *const c_char,
) -> i32 {
    let result = catch_unwind(AssertUnwindSafe(|| -> Result<usize, String> {
        let workdir = cstr_to_string(workdir)?;
        let snapshot_dir = cstr_to_string(snapshot_dir)?;
        let exclude: Vec<String> = if exclude_json.is_null() {
            Vec::new()
        } else {
            parse_json(cstr_to_string(exclude_json)?)?
        };
        let exclude_set: std::collections::HashSet<String> = exclude.into_iter().collect();
        let mgr = crate::runtime::snapshot::SnapshotManager::new(
            &workdir,
            &snapshot_dir,
            if exclude_set.is_empty() { None } else { Some(exclude_set) },
        );
        mgr.snapshot()
    }));
    match result {
        Ok(Ok(n)) => n as i32,
        Ok(Err(e)) => {
            set_error(e);
            -1
        }
        Err(_) => {
            set_error("panic in runtime snapshot");
            -2
        }
    }
}

/// Restore files from `snapshot_dir` back into `workdir`.
/// Returns the number of files restored, or -1 on failure.
#[no_mangle]
pub extern "C" fn bentobox_runtime_restore(
    workdir: *const c_char,
    snapshot_dir: *const c_char,
) -> i32 {
    let result = catch_unwind(AssertUnwindSafe(|| -> Result<usize, String> {
        let workdir = cstr_to_string(workdir)?;
        let snapshot_dir = cstr_to_string(snapshot_dir)?;
        let mgr = crate::runtime::snapshot::SnapshotManager::new(&workdir, &snapshot_dir, None);
        mgr.restore()
    }));
    match result {
        Ok(Ok(n)) => n as i32,
        Ok(Err(e)) => {
            set_error(e);
            -1
        }
        Err(_) => {
            set_error("panic in runtime restore");
            -2
        }
    }
}

/// Build a compartment Runtime from JSON and validate all compartments + edges.
/// Returns 1 if valid, 0 if invalid (reason in `bentobox_last_error()`).
#[no_mangle]
pub extern "C" fn bentobox_runtime_validate(configs_json: *const c_char, edges_json: *const c_char) -> i32 {
    let result = catch_unwind(AssertUnwindSafe(|| -> Result<(), String> {
        let configs = cstr_to_string(configs_json)?;
        let edges = if edges_json.is_null() {
            "[]".to_string()
        } else {
            cstr_to_string(edges_json)?
        };
        let runtime = build_runtime(&configs, &edges)?;
        runtime.run_order(None)?;
        Ok(())
    }));
    match result {
        Ok(Ok(())) => 1,
        Ok(Err(e)) => {
            set_error(e);
            0
        }
        Err(_) => {
            set_error("panic in runtime validate");
            -2
        }
    }
}

/// Validate that a message from `from` to `to` is permitted.
/// Returns 1 if allowed, 0 if denied by a whitelist, -1 if a compartment
/// is unknown or input is invalid. Reason is available via `bentobox_last_error()`.
#[no_mangle]
pub extern "C" fn bentobox_runtime_can_route(
    configs_json: *const c_char,
    from: *const c_char,
    to: *const c_char,
) -> i32 {
    let result = catch_unwind(AssertUnwindSafe(|| -> Result<i32, String> {
        let configs = cstr_to_string(configs_json)?;
        let from = cstr_to_string(from)?;
        let to = cstr_to_string(to)?;
        let runtime = build_runtime(&configs, "[]")?;
        // Unknown compartment names are input errors (-1), not denials (0).
        if runtime.config(&from).is_none() || runtime.config(&to).is_none() {
            return Ok(-1);
        }
        runtime
            .can_route(&from, &to)
            .map(|_| 1)
            .or_else(|e| {
                set_error(e);
                Ok(0)
            })
    }));
    match result {
        Ok(Ok(1)) => 1,
        Ok(Ok(0)) => 0,
        Ok(Ok(-1)) => {
            set_error("unknown source or target compartment");
            -1
        }
        Ok(Ok(_)) => {
            set_error("unexpected can_route result");
            -1
        }
        Ok(Err(e)) => {
            set_error(e);
            -1
        }
        Err(_) => {
            set_error("panic in runtime can_route");
            -2
        }
    }
}

/// Match a request path against credential routes JSON and, on a match,
/// return the rewritten upstream URL as an allocated string
/// (free with `bentobox_free`). Returns NULL if no route matches or on error.
#[no_mangle]
pub extern "C" fn bentobox_runtime_credential_rewrite(
    routes_json: *const c_char,
    path: *const c_char,
) -> *mut c_char {
    let result = catch_unwind(AssertUnwindSafe(|| -> Result<Option<String>, String> {
        let routes: Vec<crate::runtime::credential::RouteConfig> = parse_json(cstr_to_string(routes_json)?)?;
        let path = cstr_to_string(path)?;
        for r in &routes {
            if r.matches(&path) {
                return Ok(Some(r.rewrite_path(&path)));
            }
        }
        Ok(None)
    }));
    match result {
        Ok(Ok(Some(url))) => unsafe { alloc_string(url) },
        // Clear any stale error so callers can distinguish "no match"
        // (NULL + empty last_error) from a real failure (NULL + message).
        Ok(Ok(None)) => {
            set_error("");
            ptr::null_mut()
        }
        Ok(Err(e)) => {
            set_error(e);
            ptr::null_mut()
        }
        Err(_) => {
            set_error("panic in runtime credential rewrite");
            ptr::null_mut()
        }
    }
}

/// Resolve a credential source like `env:OPENAI_API_KEY`.
/// Returns the resolved value as an allocated string (free with `bentobox_free`)
/// or NULL if the source is unknown.
#[no_mangle]
pub extern "C" fn bentobox_runtime_credential_resolve(source: *const c_char) -> *mut c_char {
    let result = catch_unwind(AssertUnwindSafe(|| -> Result<String, String> {
        let source = cstr_to_string(source)?;
        let route = crate::runtime::credential::RouteConfig {
            credential_source: source,
            ..Default::default()
        };
        Ok(route.resolve_credential())
    }));
    match result {
        Ok(Ok(v)) => unsafe { alloc_string(v) },
        Ok(Err(e)) => {
            set_error(e);
            ptr::null_mut()
        }
        Err(_) => {
            set_error("panic in runtime credential resolve");
            ptr::null_mut()
        }
    }
}

// =========================================================================
// Opaque runtime handle — parse configs once, route many times
// =========================================================================

/// Build a compartment Runtime from configs JSON + edges JSON and return an
/// opaque handle. The handle parses the configs once; subsequent
/// `bentobox_runtime_handle_*` calls reuse it (O(1) per message instead of
/// re-parsing JSON every time). Free with `bentobox_runtime_free`.
/// Returns NULL on error; check `bentobox_last_error()`.
///
/// Thread-safe: the Runtime is wrapped in a `Mutex`, so one handle may be
/// shared across threads/goroutines. Free it exactly once, after all
/// threads have finished with it.
#[no_mangle]
pub extern "C" fn bentobox_runtime_new(
    configs_json: *const c_char,
    edges_json: *const c_char,
) -> *mut c_void {
    let result = catch_unwind(AssertUnwindSafe(|| -> Result<*mut c_void, String> {
        let configs = cstr_to_string(configs_json)?;
        let edges = if edges_json.is_null() {
            "[]".to_string()
        } else {
            cstr_to_string(edges_json)?
        };
        let runtime = build_runtime(&configs, &edges)?;
        let shared = std::sync::Mutex::new(runtime);
        Ok(Box::into_raw(Box::new(shared)) as *mut c_void)
    }));
    match result {
        Ok(Ok(ptr)) => ptr,
        Ok(Err(e)) => {
            set_error(e);
            ptr::null_mut()
        }
        Err(_) => {
            set_error("panic in runtime_new");
            ptr::null_mut()
        }
    }
}

/// Destroy a runtime handle created by `bentobox_runtime_new`.
/// Passing NULL is a no-op. Must not be called while other threads are
/// still using the handle.
#[no_mangle]
pub unsafe extern "C" fn bentobox_runtime_free(handle: *mut c_void) {
    if !handle.is_null() {
        let ptr = handle as *mut std::sync::Mutex<crate::runtime::compartments::Runtime>;
        drop(Box::from_raw(ptr));
    }
}

/// Route a message through a runtime handle.
/// Returns 1 if allowed, 0 if denied by a whitelist, -1 if a compartment
/// is unknown or the handle is NULL, -2 on panic.
#[no_mangle]
pub extern "C" fn bentobox_runtime_handle_can_route(
    handle: *mut c_void,
    from: *const c_char,
    to: *const c_char,
) -> i32 {
    if handle.is_null() {
        set_error("null runtime handle");
        return -1;
    }
    let result = catch_unwind(AssertUnwindSafe(|| -> Result<i32, String> {
        let shared = unsafe { &*(handle as *const std::sync::Mutex<crate::runtime::compartments::Runtime>) };
        let runtime = shared
            .lock()
            .map_err(|_| "runtime handle mutex poisoned".to_string())?;
        let from = cstr_to_string(from)?;
        let to = cstr_to_string(to)?;
        // Unknown compartment names are input errors (-1), not denials (0).
        if runtime.config(&from).is_none() || runtime.config(&to).is_none() {
            return Ok(-1);
        }
        runtime
            .can_route(&from, &to)
            .map(|_| 1)
            .or_else(|e| {
                set_error(e);
                Ok(0)
            })
    }));
    match result {
        Ok(Ok(1)) => 1,
        Ok(Ok(0)) => 0,
        Ok(Ok(-1)) => {
            set_error("unknown source or target compartment");
            -1
        }
        Ok(Ok(_)) => {
            set_error("unexpected can_route result");
            -1
        }
        Ok(Err(e)) => {
            set_error(e);
            -1
        }
        Err(_) => {
            set_error("panic in runtime handle can_route");
            -2
        }
    }
}

/// Resolve the execution order through a runtime handle as a JSON array of
/// compartment names, optionally starting at `entry` (NULL = from the start).
/// Returns an allocated string (free with `bentobox_free`) or NULL on error.
#[no_mangle]
pub extern "C" fn bentobox_runtime_handle_run_order(
    handle: *mut c_void,
    entry: *const c_char,
) -> *mut c_char {
    if handle.is_null() {
        set_error("null runtime handle");
        return ptr::null_mut();
    }
    let result = catch_unwind(AssertUnwindSafe(|| -> Result<String, String> {
        let shared = unsafe { &*(handle as *const std::sync::Mutex<crate::runtime::compartments::Runtime>) };
        let runtime = shared
            .lock()
            .map_err(|_| "runtime handle mutex poisoned".to_string())?;
        let entry = if entry.is_null() {
            None
        } else {
            Some(cstr_to_string(entry)?)
        };
        let order = runtime.run_order(entry.as_deref())?;
        serde_json::to_string(&order).map_err(|e| format!("serialize: {e}"))
    }));
    match result {
        Ok(Ok(s)) => unsafe { alloc_string(s) },
        Ok(Err(e)) => {
            set_error(e);
            ptr::null_mut()
        }
        Err(_) => {
            set_error("panic in runtime handle run_order");
            ptr::null_mut()
        }
    }
}

fn parse_json<T: serde::de::DeserializeOwned>(input: String) -> Result<T, String> {
    serde_json::from_str(&input).map_err(|e| format!("invalid JSON: {e}"))
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::ffi::CString;

    fn test_configs() -> CString {
        CString::new(
            r#"{"configs":[{"name":"a","allow_outbound_to":["b"]},{"name":"b"},{"name":"c","allow_inbound_from":[]}]}"#,
        )
        .unwrap()
    }

    #[test]
    fn runtime_handle_is_thread_safe() {
        let configs = test_configs();
        let edges = CString::new(r#"[["a","b"]]"#).unwrap();
        let handle = bentobox_runtime_new(configs.as_ptr(), edges.as_ptr());
        assert!(!handle.is_null(), "handle should not be NULL");

        let from_a = CString::new("a").unwrap();
        let to_b = CString::new("b").unwrap();
        let from_b = CString::new("b").unwrap();
        let to_c = CString::new("c").unwrap();
        let from_zzz = CString::new("zzz").unwrap();

        // Raw pointers are not Send, so threads share the handle as a usize
        // and cast it back inside each closure (the value is only read).
        let handle_addr = handle as usize;
        let from_a = from_a.as_ptr() as usize;
        let to_b = to_b.as_ptr() as usize;
        let from_b = from_b.as_ptr() as usize;
        let to_c = to_c.as_ptr() as usize;
        let from_zzz = from_zzz.as_ptr() as usize;

        let mut handles = Vec::new();
        for _ in 0..8 {
            handles.push(std::thread::spawn(move || {
                // The Mutex protects concurrent can_route access, so every
                // thread must observe identical results.
                let handle = handle_addr as *mut c_void;
                let mut allowed = 0i32;
                let mut denied = 0i32;
                let mut unknown = 0i32;
                for _ in 0..200 {
                    let rc = bentobox_runtime_handle_can_route(
                        handle,
                        from_a as *const c_char,
                        to_b as *const c_char,
                    );
                    if rc == 1 {
                        allowed += 1;
                    }
                    let rc = bentobox_runtime_handle_can_route(
                        handle,
                        from_b as *const c_char,
                        to_c as *const c_char,
                    );
                    if rc == 0 {
                        denied += 1;
                    }
                    let rc = bentobox_runtime_handle_can_route(
                        handle,
                        from_zzz as *const c_char,
                        to_b as *const c_char,
                    );
                    if rc == -1 {
                        unknown += 1;
                    }
                }
                (allowed, denied, unknown)
            }));
        }

        for h in handles {
            let (allowed, denied, unknown) = h.join().unwrap();
            assert_eq!(allowed, 200, "a->b should always be allowed");
            assert_eq!(denied, 200, "b->c should always be denied");
            assert_eq!(unknown, 200, "zzz->b should always be unknown");
        }

        let order_ptr = bentobox_runtime_handle_run_order(handle, std::ptr::null());
        assert!(!order_ptr.is_null());
        let order = unsafe { CStr::from_ptr(order_ptr) }.to_str().unwrap().to_string();
        unsafe { bentobox_free(order_ptr) };
        assert_eq!(order, r#"["a","b","c"]"#);

        unsafe { bentobox_runtime_free(handle) };
    }
}

fn build_runtime(configs: &str, edges: &str) -> Result<crate::runtime::compartments::Runtime, String> {
    #[derive(serde::Deserialize)]
    struct Spec {
        #[serde(default)]
        configs: Vec<crate::runtime::compartments::CompartmentConfig>,
    }
    #[derive(serde::Deserialize)]
    struct Edge {
        #[serde(default)]
        from: String,
        #[serde(default)]
        to: String,
    }

    let spec: Spec = parse_json(configs.to_string())?;
    let edges_raw: Vec<Edge> = parse_json(edges.to_string())?;
    let mut rt = crate::runtime::compartments::Runtime::new();
    for cfg in spec.configs {
        rt.add(cfg)?;
    }
    for e in edges_raw {
        rt.edge(&e.from, &e.to)?;
    }
    Ok(rt)
}


