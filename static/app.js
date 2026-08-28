document.addEventListener("submit", (event) => {
  const form = event.target;
  if (!(form instanceof HTMLFormElement)) return;

  const confirmations = {
    "confirm-archive": "Arquivar este cadastro? Os compromissos serão preservados.",
    "confirm-complete": "Marcar este compromisso como concluído?",
    "confirm-password-reset": "Redefinir a senha e encerrar as sessões anteriores desta conta?",
  };

  for (const [className, message] of Object.entries(confirmations)) {
    if (form.classList.contains(className) && !window.confirm(message)) {
      event.preventDefault();
      return;
    }
  }

  if (
    form.classList.contains("confirm-account-status") &&
    !window.confirm(form.dataset.message || "Alterar o status desta conta?")
  ) {
    event.preventDefault();
  }
});
