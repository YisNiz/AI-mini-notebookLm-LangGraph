// NotebookLM-style client. Talks to the FastAPI backend only over /api.

const api = {
  async get(url) {
    const r = await fetch(url);
    if (!r.ok) throw await err(r);
    return r.json();
  },
  async send(method, url, body) {
    const r = await fetch(url, {
      method,
      headers: body ? { "Content-Type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    });
    if (!r.ok) throw await err(r);
    return r.status === 204 ? null : r.json();
  },
};
async function err(r) {
  let detail = r.statusText;
  try {
    detail = (await r.json()).detail || detail;
  } catch {}
  const e = new Error(detail);
  e.status = r.status;
  return e;
}

// One conversation thread per page load. "New chat" starts a fresh one so the agent's
// short-term memory resets.
const state = { sources: [], threadId: crypto.randomUUID() };
const $ = (id) => document.getElementById(id);
const SUGGESTIONS = [
  "What drove Acme's gross margin improvement in Q2 2024?",
  "Compare Fleet OS growth between Q1 and Q2.",
  "What are the key risks to the subscription strategy?",
];

function escapeHtml(s) {
  return String(s).replace(
    /[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
  );
}

/* ---- sources --------------------------------------------------------------- */

async function loadSources() {
  state.sources = await api.get("/api/sources");
  renderSources();
}

function renderSources() {
  const ul = $("sources");
  ul.innerHTML = "";
  const activeCount = state.sources.filter((s) => s.active).length;
  $("active-count").textContent = `${activeCount} active`;
  $("select-all").checked = activeCount === state.sources.length && state.sources.length > 0;

  for (const s of state.sources) {
    const li = document.createElement("li");
    if (!s.active) li.className = "inactive";
    li.innerHTML = `
      <input type="checkbox" ${s.active ? "checked" : ""} />
      <span class="s-name" title="${escapeHtml(s.name)}">${escapeHtml(s.name)}</span>
      <span class="s-meta">${s.chars.toLocaleString()}</span>
      <button class="icon-btn" title="View">👁</button>
      <button class="icon-btn danger" title="Remove">✕</button>`;
    const [chk, , , viewBtn, delBtn] = li.children;
    chk.onchange = () => toggleSource(s.id, chk.checked);
    viewBtn.onclick = () => viewSource(s.id);
    delBtn.onclick = () => deleteSource(s.id);
    ul.appendChild(li);
  }
}

async function toggleSource(id, active) {
  await api.send("PATCH", `/api/sources/${id}`, { active });
  await loadSources();
}
async function deleteSource(id) {
  await api.send("DELETE", `/api/sources/${id}`);
  await loadSources();
}
async function viewSource(id) {
  const s = await api.get(`/api/sources/${id}`);
  openViewer(s.name, s.content);
}

async function addText(e) {
  e.preventDefault();
  const content = $("add-content").value.trim();
  if (!content) return;
  await api.send("POST", "/api/sources", { name: $("add-name").value, content });
  $("add-name").value = "";
  $("add-content").value = "";
  $("add-form").classList.add("hidden");
  await loadSources();
}

async function uploadFile(file) {
  const fd = new FormData();
  fd.append("file", file);
  const r = await fetch("/api/sources/upload", { method: "POST", body: fd });
  if (!r.ok) {
    addMessage("system", `⚠ ${(await err(r)).message}`);
    return;
  }
  $("add-form").classList.add("hidden");
  await loadSources();
}

async function selectAll(checked) {
  await Promise.all(
    state.sources
      .filter((s) => s.active !== checked)
      .map((s) => api.send("PATCH", `/api/sources/${s.id}`, { active: checked }))
  );
  await loadSources();
}

/* ---- chat ------------------------------------------------------------------ */

function renderEmptyState() {
  const m = $("messages");
  if (m.children.length) return;
  const div = document.createElement("div");
  div.className = "empty";
  div.innerHTML = `
    <div>Ask anything about your active sources — answers are grounded and cited.</div>
    <div class="suggestions">${SUGGESTIONS.map(
      (q) => `<button class="suggestion">${escapeHtml(q)}</button>`
    ).join("")}</div>`;
  div.querySelectorAll(".suggestion").forEach((b, i) => {
    b.onclick = () => {
      $("chat-input").value = SUGGESTIONS[i];
      $("chat-form").requestSubmit();
    };
  });
  m.appendChild(div);
}

function clearEmptyState() {
  const e = $("messages").querySelector(".empty");
  if (e) e.remove();
}

function addMessage(role, text, { pending = false } = {}) {
  clearEmptyState();
  const div = document.createElement("div");
  div.className = `msg ${role}${pending ? " pending" : ""}`;
  div.textContent = text;
  $("messages").appendChild(div);
  $("messages").scrollTop = $("messages").scrollHeight;
  return div;
}

function decorateAnswer(div, data) {
  div.className = "msg ai";
  div.textContent = data.answer;
  if (data.citations?.length) {
    const meta = document.createElement("div");
    meta.className = "meta";
    meta.innerHTML = `<div><span class="label">sources:</span> ${data.citations
      .map((c) => `<span class="chip">${escapeHtml(c.source)}</span>`)
      .join("")}</div>`;
    div.appendChild(meta);
  }
  const actions = document.createElement("div");
  actions.className = "msg-actions";
  const save = document.createElement("button");
  save.className = "link-btn";
  save.textContent = "＋ Save to note";
  save.onclick = () => saveNote(data.answer);
  actions.appendChild(save);
  div.appendChild(actions);
}

function showPendingApproval(data) {
  const message = addMessage(
    "ai",
    "הסוכן מבקש אישור לסריקת המקורות הבאים:"
  );

  const actions = data.pending_actions || [];

  actions.forEach((action) => {
    const item = document.createElement("div");
    item.className = "meta";

    const url = action.url || "(כתובת לא זמינה)";
    item.textContent = `${action.name}: ${url}`;
    message.appendChild(item);
  });

  const buttons = document.createElement("div");
  buttons.className = "msg-actions";

  const approve = document.createElement("button");
  approve.className = "link-btn";
  approve.textContent = "✓ אישור";
  approve.onclick = () => submitDecision(
    data.thread_id,
    actions.length,
    "approve",
    buttons
  );

  const reject = document.createElement("button");
  reject.className = "link-btn";
  reject.textContent = "✕ דחייה";
  reject.onclick = () => submitDecision(
    data.thread_id,
    actions.length,
    "reject",
    buttons
  );

  buttons.append(approve, reject);
  message.appendChild(buttons);
}

async function submitDecision(threadId, count, decision, buttons) {
  const controls = [...buttons.querySelectorAll("button")];

  controls.forEach((button) => {
    button.disabled = true;
  });

  try {
    const data = await api.send("POST", "/api/chat/decision", {
      thread_id: threadId,
      decisions: Array(count).fill(decision),
    });

    buttons.remove();

    if (data.pending_approval) {
      showPendingApproval(data);
    } else if (data.answer) {
      const message = addMessage("ai", "");
      decorateAnswer(message, data);
    }
  } catch (e) {
    addMessage("system", `⚠ ${e.message}`);

    controls.forEach((button) => {
      button.disabled = false;
    });
  }
}



async function sendMessage(message) {
  addMessage("user", message);
  const pending = addMessage("ai", "thinking…", { pending: true });
  $("send").disabled = true;

  try {
    const data = await api.send("POST", "/api/chat", {
      message,
      thread_id: state.threadId,
    });

    pending.remove();

   if (data.pending_approval && data.pending_actions?.length) {
  showPendingApproval(data);
} else {
  const answer = addMessage("ai", "");
  decorateAnswer(answer, data);
    }
  } catch (e) {
    pending.remove();
    addMessage("system", `⚠ ${e.message}`);
  } finally {
    $("send").disabled = false;
    $("messages").scrollTop = $("messages").scrollHeight;
  }
}

/* ---- studio + notes -------------------------------------------------------- */

async function loadArtifacts() {
  const arts = await api.get("/api/studio/artifacts");
  const grid = $("artifacts");
  grid.innerHTML = "";
  for (const a of arts) {
    const btn = document.createElement("button");
    btn.className = "artifact";
    const badge = a.status === "planned" ? `<span class="a-badge">Soon</span>` : "";
    btn.innerHTML = `<span class="a-icon">${a.icon}</span>
      <span class="a-title">${escapeHtml(a.title)}</span>${badge}`;
    btn.onclick = () => generateArtifact(a);
    grid.appendChild(btn);
  }
}

async function generateArtifact(a) {
  if (a.key === "ted") return startTed();
  try {
    await api.send("POST", "/api/studio/generate", { kind: a.key });
  } catch (e) {
    addMessage("system", `⚠ ${e.message}`);
  }
}

async function loadNotes() {
  renderNotes(await api.get("/api/notes"));
}
function renderNotes(notes) {
  const ul = $("notes");
  ul.innerHTML = "";
  if (!notes.length) {
    ul.innerHTML = `<div class="note-empty">No notes yet — save a grounded answer.</div>`;
    return;
  }
  for (const n of notes) {
    const li = document.createElement("li");
    li.innerHTML = `<span class="n-title" title="${escapeHtml(n.title)}">${escapeHtml(
      n.title
    )}</span><button class="icon-btn danger">✕</button>`;
    li.querySelector("button").onclick = async () => {
      await api.send("DELETE", `/api/notes/${n.id}`);
      loadNotes();
    };
    li.querySelector(".n-title").onclick = () => openViewer(n.title, n.content);
    ul.appendChild(li);
  }
}
async function saveNote(content) {
  const title = content.split("\n")[0].slice(0, 50);
  await api.send("POST", "/api/notes", { title, content });
  loadNotes();
}

/* ---- TED talk -------------------------------------------------------------- */
// The graph stops at an approval gate; this modal is that gate's UI.

const TED_STATUS = {
  pending_approval: "⏸ ממתינה לאישור",
  audio_ready: "🎧 מוכנה",
  failed: "⚠ נכשלה",
};
let currentTed = null;

async function loadTed() {
  const talks = await api.get("/api/ted");
  const ul = $("ted-list");
  ul.innerHTML = "";
  if (!talks.length) {
    ul.innerHTML = `<div class="note-empty">No talks yet — click TED Talk above.</div>`;
    return;
  }
  for (const t of talks) {
    const li = document.createElement("li");
    li.innerHTML = `<span class="n-title" dir="rtl" title="${escapeHtml(t.topic || "")}">${escapeHtml(
      t.topic || t.job_id
    )}</span><span class="status-dot">${TED_STATUS[t.status] || t.status}</span>
      <button class="icon-btn danger">✕</button>`;
    li.querySelector(".n-title").onclick = () => openTed(t);
    li.querySelector("button").onclick = async () => {
      await api.send("DELETE", `/api/ted/${t.job_id}`);
      loadTed();
    };
    ul.appendChild(li);
  }
}

async function startTed() {
  addMessage("system", "🎤 מכינה הרצאת TED מהמקורות הפעילים… (תכנון, כתיבה וביקורת — כדקה-שתיים)");
  try {
    const talk = await api.send("POST", "/api/ted");
    loadTed();
    openTed(talk);
  } catch (e) {
    addMessage("system", `⚠ ${e.message}`);
  }
}

function setTedBusy(text) {
  for (const id of ["ted-approve", "ted-revise", "ted-retry", "ted-feedback"]) $(id).disabled = !!text;
  $("ted-busy").textContent = text || "";
  $("ted-busy").classList.toggle("hidden", !text);
}

function openTed(t) {
  currentTed = t;
  const pending = t.status === "pending_approval";
  const ready = t.status === "audio_ready";
  const failed = t.status === "failed";

  $("ted-title").textContent = t.topic || "TED Talk";
  $("ted-meta").textContent = `${TED_STATUS[t.status] || t.status} · ${t.word_count ?? "?"} מילים · ${
    t.revision_count ?? 0
  } תיקונים`;
  $("ted-script").textContent = t.script_he || "";

  const notes = pending ? t.critique_notes || [] : [];
  $("ted-notes").classList.toggle("hidden", !notes.length);
  $("ted-notes").innerHTML = notes.length
    ? `הערות המבקר:<ul dir="rtl">${notes.map((n) => `<li>${escapeHtml(n)}</li>`).join("")}</ul>`
    : "";

  $("ted-audio").classList.toggle("hidden", !ready);
  if (ready) $("ted-audio").src = `/api/ted/${t.job_id}/audio?t=${Date.now()}`;

  $("ted-error").classList.toggle("hidden", !t.error);
  $("ted-error").textContent = t.error ? `⚠ ${t.error}` : "";

  $("ted-feedback").value = "";
  $("ted-feedback").classList.toggle("hidden", !pending);
  $("ted-approve").classList.toggle("hidden", !pending);
  $("ted-revise").classList.toggle("hidden", !pending);
  $("ted-retry").classList.toggle("hidden", !failed);
  $("ted-save").classList.toggle("hidden", !ready);
  $("ted-save").textContent = "📌 שמירה כפתק";
  setTedBusy(null);

  $("ted-modal").classList.remove("hidden");
  $("overlay").classList.remove("hidden");
}

async function resumeTed(action) {
  const feedback = $("ted-feedback").value.trim();
  if (action === "revise" && !feedback) {
    $("ted-error").textContent = "✎ כתבי קודם בתיבה למעלה מה לשנות, ואז לחצי שוב על \"בקשת שינויים\".";
    $("ted-error").classList.remove("hidden");
    $("ted-feedback").focus();
    return;
  }
  $("ted-error").classList.add("hidden");
  setTedBusy(action === "revise" ? "מתקנת לפי המשוב…" : "מקריאה את ההרצאה… (יכול לקחת דקה-שתיים)");
  try {
    const t = await api.send("POST", `/api/ted/${currentTed.job_id}/resume`, { action, feedback });
    openTed(t);
  } catch (e) {
    setTedBusy(null);
    $("ted-error").textContent = `⚠ ${e.message}`;
    $("ted-error").classList.remove("hidden");
  }
  loadTed();
}

function closeTed() {
  $("ted-audio").pause();
  $("ted-modal").classList.add("hidden");
  $("overlay").classList.add("hidden");
}

/* ---- viewer modal ---------------------------------------------------------- */

function openViewer(title, content) {
  $("viewer-title").textContent = title;
  $("viewer-content").textContent = content;
  $("viewer").classList.remove("hidden");
  $("overlay").classList.remove("hidden");
}
function closeViewer() {
  $("viewer").classList.add("hidden");
  $("overlay").classList.add("hidden");
}

/* ---- wiring ---------------------------------------------------------------- */

$("add-toggle").onclick = () => $("add-form").classList.toggle("hidden");
$("add-cancel").onclick = () => $("add-form").classList.add("hidden");
$("add-form").addEventListener("submit", addText);
$("add-file").onchange = (e) => e.target.files[0] && uploadFile(e.target.files[0]);
$("select-all").onchange = (e) => selectAll(e.target.checked);

$("chat-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const msg = $("chat-input").value.trim();
  if (!msg) return;
  $("chat-input").value = "";
  sendMessage(msg);
});

$("new-chat").onclick = () => {
  state.threadId = crypto.randomUUID(); // fresh memory
  $("messages").innerHTML = "";
  renderEmptyState();
};

$("close-viewer").onclick = closeViewer;
$("overlay").onclick = () => {
  closeViewer();
  closeTed();
};

$("close-ted").onclick = closeTed;
$("ted-approve").onclick = () => resumeTed("approve");
$("ted-revise").onclick = () => resumeTed("revise");
$("ted-retry").onclick = () => resumeTed("approve"); // no pending interrupt → retries the audio node
$("ted-save").onclick = async () => {
  await api.send("POST", "/api/notes", {
    title: `🎤 ${currentTed.topic || "TED Talk"}`.slice(0, 60),
    content: currentTed.script_he || "",
  });
  loadNotes();
  $("ted-save").textContent = "✓ נשמר";
};

/* ---- init ------------------------------------------------------------------ */

(async function init() {
  await Promise.all([loadSources(), loadArtifacts(), loadNotes(), loadTed()]);
  renderEmptyState();
})();
