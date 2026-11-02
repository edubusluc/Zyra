// Ficha de jugador (player_statistics.html): puntos SNP al cierre de cada temporada (zSeasonLine, en chart-style.js).
(function () {
  const read = (id) => {
    const el = document.getElementById(id);
    return el ? JSON.parse(el.textContent) : null;
  };
  const snpCanvas = document.getElementById('chartSnpSeasons');
  const snp = read('data-snp-seasons');
  if (snpCanvas && snp && snp.scores.length > 1) zSeasonLine(snpCanvas, snp);

  // Con «Todas»: partidos ganados y perdidos de cada temporada y evolución del % de victorias.
  zSeasonCharts(read('data-seasons'), document.getElementById('chartPlayed'), document.getElementById('chartPct'));

  // Un gráfico dentro de «Profundizar» se dibuja con el panel cerrado: al abrirlo se recalcula su tamaño.
  document.querySelectorAll('.st-fold').forEach((fold) => fold.addEventListener('toggle', () => window.dispatchEvent(new Event('resize'))));
})();
