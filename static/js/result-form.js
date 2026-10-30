// Validación en directo del resultado (mismas reglas que match/scoring.py). Hay un elemento
// [data-result] por partido: el formulario de un resultado, o cada partido en la pantalla
// «Poner resultados», que los muestra todos juntos.
document.querySelectorAll('[data-result]').forEach(function (form) {
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
    const icon = document.createElement('i');
    icon.className = `fa-solid ${ok === null ? 'fa-circle-info' : ok ? 'fa-check' : 'fa-xmark'}`;
    icon.setAttribute('aria-hidden', 'true');
    li.append(icon, document.createTextNode(' ' + text));
    checks.appendChild(li);
  }

  const retiredBox = form.querySelector('[data-retired]');
  // Sets de un partido acabado por lesión: 0-0 o vacío es un set sin jugar; un 0 con juegos del
  // rival (0-6) sí cuenta, como en scoring.py.
  const enteredSets = () => [1, 2, 3].map((n) => {
    const pair = [val(input(n, 'l')), val(input(n, 'v'))];
    return pair.every((x) => !x) ? [null, null] : pair;
  });

  // Partido finalizado por lesión: mismas reglas que scoring.validate_retired_result
  function refreshRetired() {
    const s = enteredSets();
    const played = [0, 1, 2].filter((i) => s[i][0] !== null || s[i][1] !== null);
    if (!played.length) return;
    const last = played[played.length - 1];
    let ok = true;
    for (let i = 0; i <= last; i++) {
      const [a, b] = s[i];
      if (a === null || b === null) { ok = false; line(false, interpolate(gettext('Set %(n)s: falta el resultado.'), { n: i + 1 }, true)); }
      else if (i < last && !validSet(a, b)) { ok = false; line(false, setInvalid(i + 1, a, b)); }
    }
    if (ok && last === 2 && (s[0][0] > s[0][1]) === (s[1][0] > s[1][1])) {
      ok = false;
      line(false, gettext('Set 3: no se juega si la misma pareja ha ganado los dos primeros sets. Déjalo vacío.'));
    }
    if (!ok) return;
    const entered = s.slice(0, last + 1);
    let l = entered.filter((x) => x[0] > x[1]).length;
    let v = entered.filter((x) => x[1] > x[0]).length;
    if (l === v) { l = entered.reduce((t, x) => t + x[0], 0); v = entered.reduce((t, x) => t + x[1], 0); }
    if (l === v) line(false, gettext('No se puede saber quién iba ganando: el resultado está empatado.'));
    else line(true, interpolate(gettext('Ganador del partido: %(team)s'), { team: names[l > v ? 0 : 1] }, true));
  }

  // Lesión (SNP y LAPI): la pareja sana gana y se completan sus juegos (scoring.complete_retired_result).
  const injuredBox = form.querySelector('[data-injured]');
  function refreshInjured() {
    const side = form.querySelector('[data-injured-side]:checked');
    if (!side) { line(null, gettext('Indica qué pareja se lesionó.')); return; }
    const flip = side.dataset.injuredSide === 'v';
    const s = enteredSets();
    const played = [0, 1, 2].filter((i) => s[i][0] !== null || s[i][1] !== null);
    const last = played.length ? played[played.length - 1] : -1;
    for (let i = 0; i <= last; i++) {
      const [a, b] = s[i];
      if (a === null || b === null) { line(false, interpolate(gettext('Set %(n)s: falta el resultado.'), { n: i + 1 }, true)); return; }
      if (i < last && !validSet(a, b)) { line(false, setInvalid(i + 1, a, b)); return; }
    }
    // (lesionada, sana) en cada set
    const own = s.slice(0, last + 1).map(([a, b]) => (flip ? [b, a] : [a, b]));
    if (own.length && !validSet(own[own.length - 1][0], own[own.length - 1][1])) {
      const [hurt, healthy] = own[own.length - 1];
      const target = hurt >= 5 ? 7 : 6;
      if (healthy > target || hurt > 6) { line(false, setInvalid(own.length, s[last][0], s[last][1])); return; }
      own[own.length - 1] = [hurt, target];
    }
    if (own.filter(([hurt, healthy]) => hurt > healthy).length >= 2) {
      line(false, gettext('El partido ya estaba decidido: no puede acabar por lesión.'));
      return;
    }
    while (own.filter(([hurt, healthy]) => healthy > hurt).length < 2) own.push([0, 6]);
    const score = own.map(([a, b]) => (flip ? `${b}-${a}` : `${a}-${b}`)).join(' / ');
    line(true, interpolate(gettext('Queda %(score)s. Ganador del partido: %(team)s'), { score: score, team: names[flip ? 0 : 1] }, true));
  }

  // «Pareja no presentada» (SNP): sin sets que rellenar; Zyra reparte los puntos al cerrar el acta.
  const noShow = form.querySelector('[data-pair-no-show]');
  const playedBox = form.querySelector('[data-played]');

  function refresh() {
    checks.innerHTML = '';
    if (noShow && playedBox) {
      playedBox.hidden = noShow.value !== '';
      if (noShow.value !== '') {
        line(null, gettext('Sin resultado: Zyra reparte los puntos al cerrar el acta (normativa SNP 20.2).'));
        return;
      }
    }
    if (injuredBox) injuredBox.hidden = !(retiredBox && retiredBox.checked);
    form.querySelectorAll('[data-retired-help]').forEach((el) => { el.hidden = !(retiredBox && retiredBox.checked); });
    if (retiredBox && retiredBox.checked) {
      input(3, 'l').disabled = input(3, 'v').disabled = false;
      if (injuredBox) refreshInjured(); else refreshRetired();
      return;
    }
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
  if (retiredBox) retiredBox.addEventListener('change', refresh);
  if (noShow) noShow.addEventListener('change', refresh);
  form.querySelectorAll('[data-injured-side]').forEach((el) => el.addEventListener('change', refresh));
  refresh();
});

// «Poner resultados»: «Guardar y cerrar acta» solo está activo cuando todos los partidos tienen resultado
// (o pareja no presentada), y al lado dice cuántos faltan.
(function () {
  const closeBtn = document.querySelector('[data-close-match]');
  if (!closeBtn) return;
  const hint = document.querySelector('[data-close-hint]');
  const cards = Array.from(document.querySelectorAll('[data-result]'));
  const filled = (v) => v && v.value.trim() !== '';
  const complete = (card) => {
    const noShow = card.querySelector('[data-pair-no-show]');
    if (noShow && noShow.value) return true;
    return ['set1_local', 'set1_visiting', 'set2_local', 'set2_visiting'].every((n) => filled(card.querySelector(`[name$="${n}"]`)));
  };
  function refreshClose() {
    const missing = cards.filter((c) => !complete(c));
    closeBtn.disabled = missing.length > 0;
    closeBtn.classList.toggle('disabled', missing.length > 0);
    if (hint) {
      hint.textContent = missing.length
        ? interpolate(ngettext('Falta %(n)s resultado para cerrar el acta', 'Faltan %(n)s resultados para cerrar el acta', missing.length), { n: missing.length }, true)
        : '';
    }
  }
  cards.forEach((c) => {
    c.addEventListener('input', refreshClose);
    c.addEventListener('change', refreshClose);
  });
  refreshClose();
})();
