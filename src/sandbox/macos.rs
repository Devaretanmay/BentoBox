// macOS Seatbelt sandbox: generates a dynamic profile (Scheme S-expressions)
// and applies it via the private-but-stable `sandbox_init()` API.

use std::ffi::CString;
use std::path::Path;

use super::SandboxInfo;

/// System paths that agents always need read-execute access to.
const SYSTEM_READ_PATHS: &[&str] = &[
    "/usr", "/bin", "/sbin", "/etc", "/opt", "/System", "/Library", "/nix", "/private", "/var",
];

/// Standard temp directories that agents need read-write access to.
const TEMP_WRITE_PATHS: &[&str] = &["/tmp", "/var/tmp", "/private/tmp", "/private/var/tmp"];

// Sensitive user paths kept DENIED by default (Seatbelt adds explicit deny
// rules; Landlock simply never allows them).
const DENIED_PATHS: &[&str] = &[
    ".ssh",
    ".aws",
    ".azure",
    ".gcloud",
    ".config/gcloud",
    ".docker/config.json",
    ".git-credentials",
    ".gitconfig",
    ".gnupg",
    ".bash_history",
    ".zsh_history",
    ".zshrc",
    ".bashrc",
    ".bash_profile",
    ".config",
    "Library/Application Support/Google",
    "Library/Application Support/Firefox",
    "Library/Application Support/BraveSoftware",
    "Library/Application Support/Chromium",
    "Library/Keychains",
    ".npmrc",
    ".yarnrc",
    ".yarnrc.yml",
    ".pypirc",
    ".kube",
    ".netrc",
];

fn push_file_read(sb: &mut String, path: &str) {
    sb.push_str(&format!(
        "(allow file-read* (subpath \"{}\"))\n",
        escape_path(path)
    ));
}

fn push_file_write(sb: &mut String, path: &str) {
    sb.push_str(&format!(
        "(allow file-write* (subpath \"{}\"))\n",
        escape_path(path)
    ));
}

fn push_file_read_write(sb: &mut String, path: &str) {
    push_file_read(sb, path);
    push_file_write(sb, path);
}

fn generate_profile(worktree_path: &str, block_network: bool) -> String {
    let mut sb = String::with_capacity(4096);

    sb.push_str("(version 1)\n");

    sb.push_str("(deny default)\n");

    sb.push_str("(allow process-exec*)\n");
    sb.push_str("(allow process-fork)\n");

    sb.push_str("(allow process-info*)\n");

    sb.push_str("(allow sysctl-read)\n");

    sb.push_str("(allow ipc-posix-shm*)\n");

    sb.push_str("(allow mach-lookup)\n");
    sb.push_str("(allow mach-per-user-lookup)\n");
    sb.push_str("(allow mach-task-name)\n");

    // dyld's CacheFinder issues file-read-data on the root directory "/"
    // while locating the shared cache at process exec. Without this, every
    // child process spawned after sandbox_init aborts with SIGABRT.
    sb.push_str("(allow file-read* (literal \"/\"))\n");

    push_file_read_write(&mut sb, worktree_path);

    if let Ok(resolved) = Path::new(worktree_path).canonicalize() {
        let resolved_str = resolved.to_string_lossy();
        if resolved_str != worktree_path {
            push_file_read_write(&mut sb, &resolved_str);
        }
    }

    for path in SYSTEM_READ_PATHS {
        if Path::new(path).exists() {
            push_file_read(&mut sb, path);
        }
    }

    for path in TEMP_WRITE_PATHS {
        if Path::new(path).exists() {
            push_file_read_write(&mut sb, path);
        }
    }

    if Path::new("/dev").exists() {
        push_file_read_write(&mut sb, "/dev");
    }

    if let Ok(home) = std::env::var("HOME") {
        for denied in DENIED_PATHS {
            let denied_path = format!("{}/{}", home, denied);
            let p = Path::new(&denied_path);
            if p.exists() {
                sb.push_str(&format!(
                    "(deny file-read* (subpath \"{}\"))\n",
                    escape_path(&denied_path)
                ));
                sb.push_str(&format!(
                    "(deny file-write* (subpath \"{}\"))\n",
                    escape_path(&denied_path)
                ));
            }
        }
    }

    if block_network {
        sb.push_str("(deny network*)\n");

        sb.push_str("(allow network-outbound (remote tcp \"localhost:*\"))\n");
        sb.push_str("(allow network-inbound (local tcp \"localhost:*\"))\n");
        sb.push_str("(allow network-bind (local tcp \"localhost:*\"))\n");

        sb.push_str("(allow network-outbound (path \"/private/var/run/mDNSResponder\"))\n");
        sb.push_str("(allow network-outbound (path \"/var/run/mDNSResponder\"))\n");

        sb.push_str("(allow system-socket (socket-domain AF_UNIX))\n");
    } else {
        sb.push_str("(allow network*)\n");
        sb.push_str("(allow system-socket)\n");
    }

    sb
}

fn escape_path(path: &str) -> String {
    let mut result = String::with_capacity(path.len());
    for c in path.chars() {
        match c {
            '\\' => result.push_str("\\\\"),
            '"' => result.push_str("\\\""),
            c if c.is_control() => {
                continue;
            }
            _ => result.push(c),
        }
    }
    result
}

// Irreversible for the lifetime of the process tree.
pub(super) fn apply(worktree_path: &str, block_network: bool) -> Result<(), String> {
    let profile = generate_profile(worktree_path, block_network);

    let profile_cstr =
        CString::new(profile.as_str()).map_err(|_| "Profile contains null byte".to_string())?;

    let mut error_ptr: *mut std::ffi::c_char = std::ptr::null_mut();
    let result = unsafe { sandbox_init(profile_cstr.as_ptr(), 0, &mut error_ptr) };

    if result != 0 {
        let err_msg = if !error_ptr.is_null() {
            let msg = unsafe { std::ffi::CStr::from_ptr(error_ptr) }
                .to_string_lossy()
                .into_owned();
            unsafe { sandbox_free_error(error_ptr) };
            msg
        } else {
            "Unknown sandbox_init error".to_string()
        };
        return Err(format!("macOS Seatbelt sandbox failed: {}", err_msg));
    }

    Ok(())
}

extern "C" {
    fn sandbox_init(
        profile: *const std::ffi::c_char,
        flags: u64,
        errorbuf: *mut *mut std::ffi::c_char,
    ) -> i32;
    fn sandbox_free_error(errorbuf: *mut std::ffi::c_char);
}

pub(super) fn why(path: &str, worktree_path: &str, block_network: bool) -> String {
    use std::path::Path;
    let p = Path::new(path);

    if path.starts_with("tcp:") || path.starts_with("udp:") || path.starts_with("http") {
        if block_network {
            return concat!(
                "BLOCKED: Network is disabled (block_network=true).\n",
                "Only localhost TCP (localhost:*) and Unix sockets are allowed.\n",
                "Tip: Set block_network=False in BentoBoxConfig to allow network access.",
            )
            .to_string();
        }
        return "ALLOWED: Network access is permitted (block_network=false).".to_string();
    }

    let abs = if p.is_absolute() {
        p.to_path_buf()
    } else if let Ok(cwd) = std::env::current_dir() {
        cwd.join(p)
    } else {
        p.to_path_buf()
    };
    let abs_str = abs.to_string_lossy();
    let wt = Path::new(worktree_path);
    let wt_str = wt.to_string_lossy();

    if let Ok(home) = std::env::var("HOME") {
        for denied in DENIED_PATHS {
            let denied_full = format!("{}/{}", home, denied);
            if abs_str.starts_with(&denied_full)
                || abs_str.contains(&format!(
                    "/{}{}",
                    denied,
                    if denied.ends_with('/') { "" } else { "/" }
                ))
            {
                let category = match denied {
                    d if d.starts_with(".ssh") => "SSH keys",
                    d if d.starts_with(".aws")
                        || d.starts_with(".azure")
                        || d.starts_with(".gcloud") =>
                    {
                        "Cloud credentials"
                    }
                    d if d.contains("docker") => "Docker config",
                    d if d.starts_with(".git-") || d.starts_with(".gitconfig") => "Git credentials",
                    d if d.starts_with(".gnupg") => "GPG keys",
                    d if d.contains(".bash_")
                        || d.contains(".zsh_")
                        || d.contains(".zshrc")
                        || d.contains(".bashrc") =>
                    {
                        "Shell config"
                    }
                    d if d.contains("Keychains") => "System keychain",
                    d if d.contains("Firefox")
                        || d.contains("Chrome")
                        || d.contains("Brave")
                        || d.contains("Chromium") =>
                    {
                        "Browser data"
                    }
                    d if d.starts_with(".kube") => "Kubernetes config",
                    d if d.starts_with(".npmrc") || d.starts_with(".yarnrc") => {
                        "Package manager config"
                    }
                    d if d.starts_with(".pypirc") => "Python package config",
                    d if d.starts_with(".netrc") => "Network credentials",
                    _ => "Sensitive path",
                };
                return format!(
                    "BLOCKED: {} are protected by default.\nPath: {}\nReason: {} - BentoBox denies agents access to credential files, secrets, and browser data.\nTip: If you need this path for a legitimate reason, add it to the worktree or use a custom sandbox profile.",
                    category, path, denied
                );
            }
        }
    }

    if abs_str.starts_with(&*wt_str)
        && (abs_str.len() == wt_str.len() || abs_str[wt_str.len()..].starts_with('/'))
    {
        return format!(
            "ALLOWED: Inside worktree path.\nPath: {}\nWorktree: {}\nThe sandbox grants full read-write-execute access to files under the worktree.",
            path, worktree_path
        );
    }

    for sys_path in SYSTEM_READ_PATHS {
        if abs_str.starts_with(sys_path) && Path::new(sys_path).exists() {
            return format!(
                "ALLOWED: System path (read-only).\nPath: {}\nThe sandbox grants read-only access to '{}/' for essential system binaries and libraries.",
                path, sys_path
            );
        }
    }

    for tmp_path in TEMP_WRITE_PATHS {
        if abs_str.starts_with(tmp_path) && Path::new(tmp_path).exists() {
            return format!(
                "ALLOWED: Temp directory (read-write).\nPath: {}\nThe sandbox grants read-write access to '{}/' for temporary files.",
                path, tmp_path
            );
        }
    }

    if abs_str.starts_with("/dev") && Path::new("/dev").exists() {
        return format!(
            "ALLOWED: Device path (read-write).\nPath: {}\nThe sandbox grants read-write access to /dev for basic I/O operations.",
            path
        );
    }

    format!(
        "BLOCKED: Path is outside all allowed sandbox rules.\nPath: {}\nWorktree: {}\n\nThe sandbox denies everything by default and only allows:\n  - Files under the worktree (read-write-execute)\n  - System paths: /usr, /bin, /sbin, /etc, /opt, /System, /Library, /nix, /private (read-only)\n  - Temp directories: /tmp, /var/tmp, /private/tmp (read-write)\n  - /dev (read-write)\n  {} network access",
        path,
        worktree_path,
        if block_network { "localhost-only" } else { "Full" }
    )
}

pub(super) fn check_supported() -> bool {
    true
}

pub(super) fn get_info() -> SandboxInfo {
    SandboxInfo {
        supported: true,
        platform: "macos".to_string(),
        details: "macOS Seatbelt sandbox available (sandbox_init API)".to_string(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_generate_profile_contains_worktree() {
        let profile = generate_profile("/tmp/test-worktree", false);
        assert!(profile.contains("(allow file-read* (subpath \"/tmp/test-worktree\"))"));
        assert!(profile.contains("(allow file-write* (subpath \"/tmp/test-worktree\"))"));
    }

    #[test]
    fn test_generate_profile_allows_root_read_for_dyld_cachefinder() {
        // dyld's CacheFinder file-read-data on "/" at exec; without this rule
        // every child process aborts with SIGABRT after sandbox_init.
        let profile = generate_profile("/tmp/test-worktree", true);
        assert!(profile.contains("(allow file-read* (literal \"/\"))"));
    }

    #[test]
    fn test_generate_profile_contains_deny_default() {
        let profile = generate_profile("/tmp/test", false);
        assert!(profile.contains("(deny default)"));
    }

    #[test]
    fn test_generate_profile_network_blocked() {
        let profile = generate_profile("/tmp/test", true);
        assert!(profile.contains("(deny network*)"));
        assert!(profile.contains("(allow network-outbound (remote tcp \"localhost:*\"))"));
    }

    #[test]
    fn test_generate_profile_network_allowed() {
        let profile = generate_profile("/tmp/test", false);
        assert!(profile.contains("(allow network*)"));
        assert!(!profile.contains("(deny network*)"));
    }

    #[test]
    fn test_check_supported() {
        assert!(check_supported());
    }

    #[test]
    fn test_escape_path_handles_special_chars() {
        assert_eq!(escape_path("/tmp/test"), "/tmp/test");
        assert!(escape_path("/tmp/\"test\"").contains('"'));
        assert!(escape_path("/tmp/\\test").contains('\\'));
    }
}
