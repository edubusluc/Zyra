/*
 * Formulario de partido:
 *  - Modo Amistoso: oculta el tipo de partido (Enfrentamiento, Reto, Play Off; Liga, Playoffs, Fase final) y
 *    deja elegir si el rival es un equipo del grupo o un nombre escrito a mano.
 *  - Cards de local y visitante: al elegir un equipo en el desplegable se
 *    actualizan su nombre y su foto.
 *  - Jornada: solo visible con el tipo de liga de la competición (LAPI).
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
  // Tipos que siempre se juegan en sede neutral (Play Off de la SNP): sin local ni visitante y con rival escrito.
  const neutralTypes = (form.dataset.neutralTypes || '').split(',').filter(Boolean);
  const ownSideRow = form.querySelector('[data-own-side-row]');
  const placeHelp = form.querySelector('[data-place-help]');
  function isNeutral() {
    return checkedValue('mode') !== 'amistoso' && !!typeSelect && neutralTypes.includes(typeSelect.value);
  }
  function syncMode() {
    const friendly = checkedValue('mode') === 'amistoso';
    const neutral = isNeutral();
    const manual = (friendly || neutral) && checkedValue('rival_source') === 'manual';
    if (typeRow) typeRow.hidden = friendly;
    if (sourceRow) sourceRow.hidden = !(friendly || neutral);
    if (ownSideRow) ownSideRow.hidden = neutral;
    if (placeHelp) placeHelp.hidden = neutral;
    if (groupRival) groupRival.hidden = manual;
    if (manualRival) manualRival.hidden = !manual;
    // Los desplegables ocultos no deben bloquear el envío por ser obligatorios.
    if (groupRival) groupRival.querySelectorAll('select').forEach((s) => { s.disabled = manual; });
    radios.forEach((r) => r.closest('label').classList.toggle('active', r.checked));
  }
  radios.forEach((r) => r.addEventListener('change', (event) => {
    syncMode();
    syncDefaults();
    if (event.target.name === 'rival_source' && event.target.value === 'manual') {
      const input = manualRival && manualRival.querySelector('input[type="text"]');
      if (input) input.focus();
    }
  }));
  if (kindRow && kindSelect && legacy && typeSelect) {
    kindRow.hidden = false;
    legacy.hidden = true;
    kindSelect.value = checkedValue('mode') === 'amistoso' ? 'amistoso' : (typeSelect.value || kindSelect.options[0].value);
    kindSelect.addEventListener('change', () => {
      const friendly = kindSelect.value === 'amistoso';
      const mode = form.querySelector(`input[name="mode"][value="${friendly ? 'amistoso' : 'competitivo'}"]`);
      if (mode) { mode.checked = true; mode.dispatchEvent(new Event('change', { bubbles: true })); }
      if (!friendly) typeSelect.value = kindSelect.value;
      syncMode();
      syncDefaults();
      syncRound();
    });
  }
  // Jornada (LAPI): solo en los enfrentamientos de liga (data-league-type en su fila).
  const roundRow = form.querySelector('[data-round-row]');
  function syncRound() {
    if (!roundRow) return;
    const kind = kindSelect && !kindRow.hidden ? kindSelect.value : (checkedValue('mode') === 'amistoso' ? 'amistoso' : typeSelect && typeSelect.value);
    roundRow.hidden = kind !== roundRow.dataset.leagueType;
  }
  if (typeSelect) typeSelect.addEventListener('change', syncRound);
  form.querySelectorAll('input[name="mode"]').forEach((r) => r.addEventListener('change', syncRound));
  syncMode();
  syncRound();

  // Lugar: por defecto el del equipo local (el propio si juega en casa, el rival si juega fuera);
  // si la persona lo ha escrito a mano, no se pisa.
  const place = form.querySelector('input[name="location"]');
  const rivalSelect = form.querySelector('select[name="rival"]');
  let placeEdited = place && place.value !== '' && place.value !== (form.dataset.ownLocation || '');
  const rivalPlace = form.querySelector('input[name="rival_location"]');
  function manualNow() {
    return !!manualRival && !manualRival.hidden;
  }
  function defaultPlace() {
    // Sede neutral: la fija la organización, se escribe a mano.
    if (isNeutral()) return '';
    if (checkedValue('own_side') !== 'visiting') return form.dataset.ownLocation || '';
    if (manualNow()) return rivalPlace ? rivalPlace.value : '';
    const option = rivalSelect && rivalSelect.options[rivalSelect.selectedIndex];
    return (option && option.dataset.location) || '';
  }
  function syncPlace() { if (place && !placeEdited) place.value = defaultPlace(); }
  if (place) {
    place.addEventListener('input', () => { placeEdited = true; });
    form.querySelectorAll('input[name="own_side"]').forEach((r) => r.addEventListener('change', syncPlace));
    if (rivalSelect) rivalSelect.addEventListener('change', syncPlace);
    if (rivalPlace) rivalPlace.addEventListener('input', syncPlace);
  }

  // Hora: la habitual del equipo propio si juega en casa; en visitante se deja en blanco. Si la
  // persona la ha escrito a mano, no se pisa.
  const startTime = form.querySelector('input[name="start_time"]');
  let timeEdited = startTime && startTime.value !== '' && startTime.value !== (form.dataset.ownTime || '');
  function syncTime() {
    if (!startTime || timeEdited) return;
    startTime.value = (isNeutral() || checkedValue('own_side') === 'visiting') ? '' : (form.dataset.ownTime || '');
  }
  if (startTime) {
    startTime.addEventListener('input', () => { timeEdited = true; });
    form.querySelectorAll('input[name="own_side"]').forEach((r) => r.addEventListener('change', syncTime));
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

  // Al cambiar de tipo o de rival se recalculan el lugar y la hora por defecto (sin pisar lo escrito a mano).
  function syncDefaults() { syncPlace(); syncTime(); }

  // Hora en 24 h con el mismo aspecto que el resto de campos: escribe 2030 y queda 20:30 (S-12).
  const time = form.querySelector('[data-time-24h]');
  if (time) {
    time.addEventListener('input', () => {
      const digits = time.value.replace(/\D/g, '').slice(0, 4);
      time.value = digits.length > 2 ? digits.slice(0, 2) + ':' + digits.slice(2) : digits;
    });
  }

  // «Así se verá»: tarjeta de vista previa que se rellena con lo que se va escribiendo.
  const preview = document.querySelector('[data-match-preview]');
  if (preview) {
    const field = (name) => form.querySelector(`[name="${name}"]`);
    const set = (attr, text) => { preview.querySelector(`[data-preview-${attr}]`).textContent = text; };
    function syncPreview() {
      const kind = kindSelect && !kindRow.hidden ? kindSelect.options[kindSelect.selectedIndex].textContent.trim() : '';
      set('kind', kind);
      const iso = field('start_date') && field('start_date').value;
      const date = /^\d{4}-\d{2}-\d{2}$/.test(iso || '') ? new Date(iso + 'T12:00:00') : null;
      if (date) set('date', date.toLocaleDateString(document.documentElement.lang || 'es', { weekday: 'short', day: 'numeric', month: 'short' }).replace(',', ''));
      const time = field('start_time') ? field('start_time').value : '';
      const where = place ? place.value : '';
      set('meta', [time, where].filter(Boolean).join(' · '));
      const manual = !manualRival.hidden;
      const option = rivalSelect && rivalSelect.options[rivalSelect.selectedIndex];
      const rival = manual ? (field('rival_name').value || '') : (option && option.value ? option.textContent.trim() : '');
      const own = preview.dataset.ownName;
      const home = isNeutral() || checkedValue('own_side') !== 'visiting';
      set('local', (home ? own : rival) || '—');
      set('visiting', (home ? rival : own) || '—');
      preview.querySelectorAll('[data-preview-side]').forEach((el) => { el.hidden = isNeutral(); });
    }
    form.addEventListener('input', syncPreview);
    form.addEventListener('change', syncPreview);
    // La fecha la rellena un selector propio: se vuelve a leer cuando cambia su campo oculto.
    setInterval(syncPreview, 600);
    syncPreview();
  }
})();
