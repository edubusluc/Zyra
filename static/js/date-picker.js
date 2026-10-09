/*
 * Calendario propio con el estilo de Zyra.
 *
 * Uso: <input type="date" name="..." data-datepicker>
 * El <input> original pasa a ser oculto pero sigue siendo el que se envía en
 * el formulario, con el valor en formato AAAA-MM-DD. Sin JavaScript se queda
 * el selector de fecha nativo del navegador.
 */
(function () {
  // Nombres de meses y días en el idioma de la página (es/en) vía Intl
  const LANG = document.documentElement.lang || 'es';
  const monthFmt = new Intl.DateTimeFormat(LANG, { month: 'long' });
  const MONTHS = Array.from({ length: 12 }, (_, i) => monthFmt.format(new Date(2024, i, 1)));
  // 1 ene 2024 fue lunes: la semana empieza en lunes
  const weekdayFmt = new Intl.DateTimeFormat(LANG, { weekday: 'narrow' });
  const WEEKDAYS = Array.from({ length: 7 }, (_, i) => weekdayFmt.format(new Date(2024, 0, 1 + i)));
  const longFmt = new Intl.DateTimeFormat(LANG, { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' });

  const pad = (n) => String(n).padStart(2, '0');
  const toISO = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  const sameDay = (a, b) => a && b && toISO(a) === toISO(b);
  const today = () => { const d = new Date(); d.setHours(0, 0, 0, 0); return d; };
  const addDays = (d, n) => new Date(d.getFullYear(), d.getMonth(), d.getDate() + n);
  const addMonths = (d, n) => {
    // Mantiene el día si existe en el mes destino (31 ene + 1 mes -> 28/29 feb)
    const last = new Date(d.getFullYear(), d.getMonth() + n + 1, 0).getDate();
    return new Date(d.getFullYear(), d.getMonth() + n, Math.min(d.getDate(), last));
  };
  const parseISO = (value) => {
    const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value || '');
    if (!m) return null;
    const d = new Date(+m[1], +m[2] - 1, +m[3]);
    return d.getMonth() === +m[2] - 1 ? d : null;
  };
  const longLabel = (d) => longFmt.format(d);

  let counter = 0;

  function enhance(input) {
    if (input.dataset.datepickerReady) return;
    input.dataset.datepickerReady = '1';

    let selected = parseISO(input.value);
    let focused = selected || today();
    const uid = (input.id || 'date') + '-cal-' + (++counter);

    const wrap = document.createElement('div');
    wrap.className = 'z-datepicker';

    const trigger = document.createElement('button');
    trigger.type = 'button';
    trigger.className = 'z-datepicker-trigger';
    trigger.setAttribute('aria-haspopup', 'dialog');
    trigger.setAttribute('aria-expanded', 'false');
    trigger.setAttribute('aria-controls', uid);
    const triggerText = document.createElement('span');
    trigger.innerHTML = '<i class="fa-regular fa-calendar" aria-hidden="true"></i>';
    trigger.appendChild(triggerText);
    if (input.id) {
      // El <label for="..."> apunta ahora al botón
      trigger.id = input.id + '-trigger';
      document.querySelectorAll(`label[for="${input.id}"]`).forEach((l) => l.setAttribute('for', trigger.id));
    }

    const pop = document.createElement('div');
    pop.className = 'z-datepicker-pop';
    pop.id = uid;
    pop.setAttribute('role', 'dialog');
    pop.setAttribute('aria-label', gettext('Elegir fecha'));
    pop.innerHTML = `
      <div class="z-datepicker-head">
        <button type="button" class="z-datepicker-nav" data-nav="-1" aria-label="${gettext('Mes anterior')}"><i class="fa-solid fa-chevron-left" aria-hidden="true"></i></button>
        <div class="z-datepicker-title" aria-live="polite"></div>
        <button type="button" class="z-datepicker-nav" data-nav="1" aria-label="${gettext('Mes siguiente')}"><i class="fa-solid fa-chevron-right" aria-hidden="true"></i></button>
      </div>
      <div class="z-datepicker-weekdays" aria-hidden="true">${WEEKDAYS.map((w) => `<span>${w}</span>`).join('')}</div>
      <div class="z-datepicker-grid" role="grid"></div>
      <div class="z-datepicker-foot">
        <button type="button" class="z-datepicker-today">${gettext('Hoy')}</button>
        <button type="button" class="z-datepicker-clear">${gettext('Borrar')}</button>
      </div>`;
    const title = pop.querySelector('.z-datepicker-title');
    const grid = pop.querySelector('.z-datepicker-grid');

    input.parentNode.insertBefore(wrap, input);
    wrap.append(input, trigger, pop);
    const required = input.required;
    input.type = 'hidden';

    function renderTrigger() {
      const label = selected ? longLabel(selected) : '';
      triggerText.textContent = selected ? label[0].toUpperCase() + label.slice(1) : (input.dataset.placeholder || gettext('Elegir fecha'));
      trigger.classList.toggle('is-empty', !selected);
    }

    function renderGrid() {
      const year = focused.getFullYear();
      const month = focused.getMonth();
      title.textContent = `${MONTHS[month]} ${year}`;
      const first = new Date(year, month, 1);
      const offset = (first.getDay() + 6) % 7; // semana empieza en lunes
      const start = addDays(first, -offset);
      const now = today();
      grid.innerHTML = '';
      for (let i = 0; i < 42; i++) {
        const d = addDays(start, i);
        const cell = document.createElement('button');
        cell.type = 'button';
        cell.className = 'z-datepicker-day';
        cell.textContent = d.getDate();
        cell.dataset.date = toISO(d);
        cell.setAttribute('role', 'gridcell');
        cell.setAttribute('aria-label', longLabel(d));
        cell.tabIndex = sameDay(d, focused) ? 0 : -1;
        if (d.getMonth() !== month) cell.classList.add('is-outside');
        if (sameDay(d, now)) cell.classList.add('is-today');
        if (sameDay(d, selected)) {
          cell.classList.add('is-selected');
          cell.setAttribute('aria-selected', 'true');
        }
        grid.appendChild(cell);
      }
    }

    function focusDay() {
      const cell = grid.querySelector(`[data-date="${toISO(focused)}"]`);
      if (cell) cell.focus({ preventScroll: true });
    }

    function moveTo(date) {
      focused = date;
      renderGrid();
      focusDay();
    }

    function open() {
      focused = selected || today();
      renderGrid();
      wrap.classList.add('is-open');
      trigger.setAttribute('aria-expanded', 'true');
      focusDay();
      // Que el calendario no quede tapado por la barra de navegación inferior (móvil)
      const nav = document.querySelector('.z-bottom-nav');
      const navTop = nav && getComputedStyle(nav).display !== 'none' ? nav.getBoundingClientRect().top : window.innerHeight;
      const overflow = pop.getBoundingClientRect().bottom + 12 - navTop;
      if (overflow > 0) window.scrollBy({ top: overflow, behavior: 'smooth' });
    }

    function close(returnFocus) {
      wrap.classList.remove('is-open');
      trigger.setAttribute('aria-expanded', 'false');
      if (returnFocus) trigger.focus();
    }

    function select(date) {
      selected = date;
      input.value = date ? toISO(date) : '';
      wrap.classList.remove('is-invalid');
      renderTrigger();
      input.dispatchEvent(new Event('change', { bubbles: true }));
    }

    trigger.addEventListener('click', () => (wrap.classList.contains('is-open') ? close(false) : open()));

    pop.addEventListener('click', (e) => {
      const nav = e.target.closest('[data-nav]');
      if (nav) {
        focused = addMonths(focused, +nav.dataset.nav);
        renderGrid();
        return;
      }
      const day = e.target.closest('.z-datepicker-day');
      if (day) {
        select(parseISO(day.dataset.date));
        close(true);
        return;
      }
      if (e.target.closest('.z-datepicker-today')) {
        select(today());
        close(true);
      } else if (e.target.closest('.z-datepicker-clear')) {
        select(null);
        close(true);
      }
    });

    grid.addEventListener('keydown', (e) => {
      const moves = {
        ArrowLeft: () => addDays(focused, -1),
        ArrowRight: () => addDays(focused, 1),
        ArrowUp: () => addDays(focused, -7),
        ArrowDown: () => addDays(focused, 7),
        PageUp: () => addMonths(focused, e.shiftKey ? -12 : -1),
        PageDown: () => addMonths(focused, e.shiftKey ? 12 : 1),
        Home: () => addDays(focused, -((focused.getDay() + 6) % 7)),
        End: () => addDays(focused, 6 - ((focused.getDay() + 6) % 7)),
      };
      if (moves[e.key]) {
        e.preventDefault();
        moveTo(moves[e.key]());
      }
    });

    wrap.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && wrap.classList.contains('is-open')) {
        e.preventDefault();
        close(true);
      }
    });

    document.addEventListener('click', (e) => {
      if (!wrap.contains(e.target)) close(false);
    });
    wrap.addEventListener('focusout', (e) => {
      if (e.relatedTarget && !wrap.contains(e.relatedTarget)) close(false);
    });

    // Un input oculto no pasa por la validación del navegador: se comprueba aquí
    if (required && input.form) {
      input.form.addEventListener('submit', (e) => {
        if (!input.value) {
          e.preventDefault();
          wrap.classList.add('is-invalid');
          trigger.focus();
        }
      });
    }

    renderTrigger();
  }

  function init() {
    document.querySelectorAll('input[data-datepicker]').forEach(enhance);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
