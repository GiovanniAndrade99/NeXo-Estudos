(() => {
  const banner = document.querySelector("#cookie-notice");
  const dialog = document.querySelector("#privacy-dialog");
  if (!dialog) return;

  const consentKey = "nexo-cookie-notice-seen-v1";
  fetch("/api/privacidade/contato")
    .then((response) => response.ok ? response.json() : null)
    .then((data) => {
      const email = data?.email;
      if (!email || !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) return;
      const link = document.querySelector("#privacy-contact");
      if (!link) return;
      link.href = `mailto:${email}`;
      link.textContent = email;
      link.parentElement.hidden = false;
    })
    .catch(() => {});

  try {
    if (banner && localStorage.getItem(consentKey) !== "1") banner.hidden = false;
  } catch {
    if (banner) banner.hidden = false;
  }

  document.querySelectorAll("[data-privacy-open]").forEach((button) => {
    button.addEventListener("click", () => {
      if (dialog.showModal) dialog.showModal();
      else dialog.setAttribute("open", "");
    });
  });

  document.querySelectorAll("[data-cookie-dismiss]").forEach((button) => {
    button.addEventListener("click", () => {
      if (banner) banner.hidden = true;
      try { localStorage.setItem(consentKey, "1"); } catch { /* Aviso permanece fechado nesta visita. */ }
    });
  });

  document.querySelectorAll("[data-dialog-close]").forEach((button) => {
    button.addEventListener("click", () => dialog.close?.());
  });

  if (new URLSearchParams(location.search).has("privacidade")) {
    if (dialog.showModal) dialog.showModal();
    else dialog.setAttribute("open", "");
  }
})();
