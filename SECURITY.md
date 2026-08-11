# Security Policy

## Reporting Security Vulnerabilities

If you discover a security vulnerability within Compart, please send an email to `security@compart.dev` or report it via private GitHub security advisory. Please do not report security vulnerabilities through public GitHub issues.

All security vulnerabilities will be promptly acknowledged and investigated.

## Security Architecture

Compart utilizes kernel-level enforcement primitives (macOS Seatbelt SBPL & Linux Landlock LSM) to enforce deny-by-default syscall boundaries around untrusted AI agent execution.
