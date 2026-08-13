// Interactive logic for Compart landing page

let compartments = [
    { name: "Research", perms: ["fs_read"] },
    { name: "Builder", perms: ["fs_read", "fs_write", "fs_exec"] }
];

document.addEventListener("DOMContentLoaded", () => {
    renderCompartments();
});

function copyInstallCmd() {
    const text = document.getElementById("install-cmd").innerText;
    navigator.clipboard.writeText(text);
    const copyBtn = document.querySelector(".copy-btn");
    copyBtn.innerText = "Copied!";
    setTimeout(() => { copyBtn.innerText = "Copy"; }, 2000);
}

function switchTab(tabId) {
    document.querySelectorAll(".tab-btn").forEach(btn => btn.classList.remove("active"));
    document.querySelectorAll(".tab-content").forEach(content => content.classList.remove("active"));

    event.target.classList.add("active");
    document.getElementById(`tab-${tabId}`).classList.add("active");
}

function renderCompartments() {
    const list = document.getElementById("compartment-list");
    if (!list) return;
    
    list.innerHTML = compartments.map((comp, idx) => `
        <div class="compartment-item">
            <div class="comp-header">
                <span>${comp.name}</span>
                ${compartments.length > 1 ? `<button class="copy-btn" onclick="removeCompartment(${idx})">Remove</button>` : ''}
            </div>
            <div class="perm-checkboxes">
                <label><input type="checkbox" ${comp.perms.includes('fs_read') ? 'checked' : ''} onchange="togglePerm(${idx}, 'fs_read')"> fs_read</label>
                <label><input type="checkbox" ${comp.perms.includes('fs_write') ? 'checked' : ''} onchange="togglePerm(${idx}, 'fs_write')"> fs_write</label>
                <label><input type="checkbox" ${comp.perms.includes('fs_exec') ? 'checked' : ''} onchange="togglePerm(${idx}, 'fs_exec')"> fs_exec</label>
                <label><input type="checkbox" ${comp.perms.includes('network') ? 'checked' : ''} onchange="togglePerm(${idx}, 'network')"> network</label>
            </div>
        </div>
    `).join('');

    updateTopologyJson();
}

function addCompartment() {
    const input = document.getElementById("comp-name-input");
    const name = input.value.trim();
    if (!name) return;

    compartments.push({ name: name, perms: ["fs_read"] });
    input.value = "";
    renderCompartments();
}

function removeCompartment(idx) {
    compartments.splice(idx, 1);
    renderCompartments();
}

function togglePerm(idx, perm) {
    const comp = compartments[idx];
    if (comp.perms.includes(perm)) {
        comp.perms = comp.perms.filter(p => p !== perm);
    } else {
        comp.perms.push(perm);
    }
    updateTopologyJson();
}

function updateTopologyJson() {
    const jsonObj = {
        name: "my_agent_workspace",
        compartments: {},
        connections: compartments.length > 1 ? [[compartments[0].name, compartments[1].name]] : []
    };

    compartments.forEach(c => {
        jsonObj.compartments[c.name] = {
            permissions: c.perms
        };
    });

    document.getElementById("topology-json-display").textContent = JSON.stringify(jsonObj, null, 2);
}

function copyTopologyJson() {
    const text = document.getElementById("topology-json-display").textContent;
    navigator.clipboard.writeText(text);
    alert("Copied .compart/topology.json to clipboard!");
}
