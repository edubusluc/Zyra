// Errores de formulario accesibles en todas las páginas.
// - Cada campo con error recibe aria-invalid y aria-describedby apuntando a su mensaje.
// - Al abrir una página con errores del servidor, el foco y el scroll van al primer campo erróneo.
// - Expone window.ZyraForms para que otros scripts (p. ej. el registro por pasos) pongan y quiten
//   errores con el mismo marcado.
(function () {
  const CONTROL = '.z-select-trigger, select, textarea, input:not([type=hidden]):not([type=radio]):not([type=checkbox]):not([type=submit])';
  let uid = 0;

  // Campo de un bloque de formulario (el botón del desplegable propio cuando lo hay)
  function controlOf(container) {
    return container.querySelector('.z-select-trigger') || container.querySelector(CONTROL);
  }

  function describe(control, id) {
    const ids = (control.getAttribute('aria-describedby') || '').split(/\s+/).filter(Boolean);
    if (ids.indexOf(id) === -1) ids.push(id);
    control.setAttribute('aria-describedby', ids.join(' '));
  }

  function markServerError(list) {
    const container = list.closest('p, .field, .mb-3, div');
    const control = container && controlOf(container);
    if (!control) return null;
    if (!list.id) list.id = 'z-error-' + (++uid);
    control.setAttribute('aria-invalid', 'true');
    describe(control, list.id);
    return control;
  }

  // Muestra ``message`` bajo el campo (o lo quita si va vacío)
  function setError(control, message) {
    const container = control.closest('p, .field, .mb-3') || control.parentElement;
    let box = container.querySelector('[data-js-error]');
    if (!message) {
      if (box) box.remove();
      control.removeAttribute('aria-invalid');
      const ids = (control.getAttribute('aria-describedby') || '').split(/\s+/).filter((id) => id && !/^z-error-/.test(id));
      if (ids.length) control.setAttribute('aria-describedby', ids.join(' '));
      else control.removeAttribute('aria-describedby');
      return;
    }
    if (!box) {
      box = document.createElement('span');
      box.className = 'errorlist d-block text-danger small';
      box.dataset.jsError = '';
      box.id = 'z-error-' + (++uid);
      container.appendChild(box);
    }
    box.textContent = message;
    control.setAttribute('aria-invalid', 'true');
    describe(control, box.id);
  }

  function focusControl(control) {
    if (!control) return;
    control.scrollIntoView({ block: 'center', behavior: 'auto' });
    control.focus({ preventScroll: true });
  }

  window.ZyraForms = { controlOf, setError, focusControl };

  function init() {
    let first = null;
    document.querySelectorAll('main form .errorlist').forEach((list) => {
      if (list.hasAttribute('data-js-error') || list.closest('[hidden]')) return;
      const control = markServerError(list);
      if (control && !first) first = control;
    });
    // El registro por pasos decide él mismo a qué paso va el foco
    if (first && !document.querySelector('form[data-wizard]')) focusControl(first);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => setTimeout(init, 0));
  else setTimeout(init, 0);
})();
