// Cabecera y barra de navegación inferior: se esconden al hacer scroll hacia
// abajo y vuelven a aparecer en cuanto se hace scroll hacia arriba.
(function () {
  const header = document.querySelector('.z-header');
  if (!header) return;
  const root = document.body;
  const TOLERANCE = 8;  // px: ignora los pequeños temblores del scroll táctil
  let lastY = window.scrollY;
  let ticking = false;

  function show() { root.classList.remove('z-nav-hidden'); }

  function update() {
    ticking = false;
    const y = Math.max(window.scrollY, 0);
    const delta = y - lastY;
    if (Math.abs(delta) < TOLERANCE) return;
    lastY = y;
    // Arriba del todo o con un menú de la cabecera abierto, siempre visible
    if (delta < 0 || y <= header.offsetHeight || header.querySelector('.dropdown-menu.show')) {
      show();
    } else {
      root.classList.add('z-nav-hidden');
    }
  }

  window.addEventListener('scroll', function () {
    if (!ticking) {
      ticking = true;
      window.requestAnimationFrame(update);
    }
  }, { passive: true });

  // Navegando con el teclado, la barra que recibe el foco se vuelve a mostrar
  document.querySelectorAll('.z-header, .z-bottom-nav').forEach(function (el) {
    el.addEventListener('focusin', show);
  });
})();

// Al escribir en un campo (teclado abierto en el móvil), la barra inferior se esconde: no tapa
// el campo ni el botón de enviar. Vuelve al salir del campo.
(function () {
  const FIELD = 'input:not([type=checkbox]):not([type=radio]):not([type=button]):not([type=submit]):not([type=hidden]), textarea, select, .z-select-trigger';
  const root = document.body;
  document.addEventListener('focusin', function (event) {
    if (event.target.matches && event.target.matches(FIELD)) root.classList.add('z-typing');
  });
  document.addEventListener('focusout', function (event) {
    if (event.target.matches && event.target.matches(FIELD)) root.classList.remove('z-typing');
  });
})();
