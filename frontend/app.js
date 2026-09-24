const imageInput = document.querySelector("#image-input");
const dropzone = document.querySelector("#dropzone");
const processButton = document.querySelector("#process-button");
const errorMessage = document.querySelector("#error-message");
const uploadedFilesSummary = document.querySelector("#uploaded-files-summary");
const selectedCount = document.querySelector("#selected-count");
const acceptedTypes = ["image/png", "image/jpeg", "image/bmp", "image/tiff", "image/webp"];
let selectedFiles = [];

const navItems = document.querySelectorAll(".nav-item");
const screens = document.querySelectorAll(".screen");
const resultTabs = document.querySelectorAll(".result-tab");
const resultPanels = document.querySelectorAll(".result-tab-panel");
const historyList = document.querySelector("#history-list");
const processedImage = document.querySelector("#processed-image");
const beforeImage = document.querySelector("#before-image");
const afterImage = document.querySelector("#after-image");
const saveImageButton = document.querySelector("#save-image-button");
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
  const files = Array.from(list || []).filter((file) => file && file.type && acceptedTypes.includes(file.type));

  if (!files.length) {
    selectedFiles = [];
    processButton.disabled = true;
    showError("Formato incompatível. Escolha PNG, JPG, BMP, TIFF ou WEBP.");
    updateUploadSummary();
    return;
  }

  const validFiles = [];
  for (const file of files) {
    if (file.size > 12 * 1024 * 1024) {
      showError("Uma ou mais imagens excedem 12 MB.");
      return;
    }
    validFiles.push(file);
  }

  if (validFiles.length > 2) {
    selectedFiles = validFiles.slice(0, 2);
    showError("Você pode enviar no máximo 2 imagens por vez.");
  } else {
    selectedFiles = validFiles;
  }

  processButton.disabled = !selectedFiles.length;
  dropzone.querySelector("strong").textContent = selectedFiles.length > 1 ? "2 imagens selecionadas" : selectedFiles[0].name;
  dropzone.querySelector(".drop-copy").textContent = selectedFiles.length > 1 ? "pronto para processar as imagens" : (selectedFiles[0].size / 1024 / 1024).toFixed(2) + " MB · pronto para processar";
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

  historyList.innerHTML = records.map((item) => `
    <div class="history-item">
      <div>
        <strong>${item.name}</strong>
        <small>${item.dimensions} · ${item.date}</small>
      </div>
      <span class="history-meta">${item.status}</span>
    </div>
  `).join("");
}

function updateDetails(data) {
  const pixels = (data.dimensoes?.largura || 0) * (data.dimensoes?.altura || 0);
  const sourceFile = selectedFiles[0] || null;
  document.querySelector("#detail-pixels").textContent = pixels.toLocaleString("pt-BR") + " px";
  document.querySelector("#detail-pdf-type").textContent = sourceFile?.type?.includes("pdf") ? "PDF digital" : "Imagem rasterizada";
  document.querySelector("#detail-material").textContent = sourceFile?.name?.toLowerCase().includes("caderno") ? "Caderno" : "Documento";
  document.querySelector("#detail-quality").textContent = data.texto?.length > 250 ? "Alta" : data.texto ? "Média" : "Baixa";
  document.querySelector("#detail-colors").textContent = "Cinza + preto/branco";
  document.querySelector("#detail-format").textContent = sourceFile?.type?.split("/")[1]?.toUpperCase() || "PNG";
  beforeImage.src = imageUrl(data.imagens.original);
  afterImage.src = imageUrl(data.imagens.processada);
}

processButton.addEventListener("click", async () => {
  if (!selectedFiles.length) return;
  showError();
  processButton.disabled = true;
  processButton.innerHTML = "<span>Processando imagem…</span><span class=\"spinner\"></span>";
  try {
    const body = new FormData();
    selectedFiles.forEach((file) => body.append("arquivos", file));
    const response = await fetch("/api/processar", { method: "POST", body });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Não foi possível processar a imagem.");
    const payload = Array.isArray(data) ? data[0] : (data.arquivos && Array.isArray(data.arquivos) ? data.arquivos[0] : data);
    document.querySelector("#empty-result").hidden = true;
    document.querySelector("#result-content").hidden = false;
    document.querySelector("#result-badge").textContent =
      payload.ocr_disponivel ? "ANÁLISE CONCLUÍDA" : "IMAGEM PROCESSADA";
    document.querySelector("#file-name").textContent = payload.nome_arquivo;
    document.querySelector("#image-dimensions").textContent =
      payload.dimensoes.largura + " × " + payload.dimensoes.altura;
    document.querySelector("#rotation-value").textContent =
      payload.inclinacao_corrigida_graus + "°";
    document.querySelector("#original-image").src = imageUrl(payload.imagens.original);
    processedImageSource = imageUrl(payload.imagens.processada);
    processedImage.src = processedImageSource;
    saveImageButton.disabled = false;
    applyManualAdjustments();
    document.querySelector("#recognized-text").textContent =
      payload.texto || "Nenhum texto foi reconhecido nesta imagem.";
    document.querySelector("#copy-button").disabled = !payload.texto;
    const warning = document.querySelector("#ocr-warning");
    warning.hidden = !payload.aviso;
    warning.textContent = payload.aviso || "";
    updateDetails(payload);

    const historyEntry = {
      name: payload.nome_arquivo,
      dimensions: `${payload.dimensoes.largura} × ${payload.dimensoes.altura}`,
      status: payload.ocr_disponivel ? "OCR OK" : "PROCESSADO",
      date: new Date().toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" })
    };

    const existingEntries = JSON.parse(localStorage.getItem("process-history") || "[]");
    existingEntries.unshift(historyEntry);
    localStorage.setItem("process-history", JSON.stringify(existingEntries.slice(0, 8)));
    renderHistory(JSON.parse(localStorage.getItem("process-history") || "[]"));

    activateResultTab("resumo");
    document.querySelector("#result-panel").scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (error) {
    showError(error.message || "Falha de comunicação com o servidor.");
  } finally {
    processButton.disabled = !selectedFiles.length;
    processButton.innerHTML = "<span>Processar imagem</span><span>→</span>";
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
  })
  .catch(() => { document.querySelector("#backend-status").textContent = "API desconectada"; });
