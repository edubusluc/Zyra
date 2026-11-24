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
  // «Más»: se abre donde quepa entera. Primero hacia abajo; si no cabe, hacia arriba; si tampoco, se desplaza
  // dentro de la ventana (nunca queda cortada) y, si la lista es más alta que la ventana, se recorre dentro del menú.
  const MARGIN = 8;
  document.addEventListener('toggle', (event) => {
    const menu = event.target;
    if (!menu.matches?.('details.z-more') || !menu.open) return;
    const list = menu.querySelector('ul');
    if (!list) return;
    menu.classList.remove('is-up');
    Object.assign(list.style, { transform: '', maxHeight: '', overflowY: '' });
    const fits = (rect) => rect.top >= MARGIN && rect.bottom <= window.innerHeight - MARGIN;
    if (fits(list.getBoundingClientRect())) return;
    menu.classList.add('is-up');
    if (fits(list.getBoundingClientRect())) return;
    menu.classList.remove('is-up');
    const rect = list.getBoundingClientRect();
    const room = window.innerHeight - 2 * MARGIN;
    if (rect.height > room) {
      Object.assign(list.style, { maxHeight: room + 'px', overflowY: 'auto' });
    }
    const height = Math.min(rect.height, room);
    const top = Math.min(Math.max(rect.top, MARGIN), window.innerHeight - MARGIN - height);
    list.style.transform = 'translateY(' + Math.round(top - rect.top) + 'px)';
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
