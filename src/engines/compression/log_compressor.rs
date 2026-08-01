use std::collections::{BTreeMap, BTreeSet};
use std::sync::OnceLock;

use aho_corasick::{AhoCorasick, AhoCorasickBuilder, MatchKind};

use regex::Regex;

use crate::engines::compression::adaptive_sizer::compute_optimal_k;
use crate::runtime::ccr::{self, InMemoryCcrStore};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum LogFormat {
    Pytest,
    Npm,
    Cargo,
    Jest,
    Make,
    Generic,
}

impl LogFormat {
    pub fn as_str(&self) -> &'static str {
        match self {
            LogFormat::Pytest => "pytest",
            LogFormat::Npm => "npm",
            LogFormat::Cargo => "cargo",
            LogFormat::Jest => "jest",
            LogFormat::Make => "make",
            LogFormat::Generic => "generic",
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum LogLevel {
    Error,
    Fail,
    Warn,
    Info,
    Debug,
    Trace,
    Unknown,
}

impl LogLevel {
    pub fn as_str(&self) -> &'static str {
        match self {
            LogLevel::Error => "error",
            LogLevel::Fail => "fail",
            LogLevel::Warn => "warn",
            LogLevel::Info => "info",
            LogLevel::Debug => "debug",
            LogLevel::Trace => "trace",
            LogLevel::Unknown => "unknown",
        }
    }
}

#[derive(Debug, Clone)]
pub struct LogLine {
    pub line_number: usize,
    pub content: String,
    pub level: LogLevel,
    pub is_stack_trace: bool,
    pub is_summary: bool,
    pub score: f32,
}

impl PartialEq for LogLine {
    fn eq(&self, other: &Self) -> bool {
        self.line_number == other.line_number
    }
}

impl Eq for LogLine {}

impl std::hash::Hash for LogLine {
    fn hash<H: std::hash::Hasher>(&self, state: &mut H) {
        self.line_number.hash(state);
    }
}

impl LogLine {
    pub fn new(line_number: usize, content: impl Into<String>) -> Self {
        Self {
            line_number,
            content: content.into(),
            level: LogLevel::Unknown,
            is_stack_trace: false,
            is_summary: false,
            score: 0.0,
        }
    }
}

#[derive(Debug, Clone)]
pub struct LogCompressorConfig {
    pub max_errors: usize,
    pub error_context_lines: usize,
    pub keep_first_error: bool,
    pub keep_last_error: bool,
    pub max_stack_traces: usize,
    pub stack_trace_max_lines: usize,
    pub max_warnings: usize,
    pub dedupe_warnings: bool,
    pub keep_summary_lines: bool,
    pub max_total_lines: usize,
    pub enable_ccr: bool,
    pub min_lines_for_ccr: usize,
    pub min_compression_ratio_for_ccr: f64,
}

impl Default for LogCompressorConfig {
    fn default() -> Self {
        Self {
            max_errors: 10,
            error_context_lines: 3,
            keep_first_error: true,
            keep_last_error: true,
            max_stack_traces: 3,
            stack_trace_max_lines: 20,
            max_warnings: 5,
            dedupe_warnings: true,
            keep_summary_lines: true,
            max_total_lines: 100,
            enable_ccr: true,
            min_lines_for_ccr: 50,
            min_compression_ratio_for_ccr: 0.5,
        }
    }
}

#[derive(Debug, Clone)]
pub struct LogCompressionResult {
    pub compressed: String,
    pub original: String,
    pub original_line_count: usize,
    pub compressed_line_count: usize,
    pub format_detected: LogFormat,
    pub compression_ratio: f64,
    pub cache_key: Option<String>,
    pub stats: BTreeMap<String, u64>,
}

impl LogCompressionResult {
    pub fn tokens_saved_estimate(&self) -> i64 {
        let chars_saved = self.original.len() as i64 - self.compressed.len() as i64;
        chars_saved.max(0) / 4
    }
    pub fn lines_omitted(&self) -> usize {
        self.original_line_count
            .saturating_sub(self.compressed_line_count)
    }
}

#[derive(Debug, Clone, Default)]
pub struct LogCompressorStats {
    pub format: Option<LogFormat>,
    pub stack_traces_seen: usize,
    pub stack_traces_kept: usize,
    pub warnings_dropped_by_dedupe: usize,
    pub lines_dropped_by_global_cap: usize,
    pub ccr_emitted: bool,
    pub ccr_skip_reason: Option<&'static str>,
}

struct FormatDetector {
    matchers: Vec<(LogFormat, AhoCorasick)>,
}

impl FormatDetector {
    fn new() -> Self {
        let table: &[(LogFormat, &[&str])] = &[
            (
                LogFormat::Pytest,
                &[
                    "=== FAILURES",
                    "=== ERRORS",
                    "=== test session",
                    "=== short test summary",
                    "PASSED [",
                    "FAILED [",
                    "ERROR [",
                    "SKIPPED [",
                    "collected ",
                ],
            ),
            (
                LogFormat::Npm,
                &["npm ERR!", "npm WARN", "npm info", "npm http"],
            ),
            (
                LogFormat::Cargo,
                &[
                    "Compiling ",
                    "Finished ",
                    "Running ",
                    "warning: ",
                    "error[E",
                ],
            ),
            (LogFormat::Jest, &["PASS ", "FAIL ", "Test Suites:"]),
            (
                LogFormat::Make,
                &["make[", "make:", "gcc ", "g++ ", "clang "],
            ),
        ];

        let matchers = table
            .iter()
            .map(|(fmt, patterns)| {
                let ac = AhoCorasickBuilder::new()
                    .ascii_case_insensitive(false)
                    .match_kind(MatchKind::LeftmostFirst)
                    .build(*patterns)
                    .expect("format-detector automaton must build (static input)");
                (*fmt, ac)
            })
            .collect();
        Self { matchers }
    }

    fn detect(&self, lines: &[&str]) -> LogFormat {
        let n = lines.len();
        let sample: Vec<&str> = if n <= 100 {
            lines.to_vec()
        } else {
            let mut s = Vec::with_capacity(100);
            s.extend_from_slice(&lines[..50]);
            s.extend_from_slice(&lines[n - 50..]);
            s
        };
        let mut best: Option<(LogFormat, usize)> = None;
        for (fmt, ac) in &self.matchers {
            let mut score = 0;
            for line in &sample {
                if ac.is_match(*line) {
                    score += 1;
                }
            }
            if score > 0 && best.map(|(_, s)| score > s).unwrap_or(true) {
                best = Some((*fmt, score));
            }
        }
        best.map(|(f, _)| f).unwrap_or(LogFormat::Generic)
    }
}

struct LevelClassifier {
    automaton: AhoCorasick,
    levels: Vec<LogLevel>,
}

impl LevelClassifier {
    fn new() -> Self {
        let entries: &[(LogLevel, &[&str])] = &[
            (
                LogLevel::Error,
                &[
                    "ERROR", "error", "Error", "FATAL", "fatal", "Fatal", "CRITICAL", "critical",
                ],
            ),
            (
                LogLevel::Fail,
                &["FAIL", "FAILED", "fail", "failed", "Fail", "Failed"],
            ),
            (
                LogLevel::Warn,
                &["WARN", "WARNING", "warn", "warning", "Warn", "Warning"],
            ),
            (LogLevel::Info, &["INFO", "info", "Info"]),
            (LogLevel::Debug, &["DEBUG", "debug", "Debug"]),
            (LogLevel::Trace, &["TRACE", "trace", "Trace"]),
        ];
        let mut patterns = Vec::new();
        let mut levels = Vec::new();
        for (level, words) in entries {
            for w in *words {
                patterns.push(*w);
                levels.push(*level);
            }
        }
        let automaton = AhoCorasickBuilder::new()
            .ascii_case_insensitive(false)
            .match_kind(MatchKind::LeftmostLongest)
            .build(&patterns)
            .expect("level-classifier automaton must build (static input)");
        Self { automaton, levels }
    }

    fn classify(&self, line: &str) -> LogLevel {
        let bytes = line.as_bytes();
        for m in self.automaton.find_iter(line) {
            if is_word_boundary(bytes, m.start(), m.end()) {
                return self.levels[m.pattern().as_usize()];
            }
        }
        LogLevel::Unknown
    }
}

fn is_word_boundary(bytes: &[u8], start: usize, end: usize) -> bool {
    let left_ok = start == 0 || !is_word_byte(bytes[start - 1]);
    let right_ok = end == bytes.len() || !is_word_byte(bytes[end]);
    left_ok && right_ok
}

#[inline]
fn is_word_byte(b: u8) -> bool {
    matches!(b, b'A'..=b'Z' | b'a'..=b'z' | b'0'..=b'9' | b'_')
}

struct StackTraceDetector;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum TraceFlavor {
    PythonTraceback,
    Js,
    Java,
    RustError,
    Go,
}

impl StackTraceDetector {
    fn flavor_for(line: &str) -> Option<TraceFlavor> {
        let trimmed = line.trim_start();
        if trimmed.starts_with("Traceback (most recent call last)")
            || Self::is_python_file_frame(trimmed)
        {
            Some(TraceFlavor::PythonTraceback)
        } else if Self::is_js_at_frame(trimmed) {
            Some(TraceFlavor::Js)
        } else if Self::is_java_at_frame(trimmed) {
            Some(TraceFlavor::Java)
        } else if trimmed.starts_with("--> ") && Self::has_line_col_suffix(trimmed) {
            Some(TraceFlavor::RustError)
        } else if Self::is_go_frame(line) {
            Some(TraceFlavor::Go)
        } else {
            None
        }
    }

    fn is_python_file_frame(s: &str) -> bool {
        s.starts_with("File \"")
            && s.contains("\", line ")
            && s.bytes().next_back().is_some_and(|b| b.is_ascii_digit())
    }

    fn is_js_at_frame(s: &str) -> bool {
        s.starts_with("at ") && s.contains('(') && s.contains(')') && Self::has_line_col_suffix(s)
    }

    fn is_java_at_frame(s: &str) -> bool {
        if !s.starts_with("at ") || !s.contains('(') {
            return false;
        }
        let body = &s[3..s.find('(').unwrap_or(s.len())];
        body.chars()
            .all(|c| c.is_ascii_alphanumeric() || matches!(c, '.' | '_' | '$'))
            && !body.is_empty()
    }

    fn has_line_col_suffix(s: &str) -> bool {
        let bytes = s.as_bytes();
        for i in 0..bytes.len().saturating_sub(2) {
            if bytes[i] == b':' && bytes[i + 1].is_ascii_digit() {
                let mut j = i + 1;
                while j < bytes.len() && bytes[j].is_ascii_digit() {
                    j += 1;
                }
                if j < bytes.len()
                    && bytes[j] == b':'
                    && bytes
                        .get(j + 1)
                        .copied()
                        .map(|b| b.is_ascii_digit())
                        .unwrap_or(false)
                {
                    return true;
                }
            }
        }
        false
    }

    fn is_go_frame(s: &str) -> bool {
        let trimmed = s.trim_start();
        let mut chars = trimmed.chars().peekable();
        let mut saw_digit = false;
        while let Some(&c) = chars.peek() {
            if c.is_ascii_digit() {
                saw_digit = true;
                chars.next();
            } else {
                break;
            }
        }
        if !saw_digit || chars.next() != Some(':') {
            return false;
        }
        while chars.peek() == Some(&' ') {
            chars.next();
        }
        let rest: String = chars.collect();
        rest.starts_with("0x")
            && rest[2..]
                .chars()
                .take_while(|c| c.is_ascii_hexdigit())
                .count()
                > 0
    }

    fn terminates(flavor: TraceFlavor, line: &str) -> bool {
        let trimmed = line.trim_start();
        match flavor {
            TraceFlavor::PythonTraceback => {
                let is_indented_or_blank = line.starts_with([' ', '\t']) || line.is_empty();
                let is_continuation = trimmed.starts_with("Traceback")
                    || trimmed.starts_with("File ")
                    || trimmed.starts_with("During handling")
                    || trimmed.starts_with("The above exception");
                if is_indented_or_blank || is_continuation {
                    false
                } else {
                    !trimmed.starts_with(char::is_uppercase)
                }
            }
            TraceFlavor::Js | TraceFlavor::Java => !trimmed.starts_with("at ") && !line.is_empty(),
            TraceFlavor::RustError => !trimmed.starts_with("--> ") && !line.is_empty(),
            TraceFlavor::Go => {
                !trimmed.chars().next().is_some_and(|c| c.is_ascii_digit()) && !line.is_empty()
            }
        }
    }
}

fn is_summary_line(line: &str) -> bool {
    if line.starts_with("===") || line.starts_with("---") {
        return true;
    }
    let bytes = line.as_bytes();
    let leading_digits = bytes.iter().take_while(|b| b.is_ascii_digit()).count();
    if leading_digits > 0 && line[leading_digits..].starts_with(' ') {
        let rest = &line[leading_digits + 1..];
        for kw in &["passed", "failed", "skipped", "error", "warning"] {
            if rest.starts_with(kw) {
                return true;
            }
        }
    }
    for prefix in &[
        "Test ", "Tests ", "Tests:", "Test:", "Suite ", "Suites ", "Suites:", "Suite:",
    ] {
        if let Some(rest) = line.strip_prefix(prefix) {
            return rest
                .chars()
                .find(|c| !c.is_whitespace())
                .is_some_and(|c| c.is_ascii_digit());
        }
    }
    for prefix in &["TOTAL", "Total", "Summary"] {
        if line.starts_with(prefix) {
            return true;
        }
    }
    for prefix in &["Build", "Compile", "Test"] {
        if line.starts_with(prefix) {
            for outcome in &["succeeded", "failed", "complete"] {
                if line.contains(outcome) {
                    return true;
                }
            }
        }
    }
    false
}

pub struct LogCompressor {
    config: LogCompressorConfig,
    formats: FormatDetector,
    levels: LevelClassifier,
}

impl LogCompressor {
    pub fn new(config: LogCompressorConfig) -> Self {
        Self {
            config,
            formats: FormatDetector::new(),
            levels: LevelClassifier::new(),
        }
    }

    pub fn compress(&self, content: &str, bias: f64) -> (LogCompressionResult, LogCompressorStats) {
        self.compress_with_store(content, bias, None)
    }

    pub fn compress_with_store(
        &self,
        content: &str,
        bias: f64,
        store: Option<&InMemoryCcrStore>,
    ) -> (LogCompressionResult, LogCompressorStats) {
        let mut stats = LogCompressorStats::default();
        let lines: Vec<&str> = content.split('\n').collect();
        let original_line_count = lines.len();

        if original_line_count < self.config.min_lines_for_ccr {
            return (
                LogCompressionResult {
                    compressed: content.to_string(),
                    original: content.to_string(),
                    original_line_count,
                    compressed_line_count: original_line_count,
                    format_detected: LogFormat::Generic,
                    compression_ratio: 1.0,
                    cache_key: None,
                    stats: BTreeMap::new(),
                },
                stats,
            );
        }

        let format = self.formats.detect(&lines);
        stats.format = Some(format);

        let log_lines = self.parse_lines(&lines);

        let selected = self.select_lines(&log_lines, bias, &mut stats);

        let (compressed_body, output_stats) = self.format_output(&selected, &log_lines);
        let mut compressed = compressed_body;
        let ratio = compressed.len() as f64 / content.len().max(1) as f64;

        let mut cache_key = None;
        if self.config.enable_ccr {
            if ratio >= self.config.min_compression_ratio_for_ccr {
                stats.ccr_skip_reason = Some("compression ratio too high");
            } else if let Some(store) = store {
                let key = ccr::compute_key(content.as_bytes());
                store.put(&key, content);
                let marker = format!(
                    "\n[{} lines compressed to {}. Retrieve more: hash={}]",
                    original_line_count,
                    selected.len(),
                    key
                );
                compressed.push_str(&marker);
                cache_key = Some(key);
                stats.ccr_emitted = true;
            } else {
                stats.ccr_skip_reason = Some("no store provided");
            }
        } else {
            stats.ccr_skip_reason = Some("ccr disabled in config");
        }

        let result = LogCompressionResult {
            compressed,
            original: content.to_string(),
            original_line_count,
            compressed_line_count: selected.len(),
            format_detected: format,
            compression_ratio: ratio,
            cache_key,
            stats: output_stats,
        };
        (result, stats)
    }

    pub fn detect_format(&self, lines: &[&str]) -> LogFormat {
        self.formats.detect(lines)
    }

    pub fn parse_lines(&self, lines: &[&str]) -> Vec<LogLine> {
        let mut out: Vec<LogLine> = Vec::with_capacity(lines.len());
        let mut active: Option<TraceFlavor> = None;
        let mut trace_lines = 0usize;

        for (i, line) in lines.iter().enumerate() {
            let mut entry = LogLine::new(i, *line);
            entry.level = self.levels.classify(line);
            entry.is_summary = is_summary_line(line);

            if let Some(flavor) = active {
                if trace_lines >= self.config.stack_trace_max_lines
                    || StackTraceDetector::terminates(flavor, line)
                {
                    active = None;
                    trace_lines = 0;
                    if let Some(new_flavor) = StackTraceDetector::flavor_for(line) {
                        active = Some(new_flavor);
                        trace_lines = 1;
                        entry.is_stack_trace = true;
                    }
                } else {
                    entry.is_stack_trace = true;
                    trace_lines += 1;
                }
            } else if let Some(flavor) = StackTraceDetector::flavor_for(line) {
                active = Some(flavor);
                trace_lines = 1;
                entry.is_stack_trace = true;
            }

            entry.score = score_log_line(&entry);
            out.push(entry);
        }
        out
    }

    pub fn score_line(&self, line: &LogLine) -> f32 {
        score_log_line(line)
    }

    pub fn select_lines(
        &self,
        log_lines: &[LogLine],
        bias: f64,
        stats: &mut LogCompressorStats,
    ) -> Vec<LogLine> {
        let all_strings: Vec<&str> = log_lines.iter().map(|l| l.content.as_str()).collect();
        let adaptive_max =
            compute_optimal_k(&all_strings, bias, 10, Some(self.config.max_total_lines));

        let mut errors: Vec<LogLine> = Vec::new();
        let mut fails: Vec<LogLine> = Vec::new();
        let mut warnings: Vec<LogLine> = Vec::new();
        let mut summaries: Vec<LogLine> = Vec::new();
        let mut stack_traces: Vec<Vec<LogLine>> = Vec::new();
        let mut current_stack: Vec<LogLine> = Vec::new();

        for line in log_lines {
            match line.level {
                LogLevel::Error => errors.push(line.clone()),
                LogLevel::Fail => fails.push(line.clone()),
                LogLevel::Warn => warnings.push(line.clone()),
                _ => {}
            }
            if line.is_stack_trace {
                current_stack.push(line.clone());
            } else if !current_stack.is_empty() {
                stack_traces.push(std::mem::take(&mut current_stack));
            }
            if line.is_summary {
                summaries.push(line.clone());
            }
        }
        if !current_stack.is_empty() {
            stack_traces.push(current_stack);
        }
        stats.stack_traces_seen = stack_traces.len();

        let mut selected: BTreeSet<LogLine> = BTreeSet::new();
        let _ = ();

        for line in self.select_with_first_last(&errors, self.config.max_errors) {
            selected.insert(line);
        }
        for line in self.select_with_first_last(&fails, self.config.max_errors) {
            selected.insert(line);
        }

        let warnings = if self.config.dedupe_warnings {
            let dedup_warnings = self.dedupe_similar(warnings);
            stats.warnings_dropped_by_dedupe = warnings_dropped(log_lines, &dedup_warnings);
            dedup_warnings
        } else {
            warnings
        };
        for line in warnings.into_iter().take(self.config.max_warnings) {
            selected.insert(line);
        }

        for stack in stack_traces.iter().take(self.config.max_stack_traces) {
            stats.stack_traces_kept += 1;
            for line in stack.iter().take(self.config.stack_trace_max_lines) {
                selected.insert(line.clone());
            }
        }

        if self.config.keep_summary_lines {
            for line in summaries {
                selected.insert(line);
            }
        }

        let selected_indices: BTreeSet<usize> = selected.iter().map(|l| l.line_number).collect();
        let mut context_indices: BTreeSet<usize> = BTreeSet::new();
        for &idx in &selected_indices {
            let lo = idx.saturating_sub(self.config.error_context_lines);
            let hi = (idx + self.config.error_context_lines + 1).min(log_lines.len());
            for i in lo..hi {
                if i != idx {
                    context_indices.insert(i);
                }
            }
        }
        for idx in context_indices {
            if !selected_indices.contains(&idx) && idx < log_lines.len() {
                selected.insert(log_lines[idx].clone());
            }
        }

        let mut ordered: Vec<LogLine> = selected.into_iter().collect();
        if ordered.len() > adaptive_max {
            stats.lines_dropped_by_global_cap += ordered.len() - adaptive_max;
            ordered.sort_by(|a, b| {
                b.score
                    .partial_cmp(&a.score)
                    .unwrap_or(std::cmp::Ordering::Equal)
                    .then_with(|| a.line_number.cmp(&b.line_number))
            });
            ordered.truncate(adaptive_max);
            ordered.sort_by_key(|l| l.line_number);
        }
        ordered
    }

    pub fn select_with_first_last(&self, lines: &[LogLine], max_count: usize) -> Vec<LogLine> {
        if lines.len() <= max_count {
            return lines.to_vec();
        }
        let mut out: Vec<LogLine> = Vec::with_capacity(max_count);
        let mut seen: BTreeSet<usize> = BTreeSet::new();
        let push = |line: LogLine, out: &mut Vec<LogLine>, seen: &mut BTreeSet<usize>| {
            if seen.insert(line.line_number) {
                out.push(line);
            }
        };
        if self.config.keep_first_error {
            push(lines[0].clone(), &mut out, &mut seen);
        }
        if self.config.keep_last_error {
            let last = lines.last().unwrap().clone();
            push(last, &mut out, &mut seen);
        }
        let remaining = max_count.saturating_sub(out.len());
        if remaining > 0 {
            let mut by_score = lines.to_vec();
            by_score.sort_by(|a, b| {
                b.score
                    .partial_cmp(&a.score)
                    .unwrap_or(std::cmp::Ordering::Equal)
                    .then_with(|| a.line_number.cmp(&b.line_number))
            });
            for line in by_score.into_iter() {
                if !seen.contains(&line.line_number) {
                    push(line, &mut out, &mut seen);
                    if out.len() >= max_count {
                        break;
                    }
                }
            }
        }
        out
    }

    pub fn dedupe_similar(&self, lines: Vec<LogLine>) -> Vec<LogLine> {
        let mut seen: BTreeSet<String> = BTreeSet::new();
        let mut out: Vec<LogLine> = Vec::with_capacity(lines.len());
        for line in lines {
            let key = normalize_for_dedupe(&line.content);
            if seen.insert(key) {
                out.push(line);
            }
        }
        out
    }

    pub fn format_output(
        &self,
        selected: &[LogLine],
        all_lines: &[LogLine],
    ) -> (String, BTreeMap<String, u64>) {
        let mut stats: BTreeMap<String, u64> = BTreeMap::new();
        stats.insert("errors".into(), count_level(all_lines, LogLevel::Error));
        stats.insert("fails".into(), count_level(all_lines, LogLevel::Fail));
        stats.insert("warnings".into(), count_level(all_lines, LogLevel::Warn));
        stats.insert("info".into(), count_level(all_lines, LogLevel::Info));
        stats.insert("total".into(), all_lines.len() as u64);
        stats.insert("selected".into(), selected.len() as u64);

        let mut output: Vec<String> = selected.iter().map(|l| l.content.clone()).collect();

        let omitted = all_lines.len().saturating_sub(selected.len());
        if omitted > 0 {
            let mut summary_parts: Vec<String> = Vec::new();
            for (label, key) in [
                ("ERROR", "errors"),
                ("FAIL", "fails"),
                ("WARN", "warnings"),
                ("INFO", "info"),
            ] {
                let n = stats.get(key).copied().unwrap_or(0);
                if n > 0 {
                    summary_parts.push(format!("{} {}", n, label));
                }
            }
            if !summary_parts.is_empty() {
                output.push(format!(
                    "[{} lines omitted: {}]",
                    omitted,
                    summary_parts.join(", ")
                ));
            }
        }
        (output.join("\n"), stats)
    }
}

fn count_level(lines: &[LogLine], level: LogLevel) -> u64 {
    lines.iter().filter(|l| l.level == level).count() as u64
}

fn warnings_dropped(all: &[LogLine], deduped: &[LogLine]) -> usize {
    let original_warnings = all.iter().filter(|l| l.level == LogLevel::Warn).count();
    original_warnings.saturating_sub(deduped.len())
}

impl PartialOrd for LogLine {
    fn partial_cmp(&self, other: &Self) -> Option<std::cmp::Ordering> {
        Some(self.cmp(other))
    }
}
impl Ord for LogLine {
    fn cmp(&self, other: &Self) -> std::cmp::Ordering {
        self.line_number.cmp(&other.line_number)
    }
}

fn score_log_line(line: &LogLine) -> f32 {
    let level_score: f32 = match line.level {
        LogLevel::Error | LogLevel::Fail => 1.0,
        LogLevel::Warn => 0.5,
        LogLevel::Info | LogLevel::Unknown => 0.1,
        LogLevel::Debug => 0.05,
        LogLevel::Trace => 0.02,
    };
    let stack_boost: f32 = if line.is_stack_trace { 0.3 } else { 0.0 };
    let summary_boost: f32 = if line.is_summary { 0.4 } else { 0.0 };
    (level_score + stack_boost + summary_boost).min(1.0_f32)
}

fn normalize_for_dedupe(content: &str) -> String {
    let split_at = content.find([':', '=']).unwrap_or(content.len());
    let prefix = &content[..split_at];
    let suffix = &content[split_at..];

    let digit_re = digit_regex();
    let hex_re = hex_regex();
    let path_re = path_regex();

    let stage1 = digit_re.replace_all(suffix, "N");
    let stage2 = hex_re.replace_all(&stage1, "ADDR");
    let stage3 = path_re.replace_all(&stage2, "/PATH/");
    format!("{}{}", prefix, stage3)
}

fn digit_regex() -> &'static Regex {
    static R: OnceLock<Regex> = OnceLock::new();
    R.get_or_init(|| Regex::new(r"\d+").expect("static regex must compile"))
}

fn hex_regex() -> &'static Regex {
    static R: OnceLock<Regex> = OnceLock::new();
    R.get_or_init(|| Regex::new(r"0x[0-9a-fA-F]+").expect("static regex must compile"))
}

fn path_regex() -> &'static Regex {
    static R: OnceLock<Regex> = OnceLock::new();
    R.get_or_init(|| Regex::new(r"/[\w/]+/").expect("static regex must compile"))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::runtime::ccr::InMemoryCcrStore;

    fn cmp() -> LogCompressor {
        LogCompressor::new(LogCompressorConfig::default())
    }

    #[test]
    fn detects_pytest_format() {
        let c = cmp();
        let lines = [
            "============================= test session starts =============================",
            "collected 15 items",
            "tests/test_foo.py::test_basic PASSED [  6%]",
            "FAILED tests/test_foo.py::test_edge",
        ];
        assert_eq!(c.detect_format(&lines), LogFormat::Pytest);
    }

    #[test]
    fn detects_npm_format() {
        let c = cmp();
        let lines = ["npm WARN deprecated x", "npm ERR! something"];
        assert_eq!(c.detect_format(&lines), LogFormat::Npm);
    }

    #[test]
    fn detects_cargo_format() {
        let c = cmp();
        let lines = ["   Compiling app v0.1.0", "warning: unused variable"];
        assert_eq!(c.detect_format(&lines), LogFormat::Cargo);
    }

    #[test]
    fn detects_jest_format() {
        let c = cmp();
        let lines = ["PASS src/app.test.js", "Test Suites: 1 failed"];
        assert_eq!(c.detect_format(&lines), LogFormat::Jest);
    }

    #[test]
    fn detects_make_format() {
        let c = cmp();
        let lines = ["make[1]: Entering directory", "gcc -c main.c"];
        assert_eq!(c.detect_format(&lines), LogFormat::Make);
    }

    #[test]
    fn detects_generic_for_unrecognised_input() {
        let c = cmp();
        let lines = ["INFO Starting application", "DEBUG Initializing"];
        assert_eq!(c.detect_format(&lines), LogFormat::Generic);
    }

    #[test]
    fn level_classifier_word_boundary_matches() {
        let c = cmp();
        let lines = c.parse_lines(&["ERROR: critical", "warning: x", "INFO: x", "no level here"]);
        assert_eq!(lines[0].level, LogLevel::Error);
        assert_eq!(lines[1].level, LogLevel::Warn);
        assert_eq!(lines[2].level, LogLevel::Info);
        assert_eq!(lines[3].level, LogLevel::Unknown);
    }

    #[test]
    fn level_classifier_does_not_overfire_on_substrings() {
        let c = cmp();
        let lines = c.parse_lines(&["informant arrested", "errorless code", "warned-off"]);
        assert_eq!(lines[0].level, LogLevel::Unknown);
        assert_eq!(lines[1].level, LogLevel::Unknown);
        assert_eq!(lines[2].level, LogLevel::Unknown);
    }

    #[test]
    fn fixed_in_3e5_chained_exception_traces_survive_blank_lines() {
        let c = cmp();
        let lines = c.parse_lines(&[
            "Traceback (most recent call last):",
            "  File \"a.py\", line 1, in <module>",
            "ValueError: x",
            "",
            "During handling of the above exception, another exception occurred:",
            "",
            "Traceback (most recent call last):",
            "  File \"b.py\", line 2, in <module>",
            "RuntimeError: y",
        ]);
        for (i, expect) in [
            (0, true),
            (1, true),
            (2, true),
            (3, true),
            (4, true),
            (5, true),
            (6, true),
            (7, true),
            (8, true),
        ] {
            assert_eq!(
                lines[i].is_stack_trace, expect,
                "line {}: '{}' expected is_stack_trace={}",
                i, lines[i].content, expect
            );
        }
    }

    #[test]
    fn fixed_in_3e5_dedupe_preserves_distinct_messages() {
        let c = cmp();
        let warnings = vec![
            LogLine::new(0, "segfault at 0xdeadbeef in thread main"),
            LogLine::new(1, "heap overflow at 0xcafef00d in thread worker"),
        ];
        let deduped = c.dedupe_similar(warnings);
        assert_eq!(deduped.len(), 2);
    }

    #[test]
    fn dedupe_collapses_genuinely_repeated_warnings() {
        let c = cmp();
        let warnings = vec![
            LogLine::new(0, "warning: file /tmp/a/123 issue"),
            LogLine::new(1, "warning: file /tmp/b/999 issue"),
        ];
        let deduped = c.dedupe_similar(warnings);
        assert_eq!(deduped.len(), 1);
    }

    #[test]
    fn select_lines_caps_global_total() {
        let c = LogCompressor::new(LogCompressorConfig {
            max_total_lines: 12,
            stack_trace_max_lines: 2,
            min_lines_for_ccr: 1,
            ..Default::default()
        });
        let mut content = String::new();
        for i in 0..60 {
            content.push_str(&format!("INFO line {}\n", i));
        }
        content.push_str("ERROR something exploded\n");
        content.push_str("ERROR another failure\n");
        let (result, stats) = c.compress(&content, 1.0);
        assert!(result.compressed_line_count <= 12);
        assert_eq!(stats.format, Some(LogFormat::Generic));
        assert!(stats.lines_dropped_by_global_cap > 0 || result.compressed_line_count <= 12);
    }

    #[test]
    fn empty_input_returns_unchanged() {
        let c = cmp();
        let (result, _) = c.compress("a\nb\nc", 1.0);
        assert_eq!(result.compressed, "a\nb\nc");
        assert_eq!(result.compression_ratio, 1.0);
    }

    #[test]
    fn ccr_marker_emitted_when_thresholds_clear() {
        let c = LogCompressor::new(LogCompressorConfig {
            max_total_lines: 5,
            min_lines_for_ccr: 5,
            min_compression_ratio_for_ccr: 0.95,
            ..Default::default()
        });
        let mut content = String::new();
        for i in 0..50 {
            content.push_str(&format!("INFO line {}\n", i));
        }
        content.push_str("ERROR boom\n");
        let store = InMemoryCcrStore::new();
        let (result, stats) = c.compress_with_store(&content, 1.0, Some(&store));
        assert!(result.cache_key.is_some(), "cache_key should be populated");
        assert!(stats.ccr_emitted);
        let key = result.cache_key.as_ref().unwrap();
        assert_eq!(store.get(key).unwrap(), content);
    }

    #[test]
    fn format_output_emits_summary_with_omitted_count() {
        let c = cmp();
        let all_lines = vec![
            LogLine::new(0, "ERROR a"),
            LogLine::new(1, "WARN b"),
            LogLine::new(2, "INFO c"),
            LogLine::new(3, "INFO d"),
        ]
        .into_iter()
        .map(|mut l| {
            l.level = if l.content.contains("ERROR") {
                LogLevel::Error
            } else if l.content.contains("WARN") {
                LogLevel::Warn
            } else {
                LogLevel::Info
            };
            l
        })
        .collect::<Vec<_>>();
        let selected = vec![all_lines[0].clone()];
        let (output, stats) = c.format_output(&selected, &all_lines);
        assert!(output.contains("[3 lines omitted: 1 ERROR, 1 WARN, 2 INFO]"));
        assert_eq!(stats["errors"], 1);
        assert_eq!(stats["info"], 2);
    }

    #[test]
    fn score_line_caps_at_one_point_zero() {
        let line = LogLine {
            line_number: 0,
            content: "ERROR summary".into(),
            level: LogLevel::Error,
            is_stack_trace: true,
            is_summary: true,
            score: 0.0,
        };
        assert_eq!(score_log_line(&line), 1.0);
    }

    #[test]
    fn select_with_first_last_keeps_both_endpoints() {
        let c = cmp();
        let lines: Vec<LogLine> = (0..5)
            .map(|i| {
                let mut l = LogLine::new(i, format!("line {}", i));
                l.score = if i == 2 { 0.9 } else { 0.1 };
                l
            })
            .collect();
        let kept = c.select_with_first_last(&lines, 3);
        let line_nums: Vec<_> = kept.iter().map(|l| l.line_number).collect();
        assert!(line_nums.contains(&0));
        assert!(line_nums.contains(&4));
        assert!(line_nums.contains(&2));
    }
}
