// «Mis estadísticas · Todas» (stats_mine.html): cada gráfico pone las competiciones una al lado de la otra,
// con su color (dorado SNP, turquesa LAPI; en los gráficos que comparan, el color es lo que separa las series). Nunca suma puntos de una competición con otra.
(function () {
  const source = document.getElementById('spaces-chart-data');
  if (!source || typeof Chart === 'undefined') return;
  const data = JSON.parse(source.textContent);
  const COLORS = { snp: '#DBA400', lapi: '#61E2C9' };
  const color = (code) => COLORS[code] || '#A3A3A3';
  const comps = data.comps;

  Chart.defaults.font.family = "'Archivo', system-ui, sans-serif";
  Chart.defaults.color = '#A3A3A3';
  Chart.defaults.plugins.legend.labels.usePointStyle = true;
  Chart.defaults.plugins.legend.labels.boxWidth = 8;

  // % de victorias en casa y fuera de cada competición: barras redondeadas con su cifra dentro,
  // sin ejes ni cuadrícula (la leyenda va sobre los gráficos).
  const sidesCanvas = document.getElementById('spacesSidesChart');
  if (sidesCanvas) {
    new Chart(sidesCanvas, {
      type: 'bar',
      data: {
        labels: [gettext('En casa'), gettext('Fuera')],
        datasets: comps.map((c, i) => ({
          label: c.name, data: [data.totals[i].pct_local, data.totals[i].pct_visiting], backgroundColor: color(c.code), maxBarThickness: 96,
          borderRadius: 14, minBarLength: 32, borderColor: '#151515', borderWidth: 2,
        })),
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        datasets: { bar: { barPercentage: 1, categoryPercentage: 0.8 } },
        plugins: {
          legend: { display: false },
          tooltip: { callbacks: { label: (c) => `${c.dataset.label}: ${c.parsed.y} %` } },
        },
        scales: { x: { grid: { display: false } }, y: { display: false, beginAtZero: true, max: 100, grace: '8%' } },
      },
    });
  }

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
    // Columna apilada de una sola pieza: solo se redondean la base del primer tramo y la cima del último
    // con valor; los tramos intermedios quedan rectos y pegados.
    const stackRadius = (c) => {
      const sets = c.chart.data.datasets, j = c.dataIndex, i = c.datasetIndex;
      const has = (k) => (sets[k].data[j] || 0) > 0;
      const bottom = !sets.slice(0, i).some((_, k) => has(k));
      const top = !sets.slice(i + 1).some((_, k) => has(k + i + 1));
      const r = 14;
      return { topLeft: top ? r : 0, topRight: top ? r : 0, bottomLeft: bottom ? r : 0, bottomRight: bottom ? r : 0 };
    };
    const chart = new Chart(yearsCanvas, {
      type: 'bar',
      plugins: [totalOnTop],
      data: {
        labels: labels.map(seasonLabel),
        datasets: comps.map((c, i) => ({ label: c.name, data: data.years.won[i], backgroundColor: color(c.code), maxBarThickness: 72, barPercentage: 0.8, categoryPercentage: 0.9, borderRadius: stackRadius, borderSkipped: false, borderColor: '#151515', borderWidth: 2 })),
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        layout: { padding: { top: 16 } },
        interaction: { mode: 'index', intersect: false },
        plugins: {
          legend: { display: false },
          tooltip: { callbacks: { footer: (items) => `${gettext('Total')}: ${totals[items[0].dataIndex]}` } },
        },
        scales: {
          x: { stacked: true, grid: { display: false }, ticks: { autoSkip: false, maxRotation: 0, font: { size: 12 } } },
          y: { stacked: true, display: false, beginAtZero: true, grace: '12%' },
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
    // Con una sola temporada una línea no dibuja nada: barras, una por competición.
    const single = data.attendance.labels.length === 1;
    // El último valor de cada línea, en Anton junto a su final (diseño aprobado: sin ejes).
    const endLabels = {
      id: 'endLabels',
      afterDatasetsDraw(chart) {
        if (single) return;
        const { ctx, chartArea } = chart;
        ctx.save();
        ctx.font = "400 18px 'Anton', 'Archivo', sans-serif";
        ctx.fillStyle = '#FFFFFF';
        ctx.textAlign = 'right';
        ctx.textBaseline = 'bottom';
        const placed = [];
        chart.data.datasets.forEach((ds, i) => {
          const points = chart.getDatasetMeta(i).data;
          for (let j = points.length - 1; j >= 0; j--) {
            if (ds.data[j] === null || ds.data[j] === undefined) continue;
            const key = `${Math.round(points[j].x)}-${ds.data[j]}`;
            if (!placed.includes(key)) {
              placed.push(key);
              ctx.fillText(`${ds.data[j]}%`, Math.min(points[j].x, chartArea.right), points[j].y - 8);
            }
            break;
          }
        });
        ctx.restore();
      },
    };
    new Chart(attCanvas, {
      type: single ? 'bar' : 'line',
      plugins: [endLabels],
      data: {
        labels: data.attendance.labels,
        datasets: comps.map((c, i) => ({
          label: c.name,
          data: data.attendance.series[i],
          // Líneas: su color y 4 px; barras (una sola temporada): borde del fondo como hueco entre ellas.
          borderColor: single ? '#151515' : color(c.code),
          backgroundColor: color(c.code),
          spanGaps: true,
          tension: 0.3,
          borderWidth: single ? 2 : 4,
          pointRadius: 0,
          pointHoverRadius: 6,
          maxBarThickness: 48,
          borderRadius: 12,
        })),
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        layout: { padding: { top: 26, right: 8 } },
        datasets: { bar: { barPercentage: 1, categoryPercentage: 0.8 } },
        interaction: { mode: 'index', intersect: false },
        plugins: {
          legend: { display: false },
          tooltip: { callbacks: { label: (c) => (c.parsed.y === null ? null : `${c.dataset.label}: ${c.parsed.y} %`) } },
        },
        scales: {
          x: { grid: { display: false }, ticks: { maxRotation: 45, font: { size: 11 } } },
          y: { display: false, min: 0, max: 105 },
        },
      },
    });
  }
})();
