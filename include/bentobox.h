#ifndef BENTOBOX_H
#define BENTOBOX_H

/* Stable C ABI for the BentoBox Rust core.
 * Used by the Go and TypeScript SDKs. Strings returned by this API
 * must be freed with bentobox_free(). */

#ifdef __cplusplus
extern "C" {
#endif

/* Version of the core library. Free the result with bentobox_free(). */
char *bentobox_version(void);

/* 1 if kernel sandboxing is supported on this platform, 0 otherwise. */
int bentobox_sandbox_supported(void);

/* Apply the sandbox, restricting the current process tree to worktree_path.
 * Returns 0 on success, -1 on sandbox failure, -2 on panic.
 * Check bentobox_last_error() for details. */
int bentobox_sandbox_apply(const char *worktree_path, int block_network);

/* Explain why path (file or tcp:/udp: address) would be blocked by the
 * sandbox rules for worktree_path. Free the result with bentobox_free(). */
char *bentobox_sandbox_why(const char *path, const char *worktree_path,
                           int block_network);

/* Compress content through the smart crusher. Free with bentobox_free(). */
char *bentobox_compress(const char *content);

/* Last error message. Free with bentobox_free(). */
char *bentobox_last_error(void);

/* Free a string returned by this API. */
void bentobox_free(char *ptr);

/* Compartment runtime. All functions take JSON strings and return
 * int status codes: 1 = yes/allowed, 0 = no/denied/invalid,
 * -1 = error, -2 = panic. Check bentobox_last_error() for reasons. */

/* Check policy JSON {"permissions":[...]} against required permission JSON list. */
int bentobox_runtime_check_permission(const char *policy_json, const char *required_json);

/* Check a command string against the dangerous-command blocklist. */
int bentobox_runtime_check_command(const char *cmd);

/* Snapshot workdir into snapshot_dir, excluding dirs listed in JSON array.
 * Returns number of files snapshotted, or -1 on error. */
int bentobox_runtime_snapshot(const char *workdir, const char *snapshot_dir,
                              const char *exclude_json);

/* Restore changed files from snapshot_dir back into workdir. */
int bentobox_runtime_restore(const char *workdir, const char *snapshot_dir);

/* Validate compartment configs JSON + edges JSON. */
int bentobox_runtime_validate(const char *configs_json, const char *edges_json);

/* Check if a message from `from` to `to` is permitted by the configs.
 * Returns 1 if allowed, 0 if denied by a whitelist, -1 if a compartment
 * is unknown or input is invalid, -2 on panic. */
int bentobox_runtime_can_route(const char *configs_json, const char *from, const char *to);

/* Match a request path against routes JSON; on match, return the rewritten
 * upstream URL as an allocated string (free with bentobox_free()), or NULL
 * if no route matched or on error. */
char *bentobox_runtime_credential_rewrite(const char *routes_json, const char *path);

/* Resolve a credential source like "env:OPENAI_API_KEY". Returns an
 * allocated string (free with bentobox_free()); an unknown source or
 * unset env var yields an empty string, NULL only on error. */
char *bentobox_runtime_credential_resolve(const char *source);

/* Opaque runtime handle. Builds a compartment Runtime once (parsing the
 * configs + edges JSON a single time) so hot-path routing below does not
 * re-parse JSON on every call. Destroy with bentobox_runtime_free().
 * Returns NULL on error; check bentobox_last_error().
 *
 * Thread-safe: the handle wraps the Runtime in an internal Mutex, so a
 * single handle may be shared across threads/goroutines. Free it exactly
 * once, after all threads have finished with it. */
void *bentobox_runtime_new(const char *configs_json, const char *edges_json);

/* Destroy a runtime handle created by bentobox_runtime_new(). NULL is a no-op. */
void bentobox_runtime_free(void *handle);

/* Route a message through a runtime handle. Returns 1 if allowed,
 * 0 if denied by a whitelist, -1 if a compartment is unknown or the handle
 * is NULL, -2 on panic. */
int bentobox_runtime_handle_can_route(void *handle, const char *from, const char *to);

/* Resolve the execution order through a runtime handle as a JSON array of
 * compartment names, optionally starting at entry (NULL = from the start).
 * Free the result with bentobox_free(). */
char *bentobox_runtime_handle_run_order(void *handle, const char *entry);

#ifdef __cplusplus
}
#endif

#endif /* BENTOBOX_H */
