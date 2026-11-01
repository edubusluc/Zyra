// Ficha de jugador (player_statistics.html): puntos SNP al cierre de cada temporada (línea lima sin ejes, con el
// último valor en grande) y, en competiciones sin puntos SNP, partidos ganados y perdidos por temporada.
(function () {
  const read = (id) => {
    const el = document.getElementById(id);
    return el ? JSON.parse(el.textContent) : null;
  };
  const lang = document.documentElement.lang || 'es';
  const LIME = '#B4F100';
  const CORAL = '#FF5C63';
  const shortSeason = (y) => y.replace(/^\d{2}(\d{2})-\d{2}(\d{2})$/, '$1-$2');

  const snpCanvas = document.getElementById('chartSnpSeasons');
  const snp = read('data-snp-seasons');
  if (snpCanvas && snp && snp.scores.length > 1) {
    const lastValue = {
      id: 'lastValue',
      afterDatasetsDraw(chart) {
        const meta = chart.getDatasetMeta(0).data;
        const point = meta[meta.length - 1];
        if (!point) return;
        const { ctx, chartArea } = chart;
        ctx.save();
        ctx.font = "400 22px 'Anton', 'Archivo', sans-serif";
        ctx.fillStyle = '#FFFFFF';
        ctx.textAlign = 'right';
        ctx.textBaseline = 'bottom';
        ctx.fillText(snp.scores[snp.scores.length - 1].toLocaleString(lang), Math.min(point.x + 8, chartArea.right + 8), point.y - 10);
        ctx.restore();
      },
    };
    new Chart(snpCanvas, {
      type: 'line',
      plugins: [lastValue],
      data: {
        labels: snp.labels.map(shortSeason),
        datasets: [{ label: gettext('Puntos SNP'), data: snp.scores, borderColor: LIME, fill: false, borderWidth: 3, pointRadius: 0, pointHoverRadius: 6 }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        layout: { padding: { top: 34, right: 16 } },
        plugins: {
          legend: { display: false },
          tooltip: { callbacks: { label: (c) => ' ' + interpolate(gettext('%(n)s puntos'), { n: c.parsed.y.toLocaleString(lang) }, true) } },
        },
        scales: { x: { grid: { display: false } }, y: { display: false, grace: '12%' } },
      },
    });
  }

  const playedCanvas = document.getElementById('chartPlayed');
  const seasons = read('data-seasons');
  if (playedCanvas && seasons && seasons.labels.length) {
    // Las dos barras de cada temporada van pegadas: el ancho del grupo es el de dos barras de 56 px como mucho.
    const group = () => Math.min(0.5, (2 * 56) / Math.max(1, playedCanvas.parentElement.clientWidth / seasons.labels.length));
    const played = new Chart(playedCanvas, {
      type: 'bar',
      data: {
        labels: seasons.labels.map(shortSeason),
        datasets: [
          { label: gettext('Ganados'), data: seasons.wins, backgroundColor: LIME, borderRadius: 14, minBarLength: 14, borderColor: '#151515', borderWidth: 2 },
          { label: gettext('Perdidos'), data: seasons.losses, backgroundColor: CORAL, borderRadius: 14, minBarLength: 14, borderColor: '#151515', borderWidth: 2 },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        datasets: { bar: { barPercentage: 1, categoryPercentage: group() } },
        plugins: { legend: { display: false } },
        scales: { x: { grid: { display: false } }, y: { display: false, beginAtZero: true, grace: '8%' } },
      },
    });
    window.addEventListener('resize', () => {
      played.options.datasets.bar.categoryPercentage = group();
      played.update('none');
    });
  }
})();
