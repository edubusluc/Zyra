/*
 * Crear rival: tarjeta «Así se verá» que se rellena sola con lo que se escribe o se elige (nombre,
 * división, localización, categoría y país). Los campos que se copian del equipo propio (equipo del
 * grupo) están ocultos y no se muestran. Solo se ve en escritorio.
 */
(function () {
  const card = document.querySelector('[data-team-preview]');
  const form = document.querySelector('form[data-similar-check]');
  if (!card || !form) return;
  const kicker = card.querySelector('[data-tp-kicker]');
  const nameEl = card.querySelector('[data-tp-name]');
  const meta = card.querySelector('[data-tp-meta]');
  const foot = card.querySelector('[data-tp-foot]');

  function control(name) { return form.querySelector(`[name="${name}"]`); }
  function visible(el) { return !!el && !el.closest('[hidden]'); }
  function selectedText(name) {
    const el = control(name);
    if (!visible(el) || !el.value) return '';
    const option = el.options && el.options[el.selectedIndex];
    return option ? option.textContent.trim() : el.value;
  }
  function render() {
    const name = ((control('name') || {}).value || '').trim();
    kicker.textContent = [card.dataset.competition, selectedText('division')].filter(Boolean).join(' · ');
    nameEl.textContent = name || nameEl.dataset.empty;
    if (name) nameEl.removeAttribute('data-placeholder'); else nameEl.setAttribute('data-placeholder', '');
    const location = ((control('location') || {}).value || '').trim();
    meta.textContent = [location, selectedText('gender'), selectedText('country')].filter(Boolean).join(' · ');
    const inGroup = control('in_group');
    foot.hidden = !(inGroup && inGroup.checked);
    foot.textContent = card.dataset.groupLabel || '';
  }
  form.addEventListener('input', render);
  form.addEventListener('change', render);
  render();
})();
