#![allow(dead_code, unused_imports)]

/// BentoBox Rust Core - sandbox enforcement + output compression.
pub mod compress;
pub mod sandbox;

pub mod runtime;
mod engines;

pub mod c_api;

#[cfg(feature = "pyo3-binding")]
mod py_bindings;

pub fn version() -> &'static str {
    env!("CARGO_PKG_VERSION")
}
