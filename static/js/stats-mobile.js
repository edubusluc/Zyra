/*
 * Estadísticas en móvil (UX-009): menos longitud y menos niveles antes del primer dato.
 *  - Los filtros (temporada, tipo…) se recogen en un único desplegable «Filtros · …».
 *  - Cada sección (<section class="st-section">) declara su nivel en ``data-level``: «understand»
 *    (comprender) no se pliega nunca; «compare» y «deepen» (el nivel por defecto es «compare») se pliegan
 *    bajo su título y solo se abren al pulsarlas o si se enlaza a ellas. ``data-summary`` pone un resumen
 *    junto al título plegado.
 * En escritorio no hace nada: todo sigue abierto y sin controles extra.
 */
(function () {
  'use strict';
  const page = document.querySelector('.st-page');
  if (!page) return;
  const mq = window.matchMedia('(max-width: 767.98px)');

  // ---- Filtros en una sola fila ----
  function setupFilters() {
    const wraps = Array.from(page.querySelectorAll('.z-fsel-wrap'));
    if (!wraps.length || page.querySelector('.st-filters-sheet')) return;
    const sheet = document.createElement('details');
    sheet.className = 'st-filters-sheet';
    const summary = document.createElement('summary');
    const label = document.createElement('span');
    label.textContent = gettext('Filtros');
    const current = document.createElement('small');
    summary.append(label, current);
    sheet.append(summary);
    const body = document.createElement('div');
    body.className = 'st-filters-body';
    sheet.append(body);
    wraps[0].before(sheet);
    wraps.forEach((w) => body.append(w));
    // Resumen de lo elegido: el texto de cada desplegable («2025-26 · Competitivos»)
    const values = Array.from(body.querySelectorAll('.z-fsel > summary > span')).map((el) => el.textContent.trim()).filter(Boolean);
    current.textContent = values.join(' · ');
  }

  // ---- Secciones plegables ----
  function setupSections() {
    const sections = Array.from(page.querySelectorAll('section.st-section'));
    sections.forEach((section, index) => {
      if (section.dataset.collapsible) return;
      const title = section.querySelector(':scope > .st-section-title');
      if (!title || section.dataset.level === 'understand') return;
      section.dataset.collapsible = '1';
      const body = document.createElement('div');
      body.className = 'st-section-body';
      body.id = (section.id || 'sec-' + index) + '-body';
      Array.from(section.childNodes).forEach((node) => { if (node !== title) body.append(node); });
      section.append(body);
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'st-section-toggle';
      button.setAttribute('aria-controls', body.id);
      while (title.firstChild) button.append(title.firstChild);
      if (section.dataset.summary) {
        const summary = document.createElement('small');
        summary.className = 'st-section-summary';
        summary.textContent = section.dataset.summary;
        button.append(summary);
      }
      const chevron = document.createElement('i');
      chevron.className = 'fa-solid fa-chevron-down';
      chevron.setAttribute('aria-hidden', 'true');
      button.append(chevron);
      title.append(button);
      button.addEventListener('click', () => toggle(section, body.hidden));
      section._stBody = body;
      section._stButton = button;
      section._stOpenByDefault = false;
    });
    applyMode();
  }

  function toggle(section, open) {
    if (!section._stBody) return;
    section._stBody.hidden = !open;
    section._stButton.setAttribute('aria-expanded', String(open));
    section.classList.toggle('is-open', open);
    // Los gráficos medidos con la sección oculta se recalculan al abrirla
    if (open) window.dispatchEvent(new Event('resize'));
  }

  function openFromHash() {
    if (!mq.matches || !location.hash) return;
    const target = document.getElementById(decodeURIComponent(location.hash.slice(1)));
    const section = target && target.closest('section.st-section');
    if (section) toggle(section, true);
  }

  function applyMode() {
    page.querySelectorAll('section.st-section[data-collapsible]').forEach((section) => {
      if (mq.matches) toggle(section, section._stOpenByDefault);
      else { section._stBody.hidden = false; section._stButton.removeAttribute('aria-expanded'); }
    });
    const sheet = page.querySelector('.st-filters-sheet');
    if (sheet) sheet.open = !mq.matches;
    openFromHash();
  }

  setupFilters();
  setupSections();
  mq.addEventListener('change', applyMode);
  window.addEventListener('hashchange', openFromHash);
  // Los enlaces del índice abren su sección antes de saltar
  page.addEventListener('click', (e) => {
    const a = e.target.closest('.st-index a[href^="#"]');
    if (!a || !mq.matches) return;
    const target = document.getElementById(a.getAttribute('href').slice(1));
    const section = target && target.closest('section.st-section');
    if (section) toggle(section, true);
  });
})();
