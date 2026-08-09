/// BentoBox Rust Core - sandbox enforcement + output compression.
pub mod sandbox;

mod engines;
pub mod runtime;

#[cfg(feature = "pyo3-binding")]
mod py_bindings;

pub fn version() -> &'static str {
    env!("CARGO_PKG_VERSION")
}
