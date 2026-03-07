/**
 * QMIND GUI — WebSocket client, event handling, DOM updates.
 */

const FIGURE_CONFIG = [
  { id: "fig-baseline-fairness", api: "fig_baseline_fairness" },
  { id: "fig-baseline-roc", api: "fig_baseline_roc" },
  { id: "fig-mitigation-comparison", api: "fig_mitigation_comparison" },
];
const AGENTS = ["detection", "mitigation", "auditing"];

let ws = null;
let currentAgent = null;

// --- DOM refs ---
const statusBadge = document.getElementById("status-badge");
const runBtn = document.getElementById("run-btn");
const liveLog = document.getElementById("live-log");
if (runBtn) runBtn.disabled = true;  // Disable until WebSocket connects
const attemptInfo = document.getElementById("attempt-info");
const openPaperBtn = document.getElementById("open-paper-btn");

// --- Tab switching ---
document.querySelectorAll(".tab-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab-btn").forEach((b) => {
      b.classList.remove("bg-slate-800", "text-cyan-400");
      b.classList.add("bg-slate-700", "text-slate-400");
    });
    btn.classList.remove("bg-slate-700", "text-slate-400");
    btn.classList.add("bg-slate-800", "text-cyan-400");

    document.querySelectorAll(".tab-content").forEach((c) => c.classList.add("hidden"));
    const tabId = "tab-" + btn.dataset.tab;
    document.getElementById(tabId).classList.remove("hidden");
  });
});

// --- Status ---
function setStatus(text, cls) {
  statusBadge.textContent = text;
  statusBadge.className = "px-3 py-1 rounded-full text-sm font-medium " + (cls || "bg-slate-700 text-slate-300");
}

// --- Pipeline steps ---
function setStepActive(agent) {
  AGENTS.forEach((a) => {
    const el = document.getElementById("step-" + a);
    if (el) {
      el.classList.remove("bg-cyan-600", "text-white", "bg-green-700");
      el.classList.add("bg-slate-700", "text-slate-400");
      if (a === agent) {
        el.classList.remove("bg-slate-700", "text-slate-400");
        el.classList.add("bg-cyan-600", "text-white");
      }
    }
  });
}

function setStepPassed(agent) {
  const el = document.getElementById("step-" + agent);
  if (el) {
    el.classList.remove("bg-cyan-600", "text-white");
    el.classList.add("bg-green-700", "text-white");
  }
}

// --- Live log ---
function appendLog(line) {
  liveLog.textContent += line + "\n";
  liveLog.scrollTop = liveLog.scrollHeight;
}

// --- Fetch helpers ---
async function fetchJson(url) {
  const r = await fetch(url);
  if (!r.ok) return null;
  return r.json();
}

async function fetchText(url) {
  const r = await fetch(url);
  if (!r.ok) return null;
  return r.text();
}

// --- Refresh outputs ---
async function refreshOutputs() {
  const baseline = await fetchJson("/api/outputs/baseline");
  const mitigation = await fetchJson("/api/outputs/mitigation");
  const paper = await fetchText("/api/outputs/paper");

  if (baseline && baseline.baseline_metrics) {
    renderMetricsTable("baseline-table", baseline.baseline_metrics);
  }
  if (mitigation && mitigation.mitigation_metrics) {
    renderMetricsTable("mitigation-table", mitigation.mitigation_metrics);
  }
  if (paper) {
    const paperEl = document.getElementById("paper-content");
    if (typeof marked !== "undefined") {
      paperEl.innerHTML = marked.parse(paper);
    } else {
      paperEl.textContent = paper;
    }
  }

  FIGURE_CONFIG.forEach(({ id, api }) => {
    const img = document.getElementById(id);
    const placeholder = img?.nextElementSibling;
    if (img) {
      img.style.display = "block";
      if (placeholder) placeholder.style.display = "none";
      img.src = "/api/outputs/figures/" + api + "?t=" + Date.now();
      img.onload = () => {
        if (placeholder) placeholder.style.display = "none";
      };
      img.onerror = () => {
        img.style.display = "none";
        if (placeholder) placeholder.style.display = "flex";
      };
    }
  });
}

function renderMetricsTable(containerId, rows) {
  const el = document.getElementById(containerId);
  if (!el || !rows.length) return;
  const keys = Object.keys(rows[0]);
  let html = "<table class='w-full text-sm'><thead><tr>";
  keys.forEach((k) => {
    html += "<th class='px-3 py-2 text-left border-b border-slate-600 text-cyan-400'>" + k + "</th>";
  });
  html += "</tr></thead><tbody>";
  rows.forEach((row) => {
    html += "<tr>";
    keys.forEach((k) => {
      const v = row[k];
      const disp = typeof v === "number" ? (v < 1 && v > 0 ? v.toFixed(4) : v) : String(v);
      html += "<td class='px-3 py-2 border-b border-slate-700'>" + disp + "</td>";
    });
    html += "</tr>";
  });
  html += "</tbody></table>";
  el.innerHTML = html;
}

// --- Judge feedback ---
function addJudgeFeedback(agent, passed, feedback) {
  const el = document.getElementById("judge-feedback");
  const div = document.createElement("div");
  div.className = "rounded-lg border border-slate-700 p-4";
  div.innerHTML =
    "<h4 class='font-semibold " +
    (passed ? "text-green-400" : "text-red-400") +
    "'>" +
    agent +
    ": " +
    (passed ? "PASS" : "FAIL") +
    "</h4><ul class='mt-2 space-y-1 text-sm text-slate-300'>" +
    (feedback || []).map((f) => "<li>" + f + "</li>").join("") +
    "</ul>";
  el.appendChild(div);
}

// --- Open paper on success ---
async function tryOpenPaper() {
  const pdfUrl = "/api/outputs/paper.pdf";
  const r = await fetch(pdfUrl);
  if (r.ok) {
    window.open(pdfUrl, "_blank");
    if (openPaperBtn) {
      openPaperBtn.href = pdfUrl;
      openPaperBtn.textContent = "Open Research Paper (PDF)";
      openPaperBtn.onclick = null;
      openPaperBtn.classList.remove("hidden");
    }
  } else {
    document.querySelector('[data-tab="paper"]').click();
    if (openPaperBtn) {
      openPaperBtn.href = "#";
      openPaperBtn.textContent = "View Paper (Markdown)";
      openPaperBtn.onclick = (e) => {
        e.preventDefault();
        document.querySelector('[data-tab="paper"]').click();
      };
      openPaperBtn.classList.remove("hidden");
    }
  }
}

// --- WebSocket ---
function connect() {
  const protocol = location.protocol === "https:" ? "wss:" : "ws:";
  ws = new WebSocket(protocol + "//" + location.host + "/ws");

  ws.onopen = () => {
    setStatus("Connected", "bg-green-700 text-white");
    runBtn.disabled = false;
  };

  ws.onclose = () => {
    setStatus("Disconnected", "bg-slate-700 text-slate-300");
    runBtn.disabled = false;
    setTimeout(connect, 2000);
  };

  ws.onmessage = (ev) => {
    try {
      const event = JSON.parse(ev.data);
      handleEvent(event);
    } catch (_) {}
  };
}

function handleEvent(event) {
  switch (event.type) {
    case "agent_started":
      currentAgent = event.agent;
      setStepActive(event.agent);
      attemptInfo.textContent = "Running " + event.agent + "...";
      hideProgressBar();
      break;
    case "agent_progress":
      showProgressBar(event.progress, event.label || event.agent);
      break;
    case "agent_log":
      appendLog(event.line || "");
      break;
    case "agent_finished":
      break;
    case "judge_result":
      if (event.passed) {
        setStepPassed(event.agent);
      }
      addJudgeFeedback(event.agent, event.passed, event.feedback);
      attemptInfo.textContent = "Attempt " + (event.attempt || 1) + " — " + (event.passed ? "Passed" : "Retrying...");
      break;
    case "outputs_updated":
      refreshOutputs();
      break;
    case "pipeline_finished":
      hideProgressBar();
      setStatus(event.all_passed ? "Passed" : "Failed", event.all_passed ? "bg-green-700 text-white" : "bg-red-700 text-white");
      runBtn.disabled = false;
      attemptInfo.textContent = event.all_passed ? "All agents passed." : "Pipeline failed.";
      refreshOutputs();
      if (event.all_passed) {
        tryOpenPaper();
      }
      break;
  }
}

function showProgressBar(pct, label) {
  const container = document.getElementById("agent-progress-container");
  const bar = document.getElementById("agent-progress-bar");
  const pctEl = document.getElementById("agent-progress-pct");
  const labelEl = document.getElementById("agent-progress-label");
  if (container && bar && pctEl && labelEl) {
    container.classList.remove("hidden");
    bar.style.width = Math.min(100, Math.max(0, pct * 100)) + "%";
    pctEl.textContent = Math.round(pct * 100) + "%";
    labelEl.textContent = label || currentAgent || "Running...";
  }
}

function hideProgressBar() {
  const container = document.getElementById("agent-progress-container");
  if (container) container.classList.add("hidden");
}

// --- Run ---
runBtn.addEventListener("click", async () => {
  runBtn.disabled = true;
  setStatus("Running", "bg-amber-600 text-white");
  liveLog.textContent = "";
  document.getElementById("judge-feedback").innerHTML = "";
  AGENTS.forEach((a) => {
    const el = document.getElementById("step-" + a);
    if (el) {
      el.classList.remove("bg-cyan-600", "bg-green-700", "text-white");
      el.classList.add("bg-slate-700", "text-slate-400");
    }
  });

  const r = await fetch("/run", { method: "POST" });
  const data = await r.json();
  if (data.status === "already_running") {
    runBtn.disabled = false;
  }
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ action: "run" }));
  }
});

// --- Init ---
connect();
refreshOutputs();
