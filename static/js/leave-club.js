// «Abandonar el club» (core/templates/base.html): cuando el capitán es el único miembro,
// el botón de eliminar el club solo se activa al escribir el nombre del club. El servidor
// vuelve a comprobarlo (core.views.leave_club).
(function () {
  const form = document.querySelector('[data-delete-club]');
  if (!form) return;
  const input = form.querySelector('[data-club-name]');
  const submit = form.querySelector('[data-delete-club-submit]');
  const normalize = (t) => t.trim().toLocaleLowerCase();
  const check = () => { submit.disabled = normalize(input.value) !== normalize(input.dataset.clubName); };
  input.addEventListener('input', check);
  check();
})();
