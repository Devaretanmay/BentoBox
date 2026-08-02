use serde_json::Value;
use std::collections::{BTreeMap, BTreeSet};
use std::hash::{DefaultHasher, Hash, Hasher};

use super::analyzer::SmartAnalyzer;
use super::anchors::{extract_query_anchors, item_matches_anchors};
use super::field_detect::detect_score_field_statistically;
use super::hash_field_name;
use super::must_keep;
use super::orchestration::prioritize_indices;
use super::types::{ArrayAnalysis, CompressionPlan, CompressionStrategy, FieldStats};
use super::SmartCrusherConfig;
use crate::engines::compression::anchor_selector::{AnchorSelector, DataPattern};
use crate::engines::compression::bm25::RelevanceScorer;

pub struct SmartCrusherPlanner<'a> {
    pub config: &'a SmartCrusherConfig,
    pub anchor_selector: &'a AnchorSelector,
    pub scorer: &'a (dyn RelevanceScorer + Send + Sync),
    pub analyzer: &'a SmartAnalyzer,
}

impl<'a> SmartCrusherPlanner<'a> {
    pub fn new(
        config: &'a SmartCrusherConfig,
        anchor_selector: &'a AnchorSelector,
        scorer: &'a (dyn RelevanceScorer + Send + Sync),
        analyzer: &'a SmartAnalyzer,
    ) -> Self {
        SmartCrusherPlanner {
            config,
            anchor_selector,
            scorer,
            analyzer,
        }
    }

    pub fn create_plan(
        &self,
        analysis: &ArrayAnalysis,
        items: &[Value],
        query_context: &str,
        preserve_fields: Option<&[String]>,
        effective_max_items: Option<usize>,
        item_strings: Option<&[String]>,
    ) -> CompressionPlan {
        let max_items = effective_max_items.unwrap_or(self.config.max_items_after_crush);

        let mut plan = CompressionPlan {
            strategy: analysis.recommended_strategy,
            constant_fields: if self.config.factor_out_constants {
                analysis.constant_fields.clone()
            } else {
                BTreeMap::new()
            },
            ..CompressionPlan::default()
        };

        if analysis.recommended_strategy == CompressionStrategy::Skip {
            plan.keep_indices = (0..items.len()).collect();
            return plan;
        }

        match analysis.recommended_strategy {
            CompressionStrategy::TimeSeries => self.plan_time_series(
                analysis,
                items,
                plan,
                query_context,
                preserve_fields,
                max_items,
                item_strings,
            ),
            CompressionStrategy::ClusterSample => self.plan_cluster_sample(
                analysis,
                items,
                plan,
                query_context,
                preserve_fields,
                max_items,
                item_strings,
            ),
            CompressionStrategy::TopN => self.plan_top_n(
                analysis,
                items,
                plan,
                query_context,
                preserve_fields,
                max_items,
                item_strings,
            ),
            _ => self.plan_smart_sample(
                analysis,
                items,
                plan,
                query_context,
                preserve_fields,
                max_items,
                item_strings,
            ),
        }
    }

    #[allow(clippy::too_many_arguments)]
    pub fn plan_smart_sample(
        &self,
        analysis: &ArrayAnalysis,
        items: &[Value],
        mut plan: CompressionPlan,
        query_context: &str,
        preserve_fields: Option<&[String]>,
        max_items: usize,
        item_strings: Option<&[String]>,
    ) -> CompressionPlan {
        let n = items.len();
        let mut keep: BTreeSet<usize> = BTreeSet::new();
        let anchor_pattern = map_to_anchor_pattern(CompressionStrategy::SmartSample);
        keep.extend(self.anchor_selector.select_anchors(
            items,
            max_items,
            anchor_pattern,
            query_or_none(query_context),
        ));

        keep.extend(must_keep(items, item_strings));

        for (name, stats) in &analysis.field_stats {
            for_each_anomaly(
                name,
                stats,
                items,
                self.config.variance_threshold,
                &mut keep,
            );
        }

        if self.config.preserve_change_points {
            for stats in analysis.field_stats.values() {
                for &cp in &stats.change_points {
                    for offset in -1_isize..=1 {
                        let idx = cp as isize + offset;
                        if idx >= 0 && (idx as usize) < n {
                            keep.insert(idx as usize);
                        }
                    }
                }
            }
        }

        self.apply_query_signals(items, query_context, item_strings, &mut keep, false);

        self.apply_preserve_field_matches(items, query_context, preserve_fields, &mut keep);

        let final_keep =
            prioritize_indices(self.config, &keep, items, n, Some(analysis), max_items);
        plan.keep_indices = final_keep.into_iter().collect();
        plan
    }

    #[allow(clippy::too_many_arguments)]
    pub fn plan_top_n(
        &self,
        analysis: &ArrayAnalysis,
        items: &[Value],
        mut plan: CompressionPlan,
        query_context: &str,
        preserve_fields: Option<&[String]>,
        max_items: usize,
        item_strings: Option<&[String]>,
    ) -> CompressionPlan {
        let mut score_field: Option<&str> = None;
        let mut max_confidence = 0.0_f64;
        for (name, stats) in &analysis.field_stats {
            let (is_score, confidence) = detect_score_field_statistically(stats, items);
            if is_score && confidence > max_confidence {
                score_field = Some(name);
                max_confidence = confidence;
            }
        }

        let Some(score_field) = score_field else {
            return self.plan_smart_sample(
                analysis,
                items,
                plan,
                query_context,
                preserve_fields,
                max_items,
                item_strings,
            );
        };

        plan.sort_field = Some(score_field.to_string());
        let mut keep: BTreeSet<usize> = BTreeSet::new();

        let mut scored: Vec<(usize, f64)> = items
            .iter()
            .enumerate()
            .map(|(i, item)| {
                let score = item
                    .as_object()
                    .and_then(|o| o.get(score_field))
                    .and_then(|v| v.as_f64())
                    .unwrap_or(0.0);
                (i, score)
            })
            .collect();
        scored.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap_or(std::cmp::Ordering::Equal));

        let top_count = max_items.saturating_sub(3);
        for (idx, _) in scored.iter().take(top_count) {
            keep.insert(*idx);
        }

        keep.extend(must_keep(items, item_strings));

        if !query_context.is_empty() {
            let anchors = extract_query_anchors(query_context);
            for (i, item) in items.iter().enumerate() {
                if !keep.contains(&i) && item_matches_anchors(item, &anchors) {
                    keep.insert(i);
                }
            }
        }

        if !query_context.is_empty() {
            let owned_strings: Vec<String>;
            let strs: Vec<&str> = match item_strings {
                Some(arr) => arr.iter().map(|s| s.as_str()).collect(),
                None => {
                    owned_strings = items
                        .iter()
                        .map(|i| serde_json::to_string(i).unwrap_or_default())
                        .collect();
                    owned_strings.iter().map(|s| s.as_str()).collect()
                }
            };
            let scores = self.scorer.score_batch(&strs, Some(query_context));
            let high_threshold = (self.config.relevance_threshold * 2.0).max(0.5);
            let max_relevance_adds = 3_usize;
            let mut added = 0;
            for (i, sc) in scores.iter().enumerate() {
                if !keep.contains(&i) && *sc >= high_threshold {
                    keep.insert(i);
                    added += 1;
                    if added >= max_relevance_adds {
                        break;
                    }
                }
            }
        }

        self.apply_preserve_field_matches(items, query_context, preserve_fields, &mut keep);

        plan.keep_count = keep.len();
        plan.keep_indices = keep.into_iter().collect();
        plan
    }

    #[allow(clippy::too_many_arguments)]
    pub fn plan_cluster_sample(
        &self,
        analysis: &ArrayAnalysis,
        items: &[Value],
        mut plan: CompressionPlan,
        query_context: &str,
        preserve_fields: Option<&[String]>,
        max_items: usize,
        item_strings: Option<&[String]>,
    ) -> CompressionPlan {
        let n = items.len();
        let mut keep: BTreeSet<usize> = BTreeSet::new();

        let anchor_pattern = map_to_anchor_pattern(CompressionStrategy::ClusterSample);
        keep.extend(self.anchor_selector.select_anchors(
            items,
            max_items,
            anchor_pattern,
            query_or_none(query_context),
        ));

        keep.extend(must_keep(items, item_strings));

        let mut message_field: Option<&str> = None;
        let mut max_uniqueness = 0.0_f64;
        for (name, stats) in &analysis.field_stats {
            if stats.field_type == "string"
                && stats.unique_ratio > max_uniqueness
                && stats.unique_ratio > 0.3
            {
                message_field = Some(name);
                max_uniqueness = stats.unique_ratio;
            }
        }

        if let Some(field) = message_field {
            plan.cluster_field = Some(field.to_string());
            let mut clusters: BTreeMap<String, Vec<usize>> = BTreeMap::new();
            for (i, item) in items.iter().enumerate() {
                let msg = item
                    .as_object()
                    .and_then(|o| o.get(field))
                    .and_then(|v| v.as_str())
                    .unwrap_or("");
                let truncated: String = msg.chars().take(50).collect();
                let mut hasher = DefaultHasher::new();
                truncated.hash(&mut hasher);
                let hash = format!("{:x}", hasher.finish());
                clusters.entry(hash).or_default().push(i);
            }
            for indices in clusters.values() {
                for &idx in indices.iter().take(2) {
                    keep.insert(idx);
                }
            }
        }

        self.apply_query_signals(items, query_context, item_strings, &mut keep, false);

        self.apply_preserve_field_matches(items, query_context, preserve_fields, &mut keep);

        let final_keep =
            prioritize_indices(self.config, &keep, items, n, Some(analysis), max_items);
        plan.keep_indices = final_keep.into_iter().collect();
        plan
    }

    #[allow(clippy::too_many_arguments)]
    pub fn plan_time_series(
        &self,
        analysis: &ArrayAnalysis,
        items: &[Value],
        mut plan: CompressionPlan,
        query_context: &str,
        preserve_fields: Option<&[String]>,
        max_items: usize,
        item_strings: Option<&[String]>,
    ) -> CompressionPlan {
        let n = items.len();
        let mut keep: BTreeSet<usize> = BTreeSet::new();

        let anchor_pattern = map_to_anchor_pattern(CompressionStrategy::TimeSeries);
        keep.extend(self.anchor_selector.select_anchors(
            items,
            max_items,
            anchor_pattern,
            query_or_none(query_context),
        ));

        for stats in analysis.field_stats.values() {
            for &cp in &stats.change_points {
                for offset in -2_isize..=2 {
                    let idx = cp as isize + offset;
                    if idx >= 0 && (idx as usize) < n {
                        keep.insert(idx as usize);
                    }
                }
            }
        }

        keep.extend(must_keep(items, item_strings));

        self.apply_query_signals(items, query_context, item_strings, &mut keep, false);

        self.apply_preserve_field_matches(items, query_context, preserve_fields, &mut keep);

        let final_keep =
            prioritize_indices(self.config, &keep, items, n, Some(analysis), max_items);
        plan.keep_indices = final_keep.into_iter().collect();
        plan
    }

    fn apply_query_signals(
        &self,
        items: &[Value],
        query_context: &str,
        item_strings: Option<&[String]>,
        keep: &mut BTreeSet<usize>,
        keep_existing_only: bool,
    ) {
        if query_context.is_empty() {
            return;
        }

        let anchors = extract_query_anchors(query_context);
        for (i, item) in items.iter().enumerate() {
            if keep_existing_only && keep.contains(&i) {
                continue;
            }
            if item_matches_anchors(item, &anchors) {
                keep.insert(i);
            }
        }

        let owned_strings: Vec<String>;
        let strs: Vec<&str> = match item_strings {
            Some(arr) => arr.iter().map(|s| s.as_str()).collect(),
            None => {
                owned_strings = items
                    .iter()
                    .map(|i| serde_json::to_string(i).unwrap_or_default())
                    .collect();
                owned_strings.iter().map(|s| s.as_str()).collect()
            }
        };
        let scores = self.scorer.score_batch(&strs, Some(query_context));
        for (i, sc) in scores.iter().enumerate() {
            if keep_existing_only && keep.contains(&i) {
                continue;
            }
            if *sc >= self.config.relevance_threshold {
                keep.insert(i);
            }
        }
    }

    fn apply_preserve_field_matches(
        &self,
        items: &[Value],
        query_context: &str,
        preserve_fields: Option<&[String]>,
        keep: &mut BTreeSet<usize>,
    ) {
        let Some(fields) = preserve_fields.filter(|f| !f.is_empty()) else {
            return;
        };
        if query_context.is_empty() {
            return;
        }
        for (i, item) in items.iter().enumerate() {
            if item_has_preserve_field_match(item, fields, query_context) {
                keep.insert(i);
            }
        }
    }
}

pub fn map_to_anchor_pattern(strategy: CompressionStrategy) -> DataPattern {
    match strategy {
        CompressionStrategy::TimeSeries => DataPattern::TimeSeries,
        CompressionStrategy::TopN => DataPattern::SearchResults,
        CompressionStrategy::ClusterSample => DataPattern::Logs,
        _ => DataPattern::Generic,
    }
}

pub fn item_has_preserve_field_match(
    item: &Value,
    preserve_field_hashes: &[String],
    query_context: &str,
) -> bool {
    if query_context.is_empty() {
        return false;
    }
    let Some(obj) = item.as_object() else {
        return false;
    };
    let query_lower = query_context.to_lowercase();

    for (field_name, value) in obj {
        let h = hash_field_name(field_name);
        if !preserve_field_hashes.iter().any(|p| p == &h) {
            continue;
        }
        if value.is_null() {
            continue;
        }
        let value_str = match value {
            Value::String(s) => s.clone(),
            _ => value.to_string(),
        }
        .to_lowercase();
        if value_str.contains(&query_lower) || query_lower.contains(&value_str) {
            return true;
        }
    }
    false
}

fn query_or_none(q: &str) -> Option<&str> {
    if q.is_empty() {
        None
    } else {
        Some(q)
    }
}

fn for_each_anomaly(
    field_name: &str,
    stats: &FieldStats,
    items: &[Value],
    variance_threshold: f64,
    keep: &mut BTreeSet<usize>,
) {
    if stats.field_type != "numeric" {
        return;
    }
    let (Some(mean), Some(var)) = (stats.mean_val, stats.variance) else {
        return;
    };
    if var <= 0.0 {
        return;
    }
    let std = var.sqrt();
    if std <= 0.0 {
        return;
    }
    let threshold = variance_threshold * std;
    for (i, item) in items.iter().enumerate() {
        if let Some(num) = item
            .as_object()
            .and_then(|o| o.get(field_name))
            .and_then(|v| v.as_f64())
        {
            if !num.is_nan() && (num - mean).abs() > threshold {
                keep.insert(i);
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::engines::compression::anchor_selector::AnchorConfig;
    use crate::engines::compression::bm25::BM25Scorer;
    use serde_json::json;

    fn fixture<'a>(
        config: &'a SmartCrusherConfig,
        anchor_selector: &'a AnchorSelector,
        scorer: &'a BM25Scorer,
        analyzer: &'a SmartAnalyzer,
    ) -> SmartCrusherPlanner<'a> {
        SmartCrusherPlanner::new(config, anchor_selector, scorer, analyzer)
    }

    fn make_planner_deps() -> (
        SmartCrusherConfig,
        AnchorSelector,
        BM25Scorer,
        SmartAnalyzer,
    ) {
        let cfg = SmartCrusherConfig::default();
        let asel = AnchorSelector::new(AnchorConfig::default());
        let scorer = BM25Scorer::default();
        let analyzer = SmartAnalyzer::new(cfg.clone());
        (cfg, asel, scorer, analyzer)
    }

    #[test]
    fn anchor_pattern_mapping_matches_python() {
        assert_eq!(
            map_to_anchor_pattern(CompressionStrategy::TimeSeries),
            DataPattern::TimeSeries
        );
        assert_eq!(
            map_to_anchor_pattern(CompressionStrategy::TopN),
            DataPattern::SearchResults
        );
        assert_eq!(
            map_to_anchor_pattern(CompressionStrategy::ClusterSample),
            DataPattern::Logs
        );
        assert_eq!(
            map_to_anchor_pattern(CompressionStrategy::SmartSample),
            DataPattern::Generic
        );
        assert_eq!(
            map_to_anchor_pattern(CompressionStrategy::None),
            DataPattern::Generic
        );
    }

    #[test]
    fn preserve_field_match_query_substring_in_value() {
        let item = json!({"customer_id": "alice"});
        let h = hash_field_name("customer_id");
        let fields = vec![h];
        assert!(item_has_preserve_field_match(
            &item,
            &fields,
            "find user alice please"
        ));
    }

    #[test]
    fn preserve_field_match_value_substring_in_query() {
        let item = json!({"customer_id": "user-12345-alice"});
        let h = hash_field_name("customer_id");
        let fields = vec![h];
        assert!(item_has_preserve_field_match(&item, &fields, "alice"));
    }

    #[test]
    fn preserve_field_no_match_when_field_not_in_hashes() {
        let item = json!({"random_field": "alice"});
        let fields = vec![hash_field_name("customer_id")];
        assert!(!item_has_preserve_field_match(&item, &fields, "alice"));
    }

    #[test]
    fn preserve_field_no_match_when_query_empty() {
        let item = json!({"customer_id": "alice"});
        let fields = vec![hash_field_name("customer_id")];
        assert!(!item_has_preserve_field_match(&item, &fields, ""));
    }

    #[test]
    fn create_plan_skip_returns_all_indices() {
        let (cfg, asel, scorer, analyzer) = make_planner_deps();
        let p = fixture(&cfg, &asel, &scorer, &analyzer);
        let analysis = ArrayAnalysis {
            item_count: 5,
            field_stats: BTreeMap::new(),
            detected_pattern: "generic".to_string(),
            recommended_strategy: CompressionStrategy::Skip,
            constant_fields: BTreeMap::new(),
            estimated_reduction: 0.0,
            crushability: None,
        };
        let items: Vec<Value> = (0..5).map(|i| json!({"id": i})).collect();
        let plan = p.create_plan(&analysis, &items, "", None, None, None);
        assert_eq!(plan.keep_indices, vec![0, 1, 2, 3, 4]);
    }

    #[test]
    fn create_plan_routes_smart_sample_to_smart_sample() {
        let (cfg, asel, scorer, analyzer) = make_planner_deps();
        let p = fixture(&cfg, &asel, &scorer, &analyzer);
        let items: Vec<Value> = (0..30).map(|i| json!({"id": i, "v": i})).collect();
        let analysis = analyzer.analyze_array(&items);
        let plan = p.create_plan(&analysis, &items, "", None, Some(15), None);
        assert!(!plan.keep_indices.is_empty());
        assert!(plan.sort_field.is_none());
        assert!(plan.cluster_field.is_none());
    }

    #[test]
    fn smart_sample_keeps_error_items() {
        let (cfg, asel, scorer, analyzer) = make_planner_deps();
        let p = fixture(&cfg, &asel, &scorer, &analyzer);
        let mut items: Vec<Value> = (0..30)
            .map(|i| json!({"id": i, "msg": format!("ok {}", i)}))
            .collect();
        items.push(json!({"id": 30, "msg": "FATAL: out of memory"}));
        let analysis = analyzer.analyze_array(&items);
        let plan_in = CompressionPlan {
            strategy: CompressionStrategy::SmartSample,
            ..CompressionPlan::default()
        };
        let plan = p.plan_smart_sample(&analysis, &items, plan_in, "", None, 10, None);
        assert!(
            plan.keep_indices.contains(&30),
            "error item must survive plan_smart_sample"
        );
    }

    #[test]
    fn smart_sample_query_anchor_pinned() {
        let (cfg, asel, scorer, analyzer) = make_planner_deps();
        let p = fixture(&cfg, &asel, &scorer, &analyzer);
        let items: Vec<Value> = (0..30)
            .map(|i| {
                json!({
                    "id": i,
                    "uuid": format!("550e8400-e29b-41d4-a716-44665544{:04x}", i),
                })
            })
            .collect();
        let analysis = analyzer.analyze_array(&items);
        let target_uuid = format!("550e8400-e29b-41d4-a716-44665544{:04x}", 17);
        let query = format!("find record {}", target_uuid);
        let plan_in = CompressionPlan {
            strategy: CompressionStrategy::SmartSample,
            ..CompressionPlan::default()
        };
        let plan = p.plan_smart_sample(&analysis, &items, plan_in, &query, None, 10, None);
        assert!(
            plan.keep_indices.contains(&17),
            "item matching query UUID must be kept; got {:?}",
            plan.keep_indices
        );
    }

    #[test]
    fn top_n_falls_back_when_no_score_field() {
        let (cfg, asel, scorer, analyzer) = make_planner_deps();
        let p = fixture(&cfg, &asel, &scorer, &analyzer);
        let items: Vec<Value> = (0..30).map(|i| json!({"id": i})).collect();
        let analysis = analyzer.analyze_array(&items);
        let plan_in = CompressionPlan {
            strategy: CompressionStrategy::TopN,
            ..CompressionPlan::default()
        };
        let plan = p.plan_top_n(&analysis, &items, plan_in, "", None, 10, None);
        assert!(plan.sort_field.is_none());
    }

    #[test]
    fn top_n_keeps_highest_scored_items() {
        let (cfg, asel, scorer, analyzer) = make_planner_deps();
        let p = fixture(&cfg, &asel, &scorer, &analyzer);
        let items: Vec<Value> = (0..20)
            .map(|i| json!({"id": i, "score": (19 - i) as f64 * 0.05}))
            .collect();
        let analysis = analyzer.analyze_array(&items);
        let plan_in = CompressionPlan {
            strategy: CompressionStrategy::TopN,
            ..CompressionPlan::default()
        };
        let plan = p.plan_top_n(&analysis, &items, plan_in, "", None, 10, None);
        assert!(
            plan.keep_indices.contains(&0),
            "highest-scored item (idx 0) should be kept"
        );
    }

    #[test]
    fn cluster_sample_assigns_cluster_field() {
        let (cfg, asel, scorer, analyzer) = make_planner_deps();
        let p = fixture(&cfg, &asel, &scorer, &analyzer);
        let items: Vec<Value> = (0..30)
            .map(|i| {
                json!({
                    "msg": format!("message body for entry {} with content here", i),
                    "level": if i % 2 == 0 { "INFO" } else { "ERROR" },
                })
            })
            .collect();
        let analysis = analyzer.analyze_array(&items);
        let plan_in = CompressionPlan {
            strategy: CompressionStrategy::ClusterSample,
            ..CompressionPlan::default()
        };
        let plan = p.plan_cluster_sample(&analysis, &items, plan_in, "", None, 10, None);
        assert_eq!(plan.cluster_field.as_deref(), Some("msg"));
    }

    #[test]
    fn time_series_keeps_window_around_change_points() {
        let (cfg, asel, scorer, analyzer) = make_planner_deps();
        let p = fixture(&cfg, &asel, &scorer, &analyzer);
        let items: Vec<Value> = (0..60)
            .map(|i| {
                let v = if i < 30 { 1.0 } else { 100.0 };
                json!({"id": i, "value": v})
            })
            .collect();
        let analysis = analyzer.analyze_array(&items);
        let plan_in = CompressionPlan {
            strategy: CompressionStrategy::TimeSeries,
            ..CompressionPlan::default()
        };
        let plan = p.plan_time_series(&analysis, &items, plan_in, "", None, 30, None);
        assert!(!plan.keep_indices.is_empty());
    }
}
