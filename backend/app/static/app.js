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

function setOutput(data) {
  output.textContent = JSON.stringify(data, null, 2);
}

function renderPolesTable(rows) {
  polesTableBody.innerHTML = "";
  currentPoles = rows;

  rows.forEach((row) => {
    const tr = document.createElement("tr");

    tr.innerHTML = `
      <td><button data-row-id="${row.row_id}" class="select-row-btn">Valitse</button></td>
      <td>${row.source_row_number ?? ""}</td>
      <td>${row.pole_code ?? ""}</td>
      <td>${row.pole_type ?? ""}</td>
      <td>${row.support_height_m ?? ""}</td>
      <td>${row.span_m ?? ""}</td>
      <td>${row.guying ?? ""}</td>
      <td>${row.quantity ?? ""}</td>
      <td>${row.review_status}</td>
      <td>${row.confidence}</td>
    `;

    polesTableBody.appendChild(tr);
  });

  document.querySelectorAll(".select-row-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const rowId = btn.dataset.rowId;
      const row = currentPoles.find((item) => item.row_id === rowId);
      if (!row) return;

      selectedRowId = row.row_id;
      selectedRowInfo.textContent = `Valittu rivi: ${row.row_id} (lähderivi ${row.source_row_number ?? "-"})`;

      editPoleCode.value = row.pole_code ?? "";
      editPoleType.value = row.pole_type ?? "";
      editSupportHeight.value = row.support_height_m ?? "";
      editSpan.value = row.span_m ?? "";
      editGuying.value = row.guying ?? "";
      editQuantity.value = row.quantity ?? "";
      editSelectedPoolId.value = "";
      editNote.value = "";
    });
  });
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
      li.innerHTML = `<button class="doc-select-btn" data-doc-id="${doc.document_id}">Valitse</button>
        ${doc.document_id} | ${doc.original_filename} | ${doc.status}`;
      documentsList.appendChild(li);
    });

    document.querySelectorAll(".doc-select-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        documentIdInput.value = btn.dataset.docId;
      });
    });
  } catch (error) {
    output.textContent = error.message;
  }
});

analyzeBtn.addEventListener("click", async () => {
  try {
    const id = documentIdInput.value.trim();
    const result = await api(`/api/documents/${id}/analyze`, { method: "POST" });
    renderPolesTable(result);
    setOutput(result);
  } catch (error) {
    output.textContent = error.message;
  }
});

loadPolesBtn.addEventListener("click", async () => {
  try {
    const id = documentIdInput.value.trim();
    const result = await api(`/api/documents/${id}/poles`);
    renderPolesTable(result);
    setOutput(result);
  } catch (error) {
    output.textContent = error.message;
  }
});

matchBtn.addEventListener("click", async () => {
  try {
    const id = documentIdInput.value.trim();
    const result = await api(`/api/documents/${id}/match`, { method: "POST" });
    setOutput(result);
  } catch (error) {
    output.textContent = error.message;
  }
});

calculateBtn.addEventListener("click", async () => {
  try {
    const id = documentIdInput.value.trim();
    const result = await api(`/api/documents/${id}/calculate`, { method: "POST" });
    setOutput(result);
  } catch (error) {
    output.textContent = error.message;
  }
});

summaryBtn.addEventListener("click", async () => {
  try {
    const id = documentIdInput.value.trim();
    const result = await api(`/api/documents/${id}/summary`);
    setOutput(result);
  } catch (error) {
    output.textContent = error.message;
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

    correctionResult.textContent = `Korjaus tallennettu: ${result.correction_id}`;

    const docId = documentIdInput.value.trim();
    const updatedRows = await api(`/api/documents/${docId}/poles`);
    renderPolesTable(updatedRows);
  } catch (error) {
    correctionResult.textContent = error.message;
  }
});