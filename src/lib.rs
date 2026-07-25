#![allow(clippy::not_unsafe_ptr_arg_deref)]
#![allow(clippy::missing_safety_doc)]
#![allow(unsafe_op_in_unsafe_fn)]

pub mod compress;
pub mod engines;
pub mod runtime;

pub use engines::loop_detection::history;
pub use engines::loop_detection::history::LoopVerdict;
pub use engines::loop_detection::state::HavfrysState;

pub fn verify(state: &mut HavfrysState, tool_slice: &[u8], args_slice: &[u8]) -> u8 {
    let tool_str = match std::str::from_utf8(tool_slice) {
        Ok(s) => s.to_string(),
        Err(_) => return state.block_result(),
    };
    let args_str = match std::str::from_utf8(args_slice) {
        Ok(s) => s.to_string(),
        Err(_) => return state.block_result(),
    };

    let max_repeats = state.get_effective_threshold(&tool_str);

    match state.history.check_loop(
        &tool_str,
        &args_str,
        state.ignore_args,
        max_repeats,
        state.history_window,
    ) {
        history::LoopVerdict::Allow => {}
        history::LoopVerdict::WarnOscillation(msg) => state.set_warning(&msg),
        history::LoopVerdict::BlockExactMatch(msg)
        | history::LoopVerdict::BlockOscillation(msg) => {
            state.set_error(&msg);
            return state.block_result();
        }
    }

    if let Err(msg) = state.engine.validate(&args_str) {
        state.set_error(msg);
        return state.block_result();
    }

    0
}

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;

#[pyclass(name = "LoopEngine")]
pub struct PyLoopEngine {
    state: HavfrysState,
}

#[pymethods]
impl PyLoopEngine {
    #[new]
    fn new(yaml_config: &str) -> PyResult<Self> {
        let state = HavfrysState::new(yaml_config)
            .map_err(|e| PyValueError::new_err(format!("Failed to parse config: {}", e)))?;
        Ok(Self { state })
    }

    fn verify(&mut self, tool_name: &str, tool_args_json: &str) -> u8 {
        verify(
            &mut self.state,
            tool_name.as_bytes(),
            tool_args_json.as_bytes(),
        )
    }
}

#[pyclass(name = "CheckpointEngine")]
pub struct PyCheckpointEngine;

#[pymethods]
impl PyCheckpointEngine {
    #[new]
    fn new() -> Self {
        Self
    }

    fn hash_state(&self, state_json: &str) -> String {
        crate::runtime::ccr::compute_key(state_json.as_bytes())
    }
}

#[pymodule]
fn _core(_py: Python, m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<PyLoopEngine>()?;
    m.add_class::<PyCheckpointEngine>()?;
    compress::register_module(m)?;
    Ok(())
}
