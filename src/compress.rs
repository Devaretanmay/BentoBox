/// Route content to the appropriate compression engine based on detected type.
/// Pure function — called from the C ABI, the Python binding, and the TS SDK.
pub fn compress_content(content: &str) -> String {
    crate::engines::compression::route_and_compress(content)
}
