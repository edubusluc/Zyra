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
  const seasons = read('data-seasons');
  const shortSeason = (y) => y.replace(/^\d{2}(\d{2})-\d{2}(\d{2})$/, '$1-$2');
  const playedCanvas = document.getElementById('chartPlayed');
  if (playedCanvas && seasons) {
    // Tramos pegados: solo se redondean la base del primero y la cima del último.
    const edge = (ctx) => {
      const filled = ctx.chart.data.datasets.map((d, i) => (Number(d.data[ctx.dataIndex]) > 0 ? i : -1)).filter((i) => i >= 0);
      const bottom = ctx.datasetIndex === filled[0] ? 10 : 0;
      const top = ctx.datasetIndex === filled[filled.length - 1] ? 10 : 0;
      return { topLeft: top, topRight: top, bottomLeft: bottom, bottomRight: bottom };
    };
    const bar = (label, data, color) => ({ label, data, backgroundColor: color, borderRadius: edge, borderSkipped: false, borderWidth: 0, maxBarThickness: 64 });
    new Chart(playedCanvas, {
      type: 'bar',
      data: {
        labels: seasons.labels.map(shortSeason),
        datasets: [bar(gettext('Ganados'), seasons.wins, '#B4F100'), bar(gettext('Perdidos'), seasons.losses, '#FF5C63')],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { position: 'bottom', labels: { usePointStyle: true, pointStyle: 'rectRounded', boxWidth: 10 } } },
        scales: { x: { stacked: true, grid: { display: false } }, y: { stacked: true, display: false, beginAtZero: true } },
      },
    });
  }
  const pctCanvas = document.getElementById('chartPct');
  if (pctCanvas && seasons && seasons.pct.length > 1) {
    zSeasonLine(pctCanvas, { labels: seasons.labels, scores: seasons.pct }, {
      label: gettext('% victorias'),
      format: (v) => `${Math.round(v)}%`,
      y: { min: 0, max: 100, grace: 0 },
    });
  }
})();
