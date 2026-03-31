const uploadBtn = document.getElementById("uploadBtn");
const fileInput = document.getElementById("fileInput");
const uploadResult = document.getElementById("uploadResult");

const refreshDocsBtn = document.getElementById("refreshDocsBtn");
const documentsList = document.getElementById("documentsList");

const documentIdInput = document.getElementById("documentIdInput");
const analyzeBtn = document.getElementById("analyzeBtn");
const loadPolesBtn = document.getElementById("loadPolesBtn");
const matchBtn = document.getElementById("matchBtn");
const calculateBtn = document.getElementById("calculateBtn");
const summaryBtn = document.getElementById("summaryBtn");

const output = document.getElementById("output");
const polesTableBody = document.querySelector("#polesTable tbody");

const selectedRowInfo = document.getElementById("selectedRowInfo");
const saveCorrectionBtn = document.getElementById("saveCorrectionBtn");
const correctionResult = document.getElementById("correctionResult");

const editPoleCode = document.getElementById("editPoleCode");
const editPoleType = document.getElementById("editPoleType");
const editSupportHeight = document.getElementById("editSupportHeight");
const editSpan = document.getElementById("editSpan");
const editGuying = document.getElementById("editGuying");
const editQuantity = document.getElementById("editQuantity");
const editSelectedPoolId = document.getElementById("editSelectedPoolId");
const editNote = document.getElementById("editNote");

let currentPoles = [];
let selectedRowId = null;

async function api(url, options = {}) {
  const response = await fetch(url, options);
  const data = await response.json();

  if (!response.ok) {
    throw new Error(data.detail || "Virhe");
  }

  return data;
}

function escapeHtml(value) {
  if (value === null || value === undefined) return "";
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function formatValue(value) {
  if (value === null || value === undefined || value === "") {
    return "-";
  }
  return escapeHtml(value);
}

function getStatusBadge(status) {
  const safeStatus = status || "-";
  let className = "status-badge";

  if (safeStatus === "matched") className += " status-matched";
  else if (safeStatus === "ambiguous") className += " status-ambiguous";
  else if (safeStatus === "unmatched") className += " status-unmatched";
  else if (safeStatus === "review") className += " status-review";
  else if (safeStatus === "ok") className += " status-ok";
  else if (safeStatus === "calculated") className += " status-calculated";
  else if (safeStatus === "incomplete") className += " status-incomplete";

  return `<span class="${className}">${escapeHtml(safeStatus)}</span>`;
}

function setOutputJson(data) {
  output.innerHTML = `<pre>${escapeHtml(JSON.stringify(data, null, 2))}</pre>`;
}

function renderMessage(message) {
  output.innerHTML = `<div><strong>${escapeHtml(message)}</strong></div>`;
}

function buildSelectedRowLabel(row) {
  return `Valittu rivi: ${row.row_id} (lähderivi ${row.source_row_number ?? "-"})`;
}

function renderPolesTable(rows) {
  polesTableBody.innerHTML = "";
  currentPoles = rows;

  rows.forEach((row) => {
    const tr = document.createElement("tr");

    tr.innerHTML = `
      <td><button class="select-row-btn" data-row-id="${row.row_id}">Valitse</button></td>
      <td>${formatValue(row.source_row_number)}</td>
      <td>${formatValue(row.pole_code)}</td>
      <td>${formatValue(row.pole_type)}</td>
      <td>${formatValue(row.support_height_m)}</td>
      <td>${formatValue(row.span_m)}</td>
      <td>${formatValue(row.guying)}</td>
      <td>${formatValue(row.quantity)}</td>
      <td>${getStatusBadge(row.review_status)}</td>
      <td>${formatValue(row.confidence)}</td>
      <td>${getStatusBadge(row.match_status)}</td>
      <td>${formatValue(row.suggested_pool_id)}</td>
      <td>${formatValue(row.correction_selected_pool_id)}</td>
      <td>${getStatusBadge(row.calculation_status)}</td>
      <td>${formatValue(row.total_mass_kg)}</td>
    `;

    polesTableBody.appendChild(tr);
  });

  document.querySelectorAll(".select-row-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const rowId = btn.dataset.rowId;
      const row = currentPoles.find((item) => item.row_id === rowId);
      if (!row) return;

      selectedRowId = row.row_id;
      selectedRowInfo.textContent = buildSelectedRowLabel(row);

      editPoleCode.value = row.pole_code ?? "";
      editPoleType.value = row.pole_type ?? "";
      editSupportHeight.value = row.support_height_m ?? "";
      editSpan.value = row.span_m ?? "";
      editGuying.value = row.guying ?? "";
      editQuantity.value = row.quantity ?? "";
      editSelectedPoolId.value = row.correction_selected_pool_id ?? "";
      editNote.value = row.correction_note ?? "";
    });
  });
}

function renderSummary(summary) {
  const reviewItems = Array.isArray(summary.review_items) ? summary.review_items : [];
  const rowsByPool = Array.isArray(summary.rows_by_pool) ? summary.rows_by_pool : [];

  const rowsByPoolHtml =
    rowsByPool.length === 0
      ? `<div class="empty-state">Ei laskettuja rivejä.</div>`
      : `
        <div class="summary-table-wrap">
          <table>
            <thead>
              <tr>
                <th>Pooli</th>
                <th>Tyyppi</th>
                <th>Määrä</th>
                <th>Yksikkömassa (kg)</th>
                <th>Kokonaismassa (kg)</th>
              </tr>
            </thead>
            <tbody>
              ${rowsByPool
                .map(
                  (row) => `
                    <tr>
                      <td>${formatValue(row.pool_id)}</td>
                      <td>${formatValue(row.pole_type)}</td>
                      <td>${formatValue(row.quantity)}</td>
                      <td>${formatValue(row.unit_mass_kg)}</td>
                      <td>${formatValue(row.total_mass_kg)}</td>
                    </tr>
                  `
                )
                .join("")}
            </tbody>
          </table>
        </div>
      `;

  const reviewHtml =
    reviewItems.length === 0
      ? `<div class="empty-state">Ei tarkistettavia rivejä.</div>`
      : `
        <div class="review-list">
          ${reviewItems
            .map((item) => {
              const reasons = Array.isArray(item.reasons) ? item.reasons : [];
              const reasonsHtml =
                reasons.length === 0
                  ? `<li>Ei erillisiä syitä</li>`
                  : reasons.map((reason) => `<li>${escapeHtml(reason)}</li>`).join("");

              let reviewCardClass = "review-card review-generic";
              if (item.match_status === "ambiguous") reviewCardClass = "review-card review-ambiguous";
              if (item.match_status === "unmatched") reviewCardClass = "review-card review-unmatched";

              return `
                <div class="${reviewCardClass}">
                  <h4 class="review-title">Rivi ${formatValue(item.source_row_number)} / ${formatValue(item.pole_code)}</h4>

                  <div class="review-meta-grid">
                    <div class="review-meta-item">
                      <span class="review-meta-label">Tyyppi</span>
                      <div class="review-meta-value">${formatValue(item.pole_type)}</div>
                    </div>

                    <div class="review-meta-item">
                      <span class="review-meta-label">Review-status</span>
                      <div class="review-meta-value">${getStatusBadge(item.review_status)}</div>
                    </div>

                    <div class="review-meta-item">
                      <span class="review-meta-label">Match-status</span>
                      <div class="review-meta-value">${getStatusBadge(item.match_status)}</div>
                    </div>

                    <div class="review-meta-item">
                      <span class="review-meta-label">Laskenta-status</span>
                      <div class="review-meta-value">${getStatusBadge(item.calculation_status)}</div>
                    </div>

                    <div class="review-meta-item">
                      <span class="review-meta-label">Ehdotettu pooli</span>
                      <div class="review-meta-value">${formatValue(item.suggested_pool_id)}</div>
                    </div>

                    <div class="review-meta-item">
                      <span class="review-meta-label">Valittu pooli</span>
                      <div class="review-meta-value">${formatValue(item.selected_pool_id)}</div>
                    </div>
                  </div>

                  <div>
                    <strong>Syyt</strong>
                    <ul class="reason-list">
                      ${reasonsHtml}
                    </ul>
                  </div>
                </div>
              `;
            })
            .join("")}
        </div>
      `;

  output.innerHTML = `
    <div class="summary-layout">
      <div class="summary-section">
        <h3 class="summary-section-title">Yhteenveto</h3>

        <div class="summary-grid">
          <div class="summary-card">
            <strong>Dokumentti</strong>
            <div class="summary-value-sm">${formatValue(summary.document_id)}</div>
          </div>

          <div class="summary-card">
            <strong>Status</strong>
            <div class="summary-value-sm">${getStatusBadge(summary.document_status)}</div>
          </div>

          <div class="summary-card">
            <strong>Tunnistettuja rivejä</strong>
            <div class="summary-value">${formatValue(summary.total_detected_rows)}</div>
          </div>

          <div class="summary-card">
            <strong>Matchatut rivit</strong>
            <div class="summary-value-sm">
              matched: ${formatValue(summary.matched_rows)}<br>
              ambiguous: ${formatValue(summary.ambiguous_rows)}<br>
              unmatched: ${formatValue(summary.unmatched_rows)}
            </div>
          </div>

          <div class="summary-card">
            <strong>Laskenta</strong>
            <div class="summary-value-sm">
              calculated: ${formatValue(summary.calculated_rows)}<br>
              incomplete: ${formatValue(summary.incomplete_rows)}
            </div>
          </div>

          <div class="summary-card">
            <strong>Kokonaismäärä</strong>
            <div class="summary-value">${formatValue(summary.total_quantity)}</div>
          </div>

          <div class="summary-card">
            <strong>Kokonaismassa (kg)</strong>
            <div class="summary-value">${formatValue(summary.total_mass_kg)}</div>
          </div>
        </div>
      </div>

      <div class="summary-section">
        <h3 class="summary-section-title">Poolikohtainen massayhteenveto</h3>
        ${rowsByPoolHtml}
      </div>

      <div class="summary-section">
        <h3 class="summary-section-title">Tarkistettavat rivit</h3>
        ${reviewHtml}
      </div>

      <div class="summary-section">
        <details class="raw-data">
          <summary>Näytä raakadata</summary>
          <pre>${escapeHtml(JSON.stringify(summary, null, 2))}</pre>
        </details>
      </div>
    </div>
  `;
}

async function loadPolesForDocument(documentId) {
  const rows = await api(`/api/documents/${documentId}/poles`);
  renderPolesTable(rows);
  return rows;
}

async function refreshDocumentOutputs(documentId) {
  await api(`/api/documents/${documentId}/match`, { method: "POST" });
  await api(`/api/documents/${documentId}/calculate`, { method: "POST" });

  const [rows, summary] = await Promise.all([
    api(`/api/documents/${documentId}/poles`),
    api(`/api/documents/${documentId}/summary`),
  ]);

  renderPolesTable(rows);
  renderSummary(summary);

  if (selectedRowId) {
    const selectedRow = rows.find((row) => row.row_id === selectedRowId);
    if (selectedRow) {
      selectedRowInfo.textContent = buildSelectedRowLabel(selectedRow);
      editSelectedPoolId.value = selectedRow.correction_selected_pool_id ?? "";
      editNote.value = selectedRow.correction_note ?? "";
    }
  }
}

uploadBtn.addEventListener("click", async () => {
  const file = fileInput.files[0];
  if (!file) {
    uploadResult.textContent = "Valitse tiedosto ensin.";
    return;
  }

  const formData = new FormData();
  formData.append("file", file);

  try {
    const result = await api("/api/documents/upload", {
      method: "POST",
      body: formData,
    });

    uploadResult.textContent = `Ladattu: ${result.document_id}`;
    documentIdInput.value = result.document_id;
  } catch (error) {
    uploadResult.textContent = error.message;
  }
});

refreshDocsBtn.addEventListener("click", async () => {
  try {
    const docs = await api("/api/documents");
    documentsList.innerHTML = "";

    docs.forEach((doc) => {
      const li = document.createElement("li");
      li.innerHTML = `<button class="doc-select-btn" data-doc-id="${doc.document_id}">Valitse</button> ${escapeHtml(doc.document_id)} | ${escapeHtml(doc.original_filename)} | ${escapeHtml(doc.status)}`;
      documentsList.appendChild(li);
    });

    document.querySelectorAll(".doc-select-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        documentIdInput.value = btn.dataset.docId;
      });
    });
  } catch (error) {
    renderMessage(error.message);
  }
});

analyzeBtn.addEventListener("click", async () => {
  try {
    const id = documentIdInput.value.trim();
    const result = await api(`/api/documents/${id}/analyze`, { method: "POST" });
    renderPolesTable(result);
    setOutputJson(result);
  } catch (error) {
    renderMessage(error.message);
  }
});

loadPolesBtn.addEventListener("click", async () => {
  try {
    const id = documentIdInput.value.trim();
    await loadPolesForDocument(id);
  } catch (error) {
    renderMessage(error.message);
  }
});

matchBtn.addEventListener("click", async () => {
  try {
    const id = documentIdInput.value.trim();
    const result = await api(`/api/documents/${id}/match`, { method: "POST" });
    setOutputJson(result);
    await loadPolesForDocument(id);
  } catch (error) {
    renderMessage(error.message);
  }
});

calculateBtn.addEventListener("click", async () => {
  try {
    const id = documentIdInput.value.trim();
    const result = await api(`/api/documents/${id}/calculate`, { method: "POST" });
    setOutputJson(result);
    await loadPolesForDocument(id);
  } catch (error) {
    renderMessage(error.message);
  }
});

summaryBtn.addEventListener("click", async () => {
  try {
    const id = documentIdInput.value.trim();
    const result = await api(`/api/documents/${id}/summary`);
    renderSummary(result);
  } catch (error) {
    renderMessage(error.message);
  }
});

saveCorrectionBtn.addEventListener("click", async () => {
  if (!selectedRowId) {
    correctionResult.textContent = "Valitse ensin rivi taulukosta.";
    return;
  }

  const correctedFields = {
    pole_code: editPoleCode.value || null,
    pole_type: editPoleType.value || null,
    support_height_m: editSupportHeight.value ? Number(editSupportHeight.value) : null,
    span_m: editSpan.value ? Number(editSpan.value) : null,
    guying: editGuying.value || null,
    quantity: editQuantity.value ? Number(editQuantity.value) : 1,
  };

  try {
    correctionResult.textContent = "Tallennetaan korjaus ja päivitetään tulokset...";

    const result = await api(`/api/poles/${selectedRowId}/corrections`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        corrected_fields: correctedFields,
        selected_pool_id: editSelectedPoolId.value || null,
        note: editNote.value || null,
      }),
    });

    const docId = documentIdInput.value.trim();
    await refreshDocumentOutputs(docId);

    correctionResult.textContent = `Korjaus tallennettu ja tulokset päivitetty: ${result.correction_id}`;
  } catch (error) {
    correctionResult.textContent = error.message;
  }
});