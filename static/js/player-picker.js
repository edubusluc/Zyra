/*
 * Selector con búsqueda para listas largas de jugadores.
 *
 * Uso: <select data-picker data-placeholder="Buscar jugador..."> ... </select>
 * El <select> original se oculta pero sigue siendo el que se envía en el
 * formulario, y recibe un evento "change" al elegir una opción (así siguen
 * funcionando los onchange="this.form.submit()" existentes).
 *
 * Las opciones se leen del <select> cada vez que se abre la lista, así que las que
 * otro script desactive (disabled) no aparecen. Opcional:
 *   data-meta en un <option>: texto secundario a la derecha (p. ej. los puntos SNP).
 *   data-picker-toggle en el <select>: botón de flecha para desplegar todas las opciones.
 *   data-picker-clearable en el <select>: borrar el texto y salir deja el selector vacío.
 */
(function () {
  const normalize = (text) => text.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().trim();

  // Tras elegir una opción la página va a recargarse: durante un instante se descartan los clics
  // (el emulado del móvil o un doble toque) para que no caigan sobre un enlace de debajo, p. ej.
  // un partido de la tabla de estadísticas.
  function swallowStrayClicks() {
    const stop = (e) => { e.preventDefault(); e.stopPropagation(); };
    document.addEventListener('click', stop, true);
    setTimeout(() => document.removeEventListener('click', stop, true), 600);
  }

  function enhance(select) {
    if (select.dataset.pickerReady) return;
    select.dataset.pickerReady = '1';

    // Opciones elegibles en este momento (sin la vacía ni las desactivadas).
    const readOptions = () => Array.from(select.options)
      .filter((o) => o.value !== '' && !o.disabled)
      .map((o) => ({ value: o.value, label: o.textContent.trim(), key: normalize(o.textContent), meta: o.dataset.meta || '' }));
    let options = readOptions();

    const wrap = document.createElement('div');
    wrap.className = 'z-picker';
    const input = document.createElement('input');
    input.type = 'text';
    input.className = 'z-picker-input';
    input.autocomplete = 'off';
    input.spellcheck = false;
    input.placeholder = select.dataset.placeholder || gettext('Buscar...');
    input.setAttribute('role', 'combobox');
    input.setAttribute('aria-expanded', 'false');
    input.setAttribute('aria-autocomplete', 'list');
    if (select.id) {
      // El <label for="..."> apunta ahora al buscador
      input.id = select.id + '-search';
      document.querySelectorAll(`label[for="${select.id}"]`).forEach((l) => l.setAttribute('for', input.id));
    }
    const list = document.createElement('ul');
    list.className = 'z-picker-list';
    list.setAttribute('role', 'listbox');
    list.id = (select.id || 'picker') + '-list-' + Math.random().toString(36).slice(2, 7);
    input.setAttribute('aria-controls', list.id);

    select.hidden = true;
    select.tabIndex = -1;
    select.parentNode.insertBefore(wrap, select);
    wrap.append(input, list, select);

    if ('pickerToggle' in select.dataset) {
      // Flecha para ver todas las opciones disponibles sin escribir
      const toggle = document.createElement('button');
      toggle.type = 'button';
      toggle.className = 'z-picker-toggle';
      toggle.tabIndex = -1;
      toggle.setAttribute('aria-label', gettext('Ver todos'));
      toggle.innerHTML = '<i class="fa-solid fa-chevron-down" aria-hidden="true"></i>';
      // mousedown solo evita perder el foco; la acción va en click (ver nota en la opción)
      toggle.addEventListener('mousedown', (e) => e.preventDefault());
      toggle.addEventListener('click', () => {
        if (wrap.classList.contains('is-open')) { close(); input.blur(); } else { input.focus(); }
      });
      wrap.classList.add('has-toggle');
      wrap.appendChild(toggle);
    }

    let active = -1;
    let shown = [];
    const current = () => {
      const o = Array.from(select.options).find((opt) => opt.value !== '' && opt.value === select.value);
      return o ? { value: o.value, label: o.textContent.trim() } : null;
    };
    const showSelected = () => { input.value = current() ? current().label : ''; };

    function render(query) {
      const q = normalize(query || '');
      options = readOptions();
      shown = q ? options.filter((o) => o.key.includes(q)) : options;
      list.innerHTML = '';
      if (!shown.length) {
        const li = document.createElement('li');
        li.className = 'z-picker-empty';
        li.textContent = gettext('Sin resultados');
        list.appendChild(li);
      }
      shown.forEach((o, i) => {
        const li = document.createElement('li');
        li.className = 'z-picker-option';
        li.id = `${list.id}-${i}`;
        li.setAttribute('role', 'option');
        li.setAttribute('aria-selected', String(o.value === select.value));
        li.textContent = o.label;
        if (o.meta) {
          const meta = document.createElement('small');
          meta.className = 'z-picker-meta';
          meta.textContent = o.meta;
          li.appendChild(meta);
        }
        // Elegir en «click», no en «mousedown»: en el móvil la lista se cierra al soltar el dedo
        // y el click emulado caía sobre el enlace que quedaba debajo (p. ej. un partido)
        li.addEventListener('mousedown', (e) => e.preventDefault());
        li.addEventListener('click', () => choose(o));
        list.appendChild(li);
      });
      setActive(shown.findIndex((o) => o.value === select.value));
    }

    function setActive(i) {
      active = i;
      list.querySelectorAll('.z-picker-option').forEach((li, n) => li.classList.toggle('is-active', n === i));
      const li = list.querySelector('.is-active');
      if (li) { input.setAttribute('aria-activedescendant', li.id); li.scrollIntoView({ block: 'nearest' }); }
      else input.removeAttribute('aria-activedescendant');
    }

    function open() { wrap.classList.add('is-open'); input.setAttribute('aria-expanded', 'true'); }
    function close() { wrap.classList.remove('is-open'); input.setAttribute('aria-expanded', 'false'); showSelected(); }

    function choose(o) {
      const changed = select.value !== o.value;
      select.value = o.value;
      close();
      input.blur();
      if (changed) {
        swallowStrayClicks();
        select.dispatchEvent(new Event('change', { bubbles: true }));
      }
    }

    input.addEventListener('focus', () => { input.select(); render(''); open(); });
    input.addEventListener('input', () => { render(input.value); open(); setActive(shown.length ? 0 : -1); });
    input.addEventListener('blur', () => setTimeout(() => {
      if ('pickerClearable' in select.dataset && !input.value.trim() && select.value) {
        select.value = '';
        select.dispatchEvent(new Event('change', { bubbles: true }));
      }
      close();
    }, 120));
    input.addEventListener('keydown', (e) => {
      if (e.key === 'ArrowDown') { e.preventDefault(); open(); setActive(Math.min(active + 1, shown.length - 1)); }
      else if (e.key === 'ArrowUp') { e.preventDefault(); setActive(Math.max(active - 1, 0)); }
      else if (e.key === 'Enter') { if (wrap.classList.contains('is-open') && shown[active]) { e.preventDefault(); choose(shown[active]); } }
      else if (e.key === 'Escape') { close(); input.blur(); }
    });

    // Si otro script cambia el valor (p. ej. «Resetear» en la alineación), el buscador lo refleja
    select.addEventListener('change', () => { if (document.activeElement !== input) showSelected(); });
    showSelected();
  }

  function init() { document.querySelectorAll('select[data-picker]').forEach(enhance); }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
