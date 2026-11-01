(function () {
  const seasons = JSON.parse(document.getElementById('data-seasons').textContent);
  const C = { win: '#B4F100', loss: '#FF5C63', muted: '#A3A3A3', line: 'rgba(255, 255, 255, 0.08)' };

  Chart.defaults.font.family = "'Archivo', system-ui, sans-serif";
  Chart.defaults.color = C.muted;
  Chart.defaults.borderColor = C.line;

  const base = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: { legend: { position: 'bottom', labels: { usePointStyle: true, boxWidth: 8 } } },
  };

  // Partidos jugados por temporada (ganados + perdidos apilados)
  new Chart(document.getElementById('chartPlayed'), {
    type: 'bar',
    data: {
      labels: seasons.labels,
      datasets: [
        { label: gettext('Ganados'), data: seasons.wins, backgroundColor: C.win, borderRadius: 10 },
        { label: gettext('Perdidos'), data: seasons.losses, backgroundColor: C.loss, borderRadius: 10 },
      ],
    },
    options: {
      ...base,
      scales: {
        x: { stacked: true, grid: { display: false } },
        y: { stacked: true, beginAtZero: true, ticks: { precision: 0 }, grid: { color: C.line } },
      },
    },
  });

  // Evolución del % de victorias de la pareja
  new Chart(document.getElementById('chartPct'), {
    type: 'line',
    data: {
      labels: seasons.labels,
      datasets: [{
        label: gettext('% victorias'),
        data: seasons.pct,
        borderColor: C.win,
        backgroundColor: 'rgba(180, 241, 0, 0.15)',
        pointBackgroundColor: C.win,
        pointBorderColor: '#0B0B0B',
        pointRadius: 5,
        tension: 0.3,
        fill: true,
      }],
    },
    options: {
      ...base,
      plugins: { ...base.plugins, legend: { display: false },
        tooltip: { callbacks: { label: (c) => ` ${c.parsed.y}%` } } },
      scales: {
        x: { grid: { display: false } },
        y: { min: 0, max: 100, ticks: { callback: (v) => v + '%' }, grid: { color: C.line } },
      },
    },
  });
})();
