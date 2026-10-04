// Alineación de parejas: evita repetir jugadores, muestra en vivo el orden por
// puntos SNP (columna derecha) y solo deja guardar cuando las 5 parejas están completas.
(function () {
  const form = document.querySelector('[data-lineup]');
  if (!form) return;
  const slots = Array.from(form.querySelectorAll('[data-slot]'));
  const selects = Array.from(form.querySelectorAll('select[data-player]'));
  const list = document.getElementById('pair-order-list');

  function refresh() {
    const chosen = selects.map((s) => s.value).filter(Boolean);
    selects.forEach(function (s) {
      Array.from(s.options).forEach(function (o) {
        const takenElsewhere = o.value && o.value !== s.value && chosen.includes(o.value);
        o.disabled = takenElsewhere;
        o.hidden = takenElsewhere;
      });
    });

    const pairs = [];
    slots.forEach(function (slot) {
      const [a, b] = slot.querySelectorAll('select[data-player]');
      if (!a.value || !b.value) return;
      const oa = a.selectedOptions[0], ob = b.selectedOptions[0];
      pairs.push({
        gameId: slot.dataset.gameId || null,
        player1Id: a.value,
        player2Id: b.value,
        label: interpolate(gettext('%(a)s y %(b)s'), { a: oa.dataset.short || oa.textContent.trim(), b: ob.dataset.short || ob.textContent.trim() }, true),
        points: (parseFloat(oa.dataset.points) || 0) + (parseFloat(ob.dataset.points) || 0),
      });
    });
    pairs.sort((x, y) => y.points - x.points);

    list.innerHTML = '';
    slots.forEach(function (_slot, i) {
      const p = pairs[i];
      const li = document.createElement('li');
      if (!p) li.className = 'is-empty';
      const body = document.createElement('div');
      const top = document.createElement('p');
      const head = document.createElement('small');
      head.textContent = interpolate(gettext('Partido %(n)s · %(value)s puntos'), { n: i + 1, value: i < 2 ? 3 : 2 }, true);
      top.appendChild(head);
      if (p) {
        const pts = document.createElement('b');
        pts.textContent = interpolate(gettext('%(points)s pts'), { points: Math.round(p.points * 10) / 10 }, true);
        top.appendChild(pts);
      }
      const name = document.createElement('span');
      name.textContent = p ? p.label : gettext('Pareja sin completar');
      body.append(top, name);
      li.appendChild(body);
      list.appendChild(li);
    });

    const complete = pairs.length === slots.length;
    form.querySelector('[data-lineup-output]').value = JSON.stringify(
      pairs.map((p) => ({ gameId: p.gameId, player1Id: p.player1Id, player2Id: p.player2Id }))
    );
    form.querySelector('[data-lineup-count]').textContent = pairs.length;
    form.querySelector('[data-lineup-hint]').textContent = complete ? '' : gettext('Completa todas las parejas para guardar');
    form.querySelector('[data-lineup-save]').disabled = !complete;
  }

  selects.forEach((s) => s.addEventListener('change', refresh));
  // «Resetear» deja en blanco los dos jugadores de esa pareja de una vez
  slots.forEach(function (slot) {
    slot.querySelector('[data-slot-reset]').addEventListener('click', function () {
      slot.querySelectorAll('select[data-player]').forEach(function (s) {
        if (!s.value) return;
        s.value = '';
        s.dispatchEvent(new Event('change', { bubbles: true }));
      });
    });
  });
  form.addEventListener('submit', function () {
    form.querySelector('[data-lineup-save]').disabled = true; // evita el doble envío
  });
  refresh();
})();
