// Confirmaciones propias: un formulario con data-confirm="texto" pide confirmación en un
// popup de Zyra en vez del diálogo del navegador («127.0.0.1 dice…»).
// Opcionales: data-confirm-title, data-confirm-action (texto del botón) y
// data-confirm-danger (botón rojo). Sin JS el formulario se envía sin pedir confirmación.
(function () {
  if (!window.bootstrap) return;
  const L = document.documentElement.lang === 'en'
    ? { title: 'Are you sure?', ok: 'Accept', cancel: 'Cancel', close: 'Close' }
    : { title: '¿Seguro?', ok: 'Aceptar', cancel: 'Cancelar', close: 'Cerrar' };
  let modalEl = null;

  function build() {
    modalEl = document.createElement('div');
    modalEl.className = 'modal fade z-messages-modal';
    modalEl.tabIndex = -1;
    modalEl.setAttribute('aria-labelledby', 'zConfirmTitle');
    modalEl.setAttribute('aria-hidden', 'true');
    modalEl.innerHTML =
      '<div class="modal-dialog modal-dialog-centered"><div class="modal-content">' +
      '<div class="modal-header"><span class="z-messages-icon is-warning" aria-hidden="true"><i class="fa-solid fa-circle-question"></i></span>' +
      '<h2 class="modal-title h5" id="zConfirmTitle"></h2>' +
      '<button type="button" class="btn-close" data-bs-dismiss="modal"></button></div>' +
      '<div class="modal-body"><p class="mb-0" data-z-confirm-text></p></div>' +
      '<div class="modal-footer"><button type="button" class="btn btn-outline-light" data-bs-dismiss="modal"></button>' +
      '<button type="button" class="btn" data-z-confirm-ok></button></div></div></div>';
    document.body.appendChild(modalEl);
    modalEl.querySelector('.btn-close').setAttribute('aria-label', L.close);
    modalEl.querySelector('[data-bs-dismiss="modal"].btn-outline-light').textContent = L.cancel;
    return modalEl;
  }

  document.addEventListener('submit', function (event) {
    const form = event.target;
    if (!form.matches || !form.hasAttribute('data-confirm') || form.dataset.confirmed) return;
    event.preventDefault();
    const el = modalEl || build();
    el.querySelector('#zConfirmTitle').textContent = form.dataset.confirmTitle || L.title;
    el.querySelector('[data-z-confirm-text]').textContent = form.getAttribute('data-confirm');
    const ok = el.querySelector('[data-z-confirm-ok]');
    ok.textContent = form.dataset.confirmAction || L.ok;
    ok.className = 'btn ' + (form.hasAttribute('data-confirm-danger') ? 'btn-danger' : 'btn-primary');
    ok.onclick = function () {
      form.dataset.confirmed = '1';
      bootstrap.Modal.getInstance(el).hide();
      if (event.submitter) form.requestSubmit(event.submitter); else form.requestSubmit();
    };
    bootstrap.Modal.getOrCreateInstance(el).show();
  }, true);
})();
