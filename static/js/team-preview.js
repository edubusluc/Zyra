/*
 * Registro de equipo: tarjeta «Así se verá» que se rellena sola con lo que se escribe o se elige
 * (competición, nombre, división, localización, categoría y país). Solo se ve en escritorio.
 */
(function () {
  const card = document.querySelector('[data-team-preview]');
  const form = document.querySelector('form[data-wizard]');
  if (!card || !form) return;
  const kicker = card.querySelector('[data-tp-kicker]');
  const nameEl = card.querySelector('[data-tp-name]');
  const meta = card.querySelector('[data-tp-meta]');

  function control(name) { return form.querySelector(`[name="${name}"]`); }
  function selectedText(name) {
    const el = control(name);
    if (!el || !el.value) return '';
    const option = el.options && el.options[el.selectedIndex];
    return option ? option.textContent.trim() : el.value;
  }
  function competition() {
    const checked = form.querySelector('input[name="competition"]:checked');
    if (!checked) return '';
    const label = checked.closest('label');
    const span = label && label.querySelector('span');
    return span ? span.textContent.trim() : '';
  }
  function render() {
    const name = (control('name') || {}).value || '';
    kicker.textContent = [competition(), selectedText('division')].filter(Boolean).join(' · ');
    nameEl.textContent = name.trim() || nameEl.dataset.empty;
    if (name.trim()) nameEl.removeAttribute('data-placeholder'); else nameEl.setAttribute('data-placeholder', '');
    const location = ((control('location') || {}).value || '').trim();
    meta.textContent = [location, selectedText('gender'), selectedText('country')].filter(Boolean).join(' · ');
  }
  form.addEventListener('input', render);
  form.addEventListener('change', render);
  render();
})();
