// Compart Dashboard Vanilla JS Interactive Logic

document.addEventListener("DOMContentLoaded", () => {
  // Elements Selection
  const btnRun = document.getElementById("btn-run");
  const btnRollback = document.getElementById("btn-rollback");
  const taskDescInput = document.getElementById("task-desc");
  const gatingSandbox = document.getElementById("gating-sandbox");
  
  // Permission Inputs
  const permRead = document.getElementById("perm-read");
  const permWrite = document.getElementById("perm-write");
  const permExec = document.getElementById("perm-exec");
  const permNetwork = document.getElementById("perm-network");
  
  // Proxy Inputs
  const injectOpenai = document.getElementById("inject-openai");
  const injectAnthropic = document.getElementById("inject-anthropic");

  // Telemetry Dashboard
  const statusIndicator = document.querySelector(".status-indicator");
  const statusText = document.getElementById("status-text");
  const statusElapsed = document.getElementById("status-elapsed");
  const timelineList = document.getElementById("timeline-list");
  const timelineEmpty = document.getElementById("timeline-empty");
  const diffContainer = document.getElementById("diff-container");
  const diffEmpty = document.getElementById("diff-empty");
  const manifestHashEl = document.getElementById("snap-manifest-hash");

  // Vault Modal elements
  const vaultModal = document.getElementById("vault-modal");
  const navVaultBtn = document.getElementById("nav-vault-btn");
  const vaultCloseBtn = document.getElementById("vault-close-btn");
  const vaultOkBtn = document.getElementById("vault-ok-btn");

  // Exfiltration Alert popup
  const exfilAlert = document.getElementById("exfil-alert");

  // App state variables
  let timerInterval = null;
  let elapsedSeconds = 0;
  let runCount = 0;
  let hasPendingDiffs = false;

  // Task Profiles Map (Simplified from python/compart/sandbox/task_profile.py)
  const TASK_PROFILES = {
    "code": ["upgrade", "update", "bump", "add", "install", "generate", "create", "write", "refactor", "restructure"],
    "debugging": ["fix", "bug", "error", "crash", "broken", "issue"],
    "research": ["explore", "investigate", "understand", "what", "how", "why", "list", "show", "find", "search"],
    "testing": ["test"],
    "security": ["security", "auth", "permission", "vulnerability", "injection"],
    "writing": ["document", "readme", "comment", "docstring", "docs"]
  };

  function classifyTask(text) {
    const words = text.trim().toLowerCase().split(/\s+/);
    const firstWord = words[0] || "";
    for (const [profile, keywords] of Object.entries(TASK_PROFILES)) {
      if (keywords.includes(firstWord) || words.slice(0, 3).some(w => keywords.includes(w))) {
        return profile;
      }
    }
    return "code";
  }

  // Vault Modal Triggers
  navVaultBtn.addEventListener("click", (e) => {
    e.preventDefault();
    vaultModal.classList.add("show");
  });

  const closeModal = () => vaultModal.classList.remove("show");
  vaultCloseBtn.addEventListener("click", closeModal);
  vaultOkBtn.addEventListener("click", closeModal);

  // Insulate & Run Execution Click
  btnRun.addEventListener("click", () => {
    const prompt = taskDescInput.value.trim();
    if (!prompt) {
      alert("Please enter a task prompt or request before executing the sandbox.");
      return;
    }

    runCount++;
    btnRun.disabled = true;
    taskDescInput.disabled = true;
    
    // Clear exfil alert if active
    exfilAlert.classList.remove("show");

    // Initialize Telemetry Loading Indicator
    statusIndicator.className = "status-indicator running";
    statusText.textContent = "Insulating Inner Compartments...";
    
    elapsedSeconds = 0;
    statusElapsed.textContent = "0.0s elapsed";
    
    // Start Elapsed Timer
    clearInterval(timerInterval);
    timerInterval = setInterval(() => {
      elapsedSeconds += 0.1;
      statusElapsed.textContent = `${elapsedSeconds.toFixed(1)}s elapsed`;
    }, 100);

    // Run execution simulation stages
    setTimeout(() => {
      // Step 2: Applying sandbox constraints
      statusText.textContent = gatingSandbox.checked 
        ? "Applying OS Kernel Sandbox (Seatbelt)..." 
        : "Entering Compartment (Unsandboxed Mode)...";
    }, 600);

    setTimeout(() => {
      // Step 3: Executing task logic
      statusText.textContent = "Executing Inner Compartment: main_agent...";
    }, 1300);

    setTimeout(() => {
      // Complete run execution
      clearInterval(timerInterval);
      btnRun.disabled = false;
      taskDescInput.disabled = false;

      const profile = classifyTask(prompt);
      const isSandboxActive = gatingSandbox.checked;
      
      // Determine if a mock exfiltration violation occurred
      // (If network permission is NOT checked, and task description hints at download/web/fetch/exfiltrate/curl/send)
      const needsNetwork = ["network", "curl", "wget", "fetch", "download", "post", "send", "http", "exfiltrate"].some(
        keyword => prompt.toLowerCase().includes(keyword)
      );
      const exfilBlocked = needsNetwork && !permNetwork.checked;

      // Update telemtry box status card
      statusIndicator.className = exfilBlocked ? "status-indicator error" : "status-indicator success";
      statusText.textContent = exfilBlocked ? "Policy Violation Detected" : "Execution Completed Successfully";

      // Hide empty state if present
      if (timelineEmpty) timelineEmpty.style.display = "none";

      // Build active mesh list items
      const execCard = document.createElement("div");
      execCard.className = "execution-card";
      
      const badgeClass = exfilBlocked ? "failed" : "success";
      const statusLabel = exfilBlocked ? "Violation Blocked" : "Success";
      
      // Mock log compression stats (Pro engine token reducer)
      const originalBytes = (prompt.length * 15 + Math.random() * 8000).toFixed(0);
      const compressedBytes = (originalBytes * 0.05).toFixed(0);
      const savingsPercent = 95;

      const grantedList = [];
      if (permRead.checked) grantedList.push("fs_read");
      if (permWrite.checked) grantedList.push("fs_write");
      if (permExec.checked) grantedList.push("fs_exec");
      if (permNetwork.checked) grantedList.push("network");

      execCard.innerHTML = `
        <div class="exec-header">
          <span class="exec-title">compartment_session_${runCount}</span>
          <span class="exec-badge ${badgeClass}">${statusLabel}</span>
        </div>
        <p class="exec-prompt">${prompt}</p>
        <div class="exec-stats">
          <div class="exec-stats-item">
            <span>Profile: <strong>${profile}</strong></span>
          </div>
          <div class="exec-stats-item">
            <span>Compression: <strong>${savingsPercent}% (${(originalBytes / 1024).toFixed(1)}KB → ${(compressedBytes / 1024).toFixed(1)}KB)</strong></span>
          </div>
          <div class="exec-stats-item">
            <span>Grants: <strong>[${grantedList.join(", ")}]</strong></span>
          </div>
        </div>
      `;

      // Insert at top of list
      timelineList.insertBefore(execCard, timelineList.firstChild);

      // Trigger exfiltration alert popup if blocked
      if (exfilBlocked) {
        exfilAlert.querySelector(".alert-text").textContent = `Compartment "compartment_session_${runCount}" attempted to open outbound connection. Process egress terminated by active OS kernel rules.`;
        exfilAlert.classList.add("show");
      }

      // Populate file diff cards in column 3 (Time-Machine)
      if (permWrite.checked && !exfilBlocked) {
        hasPendingDiffs = true;
        btnRollback.disabled = false;
        if (diffEmpty) diffEmpty.style.display = "none";
        
        // Generate new random manifest hash
        const nextHash = Math.floor(Math.random() * 0xffffffffffff).toString(16).padStart(16, "0");
        manifestHashEl.textContent = nextHash;

        diffContainer.innerHTML = `
          <div class="diff-item">
            <div class="diff-file-meta">
              <span class="diff-path">src/main.rs</span>
              <span class="diff-operation-badge op-modify">Modified</span>
            </div>
            <div class="diff-code-panel">
              <div class="diff-line removed">- fn execute_unsafe() {</div>
              <div class="diff-line added">+ fn execute_safe() {</div>
              <div class="diff-line context">    println!("Insulated under Compart");</div>
            </div>
          </div>
          
          <div class="diff-item">
            <div class="diff-file-meta">
              <span class="diff-path">temp_debug.log</span>
              <span class="diff-operation-badge op-add">Created</span>
            </div>
            <div class="diff-code-panel">
              <div class="diff-line added">+ [INFO] Compartment insulated successfully</div>
              <div class="diff-line added">+ [INFO] Applied macOS Seatbelt constraints</div>
            </div>
          </div>
        `;
      }

    }, 2000);
  });

  // Rollback Workspace Action Trigger
  btnRollback.addEventListener("click", () => {
    if (!hasPendingDiffs) return;

    btnRollback.disabled = true;
    
    // Clear and restore Time-Machine
    diffContainer.innerHTML = `
      <div class="empty-state" id="diff-empty">
        <svg viewBox="0 0 24 24" width="32" height="32" stroke="currentColor" stroke-width="1.5" fill="none" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="9" y1="15" x2="15" y2="15"></line></svg>
        <p>Workspace matches manifest. Rollback completed successfully via BLAKE3 hashes.</p>
      </div>
    `;

    manifestHashEl.textContent = "a9d6f920bc4ef13e"; // Restored original manifest hash
    hasPendingDiffs = false;

    // Pulse telemetry box status card green briefly
    const origClass = statusIndicator.className;
    const origText = statusText.textContent;
    statusIndicator.className = "status-indicator success";
    statusText.textContent = "Workspace Restored to Manifest";

    setTimeout(() => {
      statusIndicator.className = "status-indicator idle";
      statusText.textContent = "Sandbox Engine Idle";
    }, 1800);
  });

  // Auto-fill prompts if empty clicking placeholder
  taskDescInput.addEventListener("focus", () => {
    if (!taskDescInput.value) {
      taskDescInput.value = "Fix error logging by checking the output and sending report to external server.";
    }
  });

});
