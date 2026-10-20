const state = {
  audits: [], current: null, docs: [], matrix: [], selected: null,
  tab: "documents", auditStatus: "draft", offline: false,
};

const $ = selector => document.querySelector(selector);
const esc = value => String(value ?? "").replace(/[&<>"']/g, char => (
  { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char]
));
const labels = {
  draft: "Brouillon", processing: "Analyse en cours", ready: "Prêt à revoir",
  failed: "Échec", queued: "En attente", partial: "Lecture partielle",
  supported: "Couvert", partially_supported: "Partiel",
  no_evidence: "Preuve non trouvée", conflicting_evidence: "Contradictoire",
  uncertain: "À vérifier", not_applicable: "Non applicable",
};
const documentLabels = { ...labels, ready: "Lu", processing: "Lecture en cours" };
const sourceLabels = { ai: "Analyse IA", rule: "Règle de profil", fallback: "Recherche locale", local_search: "Recherche locale" };
const applicabilityLabels = { applicable: "Applicable", not_applicable: "Non applicable", undetermined: "À confirmer" };

async function api(path, options = {}) {
  const response = await fetch(path, options);
  if (!response.ok) {
    let error;
    try { error = await response.json(); } catch { /* HTTP response without JSON */ }
    throw new Error(error?.detail || `Erreur HTTP ${response.status}`);
  }
  return response.json();
}

function notice(message) {
  const node = $("#notice");
  node.textContent = message;
  node.classList.remove("hidden");
  clearTimeout(notice.timer);
  notice.timer = setTimeout(() => node.classList.add("hidden"), 7000);
}

function updateStatus(status) {
  state.auditStatus = status;
  const badge = $("#audit-status");
  badge.textContent = labels[status] || status;
  badge.className = `status ${status}`;
  const exportable = status === "ready";
  $("#export-btn").disabled = !exportable;
  $("#export-json-btn").disabled = !exportable;
}

function setTab(tab) {
  state.tab = tab;
  document.querySelectorAll(".tab").forEach(button => {
    const active = button.dataset.tab === tab;
    button.classList.toggle("active", active);
    button.setAttribute("aria-selected", String(active));
    button.tabIndex = active ? 0 : -1;
  });
  $("#documents-view").classList.toggle("hidden", tab !== "documents");
  $("#matrix-view").classList.toggle("hidden", tab !== "matrix");
}

async function loadAudits() {
  state.audits = await api("/api/audits");
  $("#audit-list").innerHTML = state.audits.map(audit => `
    <button class="audit-item ${audit.id === state.current ? "active" : ""}" type="button"
            data-audit="${audit.id}" ${audit.id === state.current ? 'aria-current="page"' : ""}>
      <strong>${esc(audit.name)}</strong><span>${esc(labels[audit.status] || audit.status)}</span>
    </button>
  `).join("");
  document.querySelectorAll("[data-audit]").forEach(button => {
    button.onclick = () => openAudit(button.dataset.audit).catch(error => notice(error.message));
  });
}

async function openAudit(id) {
  if ($("#review-drawer").open) $("#review-drawer").close();
  state.current = id;
  const audit = await api(`/api/audits/${id}`);
  $("#welcome").classList.add("hidden");
  $("#workspace").classList.remove("hidden");
  $("#page-title").textContent = audit.name;
  $("#entity-type").value = audit.profile.entity_type || "unknown";
  $("#sector").value = audit.profile.sector || "";
  $("#country").value = audit.profile.country || "France";
  $("#upload-progress").textContent = "";
  updateStatus(audit.status);
  await Promise.all([loadDocs(), loadMatrix(), loadAudits()]);
  setTab(state.tab);
}

async function loadDocs() {
  if (!state.current) return;
  state.docs = await api(`/api/audits/${state.current}/documents`);
  const count = state.docs.length;
  $("#document-count").textContent = `${count} document${count > 1 ? "s" : ""}`;
  $("#documents-list").classList.toggle("empty", count === 0);
  $("#documents-list").innerHTML = count ? state.docs.map(doc => `
    <div class="document-row">
      <div>
        <div class="doc-name">${esc(doc.name)}</div>
        <div class="doc-meta">${esc(doc.ext.slice(1).toUpperCase())} · ${doc.page_count || "—"} page(s)/onglet(s) · ${esc(doc.sha256.slice(0, 10))}</div>
        ${doc.error ? `<div class="doc-meta doc-error">${esc(doc.error)}</div>` : ""}
      </div>
      <span class="pill ${esc(doc.status)}">${esc(documentLabels[doc.status] || doc.status)}</span>
      <a class="secondary" href="/api/documents/${doc.id}/file" target="_blank" rel="noopener">Ouvrir</a>
    </div>
  `).join("") : "Importez un document pour commencer l’analyse.";
  const readable = state.docs.some(doc => ["ready", "partial"].includes(doc.status));
  const pending = state.docs.some(doc => ["queued", "processing"].includes(doc.status));
  $("#run-btn").disabled = !readable || pending || state.auditStatus === "processing";
}

async function loadMatrix() {
  if (!state.current) return;
  state.matrix = await api(`/api/audits/${state.current}/matrix`);
  renderMatrix();
}

function renderMatrix() {
  const filter = $("#status-filter").value;
  const rows = state.matrix.filter(row => filter === "all" || row.assessment?.status === filter);
  $("#matrix-list").innerHTML = rows.map(row => `
    <button class="requirement" type="button" data-req="${esc(row.id)}">
      <span class="req-id">${esc(row.id)}</span>
      <span><span class="req-title">${esc(row.title)}</span><span class="req-summary">${esc(row.summary)}</span></span>
      <span class="pill ${esc(row.assessment?.status || "")}">${esc(labels[row.assessment?.status] || "Non analysé")}</span>
    </button>
  `).join("") || '<div class="document-list empty">Aucune exigence ne correspond à ce filtre.</div>';
  document.querySelectorAll("[data-req]").forEach(button => {
    button.onclick = () => openRequirement(button.dataset.req);
  });
}

function openRequirement(id) {
  const requirement = state.matrix.find(row => row.id === id);
  if (!requirement) return;
  state.selected = requirement;
  $("#drawer-code").textContent = requirement.id;
  $("#drawer-title").textContent = requirement.title;
  $("#drawer-summary").textContent = requirement.summary;
  const assessment = requirement.assessment;
  $("#drawer-assessment").innerHTML = assessment ? `
    <section class="assessment-summary">
      <strong>Constat : ${esc(labels[assessment.status] || assessment.status)}</strong>
      <p>${esc(assessment.rationale)}</p>
      <small>Applicabilité : ${esc(applicabilityLabels[assessment.applicability] || assessment.applicability)} ·
        Méthode : ${esc(sourceLabels[assessment.source] || assessment.source)} ·
        ${assessment.reviewed ? "Revu" : "Revue nécessaire"}</small>
      ${assessment.reviewer_note ? `<p><strong>Note de revue :</strong> ${esc(assessment.reviewer_note)}</p>` : ""}
    </section>
  ` : '<p>Lancez l’analyse pour obtenir un constat.</p>';
  $("#drawer-evidence").innerHTML = `<h3>Passages repérés (${requirement.evidence.length})</h3>` + (
    requirement.evidence.map((evidence, index) => `
      <article class="evidence-item">
        <b>${esc(evidence.document_name)} · ${esc(evidence.locator)}</b>
        <blockquote>${esc(evidence.quote)}</blockquote>
        ${evidence.explanation && evidence.explanation !== "Correspondance documentaire candidate" ? `<p>${esc(evidence.explanation)}</p>` : ""}
        <button type="button" data-preview="${index}">Voir dans le document</button>
      </article>
    `).join("") || '<p>Aucun passage repéré dans les documents traités.</p>'
  );
  $("#drawer-preview").innerHTML = "";
  document.querySelectorAll("[data-preview]").forEach(button => {
    button.onclick = () => showPreview(requirement.evidence[Number(button.dataset.preview)]);
  });
  $("#drawer-review").innerHTML = assessment ? `
    <div class="review-box">
      <h3>Validation humaine</h3>
      <label>Statut final<select id="review-status">
        ${["uncertain", "supported", "partially_supported", "no_evidence", "conflicting_evidence", "not_applicable"]
          .map(status => `<option value="${status}" ${assessment.status === status ? "selected" : ""}>${labels[status]}</option>`).join("")}
      </select></label>
      <label>Motif de la décision<textarea id="review-note" placeholder="Expliquez ce que les pièces prouvent ou ne prouvent pas.">${esc(assessment.reviewer_note || "")}</textarea></label>
      <p id="review-error" class="form-error hidden" role="alert"></p>
      <button class="primary" type="button" id="save-review">Enregistrer la revue</button>
    </div>
  ` : "";
  if (assessment) $("#save-review").onclick = saveReview;
  if (!$("#review-drawer").open) $("#review-drawer").showModal();
}

function showPreview(evidence) {
  const doc = state.docs.find(item => item.id === evidence.document_id);
  if (!doc) return;
  const content = doc.ext === ".pdf"
    ? `<img alt="Page PDF avec zone de preuve encadrée" src="/api/elements/${evidence.element_id}/preview.png">`
    : `<blockquote>${esc(evidence.text)}</blockquote>`;
  $("#drawer-preview").innerHTML = `
    <div class="preview">
      <b>${esc(doc.name)} · ${esc(evidence.locator)}</b>
      ${content}
      <a href="/api/documents/${doc.id}/file" target="_blank" rel="noopener">Ouvrir l’original</a>
    </div>
  `;
  $("#drawer-preview").scrollIntoView({ behavior: "smooth", block: "nearest" });
}

async function saveReview() {
  const note = $("#review-note").value.trim();
  const errorNode = $("#review-error");
  if (note.length < 2) {
    errorNode.textContent = "Expliquez brièvement votre décision avant d’enregistrer.";
    errorNode.classList.remove("hidden");
    return;
  }
  const button = $("#save-review");
  button.disabled = true;
  try {
    await api(`/api/assessments/${state.selected.assessment.id}/review`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: $("#review-status").value, note }),
    });
    const id = state.selected.id;
    await loadMatrix();
    openRequirement(id);
    notice("Revue enregistrée.");
  } catch (error) {
    button.disabled = false;
    errorNode.textContent = error.message;
    errorNode.classList.remove("hidden");
  }
}

async function uploadFiles(files) {
  if (!state.current || !files.length) return;
  $("#upload-progress").textContent = `Import de ${files.length} fichier${files.length > 1 ? "s" : ""}…`;
  for (const file of files) {
    const form = new FormData();
    form.append("file", file);
    try {
      await api(`/api/audits/${state.current}/documents`, { method: "POST", body: form });
    } catch (error) {
      notice(`${file.name} : ${error.message}`);
    }
  }
  $("#files").value = "";
  $("#upload-progress").textContent = "Lecture des documents en cours…";
  updateStatus("draft");
  await Promise.all([loadDocs(), loadMatrix()]);
}

async function refresh() {
  if (!state.current) return;
  const audit = await api(`/api/audits/${state.current}`);
  const previous = state.auditStatus;
  updateStatus(audit.status);
  await loadDocs();
  if (audit.status === "processing" || previous === "processing") await loadMatrix();
  if (previous === "processing" && audit.status === "ready") {
    $("#upload-progress").textContent = "Analyse terminée.";
    await loadAudits();
  }
  if (state.offline) {
    state.offline = false;
    notice("Connexion rétablie.");
  }
}

const createDialog = $("#dialog");
$("#new-audit").onclick = $("#welcome-create").onclick = () => {
  $("#create-error").classList.add("hidden");
  createDialog.showModal();
  $("#audit-name").focus();
};
$("#close-dialog").onclick = () => createDialog.close();
$("#close-drawer").onclick = () => $("#review-drawer").close();
$("#review-drawer").addEventListener("close", () => {
  const button = [...document.querySelectorAll("[data-req]")].find(item => item.dataset.req === state.selected?.id);
  button?.focus();
});

$("#create-form").onsubmit = async event => {
  event.preventDefault();
  try {
    const audit = await api("/api/audits", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: $("#audit-name").value }),
    });
    createDialog.close();
    $("#audit-name").value = "";
    await openAudit(audit.id);
  } catch (error) {
    $("#create-error").textContent = error.message;
    $("#create-error").classList.remove("hidden");
  }
};

$("#profile-form").onsubmit = async event => {
  event.preventDefault();
  try {
    await api(`/api/audits/${state.current}/profile`, {
      method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ entity_type: $("#entity-type").value, sector: $("#sector").value, country: $("#country").value }),
    });
    updateStatus("draft");
    await loadMatrix();
    notice("Profil enregistré. Relancez l’analyse pour mettre à jour les constats.");
  } catch (error) { notice(error.message); }
};

$("#files").onchange = event => uploadFiles([...event.target.files]).catch(error => notice(error.message));
const dropzone = $(".dropzone");
dropzone.ondragover = event => { event.preventDefault(); dropzone.classList.add("drag"); };
dropzone.ondragleave = () => dropzone.classList.remove("drag");
dropzone.ondrop = event => {
  event.preventDefault();
  dropzone.classList.remove("drag");
  uploadFiles([...event.dataTransfer.files]).catch(error => notice(error.message));
};

$("#run-btn").onclick = async () => {
  const button = $("#run-btn");
  button.disabled = true;
  try {
    await api(`/api/audits/${state.current}/run`, { method: "POST" });
    updateStatus("processing");
    setTab("matrix");
    notice("Analyse lancée.");
  } catch (error) {
    await loadDocs();
    notice(error.message);
  }
};
$("#status-filter").onchange = renderMatrix;
document.querySelectorAll(".tab").forEach(button => {
  button.onclick = () => setTab(button.dataset.tab);
  button.onkeydown = event => {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    const next = event.key === "ArrowLeft" || event.key === "Home" ? "documents" : "matrix";
    setTab(next);
    $(`#tab-${next}`).focus();
  };
});
$("#export-btn").onclick = () => { if (state.current) window.location.href = `/api/audits/${state.current}/export.csv`; };
$("#export-json-btn").onclick = () => { if (state.current) window.location.href = `/api/audits/${state.current}/export.json`; };

async function boot() {
  try {
    const health = await api("/api/health");
    $("#ai-indicator").classList.toggle("on", health.ai_text);
    $("#ai-label").textContent = health.ai_text ? "IA connectée" : "Mode local · revue nécessaire";
    await loadAudits();
    if (state.audits.length) await openAudit(state.audits[0].id);
  } catch (error) { notice(error.message); }
}

boot();
setInterval(() => refresh().catch(() => {
  if (!state.offline) notice("Connexion au serveur interrompue. Vérifiez qu’il est démarré.");
  state.offline = true;
}), 5000);
