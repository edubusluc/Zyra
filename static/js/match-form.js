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
  // Selector único «Tipo de enfrentamiento»: fija el modo (competitivo/amistoso) y el tipo (enfrentamiento,
  // reto, play off) de los controles originales, que se ocultan.
  const kindRow = form.querySelector('[data-kind-row]');
  const kindSelect = form.querySelector('[data-kind-select]');
  const legacy = form.querySelector('[data-kind-legacy]');
  const typeSelect = form.querySelector('select[name="match_type"]');
  const radios = form.querySelectorAll('input[name="mode"], input[name="rival_source"], input[name="own_side"], input[name="report_scope"]');
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
    // Los desplegables ocultos no deben bloquear el envío por ser obligatorios.
    if (groupRival) groupRival.querySelectorAll('select').forEach((s) => { s.disabled = manual; });
    radios.forEach((r) => r.closest('label').classList.toggle('active', r.checked));
  }
  radios.forEach((r) => r.addEventListener('change', (event) => {
    syncMode();
    if (event.target.name === 'rival_source' && event.target.value === 'manual') {
      const input = manualRival && manualRival.querySelector('input[type="text"]');
      if (input) input.focus();
    }
  }));
  if (kindRow && kindSelect && legacy && typeSelect) {
    kindRow.hidden = false;
    legacy.hidden = true;
    kindSelect.value = checkedValue('mode') === 'amistoso' ? 'amistoso' : (typeSelect.value || 'enfrentamiento');
    kindSelect.addEventListener('change', () => {
      const friendly = kindSelect.value === 'amistoso';
      const mode = form.querySelector(`input[name="mode"][value="${friendly ? 'amistoso' : 'competitivo'}"]`);
      if (mode) { mode.checked = true; mode.dispatchEvent(new Event('change', { bubbles: true })); }
      if (!friendly) typeSelect.value = kindSelect.value;
    });
  }
  syncMode();

  // Lugar: por defecto el del equipo local (el propio si juega en casa, el rival si juega fuera);
  // si la persona lo ha escrito a mano, no se pisa.
  const place = form.querySelector('input[name="location"]');
  const rivalSelect = form.querySelector('select[name="rival"]');
  let placeEdited = place && place.value !== '' && place.value !== (form.dataset.ownLocation || '');
  function defaultPlace() {
    if (checkedValue('own_side') !== 'visiting') return form.dataset.ownLocation || '';
    const option = rivalSelect && rivalSelect.options[rivalSelect.selectedIndex];
    return (option && option.dataset.location) || '';
  }
  function syncPlace() { if (place && !placeEdited) place.value = defaultPlace(); }
  if (place) {
    place.addEventListener('input', () => { placeEdited = true; });
    form.querySelectorAll('input[name="own_side"]').forEach((r) => r.addEventListener('change', syncPlace));
    if (rivalSelect) rivalSelect.addEventListener('change', syncPlace);
  }

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
