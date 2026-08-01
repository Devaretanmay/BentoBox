/// Route content to the appropriate compression engine based on detected type.
pub fn compress_content(content: &str) -> String {
    crate::engines::compression::route_and_compress(content)
}
