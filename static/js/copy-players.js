// «Copiar jugadores» (players/templates/copy_players.html): marcar todos los que se pueden copiar
// y el botón con el número de jugadores elegidos.
document.querySelectorAll('[data-copy-players]').forEach(function (form) {
  const items = Array.from(form.querySelectorAll('[data-copy-item]'));
  const all = form.querySelector('[data-copy-all]');
  const submit = form.querySelector('[data-copy-submit]');
  const label = submit.textContent;

  function refresh() {
    const n = items.filter((i) => i.checked).length;
    submit.disabled = n === 0;
    if (n === 0) submit.textContent = label;
    else if (n === 1) submit.textContent = submit.dataset.labelOne;
    else if (n > 1) submit.textContent = interpolate(submit.dataset.labelMany, { n: n }, true);
    if (all) {
      all.checked = n > 0 && n === items.length;
      all.indeterminate = n > 0 && n < items.length;
    }
  }

  items.forEach((i) => i.addEventListener('change', refresh));
  if (all) all.addEventListener('change', () => { items.forEach((i) => { i.checked = all.checked; }); refresh(); });
  refresh();
});
