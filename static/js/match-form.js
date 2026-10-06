/*
 * Formulario de partido:
 *  - Modo Amistoso: oculta el tipo de partido (Enfrentamiento, Reto, Play Off) y
 *    deja elegir si el rival es un equipo del grupo o un nombre escrito a mano.
 *  - Cards de local y visitante: al elegir un equipo en el desplegable se
 *    actualizan su nombre y su foto.
 */
(function () {
  const form = document.querySelector('[data-match-form]');
  if (!form) return;

  const typeRow = form.querySelector('[data-match-type-row]');
  const sourceRow = form.querySelector('[data-rival-source-row]');
  const groupRival = form.querySelector('[data-group-rival]');
  const manualRival = form.querySelector('[data-manual-rival]');
  const radios = form.querySelectorAll('input[name="mode"], input[name="rival_source"], input[name="own_side"]');
  function checkedValue(name) {
    const checked = form.querySelector(`input[name="${name}"]:checked`);
    return checked ? checked.value : '';
  }
  function syncMode() {
    const friendly = checkedValue('mode') === 'amistoso';
    const manual = friendly && checkedValue('rival_source') === 'manual';
    if (typeRow) typeRow.hidden = friendly;
    if (sourceRow) sourceRow.hidden = !friendly;
    if (groupRival) groupRival.hidden = manual;
    if (manualRival) manualRival.hidden = !manual;
    radios.forEach((r) => r.closest('label').classList.toggle('active', r.checked));
  }
  radios.forEach((r) => r.addEventListener('change', (event) => {
    syncMode();
    if (event.target.name === 'rival_source' && event.target.value === 'manual') {
      const input = manualRival && manualRival.querySelector('input[type="text"]');
      if (input) input.focus();
    }
  }));
  syncMode();

  form.querySelectorAll('[data-team-card]').forEach((card) => {
    const select = card.querySelector('select');
    const name = card.querySelector('[data-team-name]');
    const photo = card.querySelector('[data-team-photo]');
    const empty = name.classList.contains('is-empty') ? name.textContent : gettext('Elige equipo');
    function sync() {
      const option = select.options[select.selectedIndex];
      const chosen = option && option.value !== '';
      name.textContent = chosen ? option.textContent.trim() : empty;
      name.classList.toggle('is-empty', !chosen);
      photo.src = (chosen && option.dataset.photo) || card.dataset.defaultPhoto;
    }
    select.addEventListener('change', sync);
    sync();
  });
})();
