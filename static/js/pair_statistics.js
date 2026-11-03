// Ficha de la pareja (pair_statistics.html): partidos jugados y % de victorias por temporada (zSeasonCharts, en chart-style.js).
(function () {
  zSeasonCharts(JSON.parse(document.getElementById('data-seasons').textContent), document.getElementById('chartPlayed'), document.getElementById('chartPct'));
})();
