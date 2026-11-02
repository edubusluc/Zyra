// «i» de las tarjetas de estadísticas: con el ratón o el foco sale la explicación (CSS, atributo data-tip);
// al pulsar (móvil) se abre y se cierra, y al pulsar fuera se cierra.
(function () {
  const closeAll = () => document.querySelectorAll('.z-tip.is-open').forEach((t) => {
    t.classList.remove('is-open');
    t.setAttribute('aria-expanded', 'false');
  });
  document.querySelectorAll('.z-tip').forEach((tip) => {
    tip.addEventListener('click', (e) => {
      e.stopPropagation();
      const open = !tip.classList.contains('is-open');
      closeAll();
      // En móvil el globo es fijo y ancho: se coloca justo debajo del «i» pulsado.
      tip.style.setProperty('--tip-y', `${Math.round(tip.getBoundingClientRect().bottom + 8)}px`);
      tip.classList.toggle('is-open', open);
      tip.setAttribute('aria-expanded', String(open));
    });
  });
  document.addEventListener('click', closeAll);
  window.addEventListener('scroll', closeAll, { passive: true });
})();
