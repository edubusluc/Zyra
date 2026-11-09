// Baja de plantilla: al guardar cambios que sacan a jugadores del equipo se pide confirmación en el popup de
// Zyra (confirm-modal.js lee el atributo data-confirm del formulario al enviarlo). Este script lo pone o lo quita
// según las casillas «en el equipo» (input[name="in_team"]) que se han desmarcado respecto a como estaban
// (data-initial="1") y avisa de las cuentas enlazadas (data-linked="1"), que además de salir de la plantilla salen
// del equipo. Textos en el formulario: data-baja-one / data-baja-many ({n}) y data-baja-accounts ({names}).
// Sin JavaScript el formulario se envía sin pedir confirmación.
(function () {
  document.querySelectorAll('form[data-baja-confirm]').forEach(function (form) {
    const boxes = Array.from(form.querySelectorAll('input[name="in_team"][data-initial]'));
    if (!boxes.length) return;

    function nameOf(box) {
      const row = box.closest('[data-name]');
      return (row ? row.dataset.name : box.dataset.name) || '';
    }

    function refresh() {
      const leaving = boxes.filter((b) => b.dataset.initial === '1' && !b.checked);
      if (!leaving.length) {
        form.removeAttribute('data-confirm');
        return;
      }
      const linked = leaving.filter((b) => b.dataset.linked === '1').map(nameOf);
      const head = (leaving.length === 1 ? form.dataset.bajaOne : form.dataset.bajaMany).replace('{n}', leaving.length);
      const tail = linked.length ? ' ' + form.dataset.bajaAccounts.replace('{names}', linked.join(', ')) : '';
      form.setAttribute('data-confirm', head + tail);
    }

    boxes.forEach((b) => b.addEventListener('change', refresh));
    form.addEventListener('roster-refresh', refresh);
    form.addEventListener('reset', () => setTimeout(refresh));
    refresh();
  });
})();
