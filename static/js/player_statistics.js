// Ficha de jugador (player_statistics.html): puntos SNP al cierre de cada temporada (zSeasonLine, en chart-style.js).
(function () {
  const read = (id) => {
    const el = document.getElementById(id);
    return el ? JSON.parse(el.textContent) : null;
  };
  const snpCanvas = document.getElementById('chartSnpSeasons');
  const snp = read('data-snp-seasons');
  if (snpCanvas && snp && snp.scores.length > 1) zSeasonLine(snpCanvas, snp);
})();
