/**
 * Compart Desktop — Frontend logic.
 *
 * Calls real Python backend via window.pywebview.api.*
 * Falls back to a static demo if pywebview is not available (browser preview).
 */

document.addEventListener("DOMContentLoaded", () => {
  const cmdInput = document.getElementById("cmd-input");
  const btnRun = document.getElementById("btn-run");
  const btnRollback = document.getElementById("btn-rollback");
  const terminal = document.getElementById("terminal");
  const outputMeta = document.getElementById("output-meta");
  const diffList = document.getElementById("diff-list");
  const diffEmpty = document.getElementById("diff-empty");
  const workdirDisplay = document.getElementById("workdir-display");
  const statusPill = document.getElementById("status-pill");
  const sysType = document.getElementById("sys-sandbox-type");
  const sysPython = document.getElementById("sys-python");
  const workspacePath = document.getElementById("workspace-path");

  const pRead = document.getElementById("p-read");
  const pWrite = document.getElementById("p-write");
  const pExec = document.getElementById("p-exec");
  const pNet = document.getElementById("p-net");
  const tSandbox = document.getElementById("t-sandbox");
  const tNetwork = document.getElementById("t-network");

  let api = null;
  let currentWorkdir = "";

  // ── Wait for pywebview bridge ──

  function initAPI() {
    if (window.pywebview && window.pywebview.api) {
      api = window.pywebview.api;
      loadSystemInfo();
      loadWorkspace();
    } else {
      // Browser fallback — show static hint
      workdirDisplay.textContent = "/path/to/your/project";
      sysType.textContent = "Preview";
      sysPython.textContent = "";
      workspacePath.textContent = "compart (browser preview)";
    }
  }

  if (window.pywebview && window.pywebview.api) {
    initAPI();
  } else {
    window.addEventListener("pywebviewready", initAPI);
    // Fallback timeout for browser preview
    setTimeout(() => { if (!api) initAPI(); }, 500);
  }

  // ── Load system info ──

  async function loadSystemInfo() {
    try {
      const info = await api.get_system_info();
      sysType.textContent = info.sandbox_type;
      sysPython.textContent = `Python ${info.python}`;
      if (info.native_available) {
        tSandbox.checked = true;
      }
    } catch (e) {
      sysType.textContent = "Unknown";
    }
  }

  // ── Load workspace ──

  async function loadWorkspace() {
    try {
      currentWorkdir = await api.get_workspace();
      workdirDisplay.textContent = currentWorkdir;
      // Show just the basename in titlebar
      const parts = currentWorkdir.split("/");
      workspacePath.textContent = parts[parts.length - 1] || currentWorkdir;
    } catch (e) {
      workdirDisplay.textContent = "Error loading workspace";
    }
  }

  // ── Run sandboxed command ──

  btnRun.addEventListener("click", runCommand);
  cmdInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") { e.preventDefault(); runCommand(); }
  });

  async function runCommand() {
    const cmd = cmdInput.value.trim();
    if (!cmd) { cmdInput.focus(); return; }

    // Gather permissions
    const perms = [];
    if (pRead.checked) perms.push("fs_read");
    if (pWrite.checked) perms.push("fs_write");
    if (pExec.checked) perms.push("fs_exec");
    if (pNet.checked) perms.push("network");

    // UI: set running state
    btnRun.disabled = true;
    statusPill.className = "status-pill running";
    statusPill.textContent = "Running";
    terminal.innerHTML = "";
    outputMeta.innerHTML = "";
    diffList.innerHTML = "";
    btnRollback.disabled = true;

    appendTerm(`$ ${cmd}\n`, "term-info");

    if (!api) {
      // Browser fallback demo
      appendTerm("⚠ pywebview not available. Running in browser preview mode.\n", "term-err");
      statusPill.className = "status-pill idle";
      statusPill.textContent = "Preview";
      btnRun.disabled = false;
      return;
    }

    try {
      const result = await api.run_sandboxed(
        cmd,
        currentWorkdir,
        perms,
        tSandbox.checked,
        tNetwork.checked,
      );

      // Display output
      if (result.stdout) appendTerm(result.stdout + "\n");
      if (result.stderr) appendTerm(result.stderr + "\n", "term-err");
      if (result.error) appendTerm(`\nError: ${result.error}\n`, "term-err");

      // Status
      const isOk = result.returncode === 0 && !result.error;
      statusPill.className = isOk ? "status-pill success" : "status-pill error";
      statusPill.textContent = isOk ? "Success" : "Failed";

      // Meta bar
      const exitClass = isOk ? "exit-ok" : "exit-fail";
      outputMeta.innerHTML = `
        <span class="${exitClass}">exit ${result.returncode}</span>
        <span>${result.elapsed_s}s</span>
      `;

      // Diffs
      if (result.diffs && result.diffs.length > 0) {
        renderDiffs(result.diffs);
        btnRollback.disabled = false;
      } else {
        diffList.innerHTML = '<div class="diff-empty">No file changes detected.</div>';
      }

    } catch (e) {
      appendTerm(`\nException: ${e}\n`, "term-err");
      statusPill.className = "status-pill error";
      statusPill.textContent = "Error";
    }

    btnRun.disabled = false;
  }

  // ── Rollback ──

  btnRollback.addEventListener("click", async () => {
    if (!api) return;
    btnRollback.disabled = true;
    appendTerm("\n↺ Rolling back workspace...\n", "term-info");

    try {
      const res = await api.rollback();
      if (res.error) {
        appendTerm(`Rollback error: ${res.error}\n`, "term-err");
      } else {
        appendTerm(`Restored ${res.restored} file(s).\n`, "term-info");
        diffList.innerHTML = '<div class="diff-empty">Workspace restored to snapshot.</div>';
        statusPill.className = "status-pill success";
        statusPill.textContent = "Rolled Back";
      }
    } catch (e) {
      appendTerm(`Rollback failed: ${e}\n`, "term-err");
    }
  });

  // ── Helpers ──

  function appendTerm(text, cls) {
    const span = document.createElement("span");
    if (cls) span.className = cls;
    span.textContent = text;
    terminal.appendChild(span);
    terminal.scrollTop = terminal.scrollHeight;
  }

  function renderDiffs(diffs) {
    diffList.innerHTML = "";
    for (const d of diffs) {
      const op = d.op || d.operation || "modified";
      const path = d.path || d.file || "unknown";
      const item = document.createElement("div");
      item.className = "diff-item";
      item.innerHTML = `
        <span class="diff-badge ${op}">${op}</span>
        <span class="diff-path">${path}</span>
      `;
      diffList.appendChild(item);
    }
  }
});
