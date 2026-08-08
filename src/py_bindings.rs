use std::collections::HashMap;

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;

#[pyfunction]
fn sandbox_apply(worktree_path: &str, block_network: bool) -> PyResult<bool> {
    match crate::sandbox::apply(worktree_path, block_network) {
        Ok(()) => Ok(true),
        Err(e) => {
            if !crate::sandbox::check_supported() {
                Ok(false)
            } else {
                Err(PyValueError::new_err(format!(
                    "Sandbox application failed: {e}"
                )))
            }
        }
    }
}

#[pyfunction]
fn sandbox_check_supported() -> PyResult<HashMap<String, String>> {
    let info = crate::sandbox::get_info();
    let mut result = HashMap::new();
    result.insert("supported".to_string(), info.supported.to_string());
    result.insert("platform".to_string(), info.platform);
    result.insert("details".to_string(), info.details);
    Ok(result)
}

#[pyfunction]
fn route_and_compress(content: &str) -> String {
    crate::compress::compress_content(content)
}

#[pymodule]
fn _core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(sandbox_apply, m)?)?;
    m.add_function(wrap_pyfunction!(sandbox_check_supported, m)?)?;
    m.add_function(wrap_pyfunction!(route_and_compress, m)?)?;
    Ok(())
}
