use std::sync::Arc;

use blake3;

use serde_json::Value;

use super::ir::OpaqueKind;
use crate::runtime::ccr::InMemoryCcrStore;

pub fn try_parse_json_container(s: &str) -> Option<Value> {
    let trimmed = s.trim_start();
    if !matches!(trimmed.chars().next(), Some('{') | Some('[')) {
        return None;
    }
    serde_json::from_str::<Value>(s)
        .ok()
        .filter(|v| matches!(v, Value::Object(_) | Value::Array(_)))
}

pub fn emit_opaque_ccr_marker(
    payload: &str,
    kind: &OpaqueKind,
    store: Option<&Arc<InMemoryCcrStore>>,
) -> String {
    let h = blake3::hash(payload.as_bytes());
    let hash = h.to_hex().as_str()[..12].to_string();
    if let Some(s) = store {
        s.put(&hash, payload);
    }
    let kind_str = match kind {
        OpaqueKind::Base64Blob => "base64",
        OpaqueKind::LongString => "string",
        OpaqueKind::HtmlChunk => "html",
        OpaqueKind::Other(s) => s.as_str(),
    };
    format!("<<ccr:{},{},{}>>", hash, kind_str, humanize(payload.len()))
}

fn humanize(n: usize) -> String {
    if n < 1024 {
        return format!("{n}B");
    }
    let kb = n as f64 / 1024.0;
    if kb < 1024.0 {
        return format!("{kb:.1}KB");
    }
    format!("{:.1}MB", kb / 1024.0)
}
