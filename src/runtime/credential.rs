use serde::{Deserialize, Deserializer, Serialize};
use std::collections::HashMap;

/// Hop-by-hop headers that must never be forwarded upstream.
const HOP_BY_HOP: &[&str] = &[
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailers", "transfer-encoding", "upgrade",
];

/// A single credential-injection rule.
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct RouteConfig {
    pub prefix: String,
    pub upstream: String,
    #[serde(default = "default_header", deserialize_with = "de_default_header")]
    pub header: String,
    #[serde(default = "default_format", deserialize_with = "de_default_format")]
    pub format: String,
    #[serde(default)]
    pub credential_source: String,
}

fn default_header() -> String {
    "Authorization".to_string()
}

fn default_format() -> String {
    "Bearer {credential}".to_string()
}

// Empty strings from Go/TS fall back to the defaults.
fn de_default_header<'de, D>(d: D) -> Result<String, D::Error>
where
    D: Deserializer<'de>,
{
    let s = String::deserialize(d)?;
    Ok(if s.is_empty() { default_header() } else { s })
}

fn de_default_format<'de, D>(d: D) -> Result<String, D::Error>
where
    D: Deserializer<'de>,
{
    let s = String::deserialize(d)?;
    Ok(if s.is_empty() { default_format() } else { s })
}

impl RouteConfig {
    pub fn resolve_credential(&self) -> String {
        if let Some(var_name) = self.credential_source.strip_prefix("env:") {
            std::env::var(var_name).unwrap_or_default()
        } else {
            String::new()
        }
    }

    pub fn matches(&self, path: &str) -> bool {
        path.starts_with(&self.prefix)
    }

    pub fn rewrite_path(&self, path: &str) -> String {
        let relative = &path[self.prefix.len()..];
        let relative = if relative.starts_with('/') {
            relative.to_string()
        } else {
            format!("/{relative}")
        };
        format!("{}{}", self.upstream.trim_end_matches('/'), relative)
    }

    pub fn header_value(&self, credential: &str) -> String {
        self.format.replace("{credential}", credential)
    }
}

// Strip hop-by-hop headers; drop `host` when rewriting to a new upstream.
pub fn clean_headers(headers: &HashMap<String, String>, strip_host: bool) -> HashMap<String, String> {
    headers
        .iter()
        .filter(|(key, _)| {
            let lower = key.to_lowercase();
            !HOP_BY_HOP.contains(&lower.as_str()) && !(strip_host && lower == "host")
        })
        .map(|(k, v)| (k.clone(), v.clone()))
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn route() -> RouteConfig {
        RouteConfig {
            prefix: "/openai".to_string(),
            upstream: "https://api.openai.com".to_string(),
            header: "Authorization".to_string(),
            format: "Bearer {credential}".to_string(),
            credential_source: "env:TEST_BENTO_KEY".to_string(),
        }
    }

    #[test]
    fn matches_prefix() {
        let r = route();
        assert!(r.matches("/openai/v1/chat"));
        assert!(!r.matches("/anthropic/v1"));
    }

    #[test]
    fn rewrites_path() {
        let r = route();
        assert_eq!(
            r.rewrite_path("/openai/v1/chat"),
            "https://api.openai.com/v1/chat"
        );
        assert_eq!(
            r.rewrite_path("/openai"),
            "https://api.openai.com/"
        );
    }

    #[test]
    fn resolves_env_credential() {
        std::env::set_var("TEST_BENTO_KEY", "sk-test-123");
        let r = route();
        assert_eq!(r.resolve_credential(), "sk-test-123");
        assert_eq!(r.header_value("sk-test-123"), "Bearer sk-test-123");
        std::env::remove_var("TEST_BENTO_KEY");
    }

    #[test]
    fn empty_header_format_fall_back_to_defaults() {
        let cfg: RouteConfig = serde_json::from_str(
            r#"{"prefix":"/x","upstream":"https://x","header":"","format":""}"#,
        )
        .unwrap();
        assert_eq!(cfg.header, "Authorization");
        assert_eq!(cfg.format, "Bearer {credential}");
    }

    #[test]
    fn filters_hop_by_hop() {
        let mut headers = HashMap::new();
        headers.insert("Authorization".to_string(), "Bearer x".to_string());
        headers.insert("Connection".to_string(), "keep-alive".to_string());
        headers.insert("Host".to_string(), "client.example".to_string());
        headers.insert("Transfer-Encoding".to_string(), "chunked".to_string());

        let cleaned = clean_headers(&headers, true);
        assert!(cleaned.contains_key("Authorization"));
        assert!(!cleaned.contains_key("Connection"));
        assert!(!cleaned.contains_key("Transfer-Encoding"));
        assert!(!cleaned.contains_key("Host"));
    }
}
