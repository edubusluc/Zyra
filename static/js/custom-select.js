/*
 * Desplegable propio para todos los <select> de la web.
 *
 * Se aplica solo a cada <select> sencillo (sin "multiple") al cargar la página; no hace falta
 * marcar nada. Quedan fuera los que ya tienen otro selector (data-picker) y los que lleven
 * data-native.
 *
 * El <select> original sigue en el DOM, oculto de forma visual, y es la fuente de verdad: se
 * envía con el formulario, dispara "change" al elegir y otros scripts pueden seguir cambiando su
 * value, selectedIndex, disabled u opciones (el botón se sincroniza solo). El botón copia las
 * clases del <select> para conservar su tamaño y aspecto, y hereda su id, su aria-label y los
 * <label for> que lo apuntaban.
 *
 * Teclado: Enter, Espacio o flechas abren; flechas, Inicio y Fin se mueven; Enter/Espacio eligen;
 * Esc cierra; escribir salta a la opción que empieza por esas letras; Tab cierra.
 */
(function () {
  const normalize = (text) => text.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
  const MARGIN = 8;
  let uid = 0;
  let openInstance = null;

  function enhance(select) {
    if (select.dataset.selectReady) return;
    select.dataset.selectReady = '1';
    const id = 'z-select-' + (++uid);

    const trigger = document.createElement('button');
    trigger.type = 'button';
    trigger.className = select.className + ' z-select-trigger';
    trigger.setAttribute('role', 'combobox');
    trigger.setAttribute('aria-haspopup', 'listbox');
    trigger.setAttribute('aria-expanded', 'false');
    trigger.setAttribute('aria-controls', id + '-list');
    if (select.id) {
      trigger.id = select.id;
      select.removeAttribute('id');
    }
    ['aria-label', 'aria-labelledby', 'aria-describedby'].forEach((name) => {
      if (select.hasAttribute(name)) trigger.setAttribute(name, select.getAttribute(name));
    });
    const text = document.createElement('span');
    text.className = 'z-select-text';
    trigger.appendChild(text);

    const list = document.createElement('ul');
    list.className = 'z-select-list';
    list.id = id + '-list';
    list.setAttribute('role', 'listbox');
    list.hidden = true;
    if (select.hasAttribute('aria-label')) list.setAttribute('aria-label', select.getAttribute('aria-label'));

    const wrap = document.createElement('div');
    wrap.className = 'z-select';
    select.parentNode.insertBefore(wrap, select);
    wrap.append(trigger, list, select);
    select.classList.add('z-select-native');
    select.tabIndex = -1;
    select.setAttribute('aria-hidden', 'true');

    let items = [];
    let active = -1;
    let typed = '';
    let typedTimer = null;

    // Pinta el texto del botón con la opción elegida
    function syncTrigger() {
      const option = select.options[select.selectedIndex];
      const label = option ? option.textContent.trim() : '';
      text.textContent = label || ' ';
      trigger.classList.toggle('is-placeholder', !option || option.value === '');
      trigger.disabled = select.disabled;
    }

    function buildList() {
      list.textContent = '';
      items = [];
      let group = null;
      Array.from(select.children).forEach((node) => {
        if (node.tagName === 'OPTGROUP') {
          const header = document.createElement('li');
          header.className = 'z-select-group';
          header.setAttribute('role', 'presentation');
          header.textContent = node.label;
          list.appendChild(header);
          group = node;
          Array.from(node.children).forEach(addOption);
          group = null;
        } else {
          addOption(node);
        }
      });
      function addOption(option) {
        if (option.tagName !== 'OPTION') return;
        const li = document.createElement('li');
        li.className = 'z-select-option';
        li.id = id + '-o' + items.length;
        li.setAttribute('role', 'option');
        li.textContent = option.textContent.trim() || ' ';
        const disabled = option.disabled || (group && group.disabled);
        if (disabled) {
          li.classList.add('is-disabled');
          li.setAttribute('aria-disabled', 'true');
        }
        if (option.value === '') li.classList.add('is-empty');
        li.setAttribute('aria-selected', option.selected ? 'true' : 'false');
        li.dataset.index = String(option.index);
        list.appendChild(li);
        items.push({ el: li, option, disabled, key: normalize(li.textContent) });
      }
    }

    function setActive(index, scroll) {
      if (active >= 0 && items[active]) items[active].el.classList.remove('is-active');
      active = index;
      if (active >= 0 && items[active]) {
        items[active].el.classList.add('is-active');
        trigger.setAttribute('aria-activedescendant', items[active].el.id);
        if (scroll !== false) items[active].el.scrollIntoView({ block: 'nearest' });
      } else {
        trigger.removeAttribute('aria-activedescendant');
      }
    }

    // Siguiente opción activable desde "from" en la dirección "step" (sin dar la vuelta)
    function nextEnabled(from, step) {
      for (let i = from + step; i >= 0 && i < items.length; i += step) {
        if (!items[i].disabled) return i;
      }
      return from;
    }

    // Coloca la lista bajo el botón, o encima si abajo no cabe
    function place() {
      const rect = trigger.getBoundingClientRect();
      const below = window.innerHeight - rect.bottom - MARGIN;
      const above = rect.top - MARGIN;
      const flip = below < 180 && above > below;
      const room = Math.max(120, Math.min(320, flip ? above : below));
      list.style.maxHeight = room - 6 + 'px';
      const width = Math.max(rect.width, 160);
      const left = Math.min(Math.max(MARGIN, rect.left), Math.max(MARGIN, window.innerWidth - width - MARGIN));
      list.style.minWidth = width + 'px';
      list.style.left = left + 'px';
      if (flip) {
        list.style.top = 'auto';
        list.style.bottom = window.innerHeight - rect.top + 6 + 'px';
      } else {
        list.style.bottom = 'auto';
        list.style.top = rect.bottom + 6 + 'px';
      }
    }

    function open() {
      if (select.disabled || !list.hidden) return;
      if (openInstance && openInstance !== api) openInstance.close();
      buildList();
      // La lista cuelga del body: dentro de un panel con filter, transform o backdrop-filter
      // el "fixed" se mediría contra ese panel y no contra la ventana
      document.body.appendChild(list);
      list.hidden = false;
      wrap.classList.add('is-open');
      trigger.setAttribute('aria-expanded', 'true');
      place();
      const selected = items.findIndex((item) => item.option.selected && !item.disabled);
      setActive(selected >= 0 ? selected : nextEnabled(-1, 1));
      openInstance = api;
    }

    function close() {
      if (list.hidden) return;
      list.hidden = true;
      wrap.appendChild(list);
      wrap.classList.remove('is-open');
      trigger.setAttribute('aria-expanded', 'false');
      trigger.removeAttribute('aria-activedescendant');
      if (openInstance === api) openInstance = null;
    }

    function choose(index) {
      const item = items[index];
      if (!item || item.disabled) return;
      const changed = select.selectedIndex !== item.option.index;
      select.selectedIndex = item.option.index;
      syncTrigger();
      close();
      trigger.focus();
      if (changed) {
        select.dispatchEvent(new Event('input', { bubbles: true }));
        select.dispatchEvent(new Event('change', { bubbles: true }));
      }
    }

    function typeAhead(char) {
      typed += normalize(char);
      clearTimeout(typedTimer);
      typedTimer = setTimeout(() => { typed = ''; }, 600);
      const start = typed.length === 1 ? active + 1 : active;
      for (let n = 0; n < items.length; n++) {
        const i = (start + n) % items.length;
        if (!items[i].disabled && items[i].key.startsWith(typed)) { setActive(i); return true; }
      }
      return false;
    }

    trigger.addEventListener('click', () => (list.hidden ? open() : close()));
    trigger.addEventListener('keydown', (e) => {
      const isOpen = !list.hidden;
      switch (e.key) {
        case 'ArrowDown':
        case 'ArrowUp':
          e.preventDefault();
          if (!isOpen) { open(); break; }
          setActive(nextEnabled(active, e.key === 'ArrowDown' ? 1 : -1));
          break;
        case 'Home':
        case 'End':
          if (!isOpen) break;
          e.preventDefault();
          setActive(e.key === 'Home' ? nextEnabled(-1, 1) : nextEnabled(items.length, -1));
          break;
        case 'Enter':
        case ' ':
          if (isOpen) { e.preventDefault(); choose(active); }
          else if (e.key === ' ') { e.preventDefault(); open(); }
          break;
        case 'Escape':
          if (isOpen) { e.preventDefault(); e.stopPropagation(); close(); }
          break;
        case 'Tab':
          close();
          break;
        default:
          if (e.key.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey) {
            if (!isOpen) open();
            if (typeAhead(e.key) || e.key === ' ') e.preventDefault();
          }
      }
    });
    // Elegir con el ratón/dedo sin quitar el foco del botón
    list.addEventListener('mousedown', (e) => e.preventDefault());
    list.addEventListener('click', (e) => {
      const li = e.target.closest('.z-select-option');
      if (li) choose(items.findIndex((item) => item.el === li));
    });
    list.addEventListener('mousemove', (e) => {
      const li = e.target.closest('.z-select-option');
      const i = li ? items.findIndex((item) => item.el === li) : -1;
      if (i >= 0 && i !== active && !items[i].disabled) setActive(i, false);
    });
    trigger.addEventListener('blur', () => { setTimeout(() => { if (!api.contains(document.activeElement)) close(); }, 0); });

    // Sincronización con cambios hechos desde fuera (otros scripts, reset del formulario)
    select.addEventListener('change', syncTrigger);
    select.addEventListener('invalid', () => trigger.focus());
    if (select.form) select.form.addEventListener('reset', () => setTimeout(syncTrigger, 0));
    window.addEventListener('pageshow', syncTrigger);
    new MutationObserver(() => { syncTrigger(); if (!list.hidden) { buildList(); } })
      .observe(select, { childList: true, subtree: true, attributes: true, attributeFilter: ['disabled', 'selected'] });
    // value y selectedIndex asignados por código no disparan eventos: se interceptan
    ['value', 'selectedIndex'].forEach((prop) => {
      const native = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, prop);
      Object.defineProperty(select, prop, {
        configurable: true,
        get() { return native.get.call(this); },
        set(v) { native.set.call(this, v); syncTrigger(); },
      });
    });

    const api = { close, contains: (node) => wrap.contains(node) || list.contains(node), reposition: () => { if (!list.hidden) place(); } };
    syncTrigger();
  }

  document.addEventListener('mousedown', (e) => {
    if (openInstance && !openInstance.contains(e.target)) openInstance.close();
  });
  document.addEventListener('touchstart', (e) => {
    if (openInstance && !openInstance.contains(e.target)) openInstance.close();
  }, { passive: true });
  window.addEventListener('resize', () => { if (openInstance) openInstance.reposition(); });
  // La lista es fija: al desplazar la página se recoloca; si el desplazamiento es dentro de ella, se deja
  window.addEventListener('scroll', (e) => {
    if (!openInstance) return;
    if (e.target instanceof Element && e.target.classList.contains('z-select-list')) return;
    openInstance.reposition();
  }, true);

  function init() {
    document.querySelectorAll('select:not([multiple]):not([data-picker]):not([data-native])').forEach(enhance);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
