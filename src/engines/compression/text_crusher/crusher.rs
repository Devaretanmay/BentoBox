use std::cmp::Ordering;
use std::collections::HashSet;

use super::config::TextCrusherConfig;
use crate::engines::compression::bm25::{BM25Scorer, RelevanceScorer};

const KEYWORDS: [&str; 10] = [
    "error",
    "exception",
    "failed",
    "failure",
    "fail",
    "warning",
    "traceback",
    "assert",
    "todo",
    "fixme",
];

#[derive(Debug, Clone)]
pub struct TextCrusherResult {
    pub compressed: String,
}

pub struct TextCrusher {
    config: TextCrusherConfig,
    scorer: BM25Scorer,
}

impl Default for TextCrusher {
    fn default() -> Self {
        TextCrusher::new(TextCrusherConfig::default())
    }
}

impl TextCrusher {
    pub fn new(config: TextCrusherConfig) -> Self {
        TextCrusher {
            config,
            scorer: BM25Scorer::default(),
        }
    }

    fn passthrough(content: &str, _n_segments: usize) -> TextCrusherResult {
        TextCrusherResult {
            compressed: content.to_string(),
        }
    }

    pub fn compress(
        &self,
        content: &str,
        context: &str,
        target_ratio: Option<f64>,
    ) -> TextCrusherResult {
        let cfg = &self.config;
        let ratio = target_ratio.unwrap_or(cfg.target_ratio).clamp(0.05, 1.0);

        let segments = split_segments(content);
        if segments.len() < cfg.min_segments_for_crush {
            return Self::passthrough(content, segments.len());
        }

        let n = segments.len();
        let total_chars: usize = segments.iter().map(|s| s.len()).sum();
        let target_chars = ((total_chars as f64 * ratio) as usize).max(1);

        let seg_refs: Vec<&str> = segments.iter().map(|s| s.as_str()).collect();
        let relevance = self.scorer.score_batch(&seg_refs, Some(context));
        let seg_tokens: Vec<Vec<String>> = segments.iter().map(|s| tokens(s)).collect();

        let mut scores = vec![0.0f64; n];
        for i in 0..n {
            let recency = (i as f64 + 1.0) / n as f64;
            let rel = relevance.get(i).copied().unwrap_or(0.0);
            let words: Vec<&str> = segments[i].split_whitespace().collect();
            let salient = words.iter().filter(|w| is_salient(w)).count();
            let salience = salient as f64 / (words.len() as f64 + 1.0);
            let mut score =
                cfg.w_recency * recency + cfg.w_relevance * rel + cfg.w_salience * salience;
            if segments[i].len() < cfg.min_segment_chars {
                score *= 0.25;
            }
            scores[i] = score;
        }

        let mut order: Vec<usize> = (0..n).collect();
        order.sort_by(|&a, &b| {
            scores[b]
                .partial_cmp(&scores[a])
                .unwrap_or(Ordering::Equal)
                .then(a.cmp(&b))
        });

        let mut kept = vec![false; n];
        let mut seen: HashSet<String> = HashSet::new();
        let mut kept_chars = 0usize;
        let mut kept_count = 0usize;
        for &i in &order {
            if kept_chars >= target_chars {
                break;
            }
            let sh = shingles(&seg_tokens[i], 3);
            if !sh.is_empty() {
                let covered =
                    sh.iter().filter(|s| seen.contains(*s)).count() as f64 / sh.len() as f64;
                if covered >= cfg.near_dup_threshold {
                    continue;
                }
            }
            kept[i] = true;
            kept_count += 1;
            for s in sh {
                seen.insert(s);
            }
            kept_chars += segments[i].len();
        }

        if kept_count == 0 {
            return Self::passthrough(content, n);
        }

        let compressed = (0..n)
            .filter(|&i| kept[i])
            .map(|i| segments[i].as_str())
            .collect::<Vec<_>>()
            .join("\n");
        TextCrusherResult { compressed }
    }
}

fn split_segments(text: &str) -> Vec<String> {
    let mut segs = Vec::new();
    for line in text.split('\n') {
        let trimmed = line.trim();
        if trimmed.is_empty() {
            continue;
        }
        let mut cur = String::new();
        let mut prev_term = false;
        for c in trimmed.chars() {
            if prev_term && c.is_whitespace() {
                let s = cur.trim();
                if !s.is_empty() {
                    segs.push(s.to_string());
                }
                cur.clear();
                prev_term = false;
                continue;
            }
            cur.push(c);
            prev_term = matches!(c, '.' | '!' | '?');
        }
        let s = cur.trim();
        if !s.is_empty() {
            segs.push(s.to_string());
        }
    }
    segs
}

fn tokens(text: &str) -> Vec<String> {
    let mut out = Vec::new();
    let mut cur = String::new();
    for c in text.chars() {
        if c.is_alphanumeric() || c == '_' {
            for lc in c.to_lowercase() {
                cur.push(lc);
            }
        } else if !cur.is_empty() {
            out.push(std::mem::take(&mut cur));
        }
    }
    if !cur.is_empty() {
        out.push(cur);
    }
    out
}

fn shingles(words: &[String], k: usize) -> HashSet<String> {
    let mut set = HashSet::new();
    if words.is_empty() {
        return set;
    }
    if words.len() < k {
        for size in 1..=words.len() {
            for w in words.windows(size) {
                set.insert(w.join("\u{1}"));
            }
        }
        return set;
    }
    for w in words.windows(k) {
        set.insert(w.join("\u{1}"));
    }
    set
}

fn is_salient(word: &str) -> bool {
    if word.chars().any(|c| c.is_ascii_digit()) {
        return true;
    }
    let lower = word
        .trim_matches(|c: char| !c.is_alphanumeric())
        .to_lowercase();
    if KEYWORDS.contains(&lower.as_str()) {
        return true;
    }
    let alpha: Vec<char> = word.chars().filter(|c| c.is_alphabetic()).collect();
    if alpha.len() >= 2 && alpha.iter().all(|c| c.is_uppercase()) {
        return true;
    }
    if let Some(dot) = word.find('.') {
        let a = &word[..dot];
        let b = &word[dot + 1..];
        if !a.is_empty()
            && !b.is_empty()
            && a.chars()
                .next()
                .is_some_and(|c| c.is_alphabetic() || c == '_')
            && b.chars()
                .next()
                .is_some_and(|c| c.is_alphabetic() || c == '_')
        {
            return true;
        }
    }
    false
}

#[cfg(test)]
mod tests {
    use super::*;

    fn doc(n: usize) -> String {
        (0..n)
            .map(|i| format!("Sentence number {i} describes a distinct topic {i} in some detail."))
            .collect::<Vec<_>>()
            .join(" ")
    }

    #[test]
    fn extractive_and_compresses() {
        let content = doc(40);
        let r = TextCrusher::default().compress(&content, "", Some(0.3));
        assert!(r.compressed.split_whitespace().count() < content.split_whitespace().count());
        let orig: HashSet<&str> = content.split_whitespace().collect();
        assert!(r.compressed.split_whitespace().all(|w| orig.contains(w)));
    }

    #[test]
    fn deterministic() {
        let content = doc(40);
        let tc = TextCrusher::default();
        assert_eq!(
            tc.compress(&content, "", Some(0.4)).compressed,
            tc.compress(&content, "", Some(0.4)).compressed
        );
    }

    #[test]
    fn passthrough_when_small() {
        let r = TextCrusher::default().compress("one. two. three.", "", None);
        assert_eq!(r.compressed, "one. two. three.");
    }
}
