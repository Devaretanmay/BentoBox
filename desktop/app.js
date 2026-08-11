document.addEventListener("DOMContentLoaded", () => {
  const btnRun = document.getElementById("btn-run");
  const taskInput = document.getElementById("task-input");
  const sessionList = document.getElementById("session-list");
  const exfilAlert = document.getElementById("exfil-alert");
  const exfilText = document.getElementById("exfil-text");

  const vaultModal = document.getElementById("vault-modal");
  const navVaultBtn = document.getElementById("nav-vault-btn");
  const vaultCloseBtn = document.getElementById("vault-close-btn");
  const vaultOkBtn = document.getElementById("vault-ok-btn");

  let runCount = 2;

  // Vault modal
  navVaultBtn.addEventListener("click", (e) => {
    e.preventDefault();
    vaultModal.classList.add("show");
  });
  const closeVault = () => vaultModal.classList.remove("show");
  vaultCloseBtn.addEventListener("click", closeVault);
  vaultOkBtn.addEventListener("click", closeVault);
  vaultModal.addEventListener("click", (e) => {
    if (e.target === vaultModal) closeVault();
  });

  // Run a new sandbox session
  function triggerRun() {
    const prompt = taskInput.value.trim();
    if (!prompt) {
      taskInput.focus();
      return;
    }

    runCount++;
    taskInput.value = "";

    const needsNetwork = /network|curl|wget|fetch|download|post|send|http|exfiltrate/i.test(prompt);
    const isBlocked = needsNetwork;

    const card = document.createElement("div");
    card.className = "branch-card";

    const sessionName = `sandbox-session-${runCount}`;
    const timeAgo = "just now";

    if (isBlocked) {
      card.innerHTML = `
        <div class="branch-header">
          <div class="branch-name-row">
            <span class="branch-icon-pill warning">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path><line x1="12" y1="9" x2="12" y2="13"></line><line x1="12" y1="17" x2="12.01" y2="17"></line></svg>
            </span>
            <span class="branch-name">${sessionName}</span>
          </div>
          <span class="branch-meta">Violation · ${timeAgo} · <span class="pr-badge">⚠ Blocked</span></span>
        </div>
        <div class="branch-actions">
          <button class="btn-branch">View Diffs ↗</button>
          <button class="btn-branch">Rollback ↺</button>
          <button class="btn-branch-icon">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="5" r="1"></circle><circle cx="12" cy="12" r="1"></circle><circle cx="12" cy="19" r="1"></circle></svg>
          </button>
        </div>
        <div class="commit-list">
          <div class="commit-item error">
            <span class="commit-dot error"></span>
            <span class="commit-msg">Egress blocked: ${prompt.substring(0, 60)}</span>
          </div>
          <div class="commit-item">
            <span class="commit-dot"></span>
            <span class="commit-msg">Workspace rolled back to manifest</span>
          </div>
        </div>
      `;

      exfilText.textContent = `"${sessionName}" attempted outbound network access. Terminated by kernel Landlock/Seatbelt rules.`;
      exfilAlert.classList.add("show");
      setTimeout(() => exfilAlert.classList.remove("show"), 5000);
    } else {
      card.innerHTML = `
        <div class="branch-header">
          <div class="branch-name-row">
            <span class="branch-icon-pill">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path></svg>
            </span>
            <span class="branch-name">${sessionName}</span>
          </div>
          <span class="branch-meta">Completed · ${timeAgo}</span>
        </div>
        <div class="branch-actions">
          <button class="btn-branch">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline></svg>
            View Diffs ↗
          </button>
          <button class="btn-branch">Rollback ↺</button>
          <button class="btn-branch-icon">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="5" r="1"></circle><circle cx="12" cy="12" r="1"></circle><circle cx="12" cy="19" r="1"></circle></svg>
          </button>
        </div>
        <div class="commit-list">
          <div class="commit-item">
            <span class="commit-dot"></span>
            <span class="commit-msg">Applied kernel sandbox constraints</span>
          </div>
          <div class="commit-item">
            <span class="commit-dot"></span>
            <span class="commit-msg">${prompt.substring(0, 70)}</span>
          </div>
          <div class="commit-item">
            <span class="commit-dot"></span>
            <span class="commit-msg">BLAKE3 snapshot captured</span>
          </div>
        </div>
      `;
    }

    sessionList.insertBefore(card, sessionList.firstChild);
  }

  btnRun.addEventListener("click", triggerRun);

  taskInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      triggerRun();
    }
  });
});
