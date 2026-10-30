// Desplegables de filtros (Competición, Temporada, Tipo): solo uno abierto y se cierran al pulsar fuera o con Escape.
(function () {
  const menus = () => Array.from(document.querySelectorAll('[data-filter-menu]'));
  document.addEventListener('click', (event) => {
    menus().forEach((menu) => { if (menu.open && !menu.contains(event.target)) menu.open = false; });
  });
  document.addEventListener('toggle', (event) => {
    if (!event.target.matches || !event.target.matches('[data-filter-menu]') || !event.target.open) return;
    menus().forEach((menu) => { if (menu !== event.target) menu.open = false; });
  }, true);
  document.addEventListener('keydown', (event) => {
    if (event.key !== 'Escape') return;
    menus().forEach((menu) => {
      if (!menu.open) return;
      menu.open = false;
      const summary = menu.querySelector('summary');
      if (summary) summary.focus();
    });
  });
})();
