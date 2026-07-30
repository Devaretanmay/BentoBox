/// BentoBox Native Sandbox Module
///
/// Kernel-enforced sandboxing for execution sessions.
/// Implements Landlock (Linux) and Seatbelt (macOS) primitives
/// natively in BentoBox's Rust core.
///
/// Design:
/// - `apply(worktree_path)` — locks the current process tree to only
///   access the given worktree path (plus system essentials).
/// - `check_supported()` — returns whether sandboxing is available.
/// - `get_info()` — returns platform + ABI details.
///
/// Once applied, the sandbox is **irreversible** until the process exits.
///
/// Platform backends:
/// - Linux: Landlock LSM (kernel 5.13+, ABI V1-V6)
/// - macOS: Seatbelt sandbox (`sandbox_init()`) — always available on macOS
/// - Other: no-op fallback with warning

// Platform-specific modules
#[cfg(target_os = "linux")]
mod linux;

#[cfg(target_os = "macos")]
mod macos;

/// Information about sandbox support on this platform.
#[derive(Debug, Clone)]
pub struct SandboxInfo {
    /// Whether sandboxing is supported and available.
    pub supported: bool,
    /// Platform identifier ("linux", "macos", "unknown").
    pub platform: String,
    /// Human-readable details (ABI version, feature set).
    pub details: String,
}

/// Apply sandbox restrictions to the current process.
///
/// Once called, the current process (and all future children) can
/// ONLY access:
/// - Files under `worktree_path` (read-write-execute)
/// - System essential paths (/usr, /lib, /System, /etc — read-execute)
/// - Standard temp directories (read-write)
/// - /dev/null, /dev/urandom, /dev/zero (read-write)
///
/// If `block_network` is true, all TCP/UDP network access is denied
/// (Landlock V4+ on Linux, Seatbelt on macOS).
///
/// Returns Ok(()) if sandbox was applied successfully.
/// Returns Err with message if sandboxing is unavailable or fails.
///
/// # Safety
///
/// This is irreversible. Once called, the restricted process cannot
/// lift the sandbox. Only call this after all setup is complete.
pub fn apply(worktree_path: &str, block_network: bool) -> Result<(), String> {
    #[cfg(target_os = "linux")]
    {
        return linux::apply(worktree_path, block_network);
    }

    #[cfg(target_os = "macos")]
    {
        return macos::apply(worktree_path, block_network);
    }

    #[cfg(not(any(target_os = "linux", target_os = "macos")))]
    {
        let _ = (worktree_path, block_network);
        Err(format!(
            "Sandboxing not supported on '{}' (requires Linux with Landlock or macOS with Seatbelt)",
            std::env::consts::OS
        ))
    }
}

/// Apply a stacked execute-restriction layer on top of an existing sandbox.
///
/// After calling `apply()`, this adds a second Landlock layer that
/// restricts `execve`/`execveat` to binaries under the given `allowed_paths`.
/// On macOS this is a no-op (Seatbelt handles execute via the profile).
///
/// On Linux this requires Landlock ABI V3+.
#[allow(dead_code)]
pub fn restrict_execute(allowed_paths: &[String]) -> Result<(), String> {
    #[cfg(target_os = "linux")]
    {
        return linux::restrict_execute(allowed_paths);
    }

    #[cfg(not(target_os = "linux"))]
    {
        let _ = allowed_paths;
        Ok(())
    }
}

/// Diagnostic: explain whether `path` would be allowed or blocked by the
/// sandbox rules applied to `worktree_path`.
///
/// This does NOT query the OS sandbox state — it checks against the same
/// rules that `apply()` would use. This lets users understand *why* a file
/// or network call was blocked without reading the sandbox profile.
///
/// Returns a human-readable explanation string.
pub fn why(path: &str, worktree_path: &str, block_network: bool) -> String {
    #[cfg(target_os = "macos")]
    {
        return macos::why(path, worktree_path, block_network);
    }

    #[cfg(target_os = "linux")]
    {
        return linux::why(path, worktree_path, block_network);
    }

    #[cfg(not(any(target_os = "linux", target_os = "macos")))]
    {
        let _ = (path, worktree_path, block_network);
        format!(
            "Unknown — sandboxing not supported on '{}'",
            std::env::consts::OS
        )
    }
}

/// Check whether sandboxing is supported on this platform.
pub fn check_supported() -> bool {
    #[cfg(target_os = "linux")]
    {
        return linux::check_supported();
    }

    #[cfg(target_os = "macos")]
    {
        return macos::check_supported();
    }

    #[cfg(not(any(target_os = "linux", target_os = "macos")))]
    {
        false
    }
}

/// Get detailed information about sandbox support.
pub fn get_info() -> SandboxInfo {
    #[cfg(target_os = "linux")]
    {
        return linux::get_info();
    }

    #[cfg(target_os = "macos")]
    {
        return macos::get_info();
    }

    #[cfg(not(any(target_os = "linux", target_os = "macos")))]
    {
        SandboxInfo {
            supported: false,
            platform: std::env::consts::OS.to_string(),
            details: format!(
                "Platform '{}' is not supported. Requires Linux (5.13+) with Landlock or macOS with Seatbelt.",
                std::env::consts::OS
            ),
        }
    }
}
