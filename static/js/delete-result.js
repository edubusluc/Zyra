// «Borrar resultado»: borra sin recargar ni mover la pantalla.
// - En «Poner resultados» el botón limpia el partido entero (sets, lesión y «pareja no presentada»), esté guardado
//   o no; si había un resultado guardado, además lo borra en el servidor (formulario data-delete-result).
// - En la ficha el borrado recarga conservando la posición.
// Si el envío falla, se usa el formulario de la forma clásica.
(function () {
  function clearCard(card) {
    card.querySelectorAll('input[data-set]').forEach((input) => { input.value = ''; });
    card.querySelectorAll('input[type="checkbox"]').forEach((box) => { box.checked = false; });
    card.querySelectorAll('select').forEach((select) => { select.selectedIndex = 0; });
    card.querySelectorAll('.z-badge--lime').forEach((badge) => badge.remove());
    const first = card.querySelector('input[data-set]');
    if (first) first.dispatchEvent(new Event('input', { bubbles: true }));
    card.querySelectorAll('select').forEach((select) => select.dispatchEvent(new Event('change', { bubbles: true })));
  }

  document.addEventListener('click', function (event) {
    const button = event.target.closest?.('[data-clear-result]');
    if (!button) return;
    event.preventDefault();
    const card = button.closest('fieldset[data-result]');
    const form = button.dataset.deleteForm && document.getElementById(button.dataset.deleteForm);
    if (form) {
      form.requestSubmit();
    } else if (card) {
      clearCard(card);
    }
  });

  document.addEventListener('submit', function (event) {
    const form = event.target;
    if (!form.matches?.('form[data-delete-result]')) return;
    event.preventDefault();
    fetch(form.action, {
      method: 'POST', body: new FormData(form), credentials: 'same-origin',
      headers: { 'X-Requested-With': 'XMLHttpRequest' },
    }).then((response) => response.json().then((data) => ({ ok: response.ok && data.ok }))).then((done) => {
      if (!done.ok) throw new Error('delete-result');
      const card = document.getElementById('partido-' + form.dataset.deleteResult);
      if (card?.matches('fieldset[data-result]')) {
        clearCard(card);
        document.querySelectorAll('[data-delete-form="' + form.id + '"]').forEach((button) => button.removeAttribute('data-delete-form'));
        form.remove();
      } else {
        window.location.reload();
      }
    }).catch(() => form.submit());
  }, true);
})();
