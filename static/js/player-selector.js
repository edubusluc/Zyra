// Selector de jugadores: búsqueda en vivo, filtros, paginación y contador.
// Lo usan las convocatorias (casillas .z-pick) y el listado de jugadores (elementos
// [data-selector-item], sin casillas, contador ni filtros). Si un jugador aparece varias veces
// (tarjeta y fila de tabla), comparten data-key y se muestran u ocultan juntos.
(function () {
  const normalize = (t) => t.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().trim();

  document.querySelectorAll('[data-selector]').forEach(function (root) {
    const picks = Array.from(root.querySelectorAll('.z-pick, [data-selector-item]'));
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
    const checked = (p) => !!box(p) && box(p).checked;
    const keyOf = (p) => p.dataset.key || p;

    function refresh() {
      const q = normalize(search.value);
      const seen = new Set();
      matching = picks.filter(function (p) {
        const matchesText = !q || normalize(p.dataset.name).includes(q);
        const matchesPos = !position
          || (position === 'selected' ? checked(p) : p.dataset.position === position);
        if (!(matchesText && matchesPos) || seen.has(keyOf(p))) return false;
        seen.add(keyOf(p));
        return true;
      });
      const pages = Math.max(1, Math.ceil(matching.length / pageSize));
      page = Math.min(page, pages - 1);
      const shown = new Set(matching.slice(page * pageSize, (page + 1) * pageSize).map(keyOf));
      picks.forEach((p) => { p.hidden = !shown.has(keyOf(p)); });
      empty.hidden = matching.length > 0 || !picks.length;

      pager.hidden = pages < 2;
      if (pages > 1) {
        const first = page * pageSize + 1;
        const last = Math.min(matching.length, first + pageSize - 1);
        pagerInfo.textContent = interpolate(gettext('%(first)s–%(last)s de %(total)s'), { first, last, total: matching.length }, true);
        pager.querySelector('[data-step="-1"]').disabled = page === 0;
        pager.querySelector('[data-step="1"]').disabled = page >= pages - 1;
      }

      if (!count) return;
      const n = picks.filter(checked).length;
      count.textContent = n;
      hint.textContent = !min ? '' : (n < min ? interpolate(gettext('Mínimo %(min)s para cerrar la convocatoria'), {min: min}, true) : interpolate(gettext('Mínimo %(min)s cumplido'), {min: min}, true));
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
    const all = root.querySelector('[data-selector-all]');
    const none = root.querySelector('[data-selector-none]');
    const menu = root.querySelector('.z-selector-more');
    const closeMenu = () => { if (menu) menu.open = false; };
    if (all) all.addEventListener('click', function () {
      matching.forEach((p) => { box(p).checked = true; });
      closeMenu();
      refresh();
    });
    // «Marcar los que dicen Sí» (enlace de disponibilidad): añade a los que respondieron Sí sin quitar a nadie
    const yes = root.querySelector('[data-selector-yes]');
    if (yes) yes.addEventListener('click', function () {
      picks.forEach((p) => { if (p.dataset.answer === 'yes') box(p).checked = true; });
      closeMenu();
      refresh();
    });
    if (none) none.addEventListener('click', function () {
      picks.forEach((p) => { box(p).checked = false; });
      closeMenu();
      refresh();
    });
    // Avisos de respuesta: cuántos elegidos dijeron «No» o están sin confirmar, en la barra inferior y en el popup al guardar.
    const warnBox = root.querySelector('[data-selector-warns]');
    const form = root.closest('form');
    const fill = (tpl, vars) => Object.keys(vars).reduce((t, k) => t.split('{' + k + '}').join(vars[k]), tpl);
    const joinNames = (list) => list.map((p) => p.dataset.name).join(', ');
    const answered = (answer) => picks.filter((p) => p.dataset.answer === answer && checked(p));

    function refreshWarnings() {
      if (!warnBox) return;
      const no = answered('no');
      const maybe = answered('maybe');
      [['no', no], ['maybe', maybe]].forEach(function (pair) {
        const el = warnBox.querySelector('[data-warn-' + pair[0] + ']');
        const n = pair[1].length;
        el.hidden = !n;
        const cap = pair[0].charAt(0).toUpperCase() + pair[0].slice(1);
        const tpl = n === 1 ? root.dataset['bar' + cap + 'One'] : root.dataset['bar' + cap + 'Many'];
        el.querySelector('span').textContent = n ? fill(tpl, { n: n }) : '';
      });
      warnBox.hidden = !(no.length || maybe.length);
      updateConfirm(no, maybe);
    }

    // Solo se pregunta por quien entra ahora: los que ya estaban convocados (casilla marcada de origen) no cuentan.
    function updateConfirm(no, maybe) {
      if (!form) return;
      const fresh = (p) => !box(p).defaultChecked;
      const nNo = no.filter(fresh);
      const nMaybe = maybe.filter(fresh);
      const total = nNo.length + nMaybe.length;
      if (!total) {
        form.removeAttribute('data-confirm');
        form.removeAttribute('data-confirm-title');
        form.removeAttribute('data-confirm-action');
        form.removeAttribute('data-confirm-danger');
        return;
      }
      let text;
      if (total === 1) {
        text = fill(nNo.length ? root.dataset.warnOneNo : root.dataset.warnOneMaybe, { names: joinNames(nNo.concat(nMaybe)) });
      } else {
        text = fill(root.dataset.warnMany, { n: total });
        if (nNo.length) text += ' ' + fill(root.dataset.warnListNo, { names: joinNames(nNo) });
        if (nMaybe.length) text += ' ' + fill(root.dataset.warnListMaybe, { names: joinNames(nMaybe) });
        text += ' ' + root.dataset.warnManyEnd;
      }
      form.setAttribute('data-confirm', text);
      form.setAttribute('data-confirm-title', nNo.length && total === 1 ? root.dataset.warnTitleNo : root.dataset.warnTitleMany);
      form.setAttribute('data-confirm-action', root.dataset.warnAction);
      if (nNo.length) form.setAttribute('data-confirm-danger', ''); else form.removeAttribute('data-confirm-danger');
    }

    picks.forEach((p) => { if (box(p)) box(p).addEventListener('change', () => { refresh(); refreshWarnings(); }); });
    [all, none, yes].forEach((b) => { if (b) b.addEventListener('click', refreshWarnings); });
    refresh();
    refreshWarnings();
  });
})();
