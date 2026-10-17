// Formularios con data-submit-lock: al enviarse, el botón se bloquea y muestra data-loading-text
// con un indicador de carga, para que un doble clic no envíe el registro dos veces.
(function () {
  'use strict';

  function unlock(form) {
    delete form.dataset.submitting;
    form.querySelectorAll('[data-original-html]').forEach((button) => {
      button.innerHTML = button.dataset.originalHtml;
      button.disabled = false;
      button.removeAttribute('aria-busy');
      delete button.dataset.originalHtml;
    });
  }

  document.addEventListener('submit', (event) => {
    const form = event.target;
    if (!(form instanceof HTMLFormElement) || !form.hasAttribute('data-submit-lock')) return;
    // Otro script (validación, asistente de pasos) ya frenó el envío: no se bloquea nada.
    if (event.defaultPrevented) return;
    if (form.dataset.submitting) {
      event.preventDefault();
      return;
    }
    form.dataset.submitting = '1';
    const button = form.querySelector('button[type=submit]');
    if (!button) return;
    const text = form.dataset.loadingText || '';
    button.dataset.originalHtml = button.innerHTML;
    button.setAttribute('aria-busy', 'true');
    button.innerHTML = '<span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>'
      + '<span></span>';
    button.lastElementChild.textContent = text;
    // Se deshabilita tras despachar el envío; un botón deshabilitado dentro del evento lo cancelaría.
    setTimeout(() => { button.disabled = true; }, 0);
  });

  // Al volver con «Atrás» la página puede restaurarse con el botón bloqueado.
  window.addEventListener('pageshow', (event) => {
    if (event.persisted) document.querySelectorAll('form[data-submit-lock]').forEach(unlock);
  });
}());
