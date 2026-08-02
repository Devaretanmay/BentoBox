use serde_json::Value;

/// Commands blocked regardless of `fs_exec` permission.
pub const DANGEROUS_COMMANDS: &[&str] = &[
    "mkfs",
    "mkfs.ext4",
    "mkfs.btrfs",
    "mkfs.xfs",
    "mkfs.fat",
    "mkswap",
    "fdisk",
    "parted",
    "partprobe",
    "gdisk",
    "sfdisk",
    "dd",
    "sudo",
    "su",
    "doas",
    "pkexec",
    "visudo",
    "shutdown",
    "reboot",
    "poweroff",
    "halt",
    "init",
    "systemctl",
    "telinit",
    "runlevel",
    "passwd",
    "chpasswd",
    "usermod",
    "groupmod",
    "useradd",
    "userdel",
    "adduser",
    "deluser",
    "addgroup",
    "delgroup",
    "kexec",
    "modprobe",
    "insmod",
    "rmmod",
    "depmod",
    "iptables",
    "ip6tables",
    "ufw",
    "firewall-cmd",
    "docker",
    "podman",
    "nerdctl",
    "ctr",
];

/// Patterns matched against full command strings.
pub const DANGEROUS_PATTERNS: &[&str] = &[
    "rm -rf /",
    "rm -rf ~",
    "rm -rf .",
    "rm -rf *",
    "rm -r /",
    "rm -rf --no-preserve-root",
    "chmod 777",
    "chmod -R 777",
    "chmod a+rwx",
    "chown -R",
    "chown 0:",
    ":(){ :|:& };:",
    ">/dev/sda",
    ">/dev/sdb",
    ">/dev/nvme",
    "eval ",
    "exec ",
    "source /dev",
    ". /dev",
];

const PIPE_TARGETS: &[&str] = &["| bash", "| sh", "| zsh", "| fish", "| python", "| python3"];

pub fn check_permission(permissions: &[String], require: &[&str]) -> Result<(), String> {
    let missing: Vec<&str> = require
        .iter()
        .copied()
        .filter(|p| !permissions.iter().any(|have| have == p))
        .collect();
    if missing.is_empty() {
        Ok(())
    } else {
        Err(format!(
            "compartment lacks: {missing:?} (needs: {require:?})"
        ))
    }
}

pub fn check_command(cmd: &str) -> Result<(), String> {
    let cmd = cmd.trim();
    if cmd.is_empty() {
        return Ok(());
    }

    let first_token = cmd.split_whitespace().next().unwrap_or("");
    let base_cmd = first_token
        .split('/')
        .next_back()
        .unwrap_or(first_token)
        .to_lowercase();
    if DANGEROUS_COMMANDS.contains(&base_cmd.as_str()) {
        return Err(format!(
            "Command blocked: '{base_cmd}' is not allowed in sandbox mode"
        ));
    }

    let cmd_lower = cmd.to_lowercase();
    for pattern in DANGEROUS_PATTERNS {
        if cmd_lower.contains(&pattern.to_lowercase()) {
            return Err(format!(
                "Command blocked: matches dangerous pattern '{pattern}'"
            ));
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
