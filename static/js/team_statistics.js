// Estadísticas del equipo (team_statistics.html): puntos por jornada (o por temporada con «Todas»), asistencia,
// balance por jugador, ranking SNP y puntos SNP por temporada (gráficos lima sin ejes) y panel lateral de secciones.
(function () {
  const read = (id) => {
    const el = document.getElementById(id);
    return el ? JSON.parse(el.textContent) : null;
  };
  const LIME = '#B4F100';
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
  if (snpCanvas && snp && snp.scores.length > 1) zSeasonLine(snpCanvas, snp);
  // Balance por jugador: partidos de 2 y 3 puntos, ganados y perdidos.
  const LIME_DARK = '#6E9400';
  const CORAL = '#FF5C63';
  const CORAL_DARK = '#9E3A3F';
    const balanceSetup = () => {
  const balanceBox = document.getElementById('balanceChart');
  if (!balanceBox) return; // no sale en competiciones con parejas sorteadas (LAPI)
  // Barras horizontales de tamaño fijo: se ven PAGE_SIZE jugadores y el resto se
  // recorre con el paginador, así el gráfico mide lo mismo con 8 jugadores que con 60.
  const PAGE_SIZE = 10;
  const ROW_HEIGHT = 44;
  // Los tramos de una misma barra van pegados: solo se redondean los dos extremos de la barra completa.
  const RADIUS = 12;
  const edgeRadius = (ctx) => {
    const sets = ctx.chart.data.datasets;
    const filled = sets.map((d, i) => (Number(d.data[ctx.dataIndex]) > 0 ? i : -1)).filter((i) => i >= 0);
    const first = ctx.datasetIndex === filled[0];
    const last = ctx.datasetIndex === filled[filled.length - 1];
    return { topLeft: first ? RADIUS : 0, bottomLeft: first ? RADIUS : 0, topRight: last ? RADIUS : 0, bottomRight: last ? RADIUS : 0 };
  };
  const SERIES = [
    { label: gettext('3 puntos ganados'), index: 2, color: LIME },
    { label: gettext('2 puntos ganados'), index: 0, color: LIME_DARK },
    { label: gettext('3 puntos perdidos'), index: 3, color: CORAL },
    { label: gettext('2 puntos perdidos'), index: 1, color: CORAL_DARK },
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

  balanceBox.style.height = `${visibleRows * ROW_HEIGHT + 50}px`;

  // En pantallas estrechas: "Eduardo Bustamante Lucena" -> "E. Bustamante"
  const PARTICLES = new Set(['de', 'del', 'la', 'las', 'los', 'y', 'da', 'do', 'dos', 'van', 'von']);
  const shortName = (name, max) => {
    if (name.length <= max) return name;
    const parts = name.trim().split(/\s+/);
    const surname = parts.slice(1).find((w) => !PARTICLES.has(w.toLowerCase()));
    const short = surname ? `${parts[0][0]}. ${surname}` : name;
    return short.length <= max ? short : `${short.slice(0, max - 1)}…`;
  };
  const labelMax = () => (balanceBox.clientWidth < 520 ? 14 : 28);

  // La última página se rellena con filas vacías para que las barras no cambien de grosor.
  const pageRows = () => {
    const sorted = [...players].sort(SORTS[balance.sort]);
    const rows = sorted.slice(balance.page * PAGE_SIZE, (balance.page + 1) * PAGE_SIZE);
    while (rows.length < visibleRows) rows.push(null);
    return rows;
  };

  const balanceChart = new Chart(document.getElementById('myColumnChart'), {
    type: 'bar',
    data: { labels: [], datasets: SERIES.map((s) => ({ label: s.label, data: [], backgroundColor: s.color, borderRadius: edgeRadius, borderSkipped: false, borderWidth: 0 })) },
    options: {
      indexAxis: 'y',
      responsive: true,
      maintainAspectRatio: false,
      datasets: { bar: { barPercentage: 0.8, categoryPercentage: 0.9, maxBarThickness: 30 } },
      interaction: { mode: 'index', axis: 'y', intersect: false },
      plugins: {
        legend: { position: 'top', labels: { usePointStyle: true, pointStyle: 'rectRounded', boxWidth: 10 } },
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
          display: false,
        },
        y: {
          stacked: true,
          grid: { display: false },
          ticks: {
            autoSkip: false,
            color: '#E8E8E8',
            font: { size: 14, weight: '600' },
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
  };
  balanceSetup();

  // Ranking SNP: media del equipo en cada actualización y botón para ver toda la plantilla.
  const rankCanvas = document.getElementById('chartSnpTeam');
  const rank = read('snp-team-data');
  if (rankCanvas && rank && rank.average.length > 1) {
    new Chart(rankCanvas, {
      type: 'line',
      data: {
        labels: rank.labels,
        datasets: [{
          label: gettext('Media del equipo'),
          data: rank.average,
          borderColor: LIME,
          backgroundColor: 'rgba(180, 241, 0, 0.12)',
          fill: true,
          tension: 0.3,
          pointRadius: 3,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: { x: { grid: { display: false } }, y: { display: false } },
      },
    });
  }
  const more = document.querySelector('[data-snp-more]');
  if (more) {
    const label = more.textContent;
    more.addEventListener('click', () => {
      const rows = document.querySelectorAll('[data-snp-extra]');
      const show = rows[0].hidden;
      rows.forEach((r) => { r.hidden = !show; });
      more.textContent = show ? more.dataset.less : label;
    });
  }

  // Panel lateral de secciones: marca la sección que se está viendo.
  const links = Array.from(document.querySelectorAll('.st-side-list a'));
  if (links.length && 'IntersectionObserver' in window) {
    const idOf = (a) => a.getAttribute('href').slice(1);
    const visible = new Set();
    const paint = () => {
      const current = links.map(idOf).find((id) => visible.has(id));
      links.forEach((a) => {
        const on = idOf(a) === current;
        a.classList.toggle('is-active', on);
        if (on) a.setAttribute('aria-current', 'location'); else a.removeAttribute('aria-current');
      });
    };
    const observer = new IntersectionObserver((entries) => {
      entries.forEach((e) => { if (e.isIntersecting) visible.add(e.target.id); else visible.delete(e.target.id); });
      paint();
    }, { rootMargin: '-90px 0px -55% 0px' });
    links.forEach((a) => { const el = document.getElementById(idOf(a)); if (el) observer.observe(el); });
  }
})();
