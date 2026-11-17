// «Reparto por partidos» (includes/game_share.html): al pasar el ratón o enfocar una fila de la leyenda, o un
// sector del anillo, se resalta ese partido y el centro muestra su recuento y porcentaje.
(function () {
  document.querySelectorAll('[data-game-share]').forEach((box) => {
    const mid = box.querySelector('[data-gs-mid]');
    if (!mid || !box.querySelector('.st-gs-seg')) return;
    const original = mid.innerHTML;
    const show = (n) => {
      box.classList.toggle('is-dim', n !== null);
      box.querySelectorAll('.st-gs-seg').forEach((s) => s.classList.toggle('is-on', s.dataset.n === n));
      box.querySelectorAll('.st-gs-legend li').forEach((li) => li.classList.toggle('is-on', li.dataset.n === n));
      const li = n === null ? null : box.querySelector(`.st-gs-legend li[data-n="${n}"]`);
      if (!li || !li.dataset.center) { mid.innerHTML = original; return; }
      mid.innerHTML = '';
      const b = document.createElement('b');
      b.textContent = li.dataset.center;
      const small = document.createElement('small');
      small.textContent = li.dataset.centerLabel;
      mid.append(b, small);
    };
    box.querySelectorAll('.st-gs-seg, .st-gs-legend li[data-center]').forEach((el) => {
      el.addEventListener('mouseenter', () => show(el.dataset.n));
      el.addEventListener('mouseleave', () => show(null));
      el.addEventListener('focus', () => show(el.dataset.n));
      el.addEventListener('blur', () => show(null));
    });
  });
})();
