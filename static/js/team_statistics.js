// Estadísticas del equipo (team_statistics.html): puntos de cada jornada o enfrentamiento (barras lima con la
// cifra dentro, solo las últimas) y puntos SNP del equipo por temporada (línea lima sin ejes, con el último
// valor en grande). El resto de la página son tarjetas sin gráfico.
(function () {
  const read = (id) => {
    const el = document.getElementById(id);
    return el ? JSON.parse(el.textContent) : null;
  };
  const lang = document.documentElement.lang || 'es';
  const LIME = '#B4F100';
  const shortSeason = (y) => y.replace(/^\d{2}(\d{2})-\d{2}(\d{2})$/, '$1-$2');
  const FONT = "400 22px 'Anton', 'Archivo', sans-serif";

  const pointsCanvas = document.getElementById('chartPoints');
  const points = read('points-card-data');
  if (pointsCanvas && points && points.values.length) {
    new Chart(pointsCanvas, {
      type: 'bar',
      data: {
        labels: points.labels,
        datasets: [{ label: gettext('Puntos'), data: points.values, backgroundColor: LIME, borderRadius: 14, minBarLength: 32, borderSkipped: false, maxBarThickness: 64 }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: { x: { grid: { display: false } }, y: { display: false, beginAtZero: true, grace: '8%' } },
      },
    });
  }

  const snpCanvas = document.getElementById('chartSnpTeamSeasons');
  const snp = read('snp-team-seasons');
  if (snpCanvas && snp && snp.scores.length > 1) {
    const lastValue = {
      id: 'lastValue',
      afterDatasetsDraw(chart) {
        const meta = chart.getDatasetMeta(0).data;
        const point = meta[meta.length - 1];
        if (!point) return;
        const { ctx, chartArea } = chart;
        ctx.save();
        ctx.font = FONT;
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
        datasets: [{ label: gettext('Puntos SNP'), data: snp.scores, borderColor: LIME, fill: true, borderWidth: 3, pointRadius: 0, pointHoverRadius: 6 }],
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
})();
