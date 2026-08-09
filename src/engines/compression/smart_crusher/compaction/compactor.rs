use std::collections::BTreeMap;
use std::sync::Arc;

use blake3;
use serde_json::Value;

use super::classifier::{classify_cell, CellClass, ClassifyConfig};
use super::ir::{Bucket, CellValue, Compaction, FieldSpec, Row, Schema};
use crate::runtime::ccr::InMemoryCcrStore;

#[derive(Debug, Clone)]
pub struct CompactConfig {
    pub classify: ClassifyConfig,

    pub min_items: usize,

    pub core_field_fraction: f64,

    pub heterogeneous_core_ratio: f64,

    pub max_flatten_inner_keys: usize,

    pub min_buckets: usize,

    pub max_buckets: usize,
}

impl Default for CompactConfig {
    fn default() -> Self {
        Self {
            classify: ClassifyConfig::default(),
            min_items: 2,
            core_field_fraction: 0.8,
            heterogeneous_core_ratio: 0.6,
            max_flatten_inner_keys: 6,
            min_buckets: 2,
            max_buckets: 8,
        }
    }
}

pub fn compact(items: &[Value], cfg: &CompactConfig) -> Compaction {
    compact_inner(items, cfg, None, 0)
}

pub fn compact_with_store(
    items: &[Value],
    cfg: &CompactConfig,
    store: Option<&Arc<InMemoryCcrStore>>,
) -> Compaction {
    compact_inner(items, cfg, store, 0)
}

fn compact_inner(
    items: &[Value],
    cfg: &CompactConfig,
    store: Option<&Arc<InMemoryCcrStore>>,
    depth: usize,
) -> Compaction {
    if items.len() < cfg.min_items || depth >= 50 {
        return Compaction::Untouched(Value::Array(items.to_vec()));
    }
    if !items.iter().all(|v| matches!(v, Value::Object(_))) {
        return Compaction::Untouched(Value::Array(items.to_vec()));
    }

    let key_freqs = compute_key_freqs(items);
    let total = items.len();
    let core_threshold = (total as f64 * cfg.core_field_fraction).ceil() as usize;
    let core_count = key_freqs.values().filter(|&&f| f >= core_threshold).count();
    let total_keys = key_freqs.len();

    let core_ratio = if total_keys == 0 {
        1.0
    } else {
        core_count as f64 / total_keys as f64
    };

    if core_ratio < cfg.heterogeneous_core_ratio {
        if let Some(disc) = detect_discriminator(items, &key_freqs, cfg) {
            return bucket_by(items, &disc, cfg, store, depth);
        }
    }

    build_homogeneous_table(items, &key_freqs, cfg, store, depth)
}

fn compute_key_freqs(items: &[Value]) -> BTreeMap<String, usize> {
    let mut freqs: BTreeMap<String, usize> = BTreeMap::new();
    for item in items {
        if let Value::Object(map) = item {
            for k in map.keys() {
                *freqs.entry(k.clone()).or_insert(0) += 1;
            }
        }
    }
    freqs
}

fn build_homogeneous_table(
    items: &[Value],
    key_freqs: &BTreeMap<String, usize>,
    cfg: &CompactConfig,
    store: Option<&Arc<InMemoryCcrStore>>,
    depth: usize,
) -> Compaction {
    let mut keys: Vec<(&String, &usize)> = key_freqs.iter().collect();
    keys.sort_by(|a, b| b.1.cmp(a.1).then_with(|| a.0.cmp(b.0)));
    let ordered_keys: Vec<String> = keys.into_iter().map(|(k, _)| k.clone()).collect();

    let total = items.len();
    let mut field_specs: Vec<FieldSpec> = ordered_keys
        .iter()
        .map(|k| FieldSpec {
            name: k.clone(),
            type_tag: infer_type_tag(items, k),
            nullable: key_freqs[k] < total
                || items
                    .iter()
                    .filter_map(|v| v.as_object())
                    .any(|o| matches!(o.get(k), Some(Value::Null))),
        })
        .collect();

    let mut rows: Vec<Row> = items
        .iter()
        .map(|item| build_row(item, &ordered_keys, cfg, store, depth))
        .collect();

    flatten_uniform_nested(&mut field_specs, &mut rows, cfg);

    Compaction::Table {
        schema: Schema {
            fields: field_specs,
        },
        rows,
        original_count: items.len(),
    }
}

fn build_row(
    item: &Value,
    ordered_keys: &[String],
    cfg: &CompactConfig,
    store: Option<&Arc<InMemoryCcrStore>>,
    depth: usize,
) -> Row {
    let obj = match item.as_object() {
        Some(o) => o,
        None => return Row::new(vec![]),
    };
    let cells: Vec<CellValue> = ordered_keys
        .iter()
        .map(|k| match obj.get(k) {
            None => CellValue::Missing,
            Some(v) => cell_from_value(v, cfg, store, depth),
        })
        .collect();
    Row::new(cells)
}

fn cell_from_value(
    v: &Value,
    cfg: &CompactConfig,
    store: Option<&Arc<InMemoryCcrStore>>,
    depth: usize,
) -> CellValue {
    match classify_cell(v, &cfg.classify) {
        CellClass::Scalar => CellValue::Scalar(v.clone()),
        CellClass::JsonObject => CellValue::Scalar(v.clone()),
        CellClass::JsonArray => {
            if let Value::Array(items) = v {
                if items.iter().all(|i| matches!(i, Value::Object(_))) && items.len() >= 2 {
                    return CellValue::Nested(Box::new(compact_inner(
                        items,
                        cfg,
                        store,
                        depth + 1,
                    )));
                }
            }
            CellValue::Scalar(v.clone())
        }
        CellClass::StringifiedJson(parsed) => {
            if let Value::Array(items) = &parsed {
                if items.iter().all(|i| matches!(i, Value::Object(_))) && items.len() >= 2 {
                    return CellValue::Nested(Box::new(compact_inner(
                        items,
                        cfg,
                        store,
                        depth + 1,
                    )));
                }
            }
            CellValue::Scalar(parsed)
        }
        CellClass::Opaque(kind) => {
            let s = match v {
                Value::String(s) => s,
                _ => return CellValue::Scalar(v.clone()),
            };
            let ccr_hash = hash_opaque(s.as_bytes());
            if let Some(store) = store {
                store.put(&ccr_hash, s);
            }
            CellValue::OpaqueRef {
                ccr_hash,
                byte_size: s.len(),
                kind,
            }
        }
    }
}

fn flatten_uniform_nested(specs: &mut Vec<FieldSpec>, rows: &mut [Row], cfg: &CompactConfig) {
    let mut i = 0;
    while i < specs.len() {
        let inner_keys = match uniform_object_keys(specs, rows, i) {
            Some(keys) if !keys.is_empty() && keys.len() <= cfg.max_flatten_inner_keys => keys,
            _ => {
                i += 1;
                continue;
            }
        };

        let parent_name = specs[i].name.clone();
        let new_specs: Vec<FieldSpec> = inner_keys
            .iter()
            .map(|k| FieldSpec {
                name: format!("{parent_name}.{k}"),
                type_tag: "string".into(),
                nullable: false,
            })
            .collect();
        let n_new = new_specs.len();

        specs.splice(i..i + 1, new_specs);

        for row in rows.iter_mut() {
            let original = row.0.remove(i);
            let inner_obj: Option<serde_json::Map<String, Value>> = match original {
                CellValue::Scalar(Value::Object(map)) => Some(map),
                CellValue::Missing => None,
                _ => unreachable!(
                    "uniform_object_keys guarantees every cell is Scalar(Object) or Missing"
                ),
            };
            let expanded: Vec<CellValue> = inner_keys
                .iter()
                .map(|k| match &inner_obj {
                    None => CellValue::Missing,
                    Some(map) => match map.get(k) {
                        None => CellValue::Missing,
                        Some(v) => CellValue::Scalar(v.clone()),
                    },
                })
                .collect();
            for (offset, cell) in expanded.into_iter().enumerate() {
                row.0.insert(i + offset, cell);
            }
        }

        for offset in 0..n_new {
            let col_idx = i + offset;
            let mut nullable = false;
            let inferred = infer_type_tag_from_cells(rows, col_idx, &mut nullable);
            specs[col_idx].type_tag = inferred;
            specs[col_idx].nullable = nullable;
        }

        i += n_new;
    }
}

fn infer_type_tag_from_cells(rows: &[Row], col: usize, nullable: &mut bool) -> String {
    let mut tag = "string";
    let mut saw_value = false;
    for row in rows {
        if let Some(cell) = row.0.get(col) {
            match cell {
                CellValue::Missing => *nullable = true,
                CellValue::Scalar(Value::Null) => *nullable = true,
                CellValue::Scalar(v) => {
                    if !saw_value {
                        tag = type_tag_for(v);
                        saw_value = true;
                    } else if type_tag_for(v) != tag {
                        tag = "json";
                    }
                }
                _ => tag = "json",
            }
        }
    }
    tag.to_string()
}

fn uniform_object_keys(specs: &[FieldSpec], rows: &[Row], col: usize) -> Option<Vec<String>> {
    if specs[col].name.contains('.') {
        return None;
    }
    let mut canonical: Option<Vec<String>> = None;
    let mut saw_object = false;
    for row in rows {
        let cell = row.0.get(col)?;
        match cell {
            CellValue::Missing => continue,
            CellValue::Scalar(Value::Object(map)) => {
                let keys: Vec<String> = map.keys().cloned().collect();
                saw_object = true;
                match &canonical {
                    None => canonical = Some(keys),
                    Some(existing) => {
                        if existing != &keys {
                            return None;
                        }
                    }
                }
            }
            _ => return None,
        }
    }
    if !saw_object {
        return None;
    }
    canonical
}

fn infer_type_tag(items: &[Value], key: &str) -> String {
    let mut tag: Option<&'static str> = None;
    for it in items {
        if let Some(v) = it.as_object().and_then(|m| m.get(key)) {
            if matches!(v, Value::Null) {
                continue;
            }
            let t = type_tag_for(v);
            match tag {
                None => tag = Some(t),
                Some(existing) if existing != t => {
                    tag = Some("json");
                    break;
                }
                _ => {}
            }
        }
    }
    tag.unwrap_or("string").to_string()
}

fn type_tag_for(v: &Value) -> &'static str {
    match v {
        Value::Null => "null",
        Value::Bool(_) => "bool",
        Value::Number(n) if n.is_i64() || n.is_u64() => "int",
        Value::Number(_) => "float",
        Value::String(_) => "string",
        Value::Object(_) | Value::Array(_) => "json",
    }
}

fn hash_opaque(bytes: &[u8]) -> String {
    let h = blake3::hash(bytes);
    h.to_hex().as_str()[..12].to_string()
}

fn detect_discriminator(
    items: &[Value],
    key_freqs: &BTreeMap<String, usize>,
    cfg: &CompactConfig,
) -> Option<String> {
    let total = items.len();
    let mut best: Option<(String, usize)> = None;

    for (k, &freq) in key_freqs {
        if freq < total {
            continue;
        }
        let mut values: Vec<&str> = Vec::with_capacity(total);
        let mut all_strings = true;
        for item in items {
            match item.as_object().and_then(|m| m.get(k)) {
                Some(Value::String(s)) => values.push(s.as_str()),
                _ => {
                    all_strings = false;
                    break;
                }
            }
        }
        if !all_strings {
            continue;
        }
        let mut distinct: std::collections::HashSet<&str> = std::collections::HashSet::new();
        for v in &values {
            distinct.insert(*v);
        }
        let n = distinct.len();
        if n < cfg.min_buckets || n > cfg.max_buckets {
            continue;
        }
        if n as f64 / total as f64 > 0.7 {
            continue;
        }
        let score = n;
        match &best {
            None => best = Some((k.clone(), score)),
            Some((_, s)) if score > *s => best = Some((k.clone(), score)),
            _ => {}
        }
    }
    best.map(|(k, _)| k)
}

fn bucket_by(
    items: &[Value],
    discriminator: &str,
    cfg: &CompactConfig,
    store: Option<&Arc<InMemoryCcrStore>>,
    depth: usize,
) -> Compaction {
    let mut groups: BTreeMap<String, Vec<Value>> = BTreeMap::new();
    for item in items {
        let key = item
            .as_object()
            .and_then(|m| m.get(discriminator))
            .and_then(|v| v.as_str())
            .unwrap_or("__missing__")
            .to_string();
        groups.entry(key).or_default().push(item.clone());
    }
    let buckets: Vec<Bucket> = groups
        .into_iter()
        .map(|(key, group_items)| {
            let inner = compact_inner(&group_items, cfg, store, depth + 1);
            match inner {
                Compaction::Table { schema, rows, .. } => Bucket {
                    key: Value::String(key),
                    schema,
                    rows,
                },
                _ => Bucket {
                    key: Value::String(key),
                    schema: Schema {
                        fields: vec![FieldSpec {
                            name: "value".into(),
                            type_tag: "json".into(),
                            nullable: false,
                        }],
                    },
                    rows: group_items
                        .into_iter()
                        .map(|v| Row::new(vec![CellValue::Scalar(v)]))
                        .collect(),
                },
            }
        })
        .collect();
    Compaction::Buckets {
        discriminator: discriminator.to_string(),
        buckets,
        original_count: items.len(),
    }
}

#[cfg(test)]
mod tests {
    use super::super::ir::OpaqueKind;
    use super::*;
    use serde_json::json;

    fn cfg() -> CompactConfig {
        CompactConfig::default()
    }

    #[test]
    fn empty_or_single_is_untouched() {
        let items: Vec<Value> = vec![];
        assert!(matches!(compact(&items, &cfg()), Compaction::Untouched(_)));
        let items = vec![json!({"a": 1})];
        assert!(matches!(compact(&items, &cfg()), Compaction::Untouched(_)));
    }

    #[test]
    fn non_object_array_is_untouched() {
        let items = vec![json!(1), json!(2), json!(3)];
        assert!(matches!(compact(&items, &cfg()), Compaction::Untouched(_)));
    }

    #[test]
    fn pure_tabular_produces_table() {
        let items = vec![
            json!({"id": 1, "name": "alice", "status": "ok"}),
            json!({"id": 2, "name": "bob", "status": "ok"}),
            json!({"id": 3, "name": "carol", "status": "fail"}),
        ];
        match compact(&items, &cfg()) {
            Compaction::Table {
                schema,
                rows,
                original_count,
            } => {
                assert_eq!(original_count, 3);
                assert_eq!(rows.len(), 3);
                let names = schema.field_names();
                assert!(names.contains(&"id"));
                assert!(names.contains(&"name"));
                assert!(names.contains(&"status"));
                let id_spec = schema.fields.iter().find(|f| f.name == "id").unwrap();
                assert_eq!(id_spec.type_tag, "int");
            }
            other => panic!("expected Table, got {other:?}"),
        }
    }

    #[test]
    fn nested_uniform_is_flattened() {
        let items = vec![
            json!({"id": 1, "meta": {"region": "us", "tier": "gold"}}),
            json!({"id": 2, "meta": {"region": "eu", "tier": "silver"}}),
            json!({"id": 3, "meta": {"region": "us", "tier": "bronze"}}),
        ];
        match compact(&items, &cfg()) {
            Compaction::Table { schema, rows, .. } => {
                let names = schema.field_names();
                assert!(names.contains(&"meta.region"), "got {names:?}");
                assert!(names.contains(&"meta.tier"), "got {names:?}");
                assert!(!names.contains(&"meta"));
                assert_eq!(rows[0].len(), schema.fields.len());
            }
            other => panic!("expected Table, got {other:?}"),
        }
    }

    #[test]
    fn nested_mixed_keys_stay_nested() {
        let items = vec![
            json!({"id": 1, "meta": {"region": "us"}}),
            json!({"id": 2, "meta": {"region": "eu", "tier": "silver"}}),
            json!({"id": 3, "meta": {"tier": "bronze"}}),
        ];
        match compact(&items, &cfg()) {
            Compaction::Table { schema, .. } => {
                let names = schema.field_names();
                assert!(names.contains(&"meta"));
                assert!(!names.iter().any(|n| n.starts_with("meta.")));
            }
            other => panic!("expected Table, got {other:?}"),
        }
    }

    #[test]
    fn stringified_json_array_recurses() {
        let items = vec![
            json!({"event": "batch", "payload": r#"[{"x":1},{"x":2},{"x":3}]"#}),
            json!({"event": "batch", "payload": r#"[{"x":4},{"x":5}]"#}),
        ];
        match compact(&items, &cfg()) {
            Compaction::Table { rows, .. } => {
                let payload_idx = 1;
                let cell0 = &rows[0].0[0];
                let cell1 = &rows[0].0[1];
                let nested_count = [cell0, cell1]
                    .iter()
                    .filter(|c| matches!(***c, CellValue::Nested(_)))
                    .count();
                let _ = payload_idx;
                assert_eq!(nested_count, 1, "expected exactly one Nested cell");
            }
            other => panic!("expected Table, got {other:?}"),
        }
    }

    #[test]
    fn opaque_cell_becomes_ccr_ref() {
        let big = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=".repeat(8);
        let items = vec![
            json!({"id": 1, "blob": big.clone()}),
            json!({"id": 2, "blob": big.clone()}),
        ];
        match compact(&items, &cfg()) {
            Compaction::Table { rows, schema, .. } => {
                let blob_idx = schema
                    .fields
                    .iter()
                    .position(|f| f.name == "blob")
                    .expect("blob col");
                match &rows[0].0[blob_idx] {
                    CellValue::OpaqueRef {
                        ccr_hash,
                        byte_size,
                        kind,
                    } => {
                        assert!(!ccr_hash.is_empty());
                        assert_eq!(*byte_size, big.len());
                        assert_eq!(*kind, OpaqueKind::Base64Blob);
                    }
                    other => panic!("expected OpaqueRef, got {other:?}"),
                }
            }
            other => panic!("expected Table, got {other:?}"),
        }
    }

    #[test]
    fn heterogeneous_array_buckets_by_discriminator() {
        let items = vec![
            json!({"type": "user", "id": 1, "name": "alice"}),
            json!({"type": "user", "id": 2, "name": "bob"}),
            json!({"type": "order", "id": 99, "total": 50}),
            json!({"type": "order", "id": 100, "total": 75}),
        ];
        match compact(&items, &cfg()) {
            Compaction::Buckets {
                discriminator,
                buckets,
                original_count,
            } => {
                assert_eq!(discriminator, "type");
                assert_eq!(buckets.len(), 2);
                assert_eq!(original_count, 4);
                let total_rows: usize = buckets.iter().map(|b| b.rows.len()).sum();
                assert_eq!(total_rows, 4);
            }
            other => panic!("expected Buckets, got {other:?}"),
        }
    }

    #[test]
    fn id_like_field_not_chosen_as_discriminator() {
        let items = vec![
            json!({"id": "a1", "kind": "x"}),
            json!({"id": "a2", "kind": "x"}),
            json!({"id": "a3", "kind": "y"}),
            json!({"id": "a4", "kind": "y"}),
        ];
        let mut freqs = BTreeMap::new();
        freqs.insert("id".to_string(), 4);
        freqs.insert("kind".to_string(), 4);
        let disc = detect_discriminator(&items, &freqs, &cfg());
        assert_eq!(disc.as_deref(), Some("kind"));
    }

    #[test]
    fn stable_field_ordering() {
        let items = vec![
            json!({"common": 1, "z_rare": 1}),
            json!({"common": 2, "a_rare": 1}),
            json!({"common": 3}),
        ];
        match compact(&items, &cfg()) {
            Compaction::Table { schema, .. } => {
                assert_eq!(schema.fields[0].name, "common");
                assert_eq!(schema.fields[1].name, "a_rare");
                assert_eq!(schema.fields[2].name, "z_rare");
            }
            other => panic!("got {other:?}"),
        }
    }

    #[test]
    fn nullable_field_marked() {
        let items = vec![
            json!({"id": 1, "tag": "a"}),
            json!({"id": 2}),
            json!({"id": 3, "tag": null}),
        ];
        match compact(&items, &cfg()) {
            Compaction::Table { schema, .. } => {
                let tag = schema.fields.iter().find(|f| f.name == "tag").unwrap();
                assert!(tag.nullable);
                let id = schema.fields.iter().find(|f| f.name == "id").unwrap();
                assert!(!id.nullable);
            }
            other => panic!("got {other:?}"),
        }
    }

    #[test]
    fn hash_opaque_stable_and_short() {
        let h1 = hash_opaque(b"hello world");
        let h2 = hash_opaque(b"hello world");
        let h3 = hash_opaque(b"different");
        assert_eq!(h1, h2);
        assert_ne!(h1, h3);
        assert_eq!(h1.len(), 12);
        assert_eq!(h1, "d74981efa70a");
    }

    #[test]
    fn opaque_payload_is_stored_under_marker_hash() {
        use crate::runtime::ccr::InMemoryCcrStore;
        use std::sync::Arc;

        let big = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=".repeat(8);
        let items = vec![
            json!({"id": 1, "blob": big.clone()}),
            json!({"id": 2, "blob": big.clone()}),
        ];

        let store: Arc<InMemoryCcrStore> = Arc::new(InMemoryCcrStore::new());
        let c = compact_with_store(&items, &cfg(), Some(&store));

        let hash = match &c {
            Compaction::Table { rows, schema, .. } => {
                let blob_idx = schema
                    .fields
                    .iter()
                    .position(|f| f.name == "blob")
                    .expect("blob col");
                match &rows[0].0[blob_idx] {
                    CellValue::OpaqueRef { ccr_hash, .. } => ccr_hash.clone(),
                    other => panic!("expected OpaqueRef, got {other:?}"),
                }
            }
            other => panic!("expected Table, got {other:?}"),
        };

        assert_eq!(store.get(&hash).as_deref(), Some(big.as_str()));
        assert_eq!(hash, hash_opaque(big.as_bytes()));
    }

    #[test]
    fn store_presence_does_not_change_the_ir() {
        use crate::runtime::ccr::InMemoryCcrStore;
        use std::sync::Arc;

        let big = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=".repeat(8);
        let items = vec![
            json!({"id": 1, "blob": big.clone()}),
            json!({"id": 2, "blob": big.clone()}),
        ];

        let without = compact(&items, &cfg());
        let store: Arc<InMemoryCcrStore> = Arc::new(InMemoryCcrStore::new());
        let with = compact_with_store(&items, &cfg(), Some(&store));

        use super::super::{Formatter, JsonFormatter};
        let fmt = JsonFormatter::new();
        assert_eq!(fmt.format(&without), fmt.format(&with));
        assert!(!store.is_empty());
    }
}
