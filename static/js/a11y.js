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

// «Volver arriba»: el ancla (#contenido) es solo el respaldo sin JavaScript. El <main>
// empieza bajo la cabecera, así que saltar a él no deja la página arriba del todo;
// se sube al principio del documento y el foco pasa al contenido sin moverlo otra vez.
// El desplazamiento suave lo decide el CSS (scroll-behavior, respeta reduced-motion).
document.querySelectorAll('[data-scroll-top]').forEach((link) => {
  link.addEventListener('click', (event) => {
    event.preventDefault();
    window.scrollTo(0, 0);
    const target = document.querySelector(link.getAttribute('href'));
    if (target) target.focus({ preventScroll: true });
  });
});

// «Saltar al contenido»: lleva el foco a <main> y lo marca con un contorno visible (si no, el salto
// parece no hacer nada porque el contenido ya está en pantalla). Sin JavaScript sigue valiendo el ancla.
document.querySelectorAll('.z-skip-link').forEach((link) => {
  link.addEventListener('click', (event) => {
    const target = document.querySelector(link.getAttribute('href'));
    if (!target) return;
    event.preventDefault();
    if (!target.hasAttribute('tabindex')) target.setAttribute('tabindex', '-1');
    target.focus({ preventScroll: true });
    target.scrollIntoView({ block: 'start' });
    target.classList.add('z-skip-target');
    target.addEventListener('blur', () => target.classList.remove('z-skip-target'), { once: true });
  });
});

// Filas enlazadas (tablas de partidos de las estadísticas): pulsar en cualquier punto de la fila
// abre el partido de su primer enlace. El enlace sigue siendo el que usa el teclado y los lectores.
(function () {
  document.addEventListener('click', function (event) {
    if (event.defaultPrevented || event.button !== 0) return;
    const row = event.target.closest?.('.st-table--links tbody tr');
    if (!row || event.target.closest('a, button, input, select, textarea')) return;
    const link = row.querySelector('a[href]');
    if (link) link.click();
  });
})();

// Pestañas de estadísticas en móvil (UX-001): la fila se desliza en horizontal; al cargar se
// lleva la pestaña activa a la vista sin mover la página en vertical.
(function () {
  const tabs = document.querySelector('.st-tabs');
  const active = tabs && tabs.querySelector('[aria-current="page"]');
  if (!active || tabs.scrollWidth <= tabs.clientWidth) return;
  const left = active.getBoundingClientRect().left - tabs.getBoundingClientRect().left + tabs.scrollLeft;
  tabs.scrollLeft = left - (tabs.clientWidth - active.offsetWidth) / 2;
})();
