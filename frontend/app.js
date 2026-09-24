const imageInput = document.querySelector("#image-input");
const dropzone = document.querySelector("#dropzone");
const processButton = document.querySelector("#process-button");
const errorMessage = document.querySelector("#error-message");
const uploadedFilesSummary = document.querySelector("#uploaded-files-summary");
const selectedCount = document.querySelector("#selected-count");
const acceptedTypes = ["image/png", "image/jpeg", "image/bmp", "image/tiff", "image/webp", "application/pdf"];
const compareLeft = document.querySelector("#compare-left");
const compareRight = document.querySelector("#compare-right");
let processedAssets = [];
let selectedFiles = [];

const navItems = document.querySelectorAll(".nav-item");
const screens = document.querySelectorAll(".screen");
const resultTabs = document.querySelectorAll(".result-tab");
const resultPanels = document.querySelectorAll(".result-tab-panel");
const historyList = document.querySelector("#history-result-list");
const processedImage = document.querySelector("#processed-image");
const beforeImage = document.querySelector("#before-image");
const afterImage = document.querySelector("#after-image");
const saveImageButton = document.querySelector("#save-image-button");
const assistantBookTitle = document.querySelector("#assistant-book-title");
const assistantAuthor = document.querySelector("#assistant-author");
const assistantDescription = document.querySelector("#assistant-description");
const assistantFigures = document.querySelector("#assistant-figures");
const studySummary = document.querySelector("#study-summary");
const studyExercises = document.querySelector("#study-exercises");
const adjustmentControls = {
  brightness: document.querySelector("#brightness-control"),
  contrast: document.querySelector("#contrast-control"),
  saturation: document.querySelector("#saturation-control"),
  rotation: document.querySelector("#rotation-control")
};
const adjustmentValues = {
  brightness: document.querySelector("#brightness-value"),
  contrast: document.querySelector("#contrast-value"),
  saturation: document.querySelector("#saturation-value"),
  rotation: document.querySelector("#rotation-adjustment-value")
};
let processedImageSource = "";

fetch("/api/auth/me")
  .then((response) => response.ok ? response.json() : null)
  .then((result) => {
    if (!result?.authenticated || !result.user) return;
    const user = result.user;
    document.querySelector("#account-name").textContent = user.name || user.email || "Conta conectada";
    document.querySelector("#account-provider").textContent = user.email || `Conectado com ${user.provider}`;
    const avatar = document.querySelector("#account-avatar");
    if (user.avatar) {
      const image = document.createElement("img");
      image.src = user.avatar;
      image.alt = "";
      avatar.replaceChildren(image);
    } else {
      avatar.textContent = (user.name || "U").slice(0, 2).toUpperCase();
    }
    document.querySelector("#logout-link").hidden = false;
  })
  .catch(() => {});

function activateScreen(screenName) {
  navItems.forEach((item) => {
    const isActive = item.dataset.screen === screenName;
    item.classList.toggle("active", isActive);
  });

  screens.forEach((screen) => {
    screen.classList.toggle("active", screen.dataset.screenContent === screenName);
  });
}

function activateResultTab(tabName) {
  resultTabs.forEach((tab) => {
    tab.classList.toggle("active", tab.dataset.resultTab === tabName);
  });

  resultPanels.forEach((panel) => {
    panel.classList.toggle("active", panel.dataset.resultPanel === tabName);
  });
}

resultTabs.forEach((tab) => {
  tab.addEventListener("click", () => activateResultTab(tab.dataset.resultTab));
});

navItems.forEach((item) => {
  item.addEventListener("click", () => activateScreen(item.dataset.screen));
});

function showError(message = "") {
  errorMessage.textContent = message;
  errorMessage.hidden = !message;
}

function updateUploadSummary() {
  if (!uploadedFilesSummary || !selectedCount) return;

  if (!selectedFiles.length) {
    selectedCount.textContent = "0 selecionadas";
    uploadedFilesSummary.innerHTML = "<li>Nenhuma imagem selecionada.</li>";
    return;
  }

  selectedCount.textContent = `${selectedFiles.length} selecionada${selectedFiles.length > 1 ? "s" : ""}`;
  uploadedFilesSummary.innerHTML = selectedFiles.map((file) => `
    <li>${file.name} · ${(file.size / 1024 / 1024).toFixed(2)} MB</li>
  `).join("");
}

function selectFiles(list) {
  showError();
  const files = Array.from(list || []).filter((file) => {
    const isPdf = file.name.toLowerCase().endsWith(".pdf");
    return file && (acceptedTypes.includes(file.type) || isPdf);
  });

  if (!files.length) {
    selectedFiles = [];
    processButton.disabled = true;
    showError("Formato invalido. Escolha PNG, JPG, BMP, TIFF, WEBP ou PDF.");
    updateUploadSummary();
    return;
  }

  const validFiles = [];
  for (const file of files) {
    if (file.size > 12 * 1024 * 1024) {
      showError("Um ou mais arquivos excedem 12 MB.");
      return;
    }
    validFiles.push(file);
  }

  if (validFiles.length > 2) {
    selectedFiles = validFiles.slice(0, 2);
    showError("Voce pode enviar no maximo 2 arquivos por vez.");
  } else {
    selectedFiles = validFiles;
  }

  processButton.disabled = !selectedFiles.length;
  dropzone.querySelector("strong").textContent = selectedFiles.length > 1 ? `${selectedFiles.length} arquivos selecionados` : selectedFiles[0].name;
  dropzone.querySelector(".drop-copy").textContent = selectedFiles.length > 1 ? "prontos para processar" : (selectedFiles[0].size / 1024 / 1024).toFixed(2) + " MB - pronto para processar";
  updateUploadSummary();
}

imageInput.addEventListener("change", () => selectFiles(imageInput.files));
dropzone.addEventListener("keydown", (event) => {
  if (event.key === "Enter" || event.key === " ") {
    event.preventDefault();
    imageInput.click();
  }
});
["dragenter", "dragover"].forEach((name) => dropzone.addEventListener(name, (event) => {
  event.preventDefault();
  dropzone.classList.add("dragging");
}));
["dragleave", "drop"].forEach((name) => dropzone.addEventListener(name, (event) => {
  event.preventDefault();
  dropzone.classList.remove("dragging");
}));
dropzone.addEventListener("drop", (event) => selectFiles(event.dataTransfer.files));

function imageUrl(base64) {
  return "data:image/png;base64," + base64;
}

function getAdjustments() {
  return {
    brightness: Number(adjustmentControls.brightness.value),
    contrast: Number(adjustmentControls.contrast.value),
    saturation: Number(adjustmentControls.saturation.value),
    rotation: Number(adjustmentControls.rotation.value)
  };
}

function applyManualAdjustments() {
  const adjustments = getAdjustments();
  const filter = `brightness(${adjustments.brightness}%) contrast(${adjustments.contrast}%) saturate(${adjustments.saturation}%)`;
  const transform = `rotate(${adjustments.rotation}deg)`;
  processedImage.style.filter = filter;
  processedImage.style.transform = transform;
  afterImage.style.filter = filter;
  afterImage.style.transform = transform;
  adjustmentValues.brightness.textContent = adjustments.brightness + "%";
  adjustmentValues.contrast.textContent = adjustments.contrast + "%";
  adjustmentValues.saturation.textContent = adjustments.saturation + "%";
  adjustmentValues.rotation.textContent = adjustments.rotation + "°";
}

Object.values(adjustmentControls).forEach((control) => {
  control.addEventListener("input", applyManualAdjustments);
});

document.querySelector("#reset-adjustments").addEventListener("click", () => {
  adjustmentControls.brightness.value = 100;
  adjustmentControls.contrast.value = 100;
  adjustmentControls.saturation.value = 100;
  adjustmentControls.rotation.value = 0;
  applyManualAdjustments();
});

saveImageButton.addEventListener("click", () => {
  if (!processedImageSource) return;
  const image = new Image();
  image.onload = () => {
    const adjustments = getAdjustments();
    const canvas = document.createElement("canvas");
    const context = canvas.getContext("2d");
    const radians = adjustments.rotation * Math.PI / 180;
    const rotated = Math.abs(adjustments.rotation) > 0;
    canvas.width = rotated ? image.height : image.width;
    canvas.height = rotated ? image.width : image.height;
    context.translate(canvas.width / 2, canvas.height / 2);
    context.rotate(radians);
    context.filter = `brightness(${adjustments.brightness}%) contrast(${adjustments.contrast}%) saturate(${adjustments.saturation}%)`;
    context.drawImage(image, -image.width / 2, -image.height / 2);
    const link = document.createElement("a");
    link.download = "imagem-processada-ajustada.png";
    link.href = canvas.toDataURL("image/png");
    link.click();
  };
  image.src = processedImageSource;
});

function renderHistory(records) {
  if (!historyList) return;
  if (!records.length) {
    historyList.innerHTML = '<div class="history-item"><div><strong>Nenhuma imagem processada</strong><small>Envie uma imagem para registrar o histórico.</small></div><span class="history-meta">SEM REGISTRO</span></div>';
    return;
  }

  historyList.innerHTML = records.map(historyItemMarkup).join("");
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#39;"
  })[character]);
}

function historyItemMarkup(item, index) {
  const name = escapeHtml(item.name);
  const dimensions = escapeHtml(item.dimensions);
  const date = escapeHtml(item.date);
  const status = escapeHtml(item.status);
  return `
    <div class="history-item">
      <div>
        <strong>${name}</strong>
        <small>${dimensions} | ${formatDuration(item.time)} | ${date}</small>
      </div>
      <div class="history-actions">
        <span class="history-meta">${status}</span>
        <select class="history-format" data-history-format="${index}" aria-label="Formato para salvar ${name}">
          <option value="txt">TXT</option>
          <option value="json">JSON</option>
        </select>
        <button class="history-save-button" type="button" data-history-save="${index}">Salvar como <span>&darr;</span></button>
      </div>
    </div>
  `;
}

function saveHistoryItem(item, format) {
  const assistant = item.assistente || {};
  const report = format === "json"
    ? JSON.stringify(item, null, 2)
    : [
      `Imagem: ${item.name}`,
      `Dimensões: ${item.dimensions}`,
      `Tempo de processamento: ${formatDuration(item.time)}`,
      `Processado em: ${item.date}`,
      `Status: ${item.status}`,
      `Livro sugerido: ${assistant.livro || "não identificado"}`,
      `Autor: ${assistant.autor || "não identificado"}`,
      `Resumo: ${assistant.resumo_estudo || "não disponível"}`,
      "",
      "Exercícios de revisão:",
      ...(assistant.exercicios_revisao || []).map((exercise, index) => `${index + 1}. ${exercise}`)
    ].join("\n");

  const blob = new Blob([report], { type: format === "json" ? "application/json" : "text/plain" });
  const link = document.createElement("a");
  link.download = `${item.name.replace(/\.[^.]+$/, "")}-historico.${format}`;
  link.href = URL.createObjectURL(blob);
  link.click();
  URL.revokeObjectURL(link.href);
}

document.addEventListener("click", (event) => {
  const button = event.target.closest("[data-history-save]");
  if (!button) return;
  const records = JSON.parse(localStorage.getItem("process-history") || "[]");
  const item = records[Number(button.dataset.historySave)];
  const format = button.parentElement.querySelector(`[data-history-format="${button.dataset.historySave}"]`)?.value || "txt";
  if (item) saveHistoryItem(item, format);
});

function updateDetails(data, sourceFile = selectedFiles[0]) {
  const pixels = (data.dimensoes?.largura || 0) * (data.dimensoes?.altura || 0);
  document.querySelector("#processing-time").textContent = formatDuration(data.tempo_processamento_ms);
  document.querySelector("#processing-time-description").textContent = data.pagina ? `Pagina ${data.pagina}: processamento, alinhamento e OCR.` : "Processamento, alinhamento e OCR desta imagem.";
  document.querySelector("#detail-pixels").textContent = pixels.toLocaleString("pt-BR") + " px";
  document.querySelector("#detail-pdf-type").textContent = sourceFile?.type?.includes("pdf") ? "PDF digital" : "Imagem rasterizada";
  document.querySelector("#detail-material").textContent = sourceFile?.name?.toLowerCase().includes("caderno") ? "Caderno" : "Documento";
  document.querySelector("#detail-quality").textContent = data.texto?.length > 250 ? "Alta" : data.texto ? "Média" : "Baixa";
  document.querySelector("#detail-colors").textContent = "Cinza + preto/branco";
  document.querySelector("#detail-format").textContent = sourceFile?.name?.toLowerCase().endsWith(".pdf") ? "PDF" : (sourceFile?.type?.split("/")[1]?.toUpperCase() || "PNG");
  beforeImage.src = imageUrl(data.imagens.original);
  afterImage.src = imageUrl(data.imagens.processada);
}

function renderAssistenteEstudos(assistente) {
  if (!assistente) {
    assistantBookTitle.textContent = "—";
    assistantAuthor.textContent = "Autor: não identificado";
    assistantDescription.textContent = "A análise da imagem ainda não gerou uma sugestão de material didático.";
    assistantFigures.innerHTML = "<li>Sem figuras detectadas</li>";
    studySummary.textContent = "O assistente ainda não gerou um resumo para esta imagem.";
    studyExercises.innerHTML = "<li>Sem exercícios gerados ainda.</li>";
    return;
  }

  assistantBookTitle.textContent = assistente.livro || "Material didático genérico";
  assistantAuthor.textContent = `Autor: ${assistente.autor || "não identificado"}`;
  assistantDescription.textContent = assistente.descricao || "A imagem parece conter material de estudo, mas ainda não foi possível identificar um livro com clareza.";

  const figuras = Array.isArray(assistente.figuras) && assistente.figuras.length
    ? assistente.figuras
    : ["Resumo visual", "Tema principal", "Exercícios de revisão"];

  assistantFigures.innerHTML = figuras.slice(0, 4).map((figura) => `<li>${figura}</li>`).join("");
  studySummary.textContent = assistente.resumo_estudo || "O assistente não gerou um resumo para esta imagem.";

  const exercicios = Array.isArray(assistente.exercicios_revisao) && assistente.exercicios_revisao.length
    ? assistente.exercicios_revisao
    : ["Revise os conceitos principais da imagem e descreva com suas próprias palavras o tema central."];

  studyExercises.innerHTML = exercicios.slice(0, 3).map((item) => `<li>${item}</li>`).join("");
}

function getHistoryRecords() {
  return JSON.parse(localStorage.getItem("process-history") || "[]");
}

function renderHistoricMenu() {
  const records = getHistoryRecords();
  const historicTargets = [
    document.querySelector("#history-result-list"),
    document.querySelector("#history-menu-list"),
    document.querySelector("#comparison-history-list")
  ].filter(Boolean);

  historicTargets.forEach((list) => {
    if (!records.length) {
      list.innerHTML = '<div class="history-item"><div><strong>Nenhuma imagem processada</strong><small>Envie uma imagem para registrar o historico.</small></div><span class="history-meta">SEM REGISTRO</span></div>';
      return;
    }
    list.innerHTML = records.map(historyItemMarkup).join("");
  });
}

function openHistoryImageStore() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open("nexo-estudos-history", 1);
    request.onupgradeneeded = () => {
      if (!request.result.objectStoreNames.contains("images")) {
        request.result.createObjectStore("images", { keyPath: "id" });
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error || new Error("Nao foi possivel abrir o armazenamento local."));
  });
}

function storeHistoryImage(id, dataUrl) {
  return openHistoryImageStore().then((database) => new Promise((resolve, reject) => {
    const transaction = database.transaction("images", "readwrite");
    transaction.objectStore("images").put({ id, dataUrl });
    transaction.oncomplete = () => { database.close(); resolve(); };
    transaction.onerror = () => { database.close(); reject(transaction.error); };
  }));
}

function loadHistoryImage(id) {
  return openHistoryImageStore().then((database) => new Promise((resolve, reject) => {
    const request = database.transaction("images", "readonly").objectStore("images").get(id);
    request.onsuccess = () => { database.close(); resolve(request.result?.dataUrl || null); };
    request.onerror = () => { database.close(); reject(request.error); };
  }));
}

function removeHistoryImages(ids) {
  if (!ids.length) return Promise.resolve();
  return openHistoryImageStore().then((database) => new Promise((resolve, reject) => {
    const transaction = database.transaction("images", "readwrite");
    ids.forEach((id) => transaction.objectStore("images").delete(id));
    transaction.oncomplete = () => { database.close(); resolve(); };
    transaction.onerror = () => { database.close(); reject(transaction.error); };
  }));
}

function makeHistoryThumbnail(base64) {
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => {
      const scale = Math.min(1, 1400 / Math.max(image.width, image.height));
      const canvas = document.createElement("canvas");
      canvas.width = Math.max(1, Math.round(image.width * scale));
      canvas.height = Math.max(1, Math.round(image.height * scale));
      const context = canvas.getContext("2d");
      if (!context) return reject(new Error("Canvas indisponivel para salvar a imagem."));
      context.drawImage(image, 0, 0, canvas.width, canvas.height);
      resolve(canvas.toDataURL("image/jpeg", 0.78));
    };
    image.onerror = () => reject(new Error("Nao foi possivel preparar a imagem para o historico."));
    image.src = imageUrl(base64);
  });
}

async function saveProcessedImagesToHistory(assets, existingRecords) {
  const newRecords = assets.map((asset) => ({
    id: `history-${Date.now()}-${Math.random().toString(36).slice(2)}`,
    name: asset.nome_arquivo + (asset.pagina ? ` | pagina ${asset.pagina}` : ""),
    dimensions: `${asset.dimensoes.largura} x ${asset.dimensoes.altura}`,
    time: asset.tempo_processamento_ms,
    status: asset.ocr_disponivel ? "OCR OK" : "PROCESSADO",
    date: new Date().toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" }),
    assistente: asset.assistente_estudos || {},
    sourceImage: asset.imagens.original
  }));
  const retainedNewRecords = newRecords.slice(0, 8);
  let storageFailed = false;

  for (const record of retainedNewRecords) {
    try {
      await storeHistoryImage(record.id, await makeHistoryThumbnail(record.sourceImage));
      record.imageId = record.id;
    } catch {
      storageFailed = true;
      record.imageId = null;
    }
    delete record.sourceImage;
  }

  const nextRecords = [...retainedNewRecords, ...existingRecords].slice(0, 8);
  const retainedImageIds = new Set(nextRecords.map((record) => record.imageId).filter(Boolean));
  const expiredImageIds = existingRecords
    .map((record) => record.imageId)
    .filter((id) => id && !retainedImageIds.has(id));
  await removeHistoryImages(expiredImageIds).catch(() => {});
  localStorage.setItem("process-history", JSON.stringify(nextRecords));
  return storageFailed;
}

async function refreshHistoryComparison() {
  const records = getHistoryRecords();
  const imageRecords = records.filter((record) => record.imageId);
  const buildHistoryOptions = () => imageRecords.map((record) =>
    new Option(`${record.name} | ${formatDuration(record.time)} | ${record.date}`, record.imageId)
  );
  compareLeft.replaceChildren(...buildHistoryOptions());
  compareRight.replaceChildren(...buildHistoryOptions());
  compareLeft.disabled = imageRecords.length < 2;
  compareRight.disabled = imageRecords.length < 2;
  document.querySelector(".user-comparison").hidden = imageRecords.length < 2;
  document.querySelector("#comparison-empty").hidden = imageRecords.length >= 2;
  document.querySelector("#history-comparison-status").textContent = "";

  if (imageRecords.length < 2) {
    document.querySelector("#comparison-empty").textContent = records.length
      ? "Reprocesse imagens antigas para salva-las e habilitar a comparacao."
      : "Processe imagens para adiciona-las ao historico e compara-las.";
    document.querySelector("#compare-left-image").removeAttribute("src");
    document.querySelector("#compare-right-image").removeAttribute("src");
    return;
  }

  compareLeft.value = imageRecords[0].imageId;
  compareRight.value = imageRecords[1].imageId;
  compareLeft.onchange = updateHistoryComparison;
  compareRight.onchange = updateHistoryComparison;
  await updateHistoryComparison();
}

async function updateHistoryComparison() {
  const left = getHistoryRecords().find((record) => record.imageId === compareLeft.value);
  const right = getHistoryRecords().find((record) => record.imageId === compareRight.value);
  if (!left || !right) return;
  if (left.imageId === right.imageId) {
    document.querySelector(".user-comparison").hidden = true;
    document.querySelector("#history-comparison-status").textContent = "Escolha dois registros diferentes para comparar.";
    return;
  }
  document.querySelector(".user-comparison").hidden = false;
  document.querySelector("#history-comparison-status").textContent = "";
  try {
    const [leftImage, rightImage] = await Promise.all([
      loadHistoryImage(left.imageId),
      loadHistoryImage(right.imageId)
    ]);
    if (!leftImage || !rightImage) {
      document.querySelector("#history-comparison-status").textContent = "Uma imagem salva nao foi encontrada. Processe-a novamente para habilitar a comparacao.";
      return;
    }
    document.querySelector("#compare-left-image").src = leftImage;
    document.querySelector("#compare-right-image").src = rightImage;
    document.querySelector("#compare-left-caption").textContent = `${left.name} | ${formatDuration(left.time)}`;
    document.querySelector("#compare-right-caption").textContent = `${right.name} | ${formatDuration(right.time)}`;
  } catch {
    document.querySelector("#history-comparison-status").textContent = "Nao foi possivel abrir as imagens salvas neste navegador.";
  }
}

function formatDuration(milliseconds) {
  if (!Number.isFinite(Number(milliseconds))) return "-";
  return milliseconds < 1000 ? `${Math.round(milliseconds)} ms` : `${(milliseconds / 1000).toFixed(2)} s`;
}


processButton.addEventListener("click", async () => {
  if (!selectedFiles.length) return;
  showError();
  processButton.disabled = true;
  processButton.innerHTML = "<span>Processando arquivos...</span><span class=\"spinner\"></span>";
  try {
    const body = new FormData();
    selectedFiles.forEach((file) => body.append("arquivos", file));
    const response = await fetch("/api/processar", { method: "POST", body });
    if (response.status === 401) {
      window.location.href = "/login";
      return;
    }
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Nao foi possivel processar os arquivos.");
    const files = data.arquivos || [{ nome_arquivo: selectedFiles[0].name, paginas: [data] }];
    processedAssets = files.flatMap((file, fileIndex) => (file.paginas || []).map((page) => ({ ...page, nome_arquivo: file.nome_arquivo, formato: file.formato, fileIndex })));
    if (!processedAssets.length) throw new Error("Nao foi encontrada nenhuma pagina para exibir.");
    const payload = processedAssets[0];
    const sourceFile = selectedFiles[payload.fileIndex] || selectedFiles[0];
    document.querySelector("#empty-result").hidden = true;
    document.querySelector("#result-content").hidden = false;
    document.querySelector("#result-badge").textContent = payload.ocr_disponivel ? "ANALISE CONCLUIDA" : "IMAGEM PROCESSADA";
    document.querySelector("#file-name").textContent = payload.nome_arquivo + (payload.pagina ? ` - Pagina ${payload.pagina}` : "");
    document.querySelector("#image-dimensions").textContent = payload.dimensoes.largura + " x " +payload.dimensoes.altura;
    document.querySelector("#rotation-value").textContent = payload.inclinacao_corrigida_graus + " graus";
    document.querySelector("#original-image").src = imageUrl(payload.imagens.original);
    processedImageSource = imageUrl(payload.imagens.processada);
    processedImage.src = processedImageSource;
    saveImageButton.disabled = false;
    applyManualAdjustments();
    const descricaoProcesso = payload.descricao_processo || "A imagem foi processada em tons de cinza, com contraste ajustado, ruido reduzido e alinhamento aplicado antes da extracao do conteudo.";
    document.querySelector("#recognized-text").textContent = payload.texto || descricaoProcesso;
    document.querySelector("#copy-button").disabled = false;
    const warning = document.querySelector("#ocr-warning");
    warning.hidden = !payload.aviso;
    warning.textContent = payload.aviso || "";
    renderAssistenteEstudos(payload.assistente_estudos);
    updateDetails(payload, sourceFile);

    const existingEntries = getHistoryRecords();
    const storageFailed = await saveProcessedImagesToHistory(processedAssets, existingEntries);
    renderHistory(getHistoryRecords());
    renderHistoricMenu();
    await refreshHistoryComparison();
    if (storageFailed) {
      document.querySelector("#history-comparison-status").textContent = "O historico foi salvo, mas algumas imagens nao puderam ser guardadas para comparacao.";
    }

    activateResultTab("resumo");
    document.querySelector("#result-panel").scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (error) {
    showError(error.message || "Falha de comunicacao com o servidor.");
  } finally {
    processButton.disabled = !selectedFiles.length;
    processButton.innerHTML = "<span>Processar imagem</span><span>&gt;</span>";
  }
});

document.querySelector("#copy-button").addEventListener("click", async (event) => {
  try {
    await navigator.clipboard.writeText(document.querySelector("#recognized-text").textContent);
    event.currentTarget.innerHTML = "Copiado <span>✓</span>";
    setTimeout(() => { event.currentTarget.innerHTML = "Copiar texto <span>▢</span>"; }, 1400);
  } catch {
    showError("Não foi possível copiar. Selecione o texto e copie manualmente.");
  }
});

fetch("/api/health")
  .then((response) => response.json())
  .then((data) => {
    const status = document.querySelector("#backend-status");
    status.textContent = data.ocr_disponivel ? "OCR pronto" : "OCR indisponível";
    status.title = data.aviso || "API ativa";
    status.previousElementSibling.classList.toggle("offline", !data.ocr_disponivel);
    document.querySelector("#support-api-status").textContent = data.status === "ok" ? "Conectada" : "Desconectada";
    document.querySelector("#support-ocr-status").textContent = data.ocr_disponivel ? "Disponivel" : (data.aviso || "Indisponivel");
  })
  .catch(() => {
    document.querySelector("#backend-status").textContent = "API desconectada";
    document.querySelector("#support-api-status").textContent = "Desconectada";
    document.querySelector("#support-ocr-status").textContent = "Indisponivel ate reconectar a API";
  });

renderHistoricMenu();
refreshHistoryComparison();
