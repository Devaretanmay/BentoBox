pub mod classifier;
pub mod compactor;
pub mod formatter;
pub mod ir;
pub mod walker;

pub use classifier::{classify_cell, CellClass, ClassifyConfig};
pub use compactor::{compact, compact_with_store, CompactConfig};
pub use formatter::{CsvSchemaFormatter, Formatter, JsonFormatter};
pub use ir::{Compaction, OpaqueKind};
pub use walker::{emit_opaque_ccr_marker, try_parse_json_container};

pub struct CompactionStage {
    pub config: CompactConfig,
    pub formatter: Box<dyn Formatter>,
}

impl CompactionStage {
    pub fn csv_schema(config: CompactConfig) -> Self {
        Self {
            config,
            formatter: Box::new(CsvSchemaFormatter::new()),
        }
    }

    pub fn run_with_store(
        &self,
        items: &[serde_json::Value],
        store: Option<&std::sync::Arc<crate::runtime::ccr::InMemoryCcrStore>>,
    ) -> (Compaction, String) {
        let c = compact_with_store(items, &self.config, store);
        let rendered = self.formatter.format(&c);
        (c, rendered)
    }
}

impl std::fmt::Debug for CompactionStage {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("CompactionStage")
            .field("config", &self.config)
            .field("formatter", &self.formatter.name())
            .finish()
    }
}
