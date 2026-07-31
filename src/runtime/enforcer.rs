/// Enforcer — per-compartment permission checks and command blocklist.
///
/// Ported from `python/bentoworks/sandbox/enforcer.py` so every SDK makes
/// identical allow/deny decisions. The *decision* lives here; host-language
/// monkeypatching (wrapping open/subprocess) stays in each SDK.

use serde_json::Value;

/// Permission names shared with `CompartmentConfig`.
pub const PERMISSION_FS_READ: &str = "fs_read";
pub const PERMISSION_FS_WRITE: &str = "fs_write";
pub const PERMISSION_FS_EXEC: &str = "fs_exec";
pub const PERMISSION_NETWORK: &str = "network";
pub const PERMISSION_GPU: &str = "gpu";
pub const PERMISSION_SYS_INFO: &str = "sys_info";

/// Commands blocked regardless of `fs_exec` permission.
pub const DANGEROUS_COMMANDS: &[&str] = &[
    // System destruction
    "mkfs", "mkfs.ext4", "mkfs.btrfs", "mkfs.xfs", "mkfs.fat", "mkswap",
    "fdisk", "parted", "partprobe", "gdisk", "sfdisk", "dd",
    // Privilege escalation
    "sudo", "su", "doas", "pkexec", "visudo",
    // System control
    "shutdown", "reboot", "poweroff", "halt", "init", "systemctl",
    "telinit", "runlevel",
    // User / permission changes
    "passwd", "chpasswd", "usermod", "groupmod", "useradd", "userdel",
    "adduser", "deluser", "addgroup", "delgroup",
    // Kernel control
    "kexec", "modprobe", "insmod", "rmmod", "depmod",
    // Firewall / network config
    "iptables", "ip6tables", "ufw", "firewall-cmd",
    // Container escape
    "docker", "podman", "nerdctl", "ctr",
];

/// Patterns matched against full command strings.
pub const DANGEROUS_PATTERNS: &[&str] = &[
    "rm -rf /", "rm -rf ~", "rm -rf .", "rm -rf *",
    "rm -r /", "rm -rf --no-preserve-root",
    "chmod 777", "chmod -R 777", "chmod a+rwx",
    "chown -R", "chown 0:",
    ":(){ :|:& };:",
    ">/dev/sda", ">/dev/sdb", ">/dev/nvme",
    "eval ", "exec ",
    "source /dev", ". /dev",
];

/// Shells that are blocked as pipe targets (e.g. `curl ... | bash`).
const PIPE_TARGETS: &[&str] = &["| bash", "| sh", "| zsh", "| fish", "| python", "| python3"];

/// Check that `permissions` includes every permission in `require`.
pub fn check_permission(permissions: &[String], require: &[&str]) -> Result<(), String> {
    let missing: Vec<&str> = require
        .iter()
        .copied()
        .filter(|p| !permissions.iter().any(|have| have == p))
        .collect();
    if missing.is_empty() {
        Ok(())
    } else {
        Err(format!("compartment lacks: {missing:?} (needs: {require:?})"))
    }
}

/// Raise an error if the command matches the dangerous-command blocklist.
pub fn check_command(cmd: &str) -> Result<(), String> {
    let cmd = cmd.trim();
    if cmd.is_empty() {
        return Ok(());
    }

    let first_token = cmd.split_whitespace().next().unwrap_or("");
    let base_cmd = first_token.split('/').last().unwrap_or(first_token).to_lowercase();
    if DANGEROUS_COMMANDS.contains(&base_cmd.as_str()) {
        return Err(format!("Command blocked: '{base_cmd}' is not allowed in sandbox mode"));
    }

    let cmd_lower = cmd.to_lowercase();
    for pattern in DANGEROUS_PATTERNS {
        if cmd_lower.contains(&pattern.to_lowercase()) {
            return Err(format!("Command blocked: matches dangerous pattern '{pattern}'"));
        }
    }

    for target in PIPE_TARGETS {
        if cmd_lower.contains(target) {
            return Err(format!(
                "Command blocked: piping to '{}' is not allowed",
                target.trim_start_matches('|').trim()
            ));
        }
    }
    Ok(())
}

/// Validate a policy JSON `{"permissions": [...]}` against required permissions.
pub fn check_permission_json(policy: &Value, require: &[String]) -> Result<(), String> {
    let perms: Vec<String> = policy
        .get("permissions")
        .and_then(Value::as_array)
        .map(|arr| {
            arr.iter()
                .filter_map(Value::as_str)
                .map(|s| s.to_string())
                .collect()
        })
        .unwrap_or_default();
    let req: Vec<&str> = require.iter().map(|s| s.as_str()).collect();
    check_permission(&perms, &req)
}
