// Selector de competición del alta de equipo: filtra las competiciones por el país elegido, bloquea las que
// no se juegan allí y pinta el escenario (color, nombre, datos y escudo 3D) de la competición marcada.
// Las competiciones en las que la cuenta ya tiene equipo llegan bloqueadas desde el servidor (is-locked).
// Los datos salen de core/competition_picker.py (json_script «competition-picker»).
(function () {
  const dataEl = document.getElementById('competition-picker');
  const stage = document.querySelector('[data-competition-stage]');
  const fieldset = document.querySelector('[data-competition-choice]');
  const country = document.querySelector('select[name=country]');
  if (!dataEl || !stage || !fieldset || !country) return;

  const entries = {};
  JSON.parse(dataEl.textContent).forEach((e) => { entries[e.code] = e; });
  const radios = Array.from(fieldset.querySelectorAll('.z-comp-card:not(.is-locked) input[type=radio]'));
  const team = document.querySelector('form input[name=name]');
  const q = (sel) => stage.querySelector(sel);

  function countryName() {
    const option = country.options[country.selectedIndex];
    return option ? option.textContent.trim() : '';
  }

  function paint(entry) {
    stage.style.setProperty('--stage', entry.color);
    stage.style.setProperty('--stage-rgb', entry.rgb);
    q('[data-stage-pill]').textContent = countryName();
    q('[data-stage-name]').textContent = entry.name;
    q('[data-stage-full]').textContent = entry.full_name;
    const view = q('.z-stage-view');
    view.setAttribute('aria-label', (view.dataset.stageLabel || '{name}').replace('{name}', entry.name));
    stage.querySelectorAll('[data-facts-for]').forEach((dl) => { dl.hidden = dl.dataset.factsFor !== entry.code; });
    if (window.ZyraStage && window.ZyraStage.last !== entry.code) window.ZyraStage.show(entry);
    if (window.ZyraStage) window.ZyraStage.last = entry.code;
  }

  function syncTeam() {
    q('[data-stage-team]').textContent = team ? team.value.trim() : '';
  }

  function sync() {
    const place = country.value;
    document.querySelectorAll('[data-comp-card]').forEach((card) => {
      const entry = entries[card.dataset.compCard];
      const allowed = !entry || !entry.countries.length || entry.countries.indexOf(place) !== -1;
      card.hidden = !allowed;
      const radio = card.querySelector('input[value]');
      if (radio) radio.disabled = !allowed;
    });
    let picked = radios.find((r) => r.checked && !r.disabled);
    if (!picked) {
      picked = radios.find((r) => !r.disabled);
      if (picked) {
        picked.checked = true;
        picked.dispatchEvent(new Event('change', { bubbles: true }));
      }
    }
    if (picked) paint(entries[picked.value]);
    syncTeam();
  }

  radios.forEach((r) => r.addEventListener('change', () => paint(entries[r.value])));
  country.addEventListener('change', sync);
  if (team) team.addEventListener('input', syncTeam);
  sync();
  // El borrador guardado (register-wizard) rellena el formulario un instante después de cargar
  setTimeout(() => { sync(); }, 150);
})();
