use pyo3::prelude::*;

/// Route content to the appropriate compression engine based on detected type.
/// Called from Python's CompressionModule via the `_core` module.
#[pyfunction]
pub fn route_and_compress(content: &str) -> String {
    crate::engines::compression::route_and_compress(content)
}
