use std::collections::BTreeMap;
use std::sync::OnceLock;
use std::time::Instant;

use regex::Regex;

use crate::runtime::ccr::{self, InMemoryCcrStore};

pub const SCORE_CHANGE_DENSITY_WEIGHT: f64 = 0.03;
pub const SCORE_CHANGE_DENSITY_CAP: f64 = 0.3;
pub const SCORE_CONTEXT_WORD_WEIGHT: f64 = 0.2;
pub const SCORE_CONTEXT_MIN_WORD_LEN: usize = 2;
pub const SCORE_PRIORITY_PATTERN_BOOST: f64 = 0.3;
pub const SCORE_TOTAL_CAP: f64 = 1.0;

#[derive(Debug, Clone)]
pub struct DiffCompressorConfig {
    pub max_context_lines: usize,
    pub max_hunks_per_file: usize,
    pub max_files: usize,
    pub always_keep_additions: bool,
    pub always_keep_deletions: bool,
    pub enable_ccr: bool,
    pub min_lines_for_ccr: usize,
    pub min_compression_ratio_for_ccr: f64,
}

impl Default for DiffCompressorConfig {
    fn default() -> Self {
        Self {
            max_context_lines: 2,
            max_hunks_per_file: 10,
            max_files: 20,
            always_keep_additions: true,
            always_keep_deletions: true,
            enable_ccr: true,
            min_lines_for_ccr: 50,
            min_compression_ratio_for_ccr: 0.8,
        }
    }
}

#[derive(Debug, Clone)]
pub struct DiffCompressionResult {
    pub compressed: String,
    pub original_line_count: usize,
    pub compressed_line_count: usize,
    pub files_affected: usize,
    pub additions: usize,
    pub deletions: usize,
    pub hunks_kept: usize,
    pub hunks_removed: usize,
    pub cache_key: Option<String>,
}

#[derive(Debug, Clone, Default)]
pub struct DiffCompressorStats {
    pub input_lines: usize,
    pub output_lines: usize,
    pub compression_ratio: f64,

    pub files_total: usize,
    pub files_kept: usize,
    pub files_dropped: Vec<String>,

    pub hunks_total: usize,
    pub hunks_kept: usize,
    pub hunks_dropped: usize,
    pub hunks_dropped_per_file: BTreeMap<String, usize>,

    pub context_lines_input: usize,
    pub context_lines_kept: usize,
    pub context_lines_trimmed: usize,

    pub largest_hunk_kept_lines: usize,
    pub largest_hunk_dropped_lines: usize,

    pub file_mode_normalizations: Vec<(String, String)>,

    pub binary_files_simplified: Vec<String>,

    pub parse_warnings: Vec<String>,

    pub processing_duration_us: u64,

    pub cache_key_emitted: bool,
    pub ccr_skipped_reason: Option<String>,
}

#[derive(Debug, Clone)]
pub struct DiffCompressor {
    config: DiffCompressorConfig,
}

impl Default for DiffCompressor {
    fn default() -> Self {
        Self::new(DiffCompressorConfig::default())
    }
}

impl DiffCompressor {
    pub fn new(config: DiffCompressorConfig) -> Self {
        Self { config }
    }

    pub fn compress(&self, content: &str, context: &str) -> DiffCompressionResult {
        self.compress_with_stats(content, context).0
    }

    pub fn compress_with_stats(
        &self,
        content: &str,
        context: &str,
    ) -> (DiffCompressionResult, DiffCompressorStats) {
        self.compress_with_store(content, context, None)
    }

    pub fn compress_with_store(
        &self,
        content: &str,
        context: &str,
        store: Option<&InMemoryCcrStore>,
    ) -> (DiffCompressionResult, DiffCompressorStats) {
        let start = Instant::now();
        let mut stats = DiffCompressorStats::default();

        let lines: Vec<&str> = content.split('\n').collect();
        let original_line_count = lines.len();
        stats.input_lines = original_line_count;

        if original_line_count < self.config.min_lines_for_ccr {
            stats.output_lines = original_line_count;
            stats.compression_ratio = 1.0;
            stats.ccr_skipped_reason = Some("input below min_lines_for_ccr".into());
            stats.processing_duration_us = start.elapsed().as_micros() as u64;
            return (
                DiffCompressionResult {
                    compressed: content.to_string(),
                    original_line_count,
                    compressed_line_count: original_line_count,
                    files_affected: 0,
                    additions: 0,
                    deletions: 0,
                    hunks_kept: 0,
                    hunks_removed: 0,
                    cache_key: None,
                },
                stats,
            );
        }

        let parsed = parse_diff(&lines);
        let pre_diff_lines = parsed.pre_diff_lines;
        let mut diff_files = parsed.files;
        stats.parse_warnings = parsed.parse_warnings;
        stats.files_total = diff_files.len();
        stats.hunks_total = diff_files.iter().map(|f| f.hunks.len()).sum();
        stats.context_lines_input = diff_files
            .iter()
            .flat_map(|f| f.hunks.iter())
            .map(|h| h.context_lines)
            .sum();

        if diff_files.is_empty() {
            stats.output_lines = original_line_count;
            stats.compression_ratio = 1.0;
            stats.ccr_skipped_reason = Some("no diff sections parsed".into());
            stats.processing_duration_us = start.elapsed().as_micros() as u64;
            return (
                DiffCompressionResult {
                    compressed: content.to_string(),
                    original_line_count,
                    compressed_line_count: original_line_count,
                    files_affected: 0,
                    additions: 0,
                    deletions: 0,
                    hunks_kept: 0,
                    hunks_removed: 0,
                    cache_key: None,
                },
                stats,
            );
        }

        score_hunks(&mut diff_files, context);

        if diff_files.len() > self.config.max_files {
            diff_files.sort_by(|a, b| {
                let a_changes = a.total_additions() + a.total_deletions();
                let b_changes = b.total_additions() + b.total_deletions();
                b_changes.cmp(&a_changes)
            });
            let dropped: Vec<DiffFile> = diff_files.split_off(self.config.max_files);
            stats.files_dropped = dropped
                .iter()
                .map(|f| format!("{} -> {}", f.old_file, f.new_file))
                .collect();
        }
        stats.files_kept = diff_files.len();

        for file in diff_files.iter() {
            let label = format!("{} -> {}", file.old_file, file.new_file);
            if let Some(orig) = &file.original_new_file_mode_line {
                if orig != "new file mode 100644" {
                    stats
                        .file_mode_normalizations
                        .push((label.clone(), orig.clone()));
                }
            }
            if let Some(orig) = &file.original_deleted_file_mode_line {
                if orig != "deleted file mode 100644" {
                    stats
                        .file_mode_normalizations
                        .push((label.clone(), orig.clone()));
                }
            }
            if let Some(orig) = &file.original_binary_line {
                if orig != "Binary files differ" {
                    stats.binary_files_simplified.push(orig.clone());
                }
            }
        }

        let mut compressed_files: Vec<DiffFile> = Vec::with_capacity(diff_files.len());
        let mut total_additions = 0usize;
        let mut total_deletions = 0usize;
        let mut hunks_kept_total = 0usize;
        let mut hunks_removed_total = 0usize;
        let mut largest_kept = 0usize;
        let mut largest_dropped = 0usize;
        let mut context_kept_total = 0usize;

        for file in diff_files {
            total_additions += file.total_additions();
            total_deletions += file.total_deletions();

            let original_hunk_count = file.hunks.len();
            let file_label = format!("{} -> {}", file.old_file, file.new_file);

            let (selected, dropped) = select_hunks(file.hunks, self.config.max_hunks_per_file);
            let dropped_count = dropped.len();
            if dropped_count > 0 {
                stats
                    .hunks_dropped_per_file
                    .insert(file_label, dropped_count);
                let max_dropped = dropped.iter().map(|h| h.lines.len()).max().unwrap_or(0);
                if max_dropped > largest_dropped {
                    largest_dropped = max_dropped;
                }
            }

            let mut compressed_hunks: Vec<DiffHunk> = Vec::with_capacity(selected.len());
            for hunk in selected {
                let trimmed = reduce_context(&hunk, self.config.max_context_lines);
                if trimmed.lines.len() > largest_kept {
                    largest_kept = trimmed.lines.len();
                }
                context_kept_total += trimmed.context_lines;
                compressed_hunks.push(trimmed);
            }

            hunks_kept_total += compressed_hunks.len();
            hunks_removed_total += original_hunk_count - compressed_hunks.len();

            compressed_files.push(DiffFile {
                hunks: compressed_hunks,
                ..file
            });
        }

        stats.hunks_kept = hunks_kept_total;
        stats.hunks_dropped = hunks_removed_total;
        stats.context_lines_kept = context_kept_total;
        stats.context_lines_trimmed = stats.context_lines_input.saturating_sub(context_kept_total);
        stats.largest_hunk_kept_lines = largest_kept;
        stats.largest_hunk_dropped_lines = largest_dropped;

        let files_affected = compressed_files.len();

        let mut compressed_output = format_output(
            &pre_diff_lines,
            &compressed_files,
            files_affected,
            total_additions,
            total_deletions,
            hunks_removed_total,
        );
        let compressed_line_count = compressed_output.split('\n').count();

        let savings_threshold = self.config.min_compression_ratio_for_ccr;
        let mut cache_key: Option<String> = None;
        if self.config.enable_ccr
            && (compressed_line_count as f64) < (original_line_count as f64) * savings_threshold
        {
            let key = ccr::compute_key(content.as_bytes());
            compressed_output.push('\n');
            compressed_output.push_str(&format!(
                "[{} lines compressed to {}. Retrieve full diff: hash={}]",
                original_line_count, compressed_line_count, key
            ));
            if let Some(s) = store {
                s.put(&key, content);
            }
            cache_key = Some(key);
            stats.cache_key_emitted = true;
        } else if !self.config.enable_ccr {
            stats.ccr_skipped_reason = Some("ccr disabled".into());
        } else {
            stats.ccr_skipped_reason = Some(format!(
                "compression ratio {:.3} above threshold {:.3}",
                if original_line_count == 0 {
                    1.0
                } else {
                    compressed_line_count as f64 / original_line_count as f64
                },
                savings_threshold
            ));
        }

        stats.output_lines = compressed_line_count;
        stats.compression_ratio = if original_line_count == 0 {
            1.0
        } else {
            compressed_line_count as f64 / original_line_count as f64
        };
        stats.processing_duration_us = start.elapsed().as_micros() as u64;

        let result = DiffCompressionResult {
            compressed: compressed_output,
            original_line_count,
            compressed_line_count,
            files_affected,
            additions: total_additions,
            deletions: total_deletions,
            hunks_kept: hunks_kept_total,
            hunks_removed: hunks_removed_total,
            cache_key,
        };

        (result, stats)
    }
}

#[derive(Debug, Clone)]
struct DiffHunk {
    header: String,
    lines: Vec<String>,
    additions: usize,
    deletions: usize,
    context_lines: usize,
    score: f64,
}

#[derive(Debug, Clone)]
struct DiffFile {
    header: String,
    old_file: String,
    new_file: String,
    hunks: Vec<DiffHunk>,
    is_binary: bool,
    is_new_file: bool,
    is_deleted_file: bool,
    is_renamed: bool,
    rename_lines: Vec<String>,
    original_new_file_mode_line: Option<String>,
    original_deleted_file_mode_line: Option<String>,
    original_binary_line: Option<String>,
}

impl DiffFile {
    fn total_additions(&self) -> usize {
        self.hunks.iter().map(|h| h.additions).sum()
    }
    fn total_deletions(&self) -> usize {
        self.hunks.iter().map(|h| h.deletions).sum()
    }
}

fn hunk_header_regex() -> &'static Regex {
    static RE: OnceLock<Regex> = OnceLock::new();
    RE.get_or_init(|| {
        Regex::new(concat!(
            r"^(?:",
            r"@@ -\d+(?:,\d+)? \+\d+(?:,\d+)? @@",
            r"|",
            r"@@@ -\d+(?:,\d+)? -\d+(?:,\d+)? \+\d+(?:,\d+)? @@@",
            r"|",
            r"@@@@ -\d+(?:,\d+)? -\d+(?:,\d+)? -\d+(?:,\d+)? \+\d+(?:,\d+)? @@@@",
            r")(.*)$"
        ))
        .expect("static regex compiles")
    })
}

fn hunk_new_range_regex() -> &'static Regex {
    static RE: OnceLock<Regex> = OnceLock::new();
    RE.get_or_init(|| Regex::new(r"\+(\d+)").expect("static regex compiles"))
}

fn diff_git_regex() -> &'static Regex {
    static RE: OnceLock<Regex> = OnceLock::new();
    RE.get_or_init(|| Regex::new(r"^diff --git a/(.+) b/(.+)$").expect("static regex compiles"))
}

fn diff_combined_regex() -> &'static Regex {
    static RE: OnceLock<Regex> = OnceLock::new();
    RE.get_or_init(|| Regex::new(r"^diff --combined (.+)$").expect("static regex compiles"))
}

fn diff_cc_regex() -> &'static Regex {
    static RE: OnceLock<Regex> = OnceLock::new();
    RE.get_or_init(|| Regex::new(r"^diff --cc (.+)$").expect("static regex compiles"))
}

fn is_diff_header(line: &str) -> bool {
    diff_git_regex().is_match(line)
        || diff_combined_regex().is_match(line)
        || diff_cc_regex().is_match(line)
}

fn old_file_regex() -> &'static Regex {
    static RE: OnceLock<Regex> = OnceLock::new();
    RE.get_or_init(|| Regex::new(r"^--- (a/(.+)|/dev/null)$").expect("static regex compiles"))
}

fn new_file_regex() -> &'static Regex {
    static RE: OnceLock<Regex> = OnceLock::new();
    RE.get_or_init(|| Regex::new(r"^\+\+\+ (b/(.+)|/dev/null)$").expect("static regex compiles"))
}

fn binary_regex() -> &'static Regex {
    static RE: OnceLock<Regex> = OnceLock::new();
    RE.get_or_init(|| Regex::new(r"^Binary files .+ differ$").expect("static regex compiles"))
}

struct ParsedDiff {
    pre_diff_lines: Vec<String>,
    files: Vec<DiffFile>,
    parse_warnings: Vec<String>,
}

fn parse_diff(lines: &[&str]) -> ParsedDiff {
    let mut files: Vec<DiffFile> = Vec::new();
    let mut current_file: Option<DiffFile> = None;
    let mut current_hunk: Option<DiffHunk> = None;
    let mut pre_diff_lines: Vec<String> = Vec::new();
    let warnings: Vec<String> = Vec::new();

    for &line in lines {
        if is_diff_header(line) {
            if let Some(h) = current_hunk.take() {
                if let Some(f) = current_file.as_mut() {
                    f.hunks.push(h);
                }
            }
            if let Some(f) = current_file.take() {
                files.push(f);
            }
            current_file = Some(DiffFile {
                header: line.to_string(),
                old_file: String::new(),
                new_file: String::new(),
                hunks: Vec::new(),
                is_binary: false,
                is_new_file: false,
                is_deleted_file: false,
                is_renamed: false,
                rename_lines: Vec::new(),
                original_new_file_mode_line: None,
                original_deleted_file_mode_line: None,
                original_binary_line: None,
            });
            continue;
        }

        if current_file.is_none() {
            pre_diff_lines.push(line.to_string());
            continue;
        }

        if let Some(f) = current_file.as_mut() {
            if line.starts_with("new file mode") {
                f.is_new_file = true;
                f.original_new_file_mode_line = Some(line.to_string());
            } else if line.starts_with("deleted file mode") {
                f.is_deleted_file = true;
                f.original_deleted_file_mode_line = Some(line.to_string());
            } else if line.starts_with("rename ")
                || line.starts_with("similarity ")
                || line.starts_with("copy ")
                || line.starts_with("dissimilarity ")
            {
                f.is_renamed = true;
                f.rename_lines.push(line.to_string());
            } else if binary_regex().is_match(line) {
                f.is_binary = true;
                f.original_binary_line = Some(line.to_string());
            }
        }

        if old_file_regex().is_match(line) {
            if let Some(f) = current_file.as_mut() {
                f.old_file = line.to_string();
            }
            continue;
        }

        if new_file_regex().is_match(line) {
            if let Some(f) = current_file.as_mut() {
                f.new_file = line.to_string();
            }
            continue;
        }

        if hunk_header_regex().is_match(line) {
            if let Some(h) = current_hunk.take() {
                if let Some(f) = current_file.as_mut() {
                    f.hunks.push(h);
                }
            }
            current_hunk = Some(DiffHunk {
                header: line.to_string(),
                lines: Vec::new(),
                additions: 0,
                deletions: 0,
                context_lines: 0,
                score: 0.0,
            });
            continue;
        }

        if let Some(h) = current_hunk.as_mut() {
            if line.starts_with('+') && !line.starts_with("+++") {
                h.additions += 1;
                h.lines.push(line.to_string());
            } else if line.starts_with('-') && !line.starts_with("---") {
                h.deletions += 1;
                h.lines.push(line.to_string());
            } else if line.starts_with(' ') || line.is_empty() {
                h.context_lines += 1;
                h.lines.push(line.to_string());
            } else {
                h.lines.push(line.to_string());
            }
        }
    }

    if let Some(h) = current_hunk.take() {
        if let Some(f) = current_file.as_mut() {
            f.hunks.push(h);
        }
    }
    if let Some(f) = current_file.take() {
        files.push(f);
    }

    ParsedDiff {
        pre_diff_lines,
        files,
        parse_warnings: warnings,
    }
}

fn priority_patterns() -> &'static [Regex] {
    static RES: OnceLock<Vec<Regex>> = OnceLock::new();
    RES.get_or_init(|| {
        vec![
            Regex::new(r"(?i)\b(error|exception|fail(?:ed|ure)?|fatal|critical|crash|panic)\b")
                .unwrap(),
            Regex::new(r"(?i)\b(important|note|todo|fixme|hack|xxx|bug|fix)\b").unwrap(),
            Regex::new(r"(?i)\b(security|auth|password|secret|token)\b").unwrap(),
        ]
    })
}

fn score_hunks(files: &mut [DiffFile], context: &str) {
    let context_lower = context.to_lowercase();
    let context_words: Vec<&str> = context_lower.split_whitespace().collect();

    for file in files.iter_mut() {
        for hunk in file.hunks.iter_mut() {
            let mut score: f64 = 0.0;
            score += (hunk.additions as f64 + hunk.deletions as f64) * SCORE_CHANGE_DENSITY_WEIGHT;
            if score > SCORE_CHANGE_DENSITY_CAP {
                score = SCORE_CHANGE_DENSITY_CAP;
            }

            let hunk_content_lower = hunk.lines.join("\n").to_lowercase();

            for word in &context_words {
                if word.len() > SCORE_CONTEXT_MIN_WORD_LEN && hunk_content_lower.contains(word) {
                    score += SCORE_CONTEXT_WORD_WEIGHT;
                }
            }

            for pat in priority_patterns() {
                if pat.is_match(&hunk_content_lower) {
                    score += SCORE_PRIORITY_PATTERN_BOOST;
                    break;
                }
            }

            if score > SCORE_TOTAL_CAP {
                score = SCORE_TOTAL_CAP;
            }
            hunk.score = score;
        }
    }
}

fn select_hunks(hunks: Vec<DiffHunk>, max_per_file: usize) -> (Vec<DiffHunk>, Vec<DiffHunk>) {
    if hunks.len() <= max_per_file {
        return (hunks, Vec::new());
    }
    if hunks.is_empty() {
        return (Vec::new(), Vec::new());
    }

    let n = hunks.len();
    let mut indexed: Vec<(usize, DiffHunk)> = hunks.into_iter().enumerate().collect();

    let first = indexed.remove(0);
    let last = if !indexed.is_empty() {
        Some(indexed.pop().unwrap())
    } else {
        None
    };
    let middle: Vec<(usize, DiffHunk)> = indexed;

    let remaining_slots = if last.is_some() {
        max_per_file.saturating_sub(2)
    } else {
        max_per_file.saturating_sub(1)
    };

    let mut middle_sorted = middle;
    middle_sorted.sort_by(|a, b| {
        b.1.score
            .partial_cmp(&a.1.score)
            .unwrap_or(std::cmp::Ordering::Equal)
    });
    let (kept_middle, dropped_middle): (Vec<_>, Vec<_>) = middle_sorted
        .into_iter()
        .enumerate()
        .partition(|(rank, _)| *rank < remaining_slots);
    let kept_middle: Vec<(usize, DiffHunk)> = kept_middle.into_iter().map(|(_, x)| x).collect();
    let dropped_middle: Vec<DiffHunk> = dropped_middle.into_iter().map(|(_, (_, h))| h).collect();

    let mut selected: Vec<(usize, DiffHunk)> = Vec::with_capacity(max_per_file);
    selected.push(first);
    selected.extend(kept_middle);
    if let Some(l) = last {
        selected.push(l);
    }
    selected.sort_by(|a, b| {
        let la = extract_line_number(&a.1.header);
        let lb = extract_line_number(&b.1.header);
        la.cmp(&lb)
    });

    let _ = n;
    (
        selected.into_iter().map(|(_, h)| h).collect(),
        dropped_middle,
    )
}

fn extract_line_number(header: &str) -> usize {
    if let Some(caps) = hunk_new_range_regex().captures(header) {
        if let Some(m) = caps.get(1) {
            if let Ok(n) = m.as_str().parse::<usize>() {
                return n;
            }
        }
    }
    0
}

fn reduce_context(hunk: &DiffHunk, max_context: usize) -> DiffHunk {
    let change_positions: Vec<usize> = hunk
        .lines
        .iter()
        .enumerate()
        .filter_map(|(i, l)| {
            if l.starts_with('+') || l.starts_with('-') {
                Some(i)
            } else {
                None
            }
        })
        .collect();

    if change_positions.is_empty() {
        let take = max_context.min(hunk.lines.len());
        let lines: Vec<String> = hunk.lines.iter().take(take).cloned().collect();
        return DiffHunk {
            header: hunk.header.clone(),
            lines,
            additions: 0,
            deletions: 0,
            context_lines: take,
            score: hunk.score,
        };
    }

    let mut keep = std::collections::BTreeSet::new();
    for &pos in &change_positions {
        keep.insert(pos);
        let lo = pos.saturating_sub(max_context);
        for i in lo..pos {
            keep.insert(i);
        }
        let hi = (pos + max_context + 1).min(hunk.lines.len());
        for i in (pos + 1)..hi {
            keep.insert(i);
        }
    }

    for (i, line) in hunk.lines.iter().enumerate() {
        if line.starts_with('\\') {
            keep.insert(i);
        }
    }

    let mut new_lines: Vec<String> = Vec::with_capacity(keep.len());
    let mut additions = 0usize;
    let mut deletions = 0usize;
    let mut context_lines = 0usize;
    for &i in &keep {
        let line = &hunk.lines[i];
        new_lines.push(line.clone());
        if line.starts_with('+') {
            additions += 1;
        } else if line.starts_with('-') {
            deletions += 1;
        } else {
            context_lines += 1;
        }
    }

    DiffHunk {
        header: hunk.header.clone(),
        lines: new_lines,
        additions,
        deletions,
        context_lines,
        score: hunk.score,
    }
}

fn format_output(
    pre_diff_lines: &[String],
    files: &[DiffFile],
    files_affected: usize,
    total_additions: usize,
    total_deletions: usize,
    hunks_removed: usize,
) -> String {
    let mut out_lines: Vec<String> = Vec::new();

    for l in pre_diff_lines {
        out_lines.push(l.clone());
    }

    for f in files {
        out_lines.push(f.header.clone());

        for l in &f.rename_lines {
            out_lines.push(l.clone());
        }

        if f.is_new_file {
            out_lines.push("new file mode 100644".into());
        } else if f.is_deleted_file {
            out_lines.push("deleted file mode 100644".into());
        }

        if f.is_binary {
            out_lines.push("Binary files differ".into());
            continue;
        }

        if !f.old_file.is_empty() {
            out_lines.push(f.old_file.clone());
        }
        if !f.new_file.is_empty() {
            out_lines.push(f.new_file.clone());
        }

        for h in &f.hunks {
            out_lines.push(h.header.clone());
            for l in &h.lines {
                out_lines.push(l.clone());
            }
        }
    }

    if hunks_removed > 0 || files_affected > 0 {
        let mut parts = Vec::with_capacity(3);
        parts.push(format!("{} files changed", files_affected));
        parts.push(format!("+{} -{} lines", total_additions, total_deletions));
        if hunks_removed > 0 {
            parts.push(format!("{} hunks omitted", hunks_removed));
        }
        out_lines.push(format!("[{}]", parts.join(", ")));
    }

    out_lines.join("\n")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn short_input_passes_through() {
        let c = DiffCompressor::default();
        let input = "diff --git a/x b/x\n@@ -1 +1 @@\n-a\n+b";
        let r = c.compress(input, "");
        assert_eq!(r.compressed, input);
        assert_eq!(r.original_line_count, 4);
        assert_eq!(r.compressed_line_count, 4);
        assert_eq!(r.files_affected, 0);
        assert!(r.cache_key.is_none());
    }

    #[test]
    fn non_diff_input_passes_through() {
        let c = DiffCompressor::default();
        let input = "this is not a diff\n".repeat(60);
        let r = c.compress(&input, "");
        assert_eq!(r.compressed, input);
        assert_eq!(r.files_affected, 0);
    }

    #[test]
    fn count_split_lines_matches_python_split_n() {
        assert_eq!("".split('\n').count(), 1);
        assert_eq!("a".split('\n').count(), 1);
        assert_eq!("a\n".split('\n').count(), 2);
        assert_eq!("a\nb".split('\n').count(), 2);
        assert_eq!("\n".split('\n').count(), 2);
    }

    #[test]
    fn stats_are_emitted_with_compress_with_stats() {
        let c = DiffCompressor::default();
        let input = "noise\n".repeat(60);
        let (_r, stats) = c.compress_with_stats(&input, "");
        assert_eq!(stats.input_lines, 61);
        assert_eq!(stats.output_lines, 61);
        assert_eq!(stats.compression_ratio, 1.0);
        assert!(stats.parse_warnings.is_empty());
        assert!(stats.ccr_skipped_reason.is_some());
    }

    fn build_synthetic_diff(n_files: usize) -> String {
        let mut s = String::new();
        for i in 0..n_files {
            s.push_str(&format!(
                "diff --git a/file_{i}.py b/file_{i}.py\n--- a/file_{i}.py\n+++ b/file_{i}.py\n@@ -1,10 +1,12 @@\n",
            ));
            for k in 0..5 {
                s.push_str(&format!(" context_{k}_{i}\n"));
            }
            for k in 0..3 {
                s.push_str(&format!("-removed_{k}_{i}\n"));
            }
            for k in 0..5 {
                s.push_str(&format!("+added_{k}_{i}\n"));
            }
            for k in 0..5 {
                s.push_str(&format!(" tail_{k}_{i}\n"));
            }
        }
        s.push_str("# variant 1");
        s
    }

    #[test]
    fn synthetic_eight_file_diff_matches_known_shape() {
        let c = DiffCompressor::default();
        let input = build_synthetic_diff(8);
        let r = c.compress(&input, "");
        assert_eq!(r.original_line_count, 177);
        assert_eq!(r.files_affected, 8);
        assert_eq!(r.additions, 40);
        assert_eq!(r.deletions, 24);
        assert_eq!(r.hunks_kept, 8);
        assert_eq!(r.hunks_removed, 0);
        assert_eq!(r.compressed_line_count, 129);
        assert!(r.cache_key.is_some());
    }

    fn build_n_hunk_diff(n: usize) -> String {
        let mut s = String::from("diff --git a/big.py b/big.py\n--- a/big.py\n+++ b/big.py\n");
        for i in 0..n {
            let start = i * 100 + 1;
            s.push_str(&format!("@@ -{0},6 +{0},6 @@\n", start));
            s.push_str(&format!(" ctx_a_{i}\n"));
            s.push_str(&format!(" ctx_b_{i}\n"));
            s.push_str(&format!("-old_{i}\n"));
            s.push_str(&format!("+new_{i}\n"));
            s.push_str(&format!(" ctx_c_{i}\n"));
            s.push_str(&format!(" ctx_d_{i}\n"));
        }
        s
    }

    #[test]
    fn max_hunks_per_file_cap_drops_excess_and_records_stats() {
        let cfg = DiffCompressorConfig {
            max_hunks_per_file: 10,
            ..Default::default()
        };
        let input = build_n_hunk_diff(15);
        let (result, stats) = DiffCompressor::new(cfg).compress_with_stats(&input, "");

        assert_eq!(result.hunks_kept, 10, "kept 10 hunks");
        assert_eq!(result.hunks_removed, 5, "dropped 5");
        assert_eq!(stats.hunks_total, 15);
        assert_eq!(stats.hunks_dropped, 5);
        let per_file_total: usize = stats.hunks_dropped_per_file.values().sum();
        assert_eq!(per_file_total, 5);
        assert!(stats.largest_hunk_dropped_lines >= 6);
    }

    #[test]
    fn max_files_cap_drops_files_and_records_names_in_stats() {
        let cfg = DiffCompressorConfig {
            max_files: 20,
            ..Default::default()
        };
        let input = build_synthetic_diff(25);
        let (_result, stats) = DiffCompressor::new(cfg).compress_with_stats(&input, "");

        assert_eq!(stats.files_total, 25);
        assert_eq!(stats.files_kept, 20);
        assert_eq!(
            stats.files_dropped.len(),
            5,
            "expected 5 dropped file labels"
        );
        for label in &stats.files_dropped {
            assert!(
                label.contains("-> "),
                "label `{label}` should contain ` -> `"
            );
        }
    }

    #[test]
    fn file_mode_normalization_is_recorded_for_executable_bit() {
        let mut input = String::from(
            "diff --git a/script.sh b/script.sh\n\
             new file mode 100755\n\
             --- /dev/null\n\
             +++ b/script.sh\n\
             @@ -0,0 +1,3 @@\n\
             +#!/bin/sh\n\
             +echo hi\n\
             +exit 0\n",
        );
        for _ in 0..50 {
            input.push_str("# pad\n");
        }
        let (_r, stats) = DiffCompressor::default().compress_with_stats(&input, "");
        assert_eq!(stats.file_mode_normalizations.len(), 1, "{stats:?}");
        let (label, original) = &stats.file_mode_normalizations[0];
        assert!(label.contains("script.sh"));
        assert_eq!(original, "new file mode 100755");
    }

    #[test]
    fn binary_files_simplification_is_recorded() {
        let mut input = String::from(
            "diff --git a/img.png b/img.png\n\
             Binary files a/img.png and b/img.png differ\n",
        );
        for _ in 0..60 {
            input.push_str("# pad\n");
        }
        let (_r, stats) = DiffCompressor::default().compress_with_stats(&input, "");
        assert_eq!(stats.binary_files_simplified.len(), 1, "{stats:?}");
        assert_eq!(
            stats.binary_files_simplified[0],
            "Binary files a/img.png and b/img.png differ"
        );
    }

    #[test]
    fn min_compression_ratio_for_ccr_is_configurable() {
        let r = DiffCompressor::default().compress(&build_synthetic_diff(8), "");
        assert!(r.cache_key.is_some(), "default 0.8 should emit CCR");

        let cfg = DiffCompressorConfig {
            min_compression_ratio_for_ccr: 0.5,
            ..Default::default()
        };
        let (r2, stats) =
            DiffCompressor::new(cfg).compress_with_stats(&build_synthetic_diff(8), "");
        assert!(
            r2.cache_key.is_none(),
            "0.5 threshold should suppress CCR for 0.729-ratio compression"
        );
        assert!(!stats.cache_key_emitted);
        assert!(stats.ccr_skipped_reason.is_some());
    }

    #[test]
    fn compress_with_store_persists_original_under_cache_key() {
        use crate::runtime::ccr::InMemoryCcrStore;
        let store = InMemoryCcrStore::new();
        let input = build_synthetic_diff(8);
        let (r, stats) = DiffCompressor::default().compress_with_store(&input, "", Some(&store));
        let key = r.cache_key.expect("default 0.8 should emit CCR");
        assert!(stats.cache_key_emitted);
        assert!(r.compressed.contains(&format!("hash={key}")));
        assert_eq!(store.get(&key).as_deref(), Some(input.as_str()));
    }

    #[test]
    fn compress_with_store_none_matches_compress_with_stats_behavior() {
        let input = build_synthetic_diff(8);
        let (legacy_result, _) = DiffCompressor::default().compress_with_stats(&input, "");
        let (new_result, _) = DiffCompressor::default().compress_with_store(&input, "", None);
        assert_eq!(new_result.compressed, legacy_result.compressed);
        assert_eq!(new_result.cache_key, legacy_result.cache_key);
    }

    #[test]
    fn compress_with_store_no_op_when_ccr_skipped() {
        use crate::runtime::ccr::InMemoryCcrStore;
        let cfg = DiffCompressorConfig {
            min_compression_ratio_for_ccr: 0.1,
            ..Default::default()
        };
        let store = InMemoryCcrStore::new();
        let (r, _) = DiffCompressor::new(cfg).compress_with_store(
            &build_synthetic_diff(8),
            "",
            Some(&store),
        );
        assert!(r.cache_key.is_none());
        assert_eq!(store.len(), 0);
    }

    #[test]
    fn score_constants_match_inline_values() {
        assert_eq!(SCORE_CHANGE_DENSITY_WEIGHT, 0.03);
        assert_eq!(SCORE_CHANGE_DENSITY_CAP, 0.3);
        assert_eq!(SCORE_CONTEXT_WORD_WEIGHT, 0.2);
        assert_eq!(SCORE_CONTEXT_MIN_WORD_LEN, 2);
        assert_eq!(SCORE_PRIORITY_PATTERN_BOOST, 0.3);
        assert_eq!(SCORE_TOTAL_CAP, 1.0);
    }

    #[test]
    fn bugfix_rename_markers_are_preserved_in_output() {
        let input = "diff --git a/old.py b/new.py\n\
                     similarity index 92%\n\
                     rename from old.py\n\
                     rename to new.py\n\
                     --- a/old.py\n\
                     +++ b/new.py\n\
                     @@ -1,3 +1,3 @@\n\
                      ctx_a\n\
                     -old_line\n\
                     +new_line\n\
                      ctx_b\n";
        let cfg = DiffCompressorConfig {
            min_lines_for_ccr: 5,
            ..Default::default()
        };
        let r = DiffCompressor::new(cfg).compress(input, "");
        assert!(
            r.compressed.contains("similarity index 92%"),
            "missing 'similarity index' marker:\n{}",
            r.compressed
        );
        assert!(
            r.compressed.contains("rename from old.py"),
            "missing 'rename from':\n{}",
            r.compressed
        );
        assert!(
            r.compressed.contains("rename to new.py"),
            "missing 'rename to':\n{}",
            r.compressed
        );
    }

    #[test]
    fn bugfix_combined_diff_3way_content_is_parsed_and_emitted() {
        let input = "diff --git a/merge.py b/merge.py\n\
                     --- a/merge.py\n\
                     +++ b/merge.py\n\
                     @@@ -1,3 -1,3 +1,4 @@@\n\
                       unchanged_a\n\
                      -old_branch_1\n\
                     - old_branch_2\n\
                     ++new_in_merge\n\
                      +new_added\n\
                       unchanged_b\n";
        let cfg = DiffCompressorConfig {
            min_lines_for_ccr: 5,
            ..Default::default()
        };
        let (r, stats) = DiffCompressor::new(cfg).compress_with_stats(input, "");
        assert!(
            r.compressed.contains("@@@ -1,3 -1,3 +1,4 @@@"),
            "@@@ header not preserved:\n{}",
            r.compressed
        );
        assert!(
            r.compressed.contains("++new_in_merge"),
            "combined-diff +/+ content not preserved:\n{}",
            r.compressed
        );
        assert!(
            stats.files_total > 0,
            "parser found no files; combined-diff still broken"
        );
    }

    #[test]
    fn bugfix_no_newline_marker_preserved_despite_distance() {
        let input = "diff --git a/last.txt b/last.txt\n\
                     --- a/last.txt\n\
                     +++ b/last.txt\n\
                     @@ -1,8 +1,8 @@\n\
                     -old_first\n\
                     +new_first\n\
                      ctx_a\n\
                      ctx_b\n\
                      ctx_c\n\
                      ctx_d\n\
                      ctx_e\n\
                      ctx_f\n\
                     \\ No newline at end of file\n";
        let cfg = DiffCompressorConfig {
            min_lines_for_ccr: 5,
            ..Default::default()
        };
        let r = DiffCompressor::new(cfg).compress(input, "");
        assert!(
            r.compressed.contains("\\ No newline at end of file"),
            "no-newline marker dropped by context trim:\n{}",
            r.compressed
        );
    }

    #[test]
    fn gap_diff_combined_header_starts_a_file() {
        let input = "diff --combined merge.py\n\
                     index abc..def..ghi 100644\n\
                     --- a/merge.py\n\
                     +++ b/merge.py\n\
                     @@@ -1,3 -1,3 +1,4 @@@\n\
                       ctx_a\n\
                     - removed_p1\n\
                      -removed_p2\n\
                     ++added_in_merge\n\
                       ctx_b\n";
        let cfg = DiffCompressorConfig {
            min_lines_for_ccr: 5,
            ..Default::default()
        };
        let r = DiffCompressor::new(cfg).compress(input, "");
        assert_eq!(r.files_affected, 1);
        assert!(r.compressed.contains("diff --combined merge.py"));
        assert!(r.compressed.contains("@@@ -1,3 -1,3 +1,4 @@@"));
        assert!(r.compressed.contains("++added_in_merge"));
    }

    #[test]
    fn gap_diff_cc_header_starts_a_file() {
        let input = "diff --cc cc_target.py\n\
                     index abc..def..ghi\n\
                     --- a/cc_target.py\n\
                     +++ b/cc_target.py\n\
                     @@@ -1,3 -1,3 +1,4 @@@\n\
                       ctx\n\
                     - p1_removed\n\
                      -p2_removed\n\
                     ++merge_added\n\
                       more_ctx\n";
        let cfg = DiffCompressorConfig {
            min_lines_for_ccr: 5,
            ..Default::default()
        };
        let r = DiffCompressor::new(cfg).compress(input, "");
        assert_eq!(r.files_affected, 1);
        assert!(r.compressed.contains("diff --cc cc_target.py"));
        assert!(r.compressed.contains("++merge_added"));
    }

    #[test]
    fn bugfix_pre_diff_content_is_preserved() {
        let input = "commit abc1234567890\n\
                     Author: Tester <t@example.com>\n\
                     Date:   Mon Apr 25 12:00:00 2026\n\
                     \n    Refactor: rename and modify\n\n\
                     diff --git a/x.py b/x.py\n\
                     --- a/x.py\n\
                     +++ b/x.py\n\
                     @@ -1 +1 @@\n\
                     -a\n\
                     +b\n";
        let cfg = DiffCompressorConfig {
            min_lines_for_ccr: 5,
            ..Default::default()
        };
        let r = DiffCompressor::new(cfg).compress(input, "");
        assert!(
            r.compressed.starts_with("commit abc1234567890"),
            "pre-diff commit header dropped:\n{}",
            r.compressed
        );
        assert!(
            r.compressed.contains("Author: Tester"),
            "pre-diff Author header dropped:\n{}",
            r.compressed
        );
        assert!(
            r.compressed.contains("Refactor: rename and modify"),
            "pre-diff commit message dropped:\n{}",
            r.compressed
        );
        assert!(r.compressed.contains("diff --git a/x.py b/x.py"));
        assert!(r.compressed.contains("-a"));
        assert!(r.compressed.contains("+b"));
    }
}
