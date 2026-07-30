// Many items in the compression engine and cache store are consumed
// indirectly through the Python FFI (route_and_compress), so the Rust
// compiler cannot see all call sites.  Suppress warnings for this crate.
#![allow(dead_code, unused_imports)]

/// BentoBox Rust Core — sandbox enforcement + output compression.
///
/// Provides kernel-level sandboxing via Landlock (Linux) and Seatbelt (macOS)
/// plus content-aware compression for AI agent output streams.

use pyo3::prelude::*;
use pyo3::exceptions::PyValueError;

mod compress;
mod runtime;
mod engines;
mod sandbox;

// =========================================================================
// Sandbox API — called from Python's Box.enter()
// =========================================================================

/// Apply kernel sandbox, restricting the process tree to `worktree_path`.
/// The caller should check `sandbox_available()` first.
#[pyfunction]
fn sandbox_apply(worktree_path: &str, block_network: bool) -> PyResult<bool> {
    match sandbox::apply(worktree_path, block_network) {
        Ok(()) => Ok(true),
        Err(e) => {
            if !sandbox::check_supported() {
                Ok(false)
            } else {
                Err(PyValueError::new_err(
                    format!("Sandbox application failed: {}", e),
                ))
            }
        }
    }
}

/// Explain why a path or network address would be blocked by the sandbox.
/// Pure diagnostic — does not query the OS sandbox state.
#[pyfunction]
fn sandbox_why(path: &str, worktree_path: &str, block_network: bool) -> String {
    sandbox::why(path, worktree_path, block_network)
}

/// Check whether kernel sandboxing is available on this platform.
/// Returns a dict with supported (bool), platform (str), details (str).
#[pyfunction]
fn sandbox_check_supported() -> PyResult<std::collections::HashMap<String, String>> {
    let info = sandbox::get_info();
    let mut result = std::collections::HashMap::new();
    result.insert("supported".to_string(), info.supported.to_string());
    result.insert("platform".to_string(), info.platform);
    result.insert("details".to_string(), info.details);
    Ok(result)
}


#[pymodule]
fn _core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(sandbox_apply, m)?)?;
    m.add_function(wrap_pyfunction!(sandbox_why, m)?)?;
    m.add_function(wrap_pyfunction!(sandbox_check_supported, m)?)?;
    m.add_function(wrap_pyfunction!(compress::route_and_compress, m)?)?;
    Ok(())
}
