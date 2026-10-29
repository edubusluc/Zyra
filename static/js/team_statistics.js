// Paleta Zyra: lima para victorias, coral para derrotas, sobre fondo oscuro.
const Z = {
  lime: '#B4F100',
  limeDark: '#6E9400',
  coral: '#FF5C63',
  coralDark: '#9E3A3F',
  draw: '#8A8A8A',
  text: '#A3A3A3',
  grid: 'rgba(255, 255, 255, 0.08)',
  card: '#151515',
};

Chart.defaults.font.family = "'Archivo', system-ui, sans-serif";
Chart.defaults.color = Z.text;
Chart.defaults.borderColor = Z.grid;
Chart.defaults.plugins.legend.labels.usePointStyle = true;
Chart.defaults.plugins.legend.labels.boxWidth = 8;

const scales = (extra = {}) => ({
  x: { grid: { display: false }, ...extra.x },
  y: { beginAtZero: true, ticks: { precision: 0 }, grid: { color: Z.grid }, ...extra.y },
});

// Ranking SNP: media del equipo en cada actualización y botón para ver toda la plantilla.
// Va antes que el resto porque la tarjeta se muestra aunque no haya partidos cerrados.
(function () {
  const canvas = document.getElementById('chartSnpTeam');
  if (canvas) {
    const snp = JSON.parse(document.getElementById('snp-team-data').textContent);
    new Chart(canvas, {
      type: 'line',
      data: {
        labels: snp.labels,
        datasets: [{
          label: gettext('Media del equipo'),
          data: snp.average,
          borderColor: Z.lime,
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
        scales: scales({ y: { beginAtZero: false, ticks: { precision: 0 } } }),
      },
    });
  }
  const more = document.querySelector('[data-snp-more]');
  if (more) {
    const label = more.textContent;
    more.addEventListener('click', function () {
      const rows = document.querySelectorAll('[data-snp-extra]');
      const show = rows[0].hidden;
      rows.forEach((r) => { r.hidden = !show; });
      more.textContent = show ? more.dataset.less : label;
    });
  }
})();

// Juegos ganados / perdidos como local y como visitante
const gamesBar = (id, won, lost) => new Chart(document.getElementById(id), {
  type: 'bar',
  data: {
    labels: [gettext('Ganados'), gettext('Perdidos')],
    datasets: [{ data: [won, lost], backgroundColor: [Z.lime, Z.coral], borderRadius: 8, maxBarThickness: 64 }],
  },
  options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: scales() },
});
gamesBar('myBarChart', teamData.localGamesWon, teamData.localGamesLost);
gamesBar('myVisitingBarChart', teamData.visitingGamesWon, teamData.visitingGamesLost);

// Partidos ganados, empatados y perdidos por temporada. Barras agrupadas por temporada, con la
// etiqueta horizontal debajo de cada grupo (en pantallas estrechas «24-25», sin rotar ni recortar)
// y el número encima de cada barra para ver de un vistazo qué color es cada resultado.
const years = Object.keys(teamData.matchesWonPerYear);
const lineBox = document.getElementById('myLineChart').parentElement;
const narrowSeasons = () => lineBox.clientWidth < 520;
const seasonLabel = (y) => {
  const text = narrowSeasons() ? y.replace(/^\d{2}(\d{2})-\d{2}(\d{2})$/, '$1-$2') : y;
  return y === teamData.currentSeason ? [text, gettext('en curso')] : text;
};
const barValues = {
  id: 'barValues',
  afterDatasetsDraw(chart) {
    const { ctx } = chart;
    ctx.save();
    ctx.font = `600 ${narrowSeasons() ? 11 : 12}px ${Chart.defaults.font.family}`;
    ctx.fillStyle = '#FFFFFF';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'bottom';
    chart.data.datasets.forEach((ds, i) => {
      chart.getDatasetMeta(i).data.forEach((bar, j) => {
        if (ds.data[j] > 0) ctx.fillText(ds.data[j], bar.x, bar.y - 3);
      });
    });
    ctx.restore();
  },
};
// Barras de una misma temporada pegadas: en vez de maxBarThickness (que encoge cada barra dentro de su
// hueco y las separa) se limita el ancho del grupo entero a unos 36 px por barra.
const groupWidth = (bars) => Math.min(0.62, (36 * bars) / Math.max(1, (lineBox.clientWidth - 60) / years.length));
// Una banda tenue detrás de cada temporada: así se ve qué barras van juntas aunque en el móvil el hueco entre grupos sea pequeño.
const seasonBands = {
  id: 'seasonBands',
  beforeDatasetsDraw(chart) {
    const { ctx, chartArea, scales: { x } } = chart;
    const slot = chartArea.width / years.length;
    ctx.save();
    ctx.fillStyle = 'rgba(255, 255, 255, 0.045)';
    years.forEach((_, i) => {
      const left = x.getPixelForValue(i) - slot / 2 + 3;
      ctx.beginPath();
      ctx.roundRect(left, chartArea.top, slot - 6, chartArea.height, 6);
      ctx.fill();
    });
    ctx.restore();
  },
};
const seasonChart = new Chart(document.getElementById('myLineChart'), {
  type: 'bar',
  plugins: [seasonBands, barValues],
  data: {
    labels: years.map(seasonLabel),
    datasets: [
      { label: gettext('Ganados'), data: years.map((y) => teamData.matchesWonPerYear[y].won), backgroundColor: Z.lime, borderRadius: 4 },
      { label: gettext('Empatados'), data: years.map((y) => teamData.matchesWonPerYear[y].drawn || 0), backgroundColor: Z.draw, borderRadius: 4 },
      { label: gettext('Perdidos'), data: years.map((y) => teamData.matchesWonPerYear[y].lost), backgroundColor: Z.coral, borderRadius: 4 },
    ].filter((ds) => ds.label !== gettext('Empatados') || ds.data.some((n) => n > 0)),  // sin empates no se reserva hueco ni leyenda
  },
  options: {
    responsive: true,
    maintainAspectRatio: false,
    layout: { padding: { top: 16 } },
    datasets: { bar: { barPercentage: 1, categoryPercentage: groupWidth(2) } },
    plugins: { legend: { position: 'top', labels: { boxWidth: 8, boxHeight: 8, padding: 12, font: { size: 12 } } } },
    scales: scales({
      x: { ticks: { autoSkip: false, maxRotation: 0, minRotation: 0, font: { size: 12 } } },
      y: { grace: '12%', title: { display: false } },
    }),
  },
});
seasonChart.options.datasets.bar.categoryPercentage = groupWidth(seasonChart.data.datasets.length);
seasonChart.update('none');
window.addEventListener('resize', () => {
  seasonChart.options.datasets.bar.categoryPercentage = groupWidth(seasonChart.data.datasets.length);
  seasonChart.data.labels = years.map(seasonLabel);
  seasonChart.update('none');
});

// Asistencia a las convocatorias: % de la plantilla que se apunta. Con «Todas» es la media por temporada;
// con una temporada, una barra por convocatoria (la etiqueta lleva fecha y rival).
(function () {
  const canvas = document.getElementById('attendanceChart');
  if (!canvas) return;
  const att = JSON.parse(document.getElementById('attendance-data').textContent);
  const rows = att.rows;
  new Chart(canvas, {
    type: 'bar',
    data: {
      labels: rows.map((r) => r.label),
      datasets: [{ data: rows.map((r) => r.pct), backgroundColor: Z.lime, borderRadius: 6, maxBarThickness: 48 }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: (c) => `${rows[c.dataIndex].pct} % · ${rows[c.dataIndex].signed}/${rows[c.dataIndex].eligible}`,
            afterLabel: (c) => (rows[c.dataIndex].calls
              ? interpolate(ngettext('%s convocatoria', '%s convocatorias', rows[c.dataIndex].calls), [rows[c.dataIndex].calls])
              : ''),
          },
        },
      },
      scales: scales({
        x: { ticks: { autoSkip: false, maxRotation: 45, font: { size: 11 } } },
        y: { max: 100, ticks: { stepSize: 25, callback: (v) => `${v} %` } },
      }),
    },
  });
})();

// Balance por jugador: partidos de 2 y 3 puntos, ganados y perdidos.
(function () {
  const balanceBox = document.getElementById('balanceChart');
  if (!balanceBox) return; // no sale en competiciones con parejas sorteadas (LAPI)
  // Barras horizontales de tamaño fijo: se ven PAGE_SIZE jugadores y el resto se
  // recorre con el paginador, así el gráfico mide lo mismo con 8 jugadores que con 60.
  const PAGE_SIZE = 10;
  const ROW_HEIGHT = 30;
  const SERIES = [
    { label: gettext('3 puntos ganados'), index: 2, color: Z.lime },
    { label: gettext('2 puntos ganados'), index: 0, color: Z.limeDark },
    { label: gettext('3 puntos perdidos'), index: 3, color: Z.coral },
    { label: gettext('2 puntos perdidos'), index: 1, color: Z.coralDark },
  ];
  const players = teamData.column_chart_data.map((r) => ({
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
          grid: { color: Z.grid },
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

// Panel lateral de secciones: marca la sección que se está viendo.
(function () {
  const links = Array.from(document.querySelectorAll('.st-side-list a'));
  if (!links.length || !('IntersectionObserver' in window)) return;
  const byId = new Map(links.map((a) => [a.getAttribute('href').slice(1), a]));
  const visible = new Set();
  const paint = () => {
    const current = links.map((a) => a.getAttribute('href').slice(1)).find((id) => visible.has(id));
    links.forEach((a) => {
      const on = a.getAttribute('href').slice(1) === current;
      a.classList.toggle('is-active', on);
      if (on) a.setAttribute('aria-current', 'location'); else a.removeAttribute('aria-current');
    });
  };
  const observer = new IntersectionObserver((entries) => {
    entries.forEach((e) => { if (e.isIntersecting) visible.add(e.target.id); else visible.delete(e.target.id); });
    paint();
  }, { rootMargin: '-90px 0px -55% 0px' });
  byId.forEach((_, id) => { const el = document.getElementById(id); if (el) observer.observe(el); });
})();
