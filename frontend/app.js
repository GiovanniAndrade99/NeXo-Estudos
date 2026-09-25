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

    const nome = user.name || user.email?.split("@")[0] || "estudante";
    document.querySelector("#hero-user-name").textContent = nome.split(" ")[0];
    document.querySelector("#profile-name").textContent = nome;
    document.querySelector("#profile-student").textContent = nome;
    if (user.email) document.querySelector("#profile-email").textContent = user.email;
    document.querySelector("#profile-avatar").textContent = nome.slice(0, 2).toUpperCase();
    preencherConta(user, result.account || {}, nome);
  })
  .catch(() => {});

function preencherConta(user, conta, nome) {
  const data = (segundos, opcoes) => segundos
    ? new Date(segundos * 1000).toLocaleString("pt-BR", opcoes)
    : "—";
  document.querySelector("#settings-name").textContent = nome;
  document.querySelector("#settings-email").textContent = user.email || "—";
  document.querySelector("#settings-avatar").textContent = nome.slice(0, 2).toUpperCase();
  const papel = document.querySelector("#settings-role");
  papel.textContent = user.role === "admin" ? "Administrador" : "Usuário";
  papel.dataset.role = user.role === "admin" ? "admin" : "usuario";
  const provedores = { senha: "E-mail e senha", google: "Google", github: "GitHub" };
  document.querySelector("#settings-provider").textContent = provedores[user.provider] || user.provider || "—";
  document.querySelector("#settings-created").textContent = data(conta.created_at, { day: "2-digit", month: "long", year: "numeric" });
  document.querySelector("#settings-session").textContent = data(conta.session_expires_at, { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
  // Contas de provedor externo não têm senha própria para trocar.
  if (user.provider !== "senha") document.querySelector(".password-card").hidden = true;
}

const passwordForm = document.querySelector("#password-form");
passwordForm?.addEventListener("submit", async (evento) => {
  evento.preventDefault();
  const mensagem = passwordForm.querySelector(".settings-message");
  const botao = passwordForm.querySelector("button[type=submit]");
  const mostrar = (texto, tipo = "error") => {
    mensagem.textContent = texto;
    mensagem.dataset.type = tipo;
    mensagem.hidden = false;
  };
  const { current, password, confirm } = passwordForm.elements;
  if (!current.value || !password.value) return mostrar("Preencha a senha atual e a nova senha.");
  if (password.value.length < 8) return mostrar("A nova senha precisa ter pelo menos 8 caracteres.");
  if (password.value !== confirm.value) return mostrar("As novas senhas não conferem.");
  botao.disabled = true;
  try {
    const resposta = await fetch("/api/auth/password", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ current_password: current.value, password: password.value })
    });
    const dados = await resposta.json().catch(() => ({}));
    if (resposta.ok) {
      passwordForm.reset();
      mostrar(dados.detail || "Senha alterada com sucesso.", "success");
    } else {
      current.value = "";
      mostrar(typeof dados.detail === "string" ? dados.detail : "Não foi possível alterar a senha agora.");
    }
  } catch {
    mostrar("Não foi possível conectar ao servidor.");
  } finally {
    botao.disabled = false;
  }
});

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
  })
  .catch(() => {
    document.querySelector("#backend-status").textContent = "API desconectada";
  });

renderHistoricMenu();
refreshHistoryComparison();

// Elementos com data-reveal entram ao aparecer na tela e saem pelo lado em que deixaram a janela.
const revealItems = document.querySelectorAll("[data-reveal]");
if ("IntersectionObserver" in window) {
  revealItems.forEach((item) => {
    const irmaos = [...item.parentElement.children].filter((el) => el.hasAttribute("data-reveal"));
    item.dataset.revealColumn = irmaos.length > 1 ? irmaos.indexOf(item) % 3 : 0;
    item.classList.add("reveal-below");
  });
  const revealObserver = new IntersectionObserver((entries) => {
    entries.forEach(({ target, isIntersecting, boundingClientRect, rootBounds }) => {
      if (isIntersecting) {
        target.style.setProperty("--reveal-delay", `${target.dataset.revealColumn * 90}ms`);
        target.classList.remove("reveal-below", "reveal-above");
        return;
      }
      // Em aba oculta o retângulo é zerado: volta ao estado inicial para animar de novo ao abrir a aba.
      const oculto = boundingClientRect.width === 0 && boundingClientRect.height === 0;
      const saiuPorCima = !oculto && rootBounds && boundingClientRect.bottom < rootBounds.top + rootBounds.height / 2;
      target.style.setProperty("--reveal-delay", "0ms");
      target.classList.toggle("reveal-above", Boolean(saiuPorCima));
      target.classList.toggle("reveal-below", !saiuPorCima);
    });
  }, { threshold: 0.15, rootMargin: "0px 0px -40px 0px" });
  revealItems.forEach((item) => revealObserver.observe(item));
}

document.querySelectorAll("[data-go-screen]").forEach((button) => {
  button.addEventListener("click", () => {
    activateScreen(button.dataset.goScreen);
    window.scrollTo({ top: 0, behavior: "smooth" });
  });
});

// Hero do perfil: digita a função processar() e depois simula a execução no terminal.
const heroCode = document.querySelector("#hero-code");
const heroTerminal = document.querySelector("#hero-terminal");
const heroCursorPos = document.querySelector("#hero-cursor-pos");
const HERO_CODIGO = [
  "# pipeline.py · do pixel ao texto",
  "def processar(imagem):",
  "    cinza = cv2.cvtColor(imagem, cv2.COLOR_BGR2GRAY)",
  "    contraste = cv2.createCLAHE(2.0).apply(cinza)",
  "    limpa = cv2.medianBlur(contraste, 3)",
  "    binaria = cv2.adaptiveThreshold(",
  "        limpa, 255, GAUSS, BINARY, 31, 11)",
  "    alinhada, angulo = corrigir_inclinacao(binaria)",
  "    return pytesseract.image_to_string(",
  "        alinhada, lang=\"por+eng\")"
];
const HERO_TERMINAL = [
  ["t-cmd", "python -m nexo processar apostila.jpg"],
  ["t-ok", "tons de cinza            0.02s"],
  ["t-ok", "CLAHE + mediana          0.05s"],
  ["t-ok", "binarização adaptativa   0.03s"],
  ["t-ok", "inclinação corrigida    -5.04°"],
  ["t-hi", "→ 9 linhas reconhecidas · pronto para estudar"]
];

function destacarPython(linha) {
  const regras = /(#.*$)|("[^"]*")|\b(def|return)\b|\b(cv2|pytesseract)\b|\b(\d+(?:\.\d+)?)\b|(\w+)(?=\()/g;
  const partes = [];
  let ultimo = 0;
  for (const m of linha.matchAll(regras)) {
    if (m.index > ultimo) partes.push(["tk-txt", linha.slice(ultimo, m.index)]);
    const classe = m[1] ? "tk-com" : m[2] ? "tk-str" : m[3] ? "tk-kw" : m[4] ? "tk-mod" : m[5] ? "tk-num" : "tk-fn";
    partes.push([classe, m[0]]);
    ultimo = m.index + m[0].length;
  }
  if (ultimo < linha.length) partes.push(["tk-txt", linha.slice(ultimo)]);
  return partes;
}

const esperar = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const heroVisivel = () => heroCode.getClientRects().length > 0 && !document.hidden;

async function animarHero() {
  const semMovimento = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const caret = document.createElement("span");
  caret.className = "type-caret";
  while (true) {
    heroCode.replaceChildren();
    heroTerminal.replaceChildren();
    for (const [indice, linha] of HERO_CODIGO.entries()) {
      const li = document.createElement("li");
      heroCode.querySelector(".current")?.classList.remove("current");
      li.className = "current";
      heroCode.append(li);
      let coluna = 0;
      for (const [classe, texto] of destacarPython(linha)) {
        const span = document.createElement("span");
        span.className = classe;
        li.append(span, caret);
        if (semMovimento) { span.textContent = texto; coluna += texto.length; continue; }
        for (const letra of texto) {
          while (!heroVisivel()) await esperar(400);
          span.textContent += letra;
          coluna += 1;
          heroCursorPos.textContent = `Ln ${indice + 1}, Col ${coluna + 1}`;
          await esperar(letra === " " ? 18 : 26 + Math.random() * 38);
        }
      }
      if (!semMovimento) await esperar(160);
    }
    for (const [classe, texto] of HERO_TERMINAL) {
      if (!semMovimento) await esperar(classe === "t-cmd" ? 500 : 380);
      const linha = document.createElement("div");
      linha.className = classe;
      linha.textContent = texto;
      heroTerminal.append(linha);
    }
    if (semMovimento) return;
    await esperar(5200);
  }
}

if (heroCode && heroTerminal) animarHero();

// MagicBento da aba Suporte: spotlight que segue o cursor, borda que acende por proximidade,
// partículas no hover, leve efeito ímã e ripple no clique. Desligado em telas pequenas e com movimento reduzido.
function iniciarMagicBento(grade) {
  const RAIO = 300;
  const PROXIMIDADE = RAIO * 0.5;
  const DISTANCIA_FADE = RAIO * 0.75;
  const PARTICULAS = 12;
  const cards = [...grade.querySelectorAll(".magic-bento-card")];
  const semAnimacao = () => window.innerWidth <= 768
    || window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  const spotlight = document.createElement("div");
  spotlight.className = "bento-spotlight";
  document.body.append(spotlight);

  document.addEventListener("mousemove", (evento) => {
    const area = grade.getBoundingClientRect();
    const dentro = !semAnimacao() && area.width > 0
      && evento.clientX >= area.left && evento.clientX <= area.right
      && evento.clientY >= area.top && evento.clientY <= area.bottom;
    if (!dentro) {
      spotlight.style.opacity = "0";
      cards.forEach((card) => card.style.setProperty("--glow-intensity", "0"));
      return;
    }
    let menorDistancia = Infinity;
    cards.forEach((card) => {
      const r = card.getBoundingClientRect();
      const distancia = Math.max(0, Math.hypot(evento.clientX - (r.left + r.width / 2), evento.clientY - (r.top + r.height / 2))
        - Math.max(r.width, r.height) / 2);
      menorDistancia = Math.min(menorDistancia, distancia);
      const intensidade = distancia <= PROXIMIDADE ? 1
        : distancia <= DISTANCIA_FADE ? (DISTANCIA_FADE - distancia) / (DISTANCIA_FADE - PROXIMIDADE) : 0;
      card.style.setProperty("--glow-x", `${((evento.clientX - r.left) / r.width) * 100}%`);
      card.style.setProperty("--glow-y", `${((evento.clientY - r.top) / r.height) * 100}%`);
      card.style.setProperty("--glow-intensity", intensidade.toFixed(3));
      card.style.setProperty("--glow-radius", `${RAIO}px`);
    });
    spotlight.style.left = `${evento.clientX}px`;
    spotlight.style.top = `${evento.clientY}px`;
    spotlight.style.opacity = menorDistancia <= PROXIMIDADE ? "0.8"
      : menorDistancia <= DISTANCIA_FADE ? String(((DISTANCIA_FADE - menorDistancia) / (DISTANCIA_FADE - PROXIMIDADE)) * 0.8) : "0";
  });
  document.addEventListener("mouseleave", () => { spotlight.style.opacity = "0"; });

  cards.forEach((card) => {
    let particulas = [];
    let timers = [];

    const limparParticulas = () => {
      timers.forEach(clearTimeout);
      timers = [];
      particulas.forEach((p) => {
        p.animate([{ opacity: getComputedStyle(p).opacity, transform: getComputedStyle(p).transform }, { opacity: 0, transform: "scale(0)" }],
          { duration: 300, easing: "cubic-bezier(.36,0,.66,-0.56)", fill: "forwards" }).onfinish = () => p.remove();
      });
      particulas = [];
    };

    card.addEventListener("mouseenter", () => {
      if (semAnimacao()) return;
      const { width, height } = card.getBoundingClientRect();
      for (let i = 0; i < PARTICULAS; i += 1) {
        timers.push(setTimeout(() => {
          const p = document.createElement("span");
          p.className = "bento-particle";
          p.style.left = `${Math.random() * width}px`;
          p.style.top = `${Math.random() * height}px`;
          card.append(p);
          particulas.push(p);
          const dx = (Math.random() - 0.5) * 100;
          const dy = (Math.random() - 0.5) * 100;
          p.animate([{ transform: "scale(0)", opacity: 0 }, { transform: "scale(1)", opacity: 1 }],
            { duration: 300, easing: "cubic-bezier(.34,1.56,.64,1)" });
          p.animate([{ transform: "translate(0, 0) rotate(0deg)" }, { transform: `translate(${dx}px, ${dy}px) rotate(${Math.random() * 360}deg)` }],
            { duration: 2000 + Math.random() * 2000, iterations: Infinity, direction: "alternate", easing: "linear", delay: 300 });
          p.animate([{ opacity: 1 }, { opacity: 0.3 }],
            { duration: 1500, iterations: Infinity, direction: "alternate", easing: "ease-in-out", delay: 300 });
        }, i * 100));
      }
    });

    card.addEventListener("mousemove", (evento) => {
      if (semAnimacao()) return;
      const r = card.getBoundingClientRect();
      card.style.setProperty("--mx", `${(evento.clientX - r.left - r.width / 2) * 0.05}px`);
      card.style.setProperty("--my", `${(evento.clientY - r.top - r.height / 2) * 0.05}px`);
    });

    card.addEventListener("mouseleave", () => {
      card.style.setProperty("--mx", "0px");
      card.style.setProperty("--my", "0px");
      limparParticulas();
    });

    card.addEventListener("click", (evento) => {
      if (semAnimacao()) return;
      const r = card.getBoundingClientRect();
      const x = evento.clientX - r.left;
      const y = evento.clientY - r.top;
      const raio = Math.max(Math.hypot(x, y), Math.hypot(x - r.width, y), Math.hypot(x, y - r.height), Math.hypot(x - r.width, y - r.height));
      const ripple = document.createElement("span");
      ripple.className = "bento-ripple";
      Object.assign(ripple.style, { width: `${raio * 2}px`, height: `${raio * 2}px`, left: `${x - raio}px`, top: `${y - raio}px` });
      card.append(ripple);
      ripple.animate([{ transform: "scale(0)", opacity: 1 }, { transform: "scale(1)", opacity: 0 }],
        { duration: 800, easing: "cubic-bezier(.22,1,.36,1)" }).onfinish = () => ripple.remove();
    });
  });
}

document.querySelectorAll(".magic-bento").forEach(iniciarMagicBento);

// Carrossel da aba Sobre: arrastar, rotação 3D dos slides vizinhos, loop infinito com clones,
// autoplay que pausa com o mouse em cima, indicadores e setas do teclado.
function iniciarCarrossel(container, { autoplay = true, intervalo = 6000, loop = true } = {}) {
  const GAP = 16;
  const LIMIAR_VELOCIDADE = 0.5; // px/ms
  const track = container.querySelector(".carousel-track");
  const originais = [...track.children];
  const total = originais.length;
  if (loop && total > 1) {
    const clone = (el) => Object.assign(el.cloneNode(true), { ariaHidden: "true" });
    track.prepend(clone(originais[total - 1]));
    track.append(clone(originais[0]));
  }
  const itens = [...track.children];
  const indicadores = originais.map((_, indice) => {
    const botao = document.createElement("button");
    botao.type = "button";
    botao.className = "carousel-indicator";
    botao.setAttribute("aria-label", `Ir para o slide ${indice + 1}`);
    botao.addEventListener("click", () => irPara(loop ? indice + 1 : indice));
    container.querySelector(".carousel-indicators").append(botao);
    return botao;
  });

  let largura = 0;
  let passo = 0;
  let posicao = loop ? 1 : 0;
  let x = 0;
  let animando = false;
  let arraste = null;
  let mouseEmCima = false;
  let quadro = 0;

  const aplicarX = (valor) => {
    x = valor;
    track.style.transform = `translate3d(${x}px, 0, 0)`;
    itens.forEach((item, indice) => {
      item.style.transform = `rotateY(${((-x - indice * passo) / passo) * 90}deg)`;
    });
  };

  const acompanharTransicao = () => {
    cancelAnimationFrame(quadro);
    const passoQuadro = () => {
      const atual = new DOMMatrixReadOnly(getComputedStyle(track).transform).m41;
      itens.forEach((item, indice) => {
        item.style.transform = `rotateY(${((-atual - indice * passo) / passo) * 90}deg)`;
      });
      if (animando) quadro = requestAnimationFrame(passoQuadro);
    };
    quadro = requestAnimationFrame(passoQuadro);
  };

  const atualizarIndicadores = () => {
    const ativo = loop ? (posicao - 1 + total) % total : Math.min(posicao, total - 1);
    indicadores.forEach((botao, indice) => {
      botao.classList.toggle("active", indice === ativo);
      botao.setAttribute("aria-current", indice === ativo ? "true" : "false");
    });
    track.style.perspectiveOrigin = `${posicao * passo + largura / 2}px 50%`;
  };

  function irPara(nova, animar = true) {
    if (!passo) return;
    posicao = Math.max(0, Math.min(nova, itens.length - 1));
    atualizarIndicadores();
    const destino = -posicao * passo;
    const semMovimento = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (!animar || semMovimento || destino === x) {
      track.classList.remove("animating");
      aplicarX(destino);
      corrigirLoop();
      return;
    }
    animando = true;
    track.classList.add("animating");
    track.style.transform = `translate3d(${destino}px, 0, 0)`;
    x = destino;
    acompanharTransicao();
  }

  // Ao chegar num clone, salta sem animação para o slide real equivalente.
  function corrigirLoop() {
    if (!loop) return;
    if (posicao === itens.length - 1) irPara(1, false);
    else if (posicao === 0) irPara(total, false);
  }

  track.addEventListener("transitionend", (evento) => {
    if (evento.target !== track) return;
    animando = false;
    track.classList.remove("animating");
    aplicarX(x);
    corrigirLoop();
  });

  const medir = () => {
    const estilo = getComputedStyle(container);
    largura = container.clientWidth - parseFloat(estilo.paddingLeft) - parseFloat(estilo.paddingRight);
    if (largura <= 0) return;
    passo = largura + GAP;
    itens.forEach((item) => { item.style.width = `${largura}px`; });
    irPara(posicao, false);
  };
  new ResizeObserver(medir).observe(container);

  track.addEventListener("pointerdown", (evento) => {
    if (animando || !passo || evento.button !== 0) return;
    arraste = { inicio: evento.clientX, base: x, ultimoX: evento.clientX, ultimoT: performance.now(), velocidade: 0 };
    track.setPointerCapture(evento.pointerId);
    container.classList.add("dragging");
  });
  track.addEventListener("pointermove", (evento) => {
    if (!arraste) return;
    const agora = performance.now();
    arraste.velocidade = (evento.clientX - arraste.ultimoX) / Math.max(1, agora - arraste.ultimoT);
    arraste.ultimoX = evento.clientX;
    arraste.ultimoT = agora;
    let novo = arraste.base + (evento.clientX - arraste.inicio);
    if (!loop) novo = Math.min(0, Math.max(novo, -(itens.length - 1) * passo));
    aplicarX(novo);
  });
  const soltar = () => {
    if (!arraste) return;
    const deslocamento = x - arraste.base;
    const direcao = deslocamento < -passo * 0.15 || arraste.velocidade < -LIMIAR_VELOCIDADE ? 1
      : deslocamento > passo * 0.15 || arraste.velocidade > LIMIAR_VELOCIDADE ? -1 : 0;
    arraste = null;
    container.classList.remove("dragging");
    irPara(posicao + direcao);
  };
  track.addEventListener("pointerup", soltar);
  track.addEventListener("pointercancel", soltar);

  container.addEventListener("keydown", (evento) => {
    if (evento.key === "ArrowRight") { evento.preventDefault(); if (!animando) irPara(posicao + 1); }
    if (evento.key === "ArrowLeft") { evento.preventDefault(); if (!animando) irPara(posicao - 1); }
  });
  container.addEventListener("mouseenter", () => { mouseEmCima = true; });
  container.addEventListener("mouseleave", () => { mouseEmCima = false; });

  if (autoplay) {
    setInterval(() => {
      const visivel = container.getClientRects().length > 0 && !document.hidden;
      const semMovimento = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      if (visivel && !mouseEmCima && !arraste && !animando && !semMovimento && container !== document.activeElement) {
        irPara(loop ? posicao + 1 : Math.min(posicao + 1, itens.length - 1));
      }
    }, intervalo);
  }
}

document.querySelectorAll("[data-carousel]").forEach((container) => iniciarCarrossel(container));

// BorderGlow: --edge-proximity (0 no centro, 100 na borda) e --cursor-angle orientam o brilho da borda.
// Delegado no documento para valer também nos slides clonados pelo carrossel.
document.addEventListener("pointermove", (evento) => {
  const card = evento.target.closest?.(".border-glow-card");
  if (!card) return;
  const r = card.getBoundingClientRect();
  const cx = r.width / 2;
  const cy = r.height / 2;
  const dx = evento.clientX - r.left - cx;
  const dy = evento.clientY - r.top - cy;
  const kx = dx === 0 ? Infinity : cx / Math.abs(dx);
  const ky = dy === 0 ? Infinity : cy / Math.abs(dy);
  const proximidade = Math.min(Math.max(1 / Math.min(kx, ky), 0), 1);
  let angulo = dx === 0 && dy === 0 ? 0 : Math.atan2(dy, dx) * (180 / Math.PI) + 90;
  if (angulo < 0) angulo += 360;
  card.style.setProperty("--edge-proximity", (proximidade * 100).toFixed(3));
  card.style.setProperty("--cursor-angle", `${angulo.toFixed(3)}deg`);
});
