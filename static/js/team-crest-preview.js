// Escudo 3D del formulario de edición de equipo: se actualiza al escribir el nombre, cambiar las opciones
// (chips) o elegir un escudo nuevo. El logo elegido se lee de la vista previa oculta que mantiene photo-crop.js.
(function () {
  const stage = document.querySelector('[data-team-crest]');
  const form = stage && stage.closest('.z-team-edit') && stage.closest('.z-team-edit').querySelector('form');
  if (!form) { return; }
  const SHIELD = 'M50 3 94 17V52C94 77 76 93 50 101 24 93 6 77 6 52V17Z';
  const nameInput = form.querySelector('#name');
  const nameEl = stage.querySelector('[data-crest-name]');
  const photoEl = form.querySelector('[data-photo-preview]');

  function initials(name) {
    const words = name.replace(/-/g, ' ').split(/\s+/).filter((w) => /^[\p{L}\p{N}]/u.test(w));
    if (words.length >= 2) { return (words[0][0] + words[1][0]).toUpperCase(); }
    return (words[0] || '').slice(0, 2).toUpperCase();
  }
  function hue(name) {
    let sum = 0;
    Array.from(name.toLowerCase()).forEach((c, i) => { sum += (i + 1) * c.charCodeAt(0); });
    return sum % 360;
  }
  function escape(text) {
    return text.replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  }
  function logoUrl() {
    return photoEl && !photoEl.hidden && photoEl.getAttribute('src') ? photoEl.getAttribute('src') : '';
  }

  // Redibuja las capas del escudo: canto (silueta o logo oscurecido) y caras (siluetas con siglas o logo).
  function paint() {
    const name = nameInput ? nameInput.value.trim() : '';
    const url = logoUrl();
    stage.querySelectorAll('.z-crest-layer').forEach((layer) => {
      const edge = layer.classList.contains('z-crest-edge');
      layer.classList.toggle('is-photo', edge && Boolean(url));
      if (url) {
        layer.innerHTML = '<img src="' + escape(url) + '" alt="" decoding="async">';
      } else if (edge) {
        layer.innerHTML = '<svg viewBox="0 0 100 104" focusable="false"><path d="' + SHIELD + '"/></svg>';
      } else {
        layer.innerHTML = '<svg viewBox="0 0 100 104" focusable="false" style="--h: ' + hue(name) + '"><path d="' + SHIELD
          + '" class="z-crest-shield"/><text x="50" y="66" text-anchor="middle" class="z-crest-initials">' + escape(initials(name)) + '</text></svg>';
      }
    });
  }
  function paintName() {
    const name = nameInput ? nameInput.value.trim() : '';
    nameEl.textContent = name || nameEl.dataset.empty;
    if (!logoUrl()) { paint(); }
  }
  function chip(key, text) {
    const el = stage.querySelector('[data-chip="' + key + '"]');
    if (el) { el.textContent = text; el.hidden = !text; }
  }
  ['division', 'gender', 'country'].forEach((id) => {
    const select = form.querySelector('#' + id);
    if (!select) { return; }
    const update = () => chip(id, select.value ? select.options[select.selectedIndex].text : '');
    select.addEventListener('change', update);
    update();
  });
  const location = form.querySelector('#location');
  if (location) { location.addEventListener('input', () => chip('location', location.value.trim())); }
  if (nameInput) { nameInput.addEventListener('input', paintName); }
  if (photoEl && 'MutationObserver' in window) {
    new MutationObserver(paint).observe(photoEl, { attributes: true, attributeFilter: ['src', 'hidden'] });
  }

  // El giro se pausa cuando el escudo sale de la pantalla.
  if ('IntersectionObserver' in window) {
    new IntersectionObserver((entries) => {
      const paused = !entries[entries.length - 1].isIntersecting;
      stage.querySelectorAll('.z-crest').forEach((c) => c.classList.toggle('is-paused', paused));
    }).observe(stage);
  }
  paintName();
})();
