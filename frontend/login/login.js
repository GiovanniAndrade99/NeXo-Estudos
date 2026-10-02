const views = document.querySelectorAll(".auth-view");
const params = new URLSearchParams(window.location.search);
const resetToken = params.get("reset");

function showView(name) {
  views.forEach((view) => {
    view.hidden = view.dataset.view !== name;
    view.querySelector(".login-message").hidden = true;
  });
  document.querySelector(`[data-view="${name}"] input`)?.focus();
}

function showMessage(form, message, type = "error") {
  const box = form.querySelector(".login-message");
  box.textContent = message;
  box.dataset.type = type;
  box.hidden = false;
}

async function postJson(url, body) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await response.json().catch(() => ({}));
  const detail = typeof data.detail === "string" ? data.detail : "Não foi possível concluir agora. Tente novamente.";
  return { ok: response.ok, status: response.status, detail, data };
}

// reCAPTCHA v2: só é carregado quando o servidor informa uma chave (RECAPTCHA_SITE_KEY no .env).
const captchaWidgets = new Map();

fetch("/api/auth/status")
  .then((response) => response.json())
  .then((status) => {
    const siteKey = status.recaptcha_site_key;
    if (!siteKey) return;
    window.nexoRecaptchaPronto = () => {
      document.querySelectorAll("[data-captcha]").forEach((box) => {
        box.hidden = false;
        captchaWidgets.set(box.closest("form"), window.grecaptcha.render(box, { sitekey: siteKey }));
      });
    };
    const script = document.createElement("script");
    script.src = "https://www.google.com/recaptcha/api.js?onload=nexoRecaptchaPronto&render=explicit&hl=pt-BR";
    script.async = true;
    document.head.append(script);
  })
  .catch(() => {});

function captchaToken(form) {
  const widget = captchaWidgets.get(form);
  return widget === undefined ? null : window.grecaptcha.getResponse(widget) || null;
}

function resetCaptcha(form) {
  const widget = captchaWidgets.get(form);
  if (widget !== undefined) window.grecaptcha.reset(widget);
}

// Desativa o botão enquanto o pedido está em andamento e mostra erros de rede no formulário.
function handleSubmit(form, action) {
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (captchaWidgets.has(form) && !captchaToken(form)) {
      showMessage(form, "Marque a caixa \"Não sou um robô\" para continuar.");
      return;
    }
    const button = form.querySelector(".submit-button");
    button.disabled = true;
    try {
      await action(form);
    } catch {
      showMessage(form, "Não foi possível conectar ao servidor.");
    } finally {
      button.disabled = false;
      // Cada resposta do reCAPTCHA vale uma vez: libera um novo desafio para a próxima tentativa.
      resetCaptcha(form);
    }
  });
}

function passwordsMatch(form) {
  if (form.password.value === form.confirm.value) return true;
  showMessage(form, "As senhas não conferem.");
  form.confirm.focus();
  return false;
}

document.querySelectorAll("[data-go]").forEach((button) => {
  button.addEventListener("click", () => showView(button.dataset.go));
});

document.querySelectorAll(".password-toggle").forEach((toggle) => {
  toggle.addEventListener("click", () => {
    const input = toggle.parentElement.querySelector("input");
    const visible = input.type === "text";
    input.type = visible ? "password" : "text";
    toggle.setAttribute("aria-label", visible ? "Mostrar senha" : "Ocultar senha");
  });
});

let lockTimer;
function lockLogin(form, seconds) {
  const button = form.querySelector(".submit-button");
  const until = Date.now() + seconds * 1000;
  clearInterval(lockTimer);
  const tick = () => {
    const remaining = Math.ceil((until - Date.now()) / 1000);
    if (remaining <= 0) {
      clearInterval(lockTimer);
      button.disabled = false;
      showMessage(form, "Você já pode tentar entrar novamente.", "info");
      return;
    }
    button.disabled = true;
    const min = String(Math.floor(remaining / 60)).padStart(2, "0");
    const sec = String(remaining % 60).padStart(2, "0");
    showMessage(form, `Muitas tentativas incorretas. Tente novamente em ${min}:${sec}.`);
  };
  tick();
  lockTimer = setInterval(tick, 1000);
}

handleSubmit(document.querySelector("#login-form"), async (form) => {
  const result = await postJson("/api/auth/login", {
    email: form.email.value,
    password: form.password.value,
    remember: form.remember.checked,
    captcha: captchaToken(form),
  });
  if (result.ok) {
    window.location.href = "/";
    return;
  }
  form.password.value = "";
  if (result.status === 429) {
    // O botão só é liberado pela contagem regressiva, não pelo "finally" do envio.
    setTimeout(() => lockLogin(form, result.data.retry_after || 900));
    return;
  }
  showMessage(form, result.detail);
});

handleSubmit(document.querySelector("#signup-form"), async (form) => {
  if (!passwordsMatch(form)) return;
  if (!form.accept_privacy.checked) {
    showMessage(form, "Para criar a conta, leia e aceite o Aviso de Privacidade.");
    return;
  }
  const result = await postJson("/api/auth/signup", {
    name: form.name.value,
    email: form.email.value,
    password: form.password.value,
    accept_privacy: true,
    captcha: captchaToken(form),
  });
  if (result.ok) window.location.href = "/";
  else showMessage(form, result.detail);
});

handleSubmit(document.querySelector("#forgot-form"), async (form) => {
  const result = await postJson("/api/auth/forgot", { email: form.email.value, captcha: captchaToken(form) });
  showMessage(form, result.detail, result.ok ? "success" : "error");
  if (result.ok) form.reset();
});

handleSubmit(document.querySelector("#reset-form"), async (form) => {
  if (!passwordsMatch(form)) return;
  const result = await postJson("/api/auth/reset", { token: resetToken, password: form.password.value });
  if (result.ok) window.location.replace("/");
  else showMessage(form, result.detail);
});

if (resetToken) showView("reset");
