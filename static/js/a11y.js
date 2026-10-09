// Accesibilidad común a todas las páginas.
// Las tablas anchas se desplazan en horizontal dentro de su contenedor; para que
// también se puedan recorrer con el teclado, el contenedor recibe el foco
// (tabindex="0") y un nombre solo cuando de verdad hay algo que desplazar (WCAG 2.1.1).
(function () {
  const SELECTOR = '.table-responsive, .z-table-wrap, .st-table-wrap';

  // Nombre de la región: el título de su bloque o «Tabla desplazable N»
  function regionName(wrap, index) {
    const box = wrap.closest('section, article, .z-panel, .st-card');
    const heading = box && box.querySelector('h1, h2, h3, h4');
    const title = heading ? heading.textContent.trim().replace(/\s+/g, ' ') : '';
    return title || interpolate(gettext('Tabla desplazable %s'), [index + 1]);
  }

  function update() {
    const used = new Set();
    document.querySelectorAll(SELECTOR).forEach((wrap, index) => {
      const scrolls = wrap.scrollWidth > wrap.clientWidth + 1;
      const ours = 'a11yScroll' in wrap.dataset;
      if (scrolls && !wrap.hasAttribute('tabindex')) {
        wrap.setAttribute('tabindex', '0');
        wrap.setAttribute('role', 'region');
        wrap.dataset.a11yScroll = '';
        if (!wrap.hasAttribute('aria-label')) {
          let name = regionName(wrap, index);
          if (used.has(name)) name += ' (' + (index + 1) + ')';
          wrap.setAttribute('aria-label', name);
          wrap.dataset.a11yLabel = '';
        }
      } else if (!scrolls && ours) {
        ['tabindex', 'role', 'data-a11y-scroll'].forEach((a) => wrap.removeAttribute(a));
        if ('a11yLabel' in wrap.dataset) ['aria-label', 'data-a11y-label'].forEach((a) => wrap.removeAttribute(a));
      }
      if (wrap.hasAttribute('aria-label')) used.add(wrap.getAttribute('aria-label'));
    });
  }

  update();
  let timer;
  window.addEventListener('resize', () => { clearTimeout(timer); timer = setTimeout(update, 150); });
})();
