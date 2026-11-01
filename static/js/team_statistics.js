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
        datasets: [{ label: gettext('Puntos'), data: points.values, backgroundColor: LIME, borderRadius: 14, minBarLength: 32, borderSkipped: false }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        // Barras casi pegadas, como en el diseño.
        datasets: { bar: { barPercentage: 0.92, categoryPercentage: 1 } },
        plugins: { legend: { display: false } },
        scales: { x: { grid: { display: false } }, y: { display: false, beginAtZero: true, grace: '8%' } },
      },
    });
  }

  // Asistencia a las convocatorias: % de la plantilla que se apunta. Con «Todas» es la media por temporada;
  // con una temporada, una barra por convocatoria (la etiqueta lleva fecha y rival).
  const attCanvas = document.getElementById('attendanceChart');
  const att = read('attendance-data');
  if (attCanvas && att && att.rows.length > 1) {
    const rows = att.rows;
    new Chart(attCanvas, {
      type: 'bar',
      data: {
        labels: rows.map((r) => r.label),
        datasets: [{ label: gettext('Asistencia'), data: rows.map((r) => r.pct), backgroundColor: LIME, borderRadius: 14, minBarLength: 32, borderSkipped: false, maxBarThickness: 64 }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: (c) => ` ${rows[c.dataIndex].pct} % · ${rows[c.dataIndex].signed}/${rows[c.dataIndex].eligible}`,
              afterLabel: (c) => (rows[c.dataIndex].calls
                ? interpolate(ngettext('%s convocatoria', '%s convocatorias', rows[c.dataIndex].calls), [rows[c.dataIndex].calls])
                : ''),
            },
          },
        },
        scales: { x: { grid: { display: false }, ticks: { autoSkip: false, maxRotation: 45, font: { size: 11 } } }, y: { display: false, beginAtZero: true, max: 100 } },
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

// Balance por jugador: partidos de 2 y 3 puntos, ganados y perdidos.
(function () {
  const read = (id) => {
    const el = document.getElementById(id);
    return el ? JSON.parse(el.textContent) : null;
  };
  const LIME = '#B4F100';
  const LIME_DARK = '#6E9400';
  const CORAL = '#FF5C63';
  const CORAL_DARK = '#9E3A3F';
  const GRID = 'rgba(255, 255, 255, 0.08)';
  const balanceBox = document.getElementById('balanceChart');
  if (!balanceBox) return; // no sale en competiciones con parejas sorteadas (LAPI)
  // Barras horizontales de tamaño fijo: se ven PAGE_SIZE jugadores y el resto se
  // recorre con el paginador, así el gráfico mide lo mismo con 8 jugadores que con 60.
  const PAGE_SIZE = 10;
  const ROW_HEIGHT = 30;
  // Las series perdidas llevan rayas además del rojo (WCAG 1.4.1: no depender solo del color).
  const striped = (color) => {
    const tile = document.createElement('canvas');
    tile.width = tile.height = 10;
    const t = tile.getContext('2d');
    t.fillStyle = color;
    t.fillRect(0, 0, 10, 10);
    t.strokeStyle = 'rgba(10, 10, 10, 0.55)';
    t.lineWidth = 2.5;
    t.beginPath();
    t.moveTo(-2, 12);
    t.lineTo(12, -2);
    t.stroke();
    return t.createPattern(tile, 'repeat') || color;
  };
  const SERIES = [
    { label: gettext('3 puntos ganados'), index: 2, color: LIME },
    { label: gettext('2 puntos ganados'), index: 0, color: LIME_DARK },
    { label: gettext('3 puntos perdidos'), index: 3, color: striped(CORAL) },
    { label: gettext('2 puntos perdidos'), index: 1, color: striped(CORAL_DARK) },
  ];
  const players = (read('column-chart-data') || []).map((r) => ({
    name: r.player,
    data: r.data,
    played: r.data.reduce((a, b) => a + b, 0),
    won: r.data[0] + r.data[2],
  }));
  const SORTS = {
    played: (a, b) => b.played - a.played || b.won - a.won,
    won: (a, b) => b.won - a.won || b.played - a.played,
    name: (a, b) => a.name.localeCompare(b.name, undefined, { sensitivity: 'base' }),
  };
  const balance = { sort: 'played', page: 0 };
  const pageCount = Math.max(1, Math.ceil(players.length / PAGE_SIZE));
  const visibleRows = Math.max(1, Math.min(players.length, PAGE_SIZE));

  balanceBox.style.height = `${visibleRows * ROW_HEIGHT + 90}px`;

  // En pantallas estrechas: "Eduardo Bustamante Lucena" -> "E. Bustamante"
  const PARTICLES = new Set(['de', 'del', 'la', 'las', 'los', 'y', 'da', 'do', 'dos', 'van', 'von']);
  const shortName = (name, max) => {
    if (name.length <= max) return name;
    const parts = name.trim().split(/\s+/);
    const surname = parts.slice(1).find((w) => !PARTICLES.has(w.toLowerCase()));
    const short = surname ? `${parts[0][0]}. ${surname}` : name;
    return short.length <= max ? short : `${short.slice(0, max - 1)}…`;
  };
  const labelMax = () => (balanceBox.clientWidth < 520 ? 14 : 26);

  // La última página se rellena con filas vacías para que las barras no cambien de grosor.
  const pageRows = () => {
    const sorted = [...players].sort(SORTS[balance.sort]);
    const rows = sorted.slice(balance.page * PAGE_SIZE, (balance.page + 1) * PAGE_SIZE);
    while (rows.length < visibleRows) rows.push(null);
    return rows;
  };

  const balanceChart = new Chart(document.getElementById('myColumnChart'), {
    type: 'bar',
    data: { labels: [], datasets: SERIES.map((s) => ({ label: s.label, data: [], backgroundColor: s.color })) },
    options: {
      indexAxis: 'y',
      responsive: true,
      maintainAspectRatio: false,
      datasets: { bar: { barPercentage: 0.8, categoryPercentage: 0.9, maxBarThickness: 22 } },
      interaction: { mode: 'index', axis: 'y', intersect: false },
      plugins: {
        legend: { position: 'top' },
        tooltip: {
          filter: (item) => item.label !== '',
          callbacks: {
            footer: (items) => (items.length ? `${gettext('Partidos')}: ${items.reduce((a, i) => a + i.parsed.x, 0)}` : ''),
          },
        },
      },
      scales: {
        x: {
          stacked: true,
          beginAtZero: true,
          // Misma escala en todas las páginas para poder compararlas
          suggestedMax: Math.max(1, ...players.map((p) => p.played)),
          position: 'top',
          ticks: { precision: 0 },
          grid: { color: GRID },
          title: { display: true, text: gettext('Partidos') },
        },
        y: {
          stacked: true,
          grid: { display: false },
          ticks: {
            autoSkip: false,
            callback(value) { return shortName(this.getLabelForValue(value), labelMax()); },
          },
        },
      },
    },
  });

  const pager = document.getElementById('balancePager');
  const pagerInfo = pager.querySelector('.st-pager-info');
  const renderBalance = () => {
    const rows = pageRows();
    balanceChart.data.labels = rows.map((r) => (r ? r.name : ''));
    balanceChart.data.datasets.forEach((ds, i) => {
      ds.data = rows.map((r) => (r ? r.data[SERIES[i].index] : null));
    });
    balanceChart.update();

    pager.hidden = pageCount < 2;
    const first = balance.page * PAGE_SIZE + 1;
    const last = Math.min(players.length, first + PAGE_SIZE - 1);
    pagerInfo.textContent = interpolate(gettext('%(first)s–%(last)s de %(total)s'), { first, last, total: players.length }, true);
    pager.querySelector('[data-step="-1"]').disabled = balance.page === 0;
    pager.querySelector('[data-step="1"]').disabled = balance.page >= pageCount - 1;
  };

  pager.addEventListener('click', (e) => {
    const btn = e.target.closest('[data-step]');
    if (!btn || btn.disabled) return;
    balance.page += Number(btn.dataset.step);
    renderBalance();
  });
  document.querySelectorAll('.st-balance-sort [data-sort]').forEach((btn) => {
    btn.addEventListener('click', () => {
      balance.sort = btn.dataset.sort;
      balance.page = 0;
      document.querySelectorAll('.st-balance-sort [data-sort]').forEach((b) => b.setAttribute('aria-pressed', String(b === btn)));
      renderBalance();
    });
  });
  renderBalance();
})();

