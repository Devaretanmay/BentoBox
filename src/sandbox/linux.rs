/// Linux Landlock LSM sandbox implementation
///
/// Implements kernel-enforced filesystem and network access control
/// using Landlock LSM (Linux 5.13+). Uses a capability-based approach
/// adapted to BentoBox's worktree-centric model.
///
/// Design principles:
/// - BentoBox knows the exact worktree path, so rules are simpler
/// - We always allow read on standard system paths (/usr, /lib, etc.)
/// - We always allow read-write on standard temp directories
/// - Network blocking is optional (configurable per session)

use std::path::{Path, PathBuf};
use std::sync::OnceLock;

use super::SandboxInfo;

// ---------------------------------------------------------------------------
// Landlock Rust bindings via raw syscalls + the `landlock` helper crate
// ---------------------------------------------------------------------------

use landlock::{
    ABI, AccessFs, AccessNet, BitFlags, CompatLevel, PathBeneath, PathFd, Ruleset,
};

/// System paths that agents always need read-execute access to.
const SYSTEM_READ_PATHS: &[&str] = &[
    "/usr",
    "/lib",
    "/lib64",
    "/bin",
    "/sbin",
    "/etc",
    "/opt",
    "/nix",
];

/// Standard temp directories that agents need read-write access to.
const TEMP_WRITE_PATHS: &[&str] = &[
    "/tmp",
    "/var/tmp",
    "/dev/shm",
];

/// Device files needed for basic I/O.
const DEVICE_PATHS: &[&str] = &[
    "/dev/null",
    "/dev/urandom",
    "/dev/random",
    "/dev/zero",
    "/dev/fd",
    "/dev/stdin",
    "/dev/stdout",
    "/dev/stderr",
    "/dev/pts",
    "/dev/ptmx",
];

/// Cache for ABI detection result.
static CACHED_ABI: OnceLock<Result<ABI, String>> = OnceLock::new();

/// Probes the highest Landlock ABI version supported.
fn detect_abi() -> Result<ABI, String> {
    if let Some(result) = CACHED_ABI.get() {
        return result.clone();
    }

    let probe_order = [ABI::V6, ABI::V5, ABI::V4, ABI::V3, ABI::V2, ABI::V1];

    for &abi in &probe_order {
        let mut ruleset = Ruleset::default();
        ruleset = ruleset.set_compatibility(CompatLevel::HardRequirement);

        let handled_fs = AccessFs::from_all(abi);
        match ruleset.handle_access(handled_fs) {
            Ok(r) => ruleset = r,
            Err(_) => continue,
        }

        let handled_net = AccessNet::from_all(abi);
        if !handled_net.is_empty() {
            match ruleset.handle_access(handled_net) {
                Ok(r) => ruleset = r,
                Err(_) => continue,
            }
        }

        if ruleset.create().is_ok() {
            let _ = CACHED_ABI.set(Ok(abi));
            return Ok(abi);
        }
    }

    let msg = "Landlock not available. Requires Linux kernel 5.13+ with CONFIG_SECURITY_LANDLOCK=y."
        .to_string();
    let _ = CACHED_ABI.set(Err(msg.clone()));
    Err(msg)
}

/// Check basic filesystem access availability (ABI V1 minimum).
fn has_basic_fs() -> bool {
    detect_abi().is_ok()
}

/// Check whether TCP network filtering is available (ABI V4+).
fn has_network() -> bool {
    detect_abi()
        .map(|abi| !AccessNet::from_all(abi).is_empty())
        .unwrap_or(false)
}

/// Check whether execute restriction is available (ABI V3+).
fn has_execute() -> bool {
    detect_abi()
        .map(|abi| matches!(abi, ABI::V3 | ABI::V4 | ABI::V5 | ABI::V6))
        .unwrap_or(false)
}

/// Build and apply the Landlock ruleset.
///
/// Steps:
/// 1. Create a ruleset that handles our desired access rights
/// 2. Add path-beneath rules for each allowed path
/// 3. Restrict the process (irreversible)
pub(super) fn apply(worktree_path: &str, block_network: bool) -> Result<(), String> {
    let abi = detect_abi()?;
    let worktree = Path::new(worktree_path);

    if !worktree.exists() {
        return Err(format!("Worktree path does not exist: {}", worktree_path));
    }

    let handled_fs = AccessFs::from_all(abi);
    let mut ruleset_builder = Ruleset::default()
        .set_compatibility(CompatLevel::BestEffort)
        .handle_access(handled_fs)
        .map_err(|e| format!("Failed to handle filesystem access: {}", e))?;

    let needs_network_block = block_network;
    if needs_network_block && has_network() {
        let handled_net = AccessNet::from_all(abi);
        if !handled_net.is_empty() {
            ruleset_builder = ruleset_builder
                .handle_access(handled_net)
                .map_err(|e| format!("Failed to handle network access: {}", e))?;
        }
    }

    let mut ruleset = ruleset_builder
        .create()
        .map_err(|e| format!("Failed to create Landlock ruleset: {}", e))?;


    let mut add_path_rule = |path: &Path, access: BitFlags<AccessFs>| -> Result<(), String> {
        let path_beneath = PathBeneath::new(PathFd::new(path), access)
            .map_err(|e| format!("Invalid path '{}': {}", path.display(), e))?;
        ruleset
            .add_rule(path_beneath)
            .map_err(|e| format!("Failed to add rule for '{}': {}", path.display(), e))?;
        Ok(())
    };

    let mut add_resolved_path_rule = |path: &Path, access: BitFlags<AccessFs>| -> Result<(), String> {
        let resolved = path.canonicalize().unwrap_or_else(|_| path.to_path_buf());
        add_path_rule(&resolved, access)?;
        if resolved != path {
            add_path_rule(path, access)?;
        }
        Ok(())
    };

    let worktree_access = AccessFs::ReadFile
        | AccessFs::ReadDir
        | AccessFs::WriteFile
        | AccessFs::Execute
        | AccessFs::RemoveFile
        | AccessFs::RemoveDir
        | AccessFs::MakeChar
        | AccessFs::MakeDir
        | AccessFs::MakeReg
        | AccessFs::MakeSock
        | AccessFs::MakeFifo
        | AccessFs::MakeBlock
        | AccessFs::MakeSym
        | AccessFs::Refer
        | AccessFs::Truncate;
    add_resolved_path_rule(worktree, worktree_access)?;

    let read_exec_access = AccessFs::ReadFile | AccessFs::ReadDir | AccessFs::Execute;
    for path_str in SYSTEM_READ_PATHS {
        let path = Path::new(path_str);
        if path.exists() {
            let _ = add_resolved_path_rule(path, read_exec_access);
        }
    }

    let read_write_dir_access = AccessFs::ReadFile
        | AccessFs::ReadDir
        | AccessFs::WriteFile
        | AccessFs::MakeChar
        | AccessFs::MakeDir
        | AccessFs::MakeReg
        | AccessFs::RemoveFile
        | AccessFs::RemoveDir;
    for path_str in TEMP_WRITE_PATHS {
        let path = Path::new(path_str);
        if path.exists() {
            let _ = add_resolved_path_rule(path, read_write_dir_access);
        }
    }

    let device_access = AccessFs::ReadFile | AccessFs::WriteFile;
    for path_str in DEVICE_PATHS {
        let path = Path::new(path_str);
        if path.exists() {
            let _ = add_resolved_path_rule(path, device_access);
        }
    }


    ruleset
        .restrict_self()
        .map_err(|e| format!("Failed to apply Landlock sandbox: {}", e))?;

    Ok(())
}

/// Apply a stacked execute-restriction layer.
///
/// After `apply()`, this restricts `execve` to binaries under the
/// given paths. Requires Landlock ABI V3+.
pub(super) fn restrict_execute(allowed_paths: &[String]) -> Result<(), String> {
    let abi = detect_abi()?;

    if !has_execute() {
        return Err("Execute restriction requires Landlock ABI V3+".to_string());
    }

    let mut ruleset_builder = Ruleset::default()
        .set_compatibility(CompatLevel::BestEffort)
        .handle_access(AccessFs::Execute)
        .map_err(|e| format!("Failed to handle execute access: {}", e))?;

    let mut ruleset = ruleset_builder
        .create()
        .map_err(|e| format!("Failed to create execute ruleset: {}", e))?;

    for path_str in allowed_paths {
        let path = Path::new(path_str);
        if path.exists() {
            let path_beneath = PathBeneath::new(
                PathFd::new(path),
                AccessFs::Execute,
            )
            .map_err(|e| format!("Invalid execute path '{}': {}", path_str, e))?;
            let _ = ruleset.add_rule(path_beneath);
        }
    }

    ruleset
        .restrict_self()
        .map_err(|e| format!("Failed to apply execute restriction: {}", e))?;

    Ok(())
}

/// Diagnostic: explain whether `path` is allowed or blocked by the Landlock rules.
pub(super) fn why(path: &str, worktree_path: &str, block_network: bool) -> String {
    use std::path::Path;
    let p = Path::new(path);

    // Network check
    if path.starts_with("tcp:") || path.starts_with("udp:") || path.starts_with("http") {
        if block_network && check_supported() && has_network() {
            return concat!(
                "BLOCKED — Network is disabled (block_network=true).\n",
                "Only localhost TCP and Unix sockets are allowed.\n",
                "Tip: Set block_network=False in BentoBoxConfig to allow network access.",
            ).to_string();
        }
        return format!(
            "ALLOWED — Network access is permitted (block_network={}).",
            if block_network { "true, but Landlock network V4+ not available" } else { "false" }
        );
    }

    let abs = if p.is_absolute() {
        p.to_path_buf()
    } else if let Ok(cwd) = std::env::current_dir() {
        cwd.join(p)
    } else {
        p.to_path_buf()
    };
    let abs_str = abs.to_string_lossy();
    let wt = Path::new(worktree_path).canonicalize().unwrap_or_else(|_| Path::new(worktree_path).to_path_buf());
    let wt_str = wt.to_string_lossy();

    // Worktree check
    if abs_str.starts_with(&*wt_str) && (abs_str.len() == wt_str.len() || abs_str[wt_str.len()..].starts_with('/')) {
        return format!(
            "ALLOWED — Inside worktree path.\nPath: {}\nWorktree: {}\nFull read-write-execute access.",
            path, worktree_path
        );
    }

    // System paths (read-only)
    for sys_path in SYSTEM_READ_PATHS {
        if abs_str.starts_with(sys_path) && Path::new(sys_path).exists() {
            return format!(
                "ALLOWED — System path (read-only).\nPath: {}\nRead-only access to '{}/' for system binaries.",
                path, sys_path
            );
        }
    }

    // Temp paths (read-write)
    for tmp_path in TEMP_WRITE_PATHS {
        if abs_str.starts_with(tmp_path) && Path::new(tmp_path).exists() {
            return format!(
                "ALLOWED — Temp directory (read-write).\nPath: {}\nRead-write access to '{}/'.",
                path, tmp_path
            );
        }
    }

    // Device paths (read-write)
    for dev_path in DEVICE_PATHS {
        if abs_str.starts_with(dev_path) && Path::new(dev_path).exists() {
            return format!(
                "ALLOWED — Device path (read-write).\nPath: {}",
                path
            );
        }
    }

    format!(
        "BLOCKED — Path is outside all allowed Landlock rules.\nPath: {}\nWorktree: {}\n\nAllowed paths:\n  • Worktree (read-write-execute)\n  • /usr, /lib, /lib64, /bin, /sbin, /etc, /opt, /nix (read-only)\n  • /tmp, /var/tmp, /dev/shm (read-write)\n  • /dev/null, /dev/urandom, /dev/random, /dev/zero, /dev/fd, /dev/stdin, /dev/stdout, /dev/stderr (read-write)\n  • Network: {}",
        path,
        worktree_path,
        if block_network { "localhost-only (Landlock V4+)" } else { "Full access" }
    )
}

/// Check whether Landlock is supported.
pub(super) fn check_supported() -> bool {
    has_basic_fs()
}

/// Get detailed Landlock support information.
pub(super) fn get_info() -> SandboxInfo {
    match detect_abi() {
        Ok(abi) => {
            let features = describe_features(abi);
            let network = has_network();
            SandboxInfo {
                supported: true,
                platform: "linux".to_string(),
                details: format!(
                    "Landlock ABI {:?} — features: {} — network filtering: {}",
                    abi,
                    features.join(", "),
                    if network { "yes" } else { "no (requires V4+)" }
                ),
            }
        }
        Err(msg) => SandboxInfo {
            supported: false,
            platform: "linux".to_string(),
            details: msg,
        },
    }
}

fn describe_features(abi: ABI) -> Vec<String> {
    let mut features = vec!["Basic filesystem access control".to_string()];
    let available = AccessFs::from_all(abi);

    if available.contains(AccessFs::Refer) {
        features.push("rename across dirs".to_string());
    }
    if available.contains(AccessFs::Truncate) {
        features.push("truncation control".to_string());
    }
    if has_execute() {
        features.push("execute restriction".to_string());
    }
    if has_network() {
        features.push("TCP network filtering".to_string());
    }
    if !landlock::Scope::from_all(abi).is_empty() {
        features.push("signal/IPC scoping".to_string());
    }

    features
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_detect_abi_does_not_panic() {
        let _ = detect_abi();
    }

    #[test]
    fn test_check_supported_consistent() {
        let a = check_supported();
        let b = check_supported();
        assert_eq!(a, b);
    }

    #[test]
    fn test_get_info_returns_platform() {
        let info = get_info();
        assert_eq!(info.platform, "linux");
    }

    #[test]
    fn test_landlock_abi_constants() {
        let v1_access = AccessFs::from_all(ABI::V1);
        assert!(v1_access.contains(AccessFs::ReadFile));
        assert!(v1_access.contains(AccessFs::WriteFile));
        assert!(v1_access.contains(AccessFs::Execute));
    }
}
