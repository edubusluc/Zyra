// Protección contra el doble clic en TODOS los formularios POST de la web (también en el
// back-office). Tras un envío válido el formulario queda bloqueado: el botón pulsado se
// deshabilita y muestra un indicador con un texto de la acción, y un segundo envío se descarta.
//
// Texto: data-loading-text del botón pulsado, o del formulario, o «Procesando…».
// Opciones del formulario: data-no-submit-lock (sin protección).
// Opciones del botón: data-submit-download (la respuesta es una descarga y la página no cambia:
// se desbloquea a los pocos segundos).
// Para el JavaScript propio de una página: ZyraSubmitLock.lock(form, botón, texto) y .unlock(form).
(function () {
  'use strict';

  const RELEASE_MS = 60000; // red caída o servidor sin responder: se puede volver a intentar
  const DOWNLOAD_MS = 4000;
  const locked = new Set();
  let status = null;

  const text = (s) => (typeof globalThis.gettext === 'function' ? globalThis.gettext(s) : s);

  function announce(message) {
    if (!status) {
      status = document.createElement('div');
      status.className = 'visually-hidden';
      status.setAttribute('role', 'status');
      status.setAttribute('aria-live', 'polite');
      document.body.appendChild(status);
    }
    status.textContent = message;
  }

  function isLockable(form) {
    return form instanceof HTMLFormElement
      && form.method.toLowerCase() === 'post'
      && !form.hasAttribute('data-no-submit-lock')
      && (!form.target || form.target === '_self');
  }

  function submitControls(form) {
    return Array.from(form.elements).filter((el) => (el.tagName === 'BUTTON' && el.type === 'submit')
      || (el.tagName === 'INPUT' && (el.type === 'submit' || el.type === 'image')));
  }

  function lock(form, submitter, message) {
    if (form._zLock) return;
    const controls = submitControls(form);
    const main = submitter && controls.includes(submitter) ? submitter : controls[0];
    const label = message || (main && main.dataset.loadingText) || form.dataset.loadingText || text('Procesando…');
    const state = { saved: [], timer: 0 };
    form._zLock = state;
    locked.add(form);
    form.setAttribute('aria-busy', 'true');
    controls.forEach((el) => state.saved.push({ el, disabled: el.disabled, html: el.innerHTML, value: el.value }));
    announce(label);
    if (main && main.tagName === 'BUTTON') {
      // Ancho fijo para que el botón no «salte» al cambiar el texto.
      state.saved.find((s) => s.el === main).minWidth = main.style.minWidth;
      main.style.minWidth = main.offsetWidth + 'px';
      main.setAttribute('aria-busy', 'true');
      main.innerHTML = '<span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span><span></span>';
      main.lastElementChild.textContent = label;
    }
    // Se deshabilita tras despachar el envío: un botón deshabilitado dentro del evento lo cancelaría
    // y el navegador no enviaría su nombre/valor.
    setTimeout(() => { if (form._zLock === state) controls.forEach((el) => { el.disabled = true; }); }, 0);
    const ms = main && main.hasAttribute('data-submit-download') ? DOWNLOAD_MS : RELEASE_MS;
    state.timer = setTimeout(() => unlock(form), ms);
  }

  function unlock(form) {
    const state = form._zLock;
    if (!state) return;
    clearTimeout(state.timer);
    state.saved.forEach((s) => {
      s.el.disabled = s.disabled;
      s.el.removeAttribute('aria-busy');
      if (s.el.tagName === 'BUTTON') {
        s.el.innerHTML = s.html;
        if (s.minWidth !== undefined) s.el.style.minWidth = s.minWidth;
      }
    });
    form.removeAttribute('aria-busy');
    // Un formulario con confirmación (confirm-modal.js) vuelve a pedirla.
    delete form.dataset.confirmed;
    delete form._zLock;
    locked.delete(form);
    if (!locked.size && status) status.textContent = '';
  }

  // Fase de burbuja: si otro script (validación, asistente de pasos, confirmación) ya frenó el
  // envío, no se bloquea nada; el navegador no lanza «submit» si su validación falla.
  document.addEventListener('submit', (event) => {
    const form = event.target;
    if (!isLockable(form)) return;
    if (form._zLock) {
      event.preventDefault();
      return;
    }
    if (event.defaultPrevented) return;
    lock(form, event.submitter);
    // Un script posterior pudo cancelar el envío: se desbloquea.
    setTimeout(() => { if (event.defaultPrevented) unlock(form); }, 0);
  });

  // Al volver con «Atrás» la página puede restaurarse de la caché con los botones bloqueados.
  window.addEventListener('pageshow', (event) => {
    if (event.persisted) Array.from(locked).forEach(unlock);
  });

  globalThis.ZyraSubmitLock = { lock, unlock };
}());
