// «Mis estadísticas · Todas» (stats_mine.html): cada gráfico pone las competiciones una al lado de la otra,
// con su color (lima SNP, azul LAPI). Nunca suma puntos de una competición con otra.
(function () {
  const source = document.getElementById('spaces-chart-data');
  if (!source || typeof Chart === 'undefined') return;
  const data = JSON.parse(source.textContent);
  const COLORS = { snp: '#B4F100', lapi: '#3D8BE0' };
  const color = (code) => COLORS[code] || '#A3A3A3';
  const comps = data.comps;

  Chart.defaults.font.family = "'Archivo', system-ui, sans-serif";
  Chart.defaults.color = '#A3A3A3';
  Chart.defaults.borderColor = 'rgba(255, 255, 255, 0.08)';
  Chart.defaults.plugins.legend.labels.usePointStyle = true;
  Chart.defaults.plugins.legend.labels.boxWidth = 8;
  const grid = 'rgba(255, 255, 255, 0.08)';
  const legend = { position: 'top', labels: { boxWidth: 8, boxHeight: 8, padding: 12, font: { size: 12 } } };

  // Partidos ganados y perdidos como local / visitante: una barra por competición en cada grupo.
  const sideChart = (id, rows) => {
    const canvas = document.getElementById(id);
    if (!canvas) return;
    new Chart(canvas, {
      type: 'bar',
      data: {
        labels: [gettext('Ganados'), gettext('Perdidos')],
        datasets: comps.map((c, i) => ({
          label: c.name, data: [rows[i].won, rows[i].lost], backgroundColor: color(c.code), borderRadius: 6, maxBarThickness: 48,
        })),
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend },
        scales: { x: { grid: { display: false } }, y: { beginAtZero: true, ticks: { precision: 0 }, grid: { color: grid } } },
      },
    });
  };
  sideChart('spacesLocalChart', data.local);
  sideChart('spacesVisitingChart', data.visiting);

  // Partidos ganados por temporada: apilados por competición y el total encima de cada columna.
  const yearsCanvas = document.getElementById('spacesYearsChart');
  if (yearsCanvas) {
    const labels = data.years.labels;
    const narrow = () => yearsCanvas.parentElement.clientWidth < 520;
    const seasonLabel = (y) => {
      const text = narrow() ? y.replace(/^\d{2}(\d{2})-\d{2}(\d{2})$/, '$1-$2') : y;
      return y === data.currentSeason ? [text, gettext('en curso')] : text;
    };
    const totals = labels.map((_, j) => data.years.won.reduce((sum, serie) => sum + (serie[j] || 0), 0));
    const totalOnTop = {
      id: 'totalOnTop',
      afterDatasetsDraw(chart) {
        const { ctx } = chart;
        const last = chart.data.datasets.length - 1;
        ctx.save();
        ctx.font = `600 12px ${Chart.defaults.font.family}`;
        ctx.fillStyle = '#FFFFFF';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'bottom';
        chart.getDatasetMeta(last).data.forEach((bar, j) => {
          if (totals[j] > 0) ctx.fillText(totals[j], bar.x, chart.scales.y.getPixelForValue(totals[j]) - 3);
        });
        ctx.restore();
      },
    };
    const chart = new Chart(yearsCanvas, {
      type: 'bar',
      plugins: [totalOnTop],
      data: {
        labels: labels.map(seasonLabel),
        datasets: comps.map((c, i) => ({ label: c.name, data: data.years.won[i], backgroundColor: color(c.code), maxBarThickness: 44 })),
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        layout: { padding: { top: 16 } },
        interaction: { mode: 'index', intersect: false },
        plugins: {
          legend,
          tooltip: { callbacks: { footer: (items) => `${gettext('Total')}: ${totals[items[0].dataIndex]}` } },
        },
        scales: {
          x: { stacked: true, grid: { display: false }, ticks: { autoSkip: false, maxRotation: 0, font: { size: 12 } } },
          y: { stacked: true, beginAtZero: true, grace: '12%', ticks: { precision: 0 }, grid: { color: grid } },
        },
      },
    });
    window.addEventListener('resize', () => {
      chart.data.labels = labels.map(seasonLabel);
      chart.update('none');
    });
  }

  // Convocatorias en las que te apuntas: una línea por competición, por temporada.
  const attCanvas = document.getElementById('spacesAttendanceChart');
  if (attCanvas) {
    new Chart(attCanvas, {
      type: 'line',
      data: {
        labels: data.attendance.labels,
        datasets: comps.map((c, i) => ({
          label: c.name,
          data: data.attendance.series[i],
          borderColor: color(c.code),
          backgroundColor: color(c.code),
          spanGaps: true,
          tension: 0.3,
          pointRadius: 4,
        })),
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        plugins: {
          legend,
          tooltip: { callbacks: { label: (c) => (c.parsed.y === null ? null : `${c.dataset.label}: ${c.parsed.y} %`) } },
        },
        scales: {
          x: { grid: { display: false }, ticks: { maxRotation: 45, font: { size: 11 } } },
          y: { min: 0, max: 100, ticks: { stepSize: 25, callback: (v) => `${v} %` }, grid: { color: grid } },
        },
      },
    });
  }
})();
