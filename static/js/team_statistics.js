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

// Partidos ganados / empatados / perdidos
new Chart(document.getElementById('myPieChart'), {
  type: 'doughnut',
  data: {
    labels: [gettext('Ganados'), gettext('Empatados'), gettext('Perdidos')],
    datasets: [{
      data: [teamData.wonMatches, teamData.drawnMatches, teamData.lostMatches],
      backgroundColor: [Z.lime, Z.draw, Z.coral],
      borderColor: Z.card,
      borderWidth: 4,
    }],
  },
  options: { responsive: true, maintainAspectRatio: false, cutout: '68%', plugins: { legend: { position: 'bottom' } } },
});

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

// Partidos ganados, empatados y perdidos por temporada
const years = Object.keys(teamData.matchesWonPerYear);
new Chart(document.getElementById('myLineChart'), {
  type: 'line',
  data: {
    labels: years,
    datasets: [
      {
        label: gettext('Ganados'),
        data: years.map((y) => teamData.matchesWonPerYear[y].won),
        borderColor: Z.lime,
        backgroundColor: 'rgba(180, 241, 0, 0.18)',
        pointBackgroundColor: Z.lime,
        tension: 0.35,
        fill: true,
      },
      {
        label: gettext('Empatados'),
        data: years.map((y) => teamData.matchesWonPerYear[y].drawn || 0),
        borderColor: Z.draw,
        backgroundColor: 'rgba(138, 138, 138, 0.08)',
        pointBackgroundColor: Z.draw,
        tension: 0.35,
        fill: false,
      },
      {
        label: gettext('Perdidos'),
        data: years.map((y) => teamData.matchesWonPerYear[y].lost),
        borderColor: Z.coral,
        backgroundColor: 'rgba(255, 92, 99, 0.10)',
        pointBackgroundColor: Z.coral,
        tension: 0.35,
        fill: true,
      },
    ],
  },
  options: {
    responsive: true,
    maintainAspectRatio: false,
    plugins: { legend: { position: 'bottom' } },
    scales: scales({ y: { title: { display: true, text: gettext('Partidos') } } }),
  },
});

// Balance por jugador: partidos de 2 y 3 puntos, ganados y perdidos.
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

const balanceBox = document.getElementById('balanceChart');
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
