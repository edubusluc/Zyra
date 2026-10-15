// Registro de club por pasos (Tu club → Tu cuenta → Tu jugador).
// El formulario es uno solo: los pasos son secciones que se muestran de una en una, así que lo
// escrito se conserva al ir y volver y, sin JavaScript, se ve todo seguido y se envía igual.
// Validación: al salir de cada campo, al pulsar «Siguiente» y al enviar; con errores se muestra
// un resumen («Faltan 3 campos») y el foco va al primer campo erróneo.
(function () {
  const form = document.querySelector('form[data-wizard]');
  if (!form) return;
  const DRAFT_KEY = 'zyra.register.draft';
  // Campos que se guardan como borrador (nunca contraseñas)
  const DRAFT_FIELDS = /^(name|location|gender|country|division|username|email|player-name|player-last_name)$/;

  function init() {
    const forms = window.ZyraForms;
    const steps = Array.from(form.querySelectorAll('[data-wizard-step]'));
    const progress = form.querySelector('[data-wizard-progress]');
    const summary = form.querySelector('[data-wizard-summary]');
    let current = 0;
    let serverErrors = form.querySelectorAll('.errorlist:not([data-js-error])').length;

    form.classList.add('is-wizard');
    steps.forEach((step) => step.querySelectorAll('[data-wizard-next], [data-wizard-back]').forEach((b) => { b.hidden = false; }));

    // --- Validación ---------------------------------------------------------------------
    function fieldsOf(scope) {
      return Array.from(scope.querySelectorAll('input, select, textarea')).filter((el) => {
        if (el.type === 'hidden' || el.type === 'radio' || el.type === 'checkbox' || el.type === 'submit') return false;
        return !el.closest('[hidden]') && el.name !== 'csrfmiddlewaretoken';
      });
    }
    function controlFor(el) {
      // El botón del desplegable propio hace de campo visible
      const wrap = el.closest('.z-select');
      return wrap ? wrap.querySelector('.z-select-trigger') : el;
    }
    function messageFor(el) {
      if (el.required && !el.value.trim()) return gettext('Este campo es obligatorio.');
      if (el.type === 'email' && el.value && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(el.value.trim())) return gettext('Escribe un email válido.');
      if (el.name === 'password2') {
        const first = form.querySelector('[name=password1]');
        if (first && el.value && first.value !== el.value) return gettext('Las contraseñas no coinciden.');
      }
      return '';
    }
    function check(el) {
      const message = messageFor(el);
      forms.setError(controlFor(el), message);
      return message;
    }
    function validate(scope) {
      const bad = [];
      let required = 0;
      fieldsOf(scope).forEach((el) => {
        const message = check(el);
        if (message) {
          bad.push(controlFor(el));
          if (message === gettext('Este campo es obligatorio.')) required += 1;
        }
      });
      return { bad, allRequired: bad.length === required };
    }
    function showSummary(result) {
      const n = result.bad.length;
      summary.hidden = n === 0;
      if (!n) { summary.textContent = ''; return; }
      summary.textContent = result.allRequired
        ? interpolate(ngettext('Falta %s campo', 'Faltan %s campos', n), [n])
        : interpolate(ngettext('Revisa %s campo', 'Revisa %s campos', n), [n]);
    }

    // --- Pasos --------------------------------------------------------------------------
    function renderProgress() {
      progress.hidden = false;
      progress.textContent = '';
      const label = document.createElement('p');
      label.className = 'z-wizard-count';
      label.textContent = interpolate(gettext('Paso %s de %s'), [current + 1, steps.length]) + ' · ' + steps[current].dataset.stepTitle;
      const list = document.createElement('ol');
      steps.forEach((step, i) => {
        const li = document.createElement('li');
        li.className = i < current ? 'is-done' : i === current ? 'is-active' : '';
        if (i === current) li.setAttribute('aria-current', 'step');
        li.innerHTML = '<span class="z-wizard-dot" aria-hidden="true"></span>';
        const text = document.createElement('span');
        text.className = 'z-wizard-title';
        text.textContent = step.dataset.stepTitle;
        li.appendChild(text);
        list.appendChild(li);
      });
      progress.append(label, list);
    }
    function go(index, focusTop) {
      current = Math.max(0, Math.min(steps.length - 1, index));
      steps.forEach((step, i) => { step.hidden = i !== current; });
      renderProgress();
      if (focusTop) {
        const heading = steps[current].querySelector('h2');
        if (heading) { heading.tabIndex = -1; heading.focus({ preventScroll: true }); }
        form.closest('.z-auth-card').scrollIntoView({ block: 'start', behavior: 'auto' });
        window.scrollBy(0, -80);
      }
    }
    function next() {
      const result = validate(steps[current]);
      showSummary(result);
      if (result.bad.length) { forms.focusControl(result.bad[0]); return; }
      go(current + 1, true);
    }

    form.addEventListener('click', (e) => {
      if (e.target.closest('[data-wizard-next]')) next();
      else if (e.target.closest('[data-wizard-back]')) { summary.hidden = true; go(current - 1, true); }
    });
    // Intro en un campo avanza de paso; solo el último paso envía el formulario
    form.addEventListener('keydown', (e) => {
      if (e.key !== 'Enter' || e.target.tagName === 'TEXTAREA' || e.target.tagName === 'BUTTON' || current === steps.length - 1) return;
      e.preventDefault();
      next();
    });
    form.addEventListener('submit', (e) => {
      for (let i = 0; i < steps.length; i += 1) {
        const wasHidden = steps[i].hidden;
        steps[i].hidden = false;
        const result = validate(steps[i]);
        if (result.bad.length) {
          e.preventDefault();
          go(i, false);
          showSummary(result);
          forms.focusControl(result.bad[0]);
          return;
        }
        steps[i].hidden = wasHidden;
      }
      try { sessionStorage.removeItem(DRAFT_KEY); } catch (err) { /* sin almacenamiento */ }
    });

    // Validación al salir de un campo y al corregirlo
    function nativeOf(target) {
      if (target.classList && target.classList.contains('z-select-trigger')) return target.closest('.z-select').querySelector('select');
      return target.matches && target.matches('input, select, textarea') ? target : null;
    }
    form.addEventListener('focusout', (e) => {
      const el = nativeOf(e.target);
      if (el && el.type !== 'radio' && fieldsOf(form).indexOf(el) !== -1 && (el.value || el.dataset.touched)) check(el);
      if (el) el.dataset.touched = '1';
    });
    form.addEventListener('input', (e) => {
      const el = nativeOf(e.target);
      if (el && controlFor(el).getAttribute('aria-invalid') === 'true') check(el);
      saveDraft();
    });
    form.addEventListener('change', (e) => {
      const el = nativeOf(e.target);
      if (el && el.tagName === 'SELECT') check(el);
      saveDraft();
    });

    // --- Borrador entre recargas (sin contraseñas) ----------------------------------------
    function saveDraft() {
      const data = {};
      Array.from(form.elements).forEach((el) => { if (el.name && DRAFT_FIELDS.test(el.name) && el.type !== 'password') data[el.name] = el.value; });
      try { sessionStorage.setItem(DRAFT_KEY, JSON.stringify(data)); } catch (err) { /* sin almacenamiento */ }
    }
    function restoreDraft() {
      if (serverErrors) return;
      let data = null;
      try { data = JSON.parse(sessionStorage.getItem(DRAFT_KEY) || 'null'); } catch (err) { data = null; }
      if (!data) return;
      Object.keys(data).forEach((name) => {
        const el = form.elements[name];
        if (el && el.type !== 'password' && data[name] !== '' && !(el.type === 'select-one' && el.value && name !== 'division')) {
          el.value = data[name];
          if (el.tagName === 'SELECT') el.dispatchEvent(new Event('change', { bubbles: true }));
        }
      });
    }
    restoreDraft();

    // --- Arranque -----------------------------------------------------------------------
    go(0, false);
    if (serverErrors) {
      const firstBad = form.querySelector('.errorlist:not([data-js-error])');
      const stepIndex = Math.max(0, steps.findIndex((s) => s.contains(firstBad)));
      go(stepIndex, false);
      const bad = [];
      form.querySelectorAll('[aria-invalid=true]').forEach((c) => bad.push(c));
      showSummary({ bad, allRequired: false });
      const target = steps[stepIndex].querySelector('[aria-invalid=true]');
      if (target) forms.focusControl(target);
    }
  }

  // Tras DOMContentLoaded: los desplegables propios y form-errors.js ya están listos
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => setTimeout(init, 20));
  else setTimeout(init, 20);
})();
