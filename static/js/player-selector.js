// Selector de jugadores de las convocatorias: búsqueda, filtros, paginación y contador.
(function () {
  const normalize = (t) => t.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().trim();

  document.querySelectorAll('[data-selector]').forEach(function (root) {
    const picks = Array.from(root.querySelectorAll('.z-pick'));
    const search = root.querySelector('[data-selector-search]');
    const count = root.querySelector('[data-selector-count]');
    const hint = root.querySelector('[data-selector-hint]');
    const empty = root.querySelector('[data-selector-empty]');
    const pager = root.querySelector('[data-selector-pager]');
    const pagerInfo = pager.querySelector('.st-pager-info');
    const min = parseInt(root.dataset.min, 10) || 0;
    const pageSize = parseInt(root.dataset.pageSize, 10) || picks.length || 1;
    let position = '';
    let page = 0;
    let matching = [];  // jugadores que cumplen búsqueda y filtro (en todas las páginas)

    const box = (p) => p.querySelector('input[type="checkbox"]');

    function refresh() {
      const q = normalize(search.value);
      matching = picks.filter(function (p) {
        const matchesText = !q || normalize(p.dataset.name).includes(q);
        const matchesPos = !position
          || (position === 'selected' ? box(p).checked : p.dataset.position === position);
        return matchesText && matchesPos;
      });
      const pages = Math.max(1, Math.ceil(matching.length / pageSize));
      page = Math.min(page, pages - 1);
      const shown = new Set(matching.slice(page * pageSize, (page + 1) * pageSize));
      picks.forEach((p) => { p.hidden = !shown.has(p); });
      empty.hidden = matching.length > 0 || !picks.length;

      pager.hidden = pages < 2;
      if (pages > 1) {
        const first = page * pageSize + 1;
        const last = Math.min(matching.length, first + pageSize - 1);
        pagerInfo.textContent = interpolate(gettext('%(first)s–%(last)s de %(total)s'), { first, last, total: matching.length }, true);
        pager.querySelector('[data-step="-1"]').disabled = page === 0;
        pager.querySelector('[data-step="1"]').disabled = page >= pages - 1;
      }

      const n = picks.filter((p) => box(p).checked).length;
      count.textContent = n;
      hint.textContent = min && n < min ? interpolate(gettext('Mínimo %(min)s para cerrar la convocatoria'), {min: min}, true) : '';
    }

    // Al cambiar la búsqueda o el filtro se vuelve a la primera página
    const restart = () => { page = 0; refresh(); };

    search.addEventListener('input', restart);
    root.querySelectorAll('[data-selector-filter]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        position = btn.dataset.selectorFilter;
        root.querySelectorAll('[data-selector-filter]').forEach((b) => b.classList.toggle('active', b === btn));
        restart();
      });
    });
    pager.addEventListener('click', function (e) {
      const btn = e.target.closest('[data-step]');
      if (!btn || btn.disabled) return;
      page += Number(btn.dataset.step);
      refresh();
      root.scrollIntoView({ block: 'start', behavior: 'smooth' });
    });
    // «Marcar visibles» marca todos los que cumplen la búsqueda y el filtro, también los de otras páginas
    root.querySelector('[data-selector-all]').addEventListener('click', function () {
      matching.forEach((p) => { box(p).checked = true; });
      refresh();
    });
    root.querySelector('[data-selector-none]').addEventListener('click', function () {
      picks.forEach((p) => { box(p).checked = false; });
      refresh();
    });
    picks.forEach((p) => box(p).addEventListener('change', refresh));
    refresh();
  });
})();
