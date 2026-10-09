// Validación en directo del resultado (mismas reglas que match/scoring.py).
(function () {
  const form = document.querySelector('[data-result]');
  if (!form) return;
  const input = (set, side) => form.querySelector(`[data-set="${set}"][data-side="${side}"]`);
  const val = (el) => (el.value.trim() === '' ? null : parseInt(el.value, 10));
  const VALID = ['6-0', '6-1', '6-2', '6-3', '6-4', '7-5', '7-6'];
  const validSet = (a, b) => VALID.includes(`${Math.max(a, b)}-${Math.min(a, b)}`);
  const validTB = (a, b) => { const h = Math.max(a, b), l = Math.min(a, b); return h >= 10 && (h === 10 ? h - l >= 2 : h - l === 2); };
  const checks = form.querySelector('[data-result-checks]');
  const names = Array.from(form.querySelectorAll('.z-result-team')).map((e) => e.textContent.trim());

  const setInvalid = (n, a, b) =>
    interpolate(gettext('Set %(n)s: %(score)s no es un resultado válido'), { n: n, score: `${a}-${b}` }, true);

  function line(ok, text) {
    const li = document.createElement('li');
    li.className = ok === null ? '' : ok ? 'is-ok' : 'is-bad';
    li.innerHTML = `<i class="fa-solid ${ok === null ? 'fa-circle-info' : ok ? 'fa-check' : 'fa-xmark'}" aria-hidden="true"></i> `;
    li.appendChild(document.createTextNode(text));
    checks.appendChild(li);
  }

  function refresh() {
    checks.innerHTML = '';
    const s = [1, 2, 3].map((n) => [val(input(n, 'l')), val(input(n, 'v'))]);
    const winners = [];
    let ok = true;

    [0, 1].forEach(function (i) {
      const [a, b] = s[i];
      if (a === null || b === null) { ok = false; return; }
      const good = validSet(a, b);
      ok = ok && good;
      // Solo se avisa de los sets no válidos; el ganador de cada set no se muestra.
      if (good) winners.push(a > b ? 0 : 1);
      else line(false, setInvalid(i + 1, a, b));
    });

    const split = winners.length === 2 && winners[0] !== winners[1];
    [input(3, 'l'), input(3, 'v')].forEach(function (el) {
      el.disabled = winners.length === 2 && !split;
      if (el.disabled) el.value = '';
    });

    if (split) {
      const [a, b] = s[2];
      if (a === null || b === null) ok = false;
      else {
        const good = validSet(a, b) || validTB(a, b);
        ok = ok && good;
        if (good) winners.push(a > b ? 0 : 1);
        else line(false, setInvalid(3, a, b));
      }
    }

    if (ok && winners.length >= 2) {
      const w = winners.filter((x) => x === 0).length >= 2 ? 0 : 1;
      line(true, interpolate(gettext('Ganador del partido: %(team)s'), { team: names[w] }, true));
    }
  }

  const order = ['1l', '1v', '2l', '2v', '3l', '3v'].map((k) => input(k[0], k[1]));
  order.forEach(function (el, i) {
    el.addEventListener('input', function () {
      el.value = el.value.replace(/\D/g, '');
      refresh();
      // Sets 1 y 2 tienen un solo dígito: se salta a la siguiente casilla
      if (el.value.length === 1 && el.dataset.set !== '3') {
        const next = order.slice(i + 1).find((x) => !x.disabled);
        if (next) next.focus();
      }
    });
    el.addEventListener('focus', () => el.select());
  });
  refresh();
})();
