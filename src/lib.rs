// Many items in the compression engine and cache store are consumed
// indirectly through the FFI, so the Rust compiler cannot see all call sites.
#![allow(dead_code, unused_imports)]

/// BentoBox Rust Core — sandbox enforcement + output compression.
///
/// Kernel-level sandboxing via Landlock (Linux) and Seatbelt (macOS),
/// plus content-aware compression for AI agent output streams.
///
/// The core is exposed three ways:
/// - C ABI (`bentobox_*`) — Go / TypeScript / any FFI consumer
/// - Python module (`bentoworks._core`) — behind the `pyo3-binding` feature
/// - Direct Rust API (`sandbox`, `compress`) — for napi-rs / Rust consumers

pub mod compress;
pub mod sandbox;

pub mod runtime;
mod engines;

pub mod c_api;

#[cfg(feature = "pyo3-binding")]
mod py_bindings;

/// Version of the core library, shared by all SDKs (`bentobox_version()`).
pub fn version() -> &'static str {
    env!("CARGO_PKG_VERSION")
}
