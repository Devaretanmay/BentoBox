#[derive(Debug, Clone)]
pub struct SmartCrusherConfig {
    pub min_items_to_analyze: usize,
    pub min_tokens_to_crush: usize,
    pub variance_threshold: f64,
    pub max_items_after_crush: usize,
    pub preserve_change_points: bool,
    pub factor_out_constants: bool,
    pub dedup_identical_items: bool,
    pub first_fraction: f64,
    pub last_fraction: f64,
    pub relevance_threshold: f64,
    pub lossless_min_savings_ratio: f64,
    pub enable_ccr_marker: bool,
    pub lossless_only: bool,
    pub compaction_core_field_fraction: f64,
    pub compaction_heterogeneous_core_ratio: f64,
    pub compaction_max_flatten_inner_keys: usize,
    pub compaction_min_buckets: usize,
    pub compaction_max_buckets: usize,
    pub preview_count: usize,
}

impl Default for SmartCrusherConfig {
    fn default() -> Self {
        SmartCrusherConfig {
            min_items_to_analyze: 5,
            min_tokens_to_crush: 200,
            variance_threshold: 2.0,
            max_items_after_crush: 15,
            preserve_change_points: true,
            factor_out_constants: false,
            dedup_identical_items: true,
            first_fraction: 0.3,
            last_fraction: 0.15,
            relevance_threshold: 0.3,
            lossless_min_savings_ratio: 0.15,
            enable_ccr_marker: true,
            lossless_only: false,
            compaction_core_field_fraction: 0.8,
            compaction_heterogeneous_core_ratio: 0.6,
            compaction_max_flatten_inner_keys: 6,
            compaction_min_buckets: 2,
            compaction_max_buckets: 8,
            preview_count: 0,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn defaults_match_python() {
        let c = SmartCrusherConfig::default();
        assert_eq!(c.min_items_to_analyze, 5);
        assert_eq!(c.min_tokens_to_crush, 200);
        assert_eq!(c.variance_threshold, 2.0);
        assert_eq!(c.max_items_after_crush, 15);
        assert!(c.preserve_change_points);
        assert!(!c.factor_out_constants);
        assert!(c.dedup_identical_items);
        assert_eq!(c.first_fraction, 0.3);
        assert_eq!(c.last_fraction, 0.15);
        assert_eq!(c.relevance_threshold, 0.3);
        assert_eq!(c.lossless_min_savings_ratio, 0.15);
        assert!(c.enable_ccr_marker);
        assert!(!c.lossless_only);
        assert_eq!(c.compaction_core_field_fraction, 0.8);
        assert_eq!(c.compaction_heterogeneous_core_ratio, 0.6);
        assert_eq!(c.compaction_max_flatten_inner_keys, 6);
        assert_eq!(c.compaction_min_buckets, 2);
        assert_eq!(c.compaction_max_buckets, 8);
        assert_eq!(c.preview_count, 0);
    }
}
