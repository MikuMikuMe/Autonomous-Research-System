/**
 * Bias Audit Pipeline GUI — WebSocket client, event handling, DOM updates.
 */

const FIGURE_CONFIG = [
  { id: "fig-baseline-fairness", api: "fig_baseline_fairness" },
  { id: "fig-baseline-roc", api: "fig_baseline_roc" },
  { id: "fig-mitigation-comparison", api: "fig_mitigation_comparison" },
];
const AGENTS = ["detection", "mitigation", "auditing"];

let ws = null;
let currentAgent = null;
let latestJourneySummary = null;

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
  const memory = await fetchJson("/api/memory/journey");

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
  if (memory && !memory.error) {
    latestJourneySummary = memory;
    renderMemorySummary(memory);
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

function renderMemorySummary(summary) {
  const el = document.getElementById("memory-summary");
  if (!el) return;
  if (!summary || !summary.total_runs) {
    el.innerHTML = "<div class='rounded-lg border border-slate-700 bg-slate-950 p-4 text-slate-400'>No memory captured yet.</div>";
    return;
  }

  const agentCards = Object.entries(summary.agents || {}).map(([agent, info]) => {
    const recentTrials = (info.recent_trials || []).slice(0, 5).map((trial) => {
      const statusClass = trial.passed ? "text-green-400" : "text-red-400";
      const statusLabel = trial.passed ? "passed" : "failed";
      const detail = [trial.error_type, trial.feedback_preview].filter(Boolean).join(" - ");
      return "<li class='text-sm text-slate-300'><span class='" + statusClass + "'>" + statusLabel + "</span> seed " + trial.seed + " (attempt " + trial.attempt + ")" + (detail ? ": " + detail : "") + "</li>";
    }).join("");

    const failureReasons = Object.entries(info.failure_reasons || {}).map(([reason, count]) => {
      return "<li class='text-sm text-slate-300'>" + reason + ": " + count + "</li>";
    }).join("");

    const directions = (info.improvement_directions || []).map((direction) => {
      return "<li class='text-sm text-amber-300'>" + direction + "</li>";
    }).join("");

    return "<section class='rounded-lg border border-slate-700 bg-slate-950 p-4'>" +
      "<div class='flex flex-wrap items-center justify-between gap-3 mb-3'>" +
      "<h3 class='text-lg font-semibold text-cyan-400'>" + agent + "</h3>" +
      "<div class='text-sm text-slate-400'>attempts: " + (info.total_attempts || 0) + " | success: " + Math.round((info.success_rate || 0) * 100) + "% | best seed: " + (info.best_seed ?? "n/a") + "</div>" +
      "</div>" +
      "<div class='grid grid-cols-1 lg:grid-cols-3 gap-4'>" +
      "<div><h4 class='mb-2 text-sm font-medium text-slate-200'>Recent trials</h4><ul class='space-y-2'>" + (recentTrials || "<li class='text-sm text-slate-500'>No trials yet.</li>") + "</ul></div>" +
      "<div><h4 class='mb-2 text-sm font-medium text-slate-200'>Failure reasons</h4><ul class='space-y-2'>" + (failureReasons || "<li class='text-sm text-slate-500'>No recurring failures.</li>") + "</ul></div>" +
      "<div><h4 class='mb-2 text-sm font-medium text-slate-200'>Improvement directions</h4><ul class='space-y-2'>" + directions + "</ul></div>" +
      "</div>" +
      "</section>";
  }).join("");

  const unverifiedClaims = (summary.unverified_claims || []).map((claim) => {
    const evidence = claim.evidence ? "<div class='text-xs text-slate-500 mt-1'>" + claim.evidence + "</div>" : "";
    return "<li class='rounded border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-300'>" + claim.claim + evidence + "</li>";
  }).join("");

  el.innerHTML =
    "<section class='rounded-lg border border-slate-700 bg-slate-950 p-4'>" +
    "<div class='flex flex-wrap items-center justify-between gap-3'>" +
    "<h2 class='text-xl font-semibold text-cyan-400'>Agent memory</h2>" +
    "<div class='text-sm text-slate-400'>Total runs remembered: " + summary.total_runs + "</div>" +
    "</div>" +
    "</section>" +
    agentCards +
    "<section class='rounded-lg border border-slate-700 bg-slate-950 p-4'>" +
    "<h3 class='mb-2 text-lg font-semibold text-cyan-400'>Unverified claims</h3>" +
    "<ul class='space-y-2'>" + (unverifiedClaims || "<li class='text-sm text-slate-500'>No unresolved claims.</li>") + "</ul>" +
    "</section>";
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
  // Dispatch to registered handlers in order
  for (const handler of _eventHandlers) {
    if (handler(event) === false) return;  // handler returns false to stop propagation
  }
}

// Registry of event handlers; first registered = first called.
const _eventHandlers = [];

function _handlePipelineEvent(event) {
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
    case "memory_insight":
      appendLog(event.line || "");
      break;
    case "journey_summary":
      latestJourneySummary = event.summary || null;
      renderMemorySummary(latestJourneySummary);
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
  latestJourneySummary = null;
  renderMemorySummary(null);
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
// Register event handlers before connecting so all messages are handled
_eventHandlers.push(_handlePipelineEvent);
// Idea handler is registered later after its function definition
connect();
refreshOutputs();

// ============================================================
// Idea Verifier UI
// ============================================================

let activeIdeaSession = null;

function ideaLog(line) {
  const el = document.getElementById("idea-live-log");
  if (el) {
    el.textContent += line + "\n";
    el.scrollTop = el.scrollHeight;
  }
}

function setIdeaProgress(pct, label) {
  const bar = document.getElementById("idea-progress-bar");
  const pctEl = document.getElementById("idea-progress-pct");
  const labelEl = document.getElementById("idea-progress-label");
  if (bar) bar.style.width = Math.min(100, Math.max(0, pct * 100)) + "%";
  if (pctEl) pctEl.textContent = Math.round(pct * 100) + "%";
  if (labelEl) labelEl.textContent = label || "Processing...";
}

function showIdeaSection(id) {
  const el = document.getElementById(id);
  if (el) el.classList.remove("hidden");
}

function renderIdeaIteration(iterData) {
  const container = document.getElementById("idea-iteration-cards");
  if (!container) return;
  showIdeaSection("idea-iterations-section");
  const flaws = (iterData.flaws || []).map((f) => `<li class="text-red-300 text-sm">${f}</li>`).join("");
  const card = document.createElement("div");
  card.className = "rounded-lg border border-slate-700 bg-slate-900 p-4";
  card.innerHTML =
    `<div class="flex items-center justify-between mb-2">` +
    `<span class="font-medium text-slate-200">Iteration ${iterData.iteration}</span>` +
    `<span class="text-xs text-slate-400">${iterData.papers_count || 0} papers found</span>` +
    `</div>` +
    `<p class="text-sm text-slate-300 mb-2">${iterData.summary || ""}</p>` +
    (flaws ? `<ul class="list-disc list-inside space-y-1">${flaws}</ul>` : "");
  container.appendChild(card);
}

function renderIdeaReport(report) {
  const container = document.getElementById("idea-report-content");
  if (!container) return;
  showIdeaSection("idea-report-section");

  const verdictColor = {
    novel: "text-green-400",
    supported: "text-blue-400",
    contradicted: "text-yellow-400",
    flawed: "text-red-400",
    error: "text-red-500",
  }[report.verdict] || "text-slate-300";

  const noveltyPct = Math.round((report.novelty_score || 0) * 100);
  const flaws = (report.flaws || []).map((f) => `<li class="text-red-300 text-sm">${f}</li>`).join("");
  const supported = (report.supported_claims || []).map((c) => `<li class="text-green-300 text-sm">${c}</li>`).join("");
  const contradicted = (report.contradicted_claims || []).map((c) => `<li class="text-yellow-300 text-sm">${c}</li>`).join("");
  const papers = (report.similar_papers || []).map((p) => `<li class="text-slate-300 text-sm">${p}</li>`).join("");
  const recs = (report.recommendations || []).map((r) => `<li class="text-slate-300 text-sm">${r}</li>`).join("");

  container.innerHTML =
    `<div class="rounded-lg border border-slate-700 bg-slate-900 p-4">` +
    `<div class="flex items-center gap-4 mb-4">` +
    `<span class="text-2xl font-bold ${verdictColor}">${(report.verdict || "unknown").toUpperCase()}</span>` +
    `<div class="flex-1">` +
    `<div class="text-xs text-slate-400 mb-1">Novelty Score: ${noveltyPct}%</div>` +
    `<div class="h-2 bg-slate-700 rounded-full overflow-hidden">` +
    `<div class="h-full bg-cyan-500" style="width: ${noveltyPct}%"></div>` +
    `</div></div></div>` +
    (recs ? `<div class="mb-4"><h4 class="font-medium text-slate-200 mb-2">Recommendations</h4><ul class="list-disc list-inside space-y-1">${recs}</ul></div>` : "") +
    (flaws ? `<div class="mb-4"><h4 class="font-medium text-red-400 mb-2">Identified Flaws</h4><ul class="list-disc list-inside space-y-1">${flaws}</ul></div>` : "") +
    (supported ? `<div class="mb-4"><h4 class="font-medium text-green-400 mb-2">Supported Claims</h4><ul class="list-disc list-inside space-y-1">${supported}</ul></div>` : "") +
    (contradicted ? `<div class="mb-4"><h4 class="font-medium text-yellow-400 mb-2">Contradicted Claims</h4><ul class="list-disc list-inside space-y-1">${contradicted}</ul></div>` : "") +
    (papers ? `<div><h4 class="font-medium text-slate-200 mb-2">Similar Papers Found</h4><ul class="list-disc list-inside space-y-1">${papers}</ul></div>` : "") +
    `</div>`;
}

async function loadIdeaSessions() {
  const el = document.getElementById("idea-sessions-list");
  if (!el) return;
  const sessions = await fetchJson("/api/idea/sessions");
  if (!sessions || !sessions.length) {
    el.innerHTML = "<span class='text-slate-500'>No past sessions yet.</span>";
    return;
  }
  el.innerHTML = sessions.map((s) => {
    const verdictColor = {
      novel: "text-green-400", supported: "text-blue-400",
      contradicted: "text-yellow-400", flawed: "text-red-400",
    }[s.verdict] || "text-slate-400";
    return (
      `<div class="rounded border border-slate-700 bg-slate-900 p-3 mb-2">` +
      `<div class="flex items-center justify-between">` +
      `<span class="font-medium text-slate-200">${s.title || s.session_id}</span>` +
      `<span class="${verdictColor} text-xs font-semibold">${(s.verdict || "?").toUpperCase()}</span>` +
      `</div>` +
      `<div class="text-xs text-slate-400 mt-1">${s.domain || ""} · novelty ${Math.round((s.novelty_score || 0) * 100)}% · ${s.iterations_done || 0} iteration(s) · ${s.flaws_count || 0} flaw(s)</div>` +
      `</div>`
    );
  }).join("");
}

// Register handlers using the handler array (no monkey-patching)
_eventHandlers.push(_handleIdeaEvent);

function _handleIdeaEvent(event) {
  if (!event.type || !event.type.startsWith("idea_")) return;  // not an idea event
  switch (event.type) {
    case "idea_log":
      if (event.session_id === activeIdeaSession) {
        ideaLog(event.line || "");
      }
      break;
    case "idea_progress":
      if (event.session_id === activeIdeaSession) {
        setIdeaProgress(event.progress || 0, event.label || "");
      }
      break;
    case "idea_extracted":
      if (event.session_id === activeIdeaSession && event.idea) {
        ideaLog(`Extracted: "${event.idea.title || ""}" (domain: ${event.idea.domain || "unknown"})`);
      }
      break;
    case "idea_memory_loaded":
      if (event.session_id === activeIdeaSession) {
        ideaLog(`Loaded ${(event.insights || []).length} memory insight(s) from prior sessions.`);
      }
      break;
    case "idea_iteration_done":
      if (event.session_id === activeIdeaSession && event.iteration) {
        renderIdeaIteration(event.iteration);
      }
      break;
    case "idea_finished":
      if (event.session_id === activeIdeaSession) {
        setIdeaProgress(1.0, "Complete");
        const badge = document.getElementById("idea-status-badge");
        if (badge) {
          badge.textContent = "Done";
          badge.className = "px-2 py-1 rounded-full text-xs font-medium bg-green-700 text-white";
        }
        const submitBtn = document.getElementById("idea-submit-btn");
        if (submitBtn) submitBtn.disabled = false;
        if (event.final_report) {
          renderIdeaReport(event.final_report);
        }
        loadIdeaSessions();
      }
      break;
  }
}

// Form submission
const ideaForm = document.getElementById("idea-form");
if (ideaForm) {
  ideaForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const text = document.getElementById("idea-text")?.value?.trim();
    if (!text) {
      alert("Please enter a research idea description.");
      return;
    }
    const maxIter = document.getElementById("idea-iterations")?.value || "3";
    const filesInput = document.getElementById("idea-files");
    const submitBtn = document.getElementById("idea-submit-btn");

    if (submitBtn) submitBtn.disabled = true;

    // Reset UI
    const logEl = document.getElementById("idea-live-log");
    if (logEl) logEl.textContent = "";
    const iterCards = document.getElementById("idea-iteration-cards");
    if (iterCards) iterCards.innerHTML = "";
    const reportContent = document.getElementById("idea-report-content");
    if (reportContent) reportContent.innerHTML = "";
    document.getElementById("idea-iterations-section")?.classList.add("hidden");
    document.getElementById("idea-report-section")?.classList.add("hidden");
    showIdeaSection("idea-progress-section");
    setIdeaProgress(0, "Submitting...");
    const badge = document.getElementById("idea-status-badge");
    if (badge) {
      badge.textContent = "Running";
      badge.className = "px-2 py-1 rounded-full text-xs font-medium bg-amber-600 text-white";
    }

    const formData = new FormData();
    formData.append("text", text);
    formData.append("max_iterations", maxIter);
    if (filesInput && filesInput.files) {
      for (const file of filesInput.files) {
        formData.append("files", file);
      }
    }

    try {
      const resp = await fetch("/api/idea/verify", { method: "POST", body: formData });
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        alert("Error: " + (err.error || resp.statusText));
        if (submitBtn) submitBtn.disabled = false;
        return;
      }
      const data = await resp.json();
      activeIdeaSession = data.session_id;
      ideaLog(`Session started: ${data.session_id}`);
    } catch (err) {
      alert("Failed to submit: " + err.message);
      if (submitBtn) submitBtn.disabled = false;
    }
  });
}

const sessionsRefreshBtn = document.getElementById("idea-sessions-refresh");
if (sessionsRefreshBtn) {
  sessionsRefreshBtn.addEventListener("click", loadIdeaSessions);
}

// Load past sessions when the Idea tab is activated
document.querySelectorAll(".tab-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    if (btn.dataset.tab === "idea") {
      loadIdeaSessions();
    }
  });
});
