use napi_derive::napi;

/// Version of the BentoBox core library.
#[napi]
pub fn version() -> String {
    bentoworks_core::version().to_string()
}

/// Whether kernel sandboxing is available on this platform.
#[napi]
pub fn sandbox_supported() -> bool {
    bentoworks_core::sandbox::check_supported()
}

/// Explain why `path` (file or tcp:/udp: address) would be blocked by the
/// sandbox rules for `worktree_path`.
#[napi]
pub fn sandbox_why(path: String, worktree_path: String, block_network: bool) -> String {
    bentoworks_core::sandbox::why(&path, &worktree_path, block_network)
}

/// Compress content through the BentoBox smart crusher.
#[napi]
pub fn compress(content: String) -> String {
    bentoworks_core::compress::compress_content(&content)
}

// =========================================================================
// Compartment runtime — enforcer, snapshots, credentials, coordination
// =========================================================================

fn parse<T: serde::de::DeserializeOwned>(input: &str) -> napi::Result<T> {
    serde_json::from_str(input).map_err(|e| napi::Error::from_reason(format!("invalid JSON: {e}")))
}

/// Check policy JSON `{"permissions": [...]}` against required permission JSON.
/// Returns true if allowed, false if denied.
#[napi]
pub fn runtime_check_permission(policy_json: String, required_json: String) -> napi::Result<bool> {
    let policy: serde_json::Value = parse(&policy_json)?;
    let required: Vec<String> = parse(&required_json)?;
    // check_permission_json only errors on a denial; parse failures surfaced above.
    Ok(bentoworks_core::runtime::enforcer::check_permission_json(&policy, &required).is_ok())
}

/// Check a command string against the dangerous-command blocklist.
/// Returns true if allowed, false if blocked.
#[napi]
pub fn runtime_check_command(cmd: String) -> napi::Result<bool> {
    Ok(bentoworks_core::runtime::enforcer::check_command(&cmd).is_ok())
}

/// Snapshot `workdir` into `snapshot_dir`, excluding dirs in the JSON array.
/// Returns the number of files snapshotted.
#[napi]
pub fn runtime_snapshot(
    workdir: String,
    snapshot_dir: String,
    exclude_json: Option<String>,
) -> napi::Result<i32> {
    let exclude: Vec<String> = match exclude_json {
        Some(raw) => parse(&raw)?,
        None => Vec::new(),
    };
    let set: std::collections::HashSet<String> = exclude.into_iter().collect();
    let mgr = bentoworks_core::runtime::snapshot::SnapshotManager::new(
        &workdir,
        &snapshot_dir,
        if set.is_empty() { None } else { Some(set) },
    );
    Ok(mgr.snapshot().map_err(|e| napi::Error::from_reason(e))? as i32)
}

/// Restore files from `snapshot_dir` back into `workdir`.
/// Returns the number of files restored.
#[napi]
pub fn runtime_restore(workdir: String, snapshot_dir: String) -> napi::Result<i32> {
    let mgr = bentoworks_core::runtime::snapshot::SnapshotManager::new(&workdir, &snapshot_dir, None);
    Ok(mgr.restore().map_err(|e| napi::Error::from_reason(e))? as i32)
}

/// Validate compartment configs JSON `{"configs": [...]}` and edges JSON
/// `[["a", "b"]]`. Returns true if valid, false if invalid (matches Go).
#[napi]
pub fn runtime_validate(configs_json: String, edges_json: String) -> napi::Result<bool> {
    // Any bad input or unknown compartment is "invalid" → false, never throws.
    let edges: Vec<(String, String)> = match parse(&edges_json) {
        Ok(e) => e,
        Err(_) => return Ok(false),
    };
    let runtime = match build_runtime(&configs_json, &edges) {
        Ok(rt) => rt,
        Err(_) => return Ok(false),
    };
    Ok(runtime.run_order(None).is_ok())
}

/// Check if a message `from` to `to` is permitted by the configs JSON.
/// Returns true if allowed, false if denied; throws if a compartment is unknown.
#[napi]
pub fn runtime_can_route(configs_json: String, from: String, to: String) -> napi::Result<bool> {
    let runtime = build_runtime(&configs_json, &[])?;
    // Unknown compartment names are input errors, not denials.
    if runtime.config(&from).is_none() || runtime.config(&to).is_none() {
        return Err(napi::Error::from_reason("unknown source or target compartment"));
    }
    // Both compartments exist, so any remaining error is a whitelist denial.
    Ok(runtime.can_route(&from, &to).is_ok())
}

/// Match a request path against credential routes JSON; on a match, return
/// the rewritten upstream URL, or null if no route matched.
#[napi]
pub fn runtime_credential_rewrite(routes_json: String, path: String) -> napi::Result<Option<String>> {
    let routes: Vec<bentoworks_core::runtime::credential::RouteConfig> = parse(&routes_json)?;
    for r in &routes {
        if r.matches(&path) {
            return Ok(Some(r.rewrite_path(&path)));
        }
    }
    Ok(None)
}

/// Resolve a credential source like `env:OPENAI_API_KEY`.
#[napi]
pub fn runtime_credential_resolve(source: String) -> napi::Result<String> {
    let route = bentoworks_core::runtime::credential::RouteConfig {
        credential_source: source,
        ..Default::default()
    };
    Ok(route.resolve_credential())
}

fn build_runtime(configs: &str, edges: &[(String, String)]) -> napi::Result<bentoworks_core::runtime::compartments::Runtime> {
    #[derive(serde::Deserialize)]
    struct Spec {
        #[serde(default)]
        configs: Vec<bentoworks_core::runtime::compartments::CompartmentConfig>,
    }
    let spec: Spec = parse(configs)?;
    let mut rt = bentoworks_core::runtime::compartments::Runtime::new();
    for cfg in spec.configs {
        rt.add(cfg).map_err(|e| napi::Error::from_reason(e))?;
    }
    for (from, to) in edges {
        rt.edge(from, to).map_err(|e| napi::Error::from_reason(e))?;
    }
    Ok(rt)
}

/// Opaque, pre-built compartment runtime. Parses configs once so hot-path
/// `canRoute`/`runOrder` calls do not re-parse JSON. Not thread-safe.
#[napi]
pub struct Runtime {
    inner: bentoworks_core::runtime::compartments::Runtime,
}

#[napi]
impl Runtime {
    /// Build a Runtime from configs JSON `{"configs": [...]}` and edges JSON.
    /// Throws if a compartment or edge is invalid.
    #[napi(constructor)]
    pub fn new(configs_json: String, edges_json: String) -> napi::Result<Self> {
        let edges: Vec<(String, String)> = parse(&edges_json)?;
        Ok(Self {
            inner: build_runtime(&configs_json, &edges)?,
        })
    }

    /// Check if a message `from` to `to` is permitted.
    /// Returns true if allowed, false if denied; throws if a compartment is unknown.
    #[napi]
    pub fn can_route(&self, from: String, to: String) -> napi::Result<bool> {
        // Unknown compartment names are input errors, not denials.
        if self.inner.config(&from).is_none() || self.inner.config(&to).is_none() {
            return Err(napi::Error::from_reason("unknown source or target compartment"));
        }
        // Both compartments exist, so any remaining error is a whitelist denial.
        Ok(self.inner.can_route(&from, &to).is_ok())
    }

    /// Execution order as compartment names, optionally starting at `entry`
    /// (omit to run from the start).
    #[napi]
    pub fn run_order(&self, entry: Option<String>) -> napi::Result<Vec<String>> {
        self.inner
            .run_order(entry.as_deref())
            .map_err(|e| napi::Error::from_reason(e))
    }

    /// Registered compartment names, in registration order.
    #[napi]
    pub fn names(&self) -> Vec<String> {
        self.inner.names()
    }
}
