pub mod adaptive_sizer;
pub mod anchor_selector;
pub mod bm25;
pub mod content_detector;
pub mod diff_compressor;
pub mod log_compressor;
pub mod smart_crusher;
pub mod text_crusher;

use std::sync::OnceLock;

use content_detector::ContentType;
use diff_compressor::{DiffCompressor, DiffCompressorConfig};
use log_compressor::{LogCompressor, LogCompressorConfig};
use smart_crusher::{SmartCrusher, SmartCrusherConfig};
use text_crusher::{TextCrusher, TextCrusherConfig};

fn smart_crusher() -> &'static SmartCrusher {
    static INSTANCE: OnceLock<SmartCrusher> = OnceLock::new();
    INSTANCE.get_or_init(|| SmartCrusher::new(SmartCrusherConfig::default()))
}

fn log_compressor() -> &'static LogCompressor {
    static INSTANCE: OnceLock<LogCompressor> = OnceLock::new();
    INSTANCE.get_or_init(|| LogCompressor::new(LogCompressorConfig::default()))
}

fn diff_compressor() -> &'static DiffCompressor {
    static INSTANCE: OnceLock<DiffCompressor> = OnceLock::new();
    INSTANCE.get_or_init(|| DiffCompressor::new(DiffCompressorConfig::default()))
}

fn text_crusher() -> &'static TextCrusher {
    static INSTANCE: OnceLock<TextCrusher> = OnceLock::new();
    INSTANCE.get_or_init(|| TextCrusher::new(TextCrusherConfig::default()))
}

pub fn route_and_compress(content: &str) -> String {
    if content.len() < 512 {
        return content.to_string();
    }

    let detection = content_detector::detect_content_type(content);

    let compressed = match detection.content_type {
        ContentType::JsonArray => {
            let res = smart_crusher().crush(content, "", 0.0);
            if res.was_modified {
                Some(res.compressed)
            } else {
                None
            }
        }
        ContentType::BuildOutput => {
            let (res, _) = log_compressor().compress(content, 0.0);
            if res.compressed != res.original {
                Some(res.compressed)
            } else {
                None
            }
        }
        ContentType::SearchResults | ContentType::PlainText | ContentType::SourceCode => {
            let res = text_crusher().compress(content, "", None);
            if res.compressed != content {
                Some(res.compressed)
            } else {
                None
            }
        }
        ContentType::GitDiff => {
            let res = diff_compressor().compress(content, "");
            if res.compressed != content {
                Some(res.compressed)
            } else {
                None
            }
        }
        ContentType::Html => None,
    };

    compressed.unwrap_or_else(|| content.to_string())
}
