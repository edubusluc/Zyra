/*
 * Contraseñas en los formularios.
 *
 * 1. Cada <input type="password"> recibe un botón con un ojo para mostrar u
 *    ocultar lo escrito.
 * 2. Si el campo lleva data-password-rules="<id>", la lista con ese id
 *    (core/templates/includes/password_rules.html) se marca mientras se escribe.
 *    Longitud, solo números y coincidencia se comprueban aquí; el parecido al
 *    usuario/email y las contraseñas comunes los responde el servidor
 *    (data-password-check), con las mismas reglas que el registro.
 */
(function () {
  const gettext = window.gettext || ((s) => s);

  function addToggle(input) {
    if (input.dataset.noToggle !== undefined || input.closest('.z-password')) return;
    const wrap = document.createElement('span');
    wrap.className = 'z-password';
    input.parentNode.insertBefore(wrap, input);
    wrap.appendChild(input);

    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'z-password-toggle';
    btn.setAttribute('aria-controls', input.id || '');
    const icon = document.createElement('i');
    btn.appendChild(icon);
    wrap.appendChild(btn);

    function render(visible) {
      icon.className = visible ? 'fa-regular fa-eye-slash' : 'fa-regular fa-eye';
      const label = visible ? gettext('Ocultar contraseña') : gettext('Mostrar contraseña');
      btn.setAttribute('aria-label', label);
      btn.title = label;
      btn.setAttribute('aria-pressed', visible ? 'true' : 'false');
    }
    btn.addEventListener('click', function () {
      const visible = input.type === 'password';
      input.type = visible ? 'text' : 'password';
      render(visible);
      input.focus();
    });
    // Al enviar, vuelve a ocultarla para que el navegador no la guarde como texto.
    if (input.form) input.form.addEventListener('submit', () => { input.type = 'password'; });
    render(false);
  }

  function setupRules(input) {
    const list = document.getElementById(input.dataset.passwordRules);
    if (!list || !input.form) return;
    const form = input.form;
    const confirm = form.querySelector('input[name="password2"]');
    const field = (name) => form.querySelector(`input[name="${name}"]`);
    const item = (rule) => list.querySelector(`[data-rule="${rule}"]`);
    const minLength = parseInt(item('length').dataset.minLength, 10) || 8;
    let timer = null;
    let pending = null;

    function mark(rule, ok) {
      const li = item(rule);
      if (!li) return;
      li.classList.toggle('is-ok', ok === true);
      li.classList.toggle('is-bad', ok === false);
    }

    function checkServer(value) {
      if (pending) pending.abort();
      if (!value || !window.fetch) { mark('similar', null); mark('common', null); return; }
      pending = new AbortController();
      const data = new FormData();
      data.append('password', value);
      // Sin campos de usuario/email (cambio de contraseña), los de la cuenta van en la lista.
      ['username', 'email'].forEach((name) => {
        const value = field(name) ? field(name).value : list.dataset[name];
        if (value) data.append(name, value);
      });
      fetch(list.dataset.passwordCheck, {
        method: 'POST',
        body: data,
        headers: { 'X-CSRFToken': field('csrfmiddlewaretoken').value },
        signal: pending.signal,
      })
        .then((r) => (r.ok ? r.json() : null))
        .then((res) => { if (res) { mark('similar', res.similar); mark('common', res.common); } })
        .catch(() => {});
    }

    function update() {
      const value = input.value;
      mark('length', value ? value.length >= minLength : null);
      mark('numeric', value ? !/^\d+$/.test(value) : null);
      if (confirm) mark('match', value && confirm.value ? value === confirm.value : null);
      clearTimeout(timer);
      timer = setTimeout(() => checkServer(value), 300);
    }

    input.addEventListener('input', update);
    if (confirm) confirm.addEventListener('input', update);
    ['username', 'email'].forEach((name) => { if (field(name)) field(name).addEventListener('input', update); });
    list.classList.add('is-live');
    if (input.value) update();
  }

  document.querySelectorAll('input[type="password"]').forEach(addToggle);
  document.querySelectorAll('input[data-password-rules]').forEach(setupRules);
})();
